"""DGCA NEXT V2 - Forensic Investigation R2-B01: Assembly Duplicate Formation.

Comprehensive in-memory instrumentation of Assembly FORM, GROW, MERGE, and READOUT
to determine the precise structural and causal origin of Assembly 5 and 6 duplicate collision.
"""

from __future__ import annotations

import dataclasses
import io
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
from dgca.core.assembly import (
    K_MAX,
    M_MAX,
    RHO_CORE,
    SIGMA_G,
    THETA_MERGE,
    THETA_OB,
    Assembly,
    AssemblyStatus,
    compute_core_coverage,
    compute_mutual_support_r_b,
)
from dgca.core.generator import generate_episode
from dgca.core.readout import evaluate_full_vs_control_readout, is_legal_readout_assembly
from dgca.core.state import MachineState
from dgca.encoder.envelope import Marker, encode_exposure
from dgca.lifecycle.exposure_tx import ExposureTransactionManager
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1

# ---------------------------------------------------------------------------
# In-Memory Diagnostic Loggers (Zero Production Code Modification)
# ---------------------------------------------------------------------------

current_root_context: int = 0
form_events_log: list[dict[str, Any]] = []
grow_events_log: list[dict[str, Any]] = []
merge_attempts_log: list[dict[str, Any]] = []

orig_run_form_stage = asm_module._run_form_stage
orig_run_grow_stage = asm_module._run_grow_stage
orig_try_merge_pair = asm_module._try_merge_pair


def instrumented_run_form_stage(
    w: asm_module.WState,
    h_slow: asm_module.HSlowState,
    event_results: Any,
    preexisting_live_assemblies: list[Assembly],
    n_rec_cache: dict[int, dict[int, float]],
) -> tuple[list[int], list[StatusCode]]:
    global current_root_context
    for ev in sorted(event_results, key=lambda e: e.event_order):
        covered = set()
        for a in w.assemblies.values():
            if a.status == AssemblyStatus.LIVE and compute_core_coverage(a, ev, h_slow) >= RHO_CORE:
                covered.update(a.member_cell_ids)
        for a in preexisting_live_assemblies:
            if compute_core_coverage(a, ev, h_slow) >= RHO_CORE:
                covered.update(a.member_cell_ids)

        u_t = sorted(
            cid
            for cid in ev.committed_before_event
            if cid not in covered
            and len(asm_module._live_assembly_ids_for_cell(cid, w)) < M_MAX
            and asm_module._is_externally_grounded_fresh_emitter(cid, ev, h_slow, w)
        )
        form_events_log.append({
            "root_id": current_root_context,
            "event_order": ev.event_order,
            "covered_cells_count": len(covered),
            "u_t_count": len(u_t),
            "u_t": u_t,
        })

    formed_ids, diags = orig_run_form_stage(
        w, h_slow, event_results, preexisting_live_assemblies, n_rec_cache
    )
    for aid in formed_ids:
        asm = w.assemblies[aid]
        form_events_log.append({
            "root_id": current_root_context,
            "action": "FORMED",
            "assembly_id": aid,
            "members": list(asm.member_cell_ids),
        })
    return formed_ids, diags


def instrumented_run_grow_stage(
    w: asm_module.WState,
    n_rec_cache: dict[int, dict[int, float]],
) -> list[int]:
    global current_root_context
    # Snapshot before grow
    pre_members = {aid: list(asm.member_cell_ids) for aid, asm in w.assemblies.items() if asm.status == AssemblyStatus.LIVE}
    grown_ids = orig_run_grow_stage(w, n_rec_cache)
    for aid in grown_ids:
        post_m = list(w.assemblies[aid].member_cell_ids)
        added = sorted(set(post_m) - set(pre_members.get(aid, [])))
        grow_events_log.append({
            "root_id": current_root_context,
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
            "excl_a": excl_a,
            "excl_b": excl_b,
        })
        if not excl_a or not excl_b:
            attempt_info["between_strength"] = 0.0
            attempt_info["blocked_by"] = "EMPTY_EXCLUSIVE_SET_ZERO_BETWEEN_STRENGTH"
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

    res = orig_try_merge_pair(a_id, b_id, w, n_rec_cache)
    attempt_info["result"] = res
    merge_attempts_log.append(attempt_info)
    return res


# Patch assembly module dynamically
asm_module._run_form_stage = instrumented_run_form_stage
asm_module._run_grow_stage = instrumented_run_grow_stage
asm_module._try_merge_pair = instrumented_try_merge_pair


