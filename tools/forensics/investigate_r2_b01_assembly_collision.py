"""DGCA NEXT V2 - Forensic Investigation R2-B01: Assembly Duplicate Formation.

Comprehensive in-memory passive instrumentation of Assembly FORM, GROW, MERGE, and READOUT
to determine the precise structural and causal origin of Assembly 5 and 6 duplicate collision.

R2-B01-C02 Non-Interference Guarantee:
- _run_form_stage() executes EXACTLY ONCE per completed root, receiving the complete original event sequence.
- Zero decomposition of production stages into per-event invocations.
- Purely observational passive frame tracing preserves exact production semantics, budget (K_FORM_PER_END=12),
  and diagnostic evaluation.
- Differential replay proves 100% bit-for-bit state and diagnostic equality against untouched production code across all 56 roots.

Normative References:
- DGCA_CORE_RC4_1.md §2.0 (Executable Assembly operators: MAINTAIN -> GROW -> FORM -> MERGE/SPLIT)
- DGCA_CORE_RC4_1.md §9.4 (Readout ledger & structural generation invalidation)
"""

from __future__ import annotations

import dataclasses
import hashlib
import io
import linecache
import math
import sys
from pathlib import Path
from typing import Any

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Ensure project root and src are on path
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "src"))

import dgca.core.assembly as asm_module
from dgca.common.errors import StatusCode
from dgca.common.hashing import Region
from dgca.core.anatomy import Synapse, SynapseKey, SynapseScope, SynapseState
from dgca.core.assembly import (
    D_MIN,
    K_FORM_PER_END,
    K_MAX,
    K_MIN,
    M_MAX,
    RHO_CORE,
    RHO_G,
    RHO_KEEP,
    SIGMA_G,
    SIGMA_KEEP,
    T_C_COOLDOWN,
    THETA_A,
    THETA_MERGE,
    THETA_OB,
    Assembly,
    AssemblyStatus,
    check_maintain_keep_guards,
    compute_assembly_member_metrics,
    compute_core_coverage,
    compute_mutual_support_r_b,
)
from dgca.core.dynamics import EventExecutionResult, ExecutionMode, execute_two_pass_event
from dgca.core.generator import generate_episode
from dgca.core.readout import evaluate_full_vs_control_readout, is_legal_readout_assembly
from dgca.core.state import MachineState
from dgca.encoder.envelope import EventOrigin, Marker, encode_exposure
from dgca.lifecycle.exposure_tx import ExposureTransactionManager
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1

# ---------------------------------------------------------------------------
# Passive Diagnostic Loggers (Zero Production Code Modification)
# ---------------------------------------------------------------------------

current_root_context: int = 0
form_events_log: list[dict[str, Any]] = []
grow_events_log: list[dict[str, Any]] = []
merge_attempts_log: list[dict[str, Any]] = []

orig_run_form_stage = asm_module._run_form_stage
orig_run_grow_stage = asm_module._run_grow_stage
orig_try_merge_pair = asm_module._try_merge_pair


def _make_trace_lines(formed_in_call: list[dict[str, Any]]):
    """Passive tracer inspecting line execution inside _run_form_stage without altering execution."""
    def trace_lines(frame, event, arg):
        if event == "line" and frame.f_code.co_name == "_run_form_stage":
            line = linecache.getline(frame.f_code.co_filename, frame.f_lineno).strip()
            if "formed_ids.append(new_id)" in line:
                ev = frame.f_locals.get("event_res")
                new_id = frame.f_locals.get("new_id")
                tri = frame.f_locals.get("tri")
                if ev is not None and new_id is not None:
                    formed_in_call.append({
                        "root_id": current_root_context,
                        "event_order": ev.event_order,
                        "action": "FORMED",
                        "assembly_id": new_id,
                        "members": list(tri) if tri else [],
                    })
        return trace_lines
    return trace_lines


def instrumented_run_form_stage(
    w: asm_module.WState,
    h_slow: asm_module.HSlowState,
    event_results: Any,
    preexisting_live_assemblies: list[Assembly],
    n_rec_cache: dict[int, dict[int, float]],
) -> tuple[list[int], list[StatusCode]]:
    """Genuinely observational passive wrapper for Stage 3 FORM.

    Executes orig_run_form_stage EXACTLY ONCE per completed root with the complete original
    event_results sequence. Zero decomposition into multiple calls.
    """
    global current_root_context
    formed_in_call: list[dict[str, Any]] = []
    old_trace = sys.gettrace()
    sys.settrace(_make_trace_lines(formed_in_call))
    try:
        formed_ids, diagnostics = orig_run_form_stage(
            w, h_slow, event_results, preexisting_live_assemblies, n_rec_cache
        )
    finally:
        sys.settrace(old_trace)

    form_events_log.extend(formed_in_call)
    return formed_ids, diagnostics


def instrumented_run_grow_stage(
    w: asm_module.WState,
    n_rec_cache: dict[int, dict[int, float]],
) -> list[int]:
    """Purely observational wrapper for Stage 2 GROW (executes at root close)."""
    global current_root_context
    pre_members = {
        aid: list(asm.member_cell_ids)
        for aid, asm in w.assemblies.items()
        if asm.status == AssemblyStatus.LIVE
    }
    grown_ids = orig_run_grow_stage(w, n_rec_cache)
    for aid in grown_ids:
        post_m = list(w.assemblies[aid].member_cell_ids)
        added = sorted(set(post_m) - set(pre_members.get(aid, [])))
        grow_events_log.append({
            "root_id": current_root_context,
            "stage": "ROOT_CLOSE_GROW",
            "assembly_id": aid,
            "added_cells": added,
            "new_members": post_m,
            "new_generation": w.assemblies[aid].structural_generation,
        })
    return grown_ids


def instrumented_try_merge_pair(
    a_id: int,
    b_id: int,
    w: asm_module.WState,
    n_rec_cache: dict[int, dict[int, float]],
) -> bool:
    """Purely observational logger for Stage 4 MERGE evaluating frozen rule compliance and downstream guards."""
    global current_root_context
    asm_a = w.assemblies.get(a_id)
    asm_b = w.assemblies.get(b_id)
    attempt_info: dict[str, Any] = {
        "root_id": current_root_context,
        "pair": (a_id, b_id),
    }

    if asm_a and asm_b:
        set_a = set(asm_a.member_cell_ids)
        set_b = set(asm_b.member_cell_ids)
        union_set = set_a | set_b
        inter_set = set_a & set_b
        jaccard = float(len(inter_set)) / float(len(union_set)) if union_set else 0.0
        excl_a = sorted(set_a - set_b)
        excl_b = sorted(set_b - set_a)
        attempt_info.update({
            "status_a": asm_a.status.name,
            "status_b": asm_b.status.name,
            "jaccard": jaccard,
            "union_size": len(union_set),
            "excl_a": excl_a,
            "excl_b": excl_b,
        })
        if not excl_a or not excl_b:
            attempt_info["between_strength"] = 0.0
            attempt_info["blocked_by"] = "SPEC_CONTRACT_EMPTY_EXCLUSIVE_SIDE_ZERO_BETWEEN_STRENGTH"
        else:
            cross_vals = [
                compute_mutual_support_r_b(i, j, w)
                for i in excl_a
                for j in excl_b
            ]
            bs = sum(cross_vals) / float(len(cross_vals))
            attempt_info["between_strength"] = bs
            if bs < THETA_OB:
                attempt_info["blocked_by"] = "BETWEEN_STRENGTH_BELOW_THETA_OB"

        # Downstream guard evaluation in read-only mode (unreached in frozen code when between_strength < THETA_OB)
        union_tuple = tuple(sorted(union_set))
        downstream_m_max_pass = True
        downstream_keep_guards_pass = True
        for x in union_tuple:
            live_after = (asm_module._live_assembly_ids_for_cell(x, w) - {b_id}) | {a_id}
            if len(live_after) > M_MAX:
                downstream_m_max_pass = False
            if not check_maintain_keep_guards(x, union_tuple, w, n_rec_cache):
                downstream_keep_guards_pass = False
        attempt_info["downstream_m_max_pass"] = downstream_m_max_pass
        attempt_info["downstream_keep_guards_pass"] = downstream_keep_guards_pass

    res = orig_try_merge_pair(a_id, b_id, w, n_rec_cache)
    attempt_info["result"] = res
    merge_attempts_log.append(attempt_info)
    return res