def run_investigation() -> dict[str, Any]:
    global current_root_context

    print("=" * 80)
    print("DGCA NEXT V2 - R2-B01 ASSEMBLY FORENSIC INVESTIGATION")
    print("=" * 80)

    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
    )

    branch_ab = encode_exposure("القط يشرب حليب", append_eos=True)
    branch_db = encode_exposure("النسر يشرب ماء", append_eos=True)

    asm_snapshots_by_root: dict[int, dict[int, list[int]]] = {}

    print("\n--- RUNNING 56-ROOT CURRICULUM ---")
    for root_id in range(1, 57):
        current_root_context = root_id
        is_ab = (root_id % 2 != 0)
        envs = branch_ab if is_ab else branch_db

        tx.begin_exposure(root_id)
        for env in envs:
            core_ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        tx.end_exposure(root_id)

        asm_snapshots_by_root[root_id] = {
            aid: list(asm.member_cell_ids)
            for aid, asm in sorted(state.W.assemblies.items())
        }

    # Restore original assembly methods
    asm_module._run_form_stage = orig_run_form_stage
    asm_module._run_grow_stage = orig_run_grow_stage
    asm_module._try_merge_pair = orig_try_merge_pair

    # -----------------------------------------------------------------------
    # Trace A: Assembly Birth Investigation
    # -----------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("FORENSIC TRACE A: ASSEMBLY BIRTH & FORMATION TIMELINE")
    print("=" * 80)

    # Find which events in Root 8 produced Asm 5 and Asm 6
    root8_forms = [f for f in form_events_log if f.get("root_id") == 8]
    print("\nRoot 8 Form Stage Log:")
    for entry in root8_forms:
        if entry.get("action") == "FORMED":
            print(f"  --> FORMED Assembly {entry['assembly_id']}: {entry['members']}")
        else:
            print(f"  Event {entry.get('event_order')}: covered={entry.get('covered_cells_count')}, u_t_count={entry.get('u_t_count')}, u_t={entry.get('u_t')}")

    # -----------------------------------------------------------------------
    # Trace B: Membership Growth & Convergence Timeline
    # -----------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("FORENSIC TRACE B: ASSEMBLY 5 & 6 MEMBERSHIP EVOLUTION")
    print("=" * 80)

    first_identical_root = None
    for r in range(8, 57):
        m5 = asm_snapshots_by_root[r].get(5, [])
        m6 = asm_snapshots_by_root[r].get(6, [])
        is_equal = (m5 == m6)
        if is_equal and first_identical_root is None:
            first_identical_root = r
        if r in (8, 9, 10, 11, 12, 14, 16, 20, 24, 30, 40, 50, 56) or is_equal:
            if r <= 16 or r == first_identical_root or r == 56:
                print(f"  Root {r:02d}: Asm 5 ({len(m5)} cells)={m5} | Asm 6 ({len(m6)} cells)={m6} | Match: {is_equal}")

    print(f"\n>>> Assemblies 5 and 6 became 100% IDENTICAL at Root {first_identical_root}!")

    # Print all grow events for 5 and 6
    grows_5_6 = [g for g in grow_events_log if g["assembly_id"] in (5, 6)]
    print(f"\nAll GROW events for Assemblies 5 and 6:")
    for g in grows_5_6:
        print(f"  Root {g['root_id']:02d}: Assembly {g['assembly_id']} added {g['added_cells']} -> now {g['new_members']} (Gen {g['new_generation']})")

    # -----------------------------------------------------------------------
    # Trace C: MERGE Predicate Evaluation
    # -----------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("FORENSIC TRACE C: MERGE EVALUATION BETWEEN ASSEMBLIES 5 & 6")
    print("=" * 80)

    merges_5_6 = [m for m in merge_attempts_log if m["pair"] == (5, 6)]
    print(f"Total merge evaluations of pair (5, 6): {len(merges_5_6)}")
    for m in merges_5_6[:10]:
        print(f"  Root {m['root_id']:02d}: Jaccard={m.get('jaccard', 0):.4f}, excl_a={m.get('excl_a')}, excl_b={m.get('excl_b')}, between_strength={m.get('between_strength')}, blocked_by={m.get('blocked_by')}")
    if len(merges_5_6) > 10:
        print(f"  ... ({len(merges_5_6) - 10} more identical evaluations)")

    # -----------------------------------------------------------------------
    # Trace D: Readout Collision on Eagle
    # -----------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("FORENSIC TRACE D: READOUT COLLISION AT ROOT 56")
    print("=" * 80)

    prompt_eagle = [branch_db[0].core_event]
    gen_eagle = generate_episode(state, prompt_eagle, ledger, max_steps=5)
    step2 = gen_eagle.steps[2]
    readout = step2.readout_result
    top = readout.ranked_scores[0]
    second = readout.ranked_scores[1]

    print(f"Step 2 Collision Details:")
    print(f"  Top Assembly:    ID {top.assembly_id}, score={top.score_next:.10f}, Q6={top.score_next_q6}")
    print(f"  Second Assembly: ID {second.assembly_id}, score={second.score_next:.10f}, Q6={second.score_next_q6}")
    print(f"  Score Margin:    {readout.margin:.10f}")
    print(f"  Ambiguity Code:  {readout.status.name}")

    return {
        "birth_root_5": 8,
        "birth_root_6": 8,
        "first_identical_root": first_identical_root,
        "merge_attempts_count": len(merges_5_6),
        "collision_step": 2,
        "top_score": top.score_next,
        "second_score": second.score_next,
        "margin": readout.margin,
    }


if __name__ == "__main__":
    run_investigation()