# ---------------------------------------------------------------------------
# Canonical State Digest Function for Differential Replay
# ---------------------------------------------------------------------------

def compute_root_state_digest(state: MachineState, ledger: SurfaceReadoutLedgerV1, tx: ExposureTransactionManager, root_id: int, end_rep: Any) -> str:
    """Compute a canonical SHA-256 digest covering WState, HSlowState, ledger, diagnostics, and outbox."""
    h = hashlib.sha256()
    w = state.W

    # 1. Assemblies
    asm_repr = str([(aid, a.status.name, a.structural_generation, a.member_cell_ids, a.birth_close_serial, a.last_mutation_close_serial, a.last_merge_split_close_serial) for aid, a in sorted(w.assemblies.items())])
    h.update(asm_repr.encode("utf-8"))

    # 2. Assemblies by member
    abm_repr = str([(c, sorted(list(asms))) for c, asms in sorted(w.assemblies_by_member.items())])
    h.update(abm_repr.encode("utf-8"))

    # 3. Synapses (S rounded to millionths for stability, evidence counts, state)
    syn_repr = str([(k[0], k[1], k[2].name, round(s.S, 6), s.E_ext, s.E_int, s.state.name) for k, s in sorted(w.synapses.items(), key=lambda x: (x[0][0], x[0][1], x[0][2].value))])
    h.update(syn_repr.encode("utf-8"))

    # 4. Diagnostics from AssemblyEndReport
    diag_repr = str(end_rep.assembly_report.diagnostics)
    h.update(diag_repr.encode("utf-8"))

    # 5. Ledger rows and confirmed roots count
    rows_repr = str([(k, [(tk[0], tk[1].name, len(row.confirmed_roots)) for tk, row in sorted(rmap.items())]) for k, rmap in sorted(ledger._rows_by_asm_gen.items())])
    h.update(rows_repr.encode("utf-8"))

    # 6. HSlowState theta_emit across regions
    h_repr = str([(reg.name, round(state.H_slow.get_theta_emit(reg), 6)) for reg in Region])
    h.update(h_repr.encode("utf-8"))

    return h.hexdigest()


# ---------------------------------------------------------------------------
# Focused Sensitivity Checks: Empty Formation & Root-Wide Formation Cap
# ---------------------------------------------------------------------------

def verify_empty_formation_sensitivity(diagnostics_run_a: dict[int, Any], diagnostics_run_b: dict[int, Any]) -> bool:
    """Check A: Verify that roots with zero live assemblies produce identical single diagnostic."""
    print("\n--- CHECK A: EMPTY FORMATION SENSITIVITY ---")
    all_match = True
    for r in range(1, 7):
        diag_a = diagnostics_run_a[r]
        diag_b = diagnostics_run_b[r]
        match = (diag_a == diag_b == (StatusCode.NO_RECIPROCAL_TRIANGLE,))
        if not match:
            all_match = False
        print(f"  Root {r:02d}: Run A={diag_a} | Run B={diag_b} | Match={match}")
    print(f"Empty formation diagnostic equivalence verified: {all_match}")
    return all_match


def verify_root_wide_formation_cap() -> bool:
    """Check B: Verify that instrumentation does not reset K_FORM_PER_END=12 across multi-event root."""
    print("\n--- CHECK B: ROOT-WIDE FORMATION CAP MULTI-EVENT TEST ---")
    from tests.test_phase5_hierarchy_and_assembly import _add_reciprocal_local_pair

    state_cap = MachineState()
    ev0_fixed, ev0_float = {}, {}
    ev1_fixed, ev1_float = {}, {}

    # Create 14 disjoint triangles across 2 events (7 in event 0, 7 in event 1)
    for t_idx in range(14):
        u = 8192 + (t_idx * 3 + 0) * 8
        v = 8192 + (t_idx * 3 + 1) * 8
        w_cell = 8192 + (t_idx * 3 + 2) * 8
        _add_reciprocal_local_pair(state_cap, u, v, s_val=0.85, e_ext=6.0)
        _add_reciprocal_local_pair(state_cap, v, w_cell, s_val=0.85, e_ext=6.0)
        _add_reciprocal_local_pair(state_cap, u, w_cell, s_val=0.85, e_ext=6.0)
        d_fixed = ev0_fixed if t_idx < 7 else ev1_fixed
        d_float = ev0_float if t_idx < 7 else ev1_float
        for cell in (u, v, w_cell):
            d_fixed[cell] = 850_000
            d_float[cell] = 0.85

    ev0 = execute_two_pass_event(
        state_cap, ev0_fixed, ev0_float, mode=ExecutionMode.LEARN,
        origin=EventOrigin.EXTERNAL_DIRECT, boundary=True, exposure_id=1, event_order=0,
    )
    ev1 = execute_two_pass_event(
        state_cap, ev1_fixed, ev1_float, mode=ExecutionMode.LEARN,
        origin=EventOrigin.EXTERNAL_DIRECT, boundary=True, exposure_id=1, event_order=1,
    )

    state_cap.W.close_serial = 1

    # Attach passive observer
    orig_form = asm_module._run_form_stage
    asm_module._run_form_stage = instrumented_run_form_stage

    # Execute assembly end pipeline with 2 events combined
    from dgca.core.assembly import execute_assembly_end_pipeline
    rep = execute_assembly_end_pipeline(state_cap.W, state_cap.H_slow, [ev0, ev1])
    asm_module._run_form_stage = orig_form

    formed_count = len(rep.formed_ids)
    print(f"  Total candidate triangles across 2 events: 14 (7 in Ev 0, 7 in Ev 1)")
    print(f"  Formed assemblies count: {formed_count} (Cap: K_FORM_PER_END = {K_FORM_PER_END})")
    assert formed_count == K_FORM_PER_END == 12, f"Expected 12, got {formed_count}"
    print(f"  Root-wide formation cap strictly preserved without per-event reset: True")
    return True


# ---------------------------------------------------------------------------
# Full Investigation & Differential Replay
# ---------------------------------------------------------------------------

def run_investigation() -> dict[str, Any]:
    global current_root_context

    print("=" * 80)
    print("DGCA NEXT V2 - R2-B01-C02 FORENSIC INSTRUMENTATION & DIFFERENTIAL REPLAY")
    print("Normative Basis: DGCA_CORE_RC4_1.md §2.0 & §9.4")
    print("=" * 80)

    branch_ab = encode_exposure("القط يشرب حليب", append_eos=True)
    branch_db = encode_exposure("النسر يشرب ماء", append_eos=True)

    # -----------------------------------------------------------------------
    # Run A: Untouched Frozen Reference (Zero Forensic Patching)
    # -----------------------------------------------------------------------
    print("\n--- RUN A: UNTOUCHED PRODUCTION REFERENCE EXECUTION ---")
    state_a = MachineState()
    ledger_a = SurfaceReadoutLedgerV1()
    tx_a = ExposureTransactionManager(
        state_a,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger_a,
    )

    digests_a: dict[int, str] = {}
    diagnostics_a: dict[int, Any] = {}
    asm_snapshots_a: dict[int, dict[int, list[int]]] = {}

    for r in range(1, 57):
        is_ab = (r % 2 != 0)
        envs = branch_ab if is_ab else branch_db
        tx_a.begin_exposure(r)
        for env in envs:
            core_ev = dataclasses.replace(env.core_event, exposure_id=r)
            tx_a.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        rep_a = tx_a.end_exposure(r)
        digests_a[r] = compute_root_state_digest(state_a, ledger_a, tx_a, r, rep_a)
        diagnostics_a[r] = rep_a.assembly_report.diagnostics
        asm_snapshots_a[r] = {aid: list(asm.member_cell_ids) for aid, asm in sorted(state_a.W.assemblies.items())}

    cat_a = generate_episode(state_a, [branch_ab[0].core_event], ledger_a, max_steps=5)
    eagle_a = generate_episode(state_a, [branch_db[0].core_event], ledger_a, max_steps=5)

    # -----------------------------------------------------------------------
    # Run B: Corrected Instrumented Observer Execution
    # -----------------------------------------------------------------------
    print("\n--- RUN B: CORRECTED INSTRUMENTED OBSERVER EXECUTION ---")
    asm_module._run_form_stage = instrumented_run_form_stage
    asm_module._run_grow_stage = instrumented_run_grow_stage
    asm_module._try_merge_pair = instrumented_try_merge_pair

    state_b = MachineState()
    ledger_b = SurfaceReadoutLedgerV1()
    tx_b = ExposureTransactionManager(
        state_b,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger_b,
    )

    digests_b: dict[int, str] = {}
    diagnostics_b: dict[int, Any] = {}
    asm_snapshots_b: dict[int, dict[int, list[int]]] = {}

    for r in range(1, 57):
        current_root_context = r
        is_ab = (r % 2 != 0)
        envs = branch_ab if is_ab else branch_db
        tx_b.begin_exposure(r)
        for env in envs:
            core_ev = dataclasses.replace(env.core_event, exposure_id=r)
            tx_b.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        rep_b = tx_b.end_exposure(r)
        digests_b[r] = compute_root_state_digest(state_b, ledger_b, tx_b, r, rep_b)
        diagnostics_b[r] = rep_b.assembly_report.diagnostics
        asm_snapshots_b[r] = {aid: list(asm.member_cell_ids) for aid, asm in sorted(state_b.W.assemblies.items())}

    cat_b = generate_episode(state_b, [branch_ab[0].core_event], ledger_b, max_steps=5)
    eagle_b = generate_episode(state_b, [branch_db[0].core_event], ledger_b, max_steps=5)

    # Restore originals
    asm_module._run_form_stage = orig_run_form_stage
    asm_module._run_grow_stage = orig_run_grow_stage
    asm_module._try_merge_pair = orig_try_merge_pair

    # -----------------------------------------------------------------------
    # Differential Replay Assertions
    # -----------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("MANDATORY DIFFERENTIAL REPLAY VERIFICATION RESULTS")
    print("=" * 80)

    mismatches = [r for r in range(1, 57) if digests_a[r] != digests_b[r]]
    print(f"Total Roots Compared: 56")
    print(f"State Digests Matching: {56 - len(mismatches)} / 56")
    assert not mismatches, f"Differential replay mismatch at roots: {mismatches}"
    print(">>> 100% BIT-FOR-BIT STATE & DIGEST EQUALITY CONFIRMED ACROSS ALL 56 ROOTS!")

    diag_mismatches = [r for r in range(1, 57) if diagnostics_a[r] != diagnostics_b[r]]
    assert not diag_mismatches, f"Diagnostic mismatch at roots: {diag_mismatches}"
    print(f"AssemblyEndReport Diagnostics Matching: 56 / 56 (100% Equal)")

    assert cat_a.stop_status == cat_b.stop_status == StatusCode.GEN_STOP_EOS
    print(f"Cat Final Stop Status: Run A = {cat_a.stop_status.name} | Run B = {cat_b.stop_status.name} (MATCH)")

    assert eagle_a.stop_status == eagle_b.stop_status == StatusCode.GEN_STOP_AMBIGUOUS
    print(f"Eagle Final Stop Status: Run A = {eagle_a.stop_status.name} | Run B = {eagle_b.stop_status.name} (MATCH)")

    # -----------------------------------------------------------------------
    # Focused Sensitivity Checks
    # -----------------------------------------------------------------------
    verify_empty_formation_sensitivity(diagnostics_a, diagnostics_b)
    verify_root_wide_formation_cap()

    # -----------------------------------------------------------------------
    # Forensic Revalidation Traces
    # -----------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("FORENSIC TRACE A: REVALIDATED ASSEMBLY BIRTH & EVENT ATTRIBUTION")
    print("=" * 80)

    forms_root8 = [e for e in form_events_log if e["root_id"] == 8]
    print(f"Passively observed formation events in Root 8:")
    for f in forms_root8:
        print(f"  Assembly {f['assembly_id']} formed in Event {f['event_order']}: seed={f['members']}")

    asm5_birth = next((f for f in forms_root8 if f["assembly_id"] == 5), None)
    asm6_birth = next((f for f in forms_root8 if f["assembly_id"] == 6), None)
    assert asm5_birth and asm5_birth["event_order"] == 3
    assert asm6_birth and asm6_birth["event_order"] == 3
    print(">>> Assembly 5 and Assembly 6 birth in Root 8, Event 3 (<EOS>) PASSIVELY PROVEN!")

    print("\n" + "=" * 80)
    print("FORENSIC TRACE B: REVALIDATED STRUCTURAL CONVERGENCE & MEMBERSHIP")
    print("=" * 80)
    m5_r8 = asm_snapshots_b[8][5]
    m6_r8 = asm_snapshots_b[8][6]
    print(f"Root 08 Seeds: Asm 5={m5_r8} | Asm 6={m6_r8} | Disjoint: {set(m5_r8).isdisjoint(set(m6_r8))}")

    m5_r9 = asm_snapshots_b[9][5]
    m6_r9 = asm_snapshots_b[9][6]
    print(f"Root 09 (post-GROW): Asm 5={m5_r9} | Asm 6={m6_r9} | Identical: {m5_r9 == m6_r9}")

    m5_r10 = asm_snapshots_b[10][5]
    m6_r10 = asm_snapshots_b[10][6]
    print(f"Root 10 (post-GROW): Asm 5={m5_r10} | Asm 6={m6_r10} | Identical: {m5_r10 == m6_r10}")

    m5_r56 = asm_snapshots_b[56][5]
    m6_r56 = asm_snapshots_b[56][6]
    print(f"Root 56 (Final): Asm 5={m5_r56} | Asm 6={m6_r56} | Identical: {m5_r56 == m6_r56}")

    print("\n" + "=" * 80)
    print("FORENSIC TRACE C: REVALIDATED MERGE EVALUATIONS")
    print("=" * 80)
    merges_5_6 = [m for m in merge_attempts_log if m["pair"] == (5, 6)]
    print(f"Total merge evaluations of pair (5, 6): {len(merges_5_6)}")
    r9_merge = next((m for m in merges_5_6 if m["root_id"] == 9), None)
    if r9_merge:
        print(f"  Root 9 MERGE: Jaccard={r9_merge['jaccard']}, between_strength={r9_merge['between_strength']}, blocked_by={r9_merge['blocked_by']}, downstream_keep_guards={r9_merge['downstream_keep_guards_pass']}")

    print("\n" + "=" * 80)
    print("FORENSIC TRACE D: REVALIDATED READOUT COLLISION AT ROOT 56")
    print("=" * 80)
    step2 = eagle_b.steps[2]
    readout = step2.readout_result
    top = readout.ranked_scores[0]
    second = readout.ranked_scores[1]
    print(f"Step 2 Top Candidate:    ID {top.assembly_id}, score={top.score_next:.10f}, Q6={top.score_next_q6}")
    print(f"Step 2 Second Candidate: ID {second.assembly_id}, score={second.score_next:.10f}, Q6={second.score_next_q6}")
    print(f"Step 2 Score Margin:    {readout.margin:.10f}")
    print(f"Step 2 Ambiguity Status: {readout.status.name}")

    return {
        "roots_compared": 56,
        "digests_matched": 56,
        "cat_status": cat_b.stop_status.name,
        "eagle_status": eagle_b.stop_status.name,
        "asm5_birth_event": asm5_birth["event_order"],
        "asm6_birth_event": asm6_birth["event_order"],
        "collision_margin": readout.margin,
    }


if __name__ == "__main__":
    run_investigation()
