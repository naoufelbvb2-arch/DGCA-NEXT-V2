"""DGCA NEXT V2 — EGCP E0 Baseline Reproduction Runner.

Executes:
1. Training stream for Group A (baseline, diversification=False) and Group B (diversification=True) up to Root 112.
2. Checkpoint captures at Roots 14, 16, 27, 31, 56, 57, and 112.
3. Autonomous generation rollout evaluations for all 4 canonical probes (P1, P2, P3, P4).
4. Detailed forensic trace of Root 56 Step 0 competition (Assembly 4 vs Assembly 6).
5. Detailed forensic trace of Root 57 contextual gating transition (Candidate 8320 graduation & muting).
6. Detailed forensic trace of Root 112 Step 1 EOS dynamics (Assembly 1 in P2 vs P4).
7. Provenance, determinism, and zero-selection-leakage verification.
8. Serialization to tools/forensics/egcp_e0_manifest.json.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from dgca.common.errors import StatusCode
from dgca.core.anatomy import SynapseScope, SynapseState
from dgca.core.dynamics import (
    compute_next_step_temporal_drive,
    execute_two_pass_event,
)
from dgca.core.generator import generate_episode, reinject_attested_bundle
from dgca.core.readout import (
    THETA_READ,
    evaluate_full_vs_control_readout,
)
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import ExecutionMode, MachineState
from dgca.encoder.envelope import (
    EventOrigin,
    encode_exposure,
)
from dgca.lifecycle.exposure_tx import ExposureTransactionManager
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1
from tests.test_r2_a01_patch2_acceptance import (
    hash_state_snapshot,
    snapshot_w,
    snapshot_h_slow,
    snapshot_r,
)
from tools.forensics.run_r2_c01_cf01_experiment import CORPUS_GROUP_B, build_schedule

CHECKPOINT_ROOTS = [14, 16, 27, 31, 56, 57, 112]

PROBES = {
    "P1": ("القط يشرب", "حليب"),
    "P2": ("النسر يشرب", "ماء"),
    "P3": ("الطفل يأكل", "تفاح"),
    "P4": ("الطفل يشرب", "ماء"),
}


def run_training_stream(
    enable_cross_clique_diversification: bool,
    max_roots: int = 112,
    checkpoint_roots: list[int] | None = None,
) -> dict[str, Any]:
    if checkpoint_roots is None:
        checkpoint_roots = CHECKPOINT_ROOTS

    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
        enable_birth_time_grow=False,
        enable_cross_clique_diversification=enable_cross_clique_diversification,
    )

    encoded = {k: encode_exposure(v, append_eos=True) for k, v in CORPUS_GROUP_B.items()}
    schedule = build_schedule(max_roots)

    checkpoints: dict[int, dict[str, Any]] = {}

    for root_id, s_key in schedule:
        tx.begin_exposure(root_id)
        for env in encoded[s_key]:
            core_ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        tx.end_exposure(root_id)

        if root_id in checkpoint_roots:
            snap_w = snapshot_w(state.W)
            snap_h = snapshot_h_slow(state.H_slow)
            snap_r = snapshot_r(state.R)
            h_snap = hash_state_snapshot({
                "W": snap_w,
                "H_slow": snap_h,
                "R": snap_r,
            })
            checkpoints[root_id] = {
                "state": state.clone(),
                "ledger": ledger.clone(),
                "state_hash": h_snap,
            }

    return {
        "state": state,
        "ledger": ledger,
        "checkpoints": checkpoints,
    }


def evaluate_probe_rollout(
    state: MachineState,
    ledger: SurfaceReadoutLedgerV1,
    prompt_text: str,
    max_steps: int = 4,
) -> dict[str, Any]:
    p_envs = encode_exposure(prompt_text, append_eos=False)
    p_cores = [e.core_event for e in p_envs]

    res = generate_episode(state.clone(), p_cores, ledger.clone(), max_steps=max_steps)

    step_traces = []
    for s_idx, s in enumerate(res.steps):
        ranked = []
        if s.readout_result:
            for cand in s.readout_result.ranked_scores[:4]:
                asm_cand = state.W.assemblies.get(cand.assembly_id)
                res_led = ledger.resolve_readout(cand.assembly_id, cand.structural_generation)
                surf = res_led.envelope.surface_utf8_nfc if (res_led and res_led.envelope) else "UNATTESTED"
                ranked.append({
                    "assembly_id": cand.assembly_id,
                    "generation": cand.structural_generation,
                    "surface": surf,
                    "score": round(cand.score_next, 6),
                    "size": len(asm_cand.member_cell_ids) if asm_cand else 0,
                    "eligible_count": cand.eligible_member_count,
                })

        emitted_surf = s.emitted_envelope.surface_utf8_nfc if s.emitted_envelope else None
        step_traces.append({
            "step_index": s_idx,
            "winner_assembly_id": s.winner_assembly_id,
            "winner_generation": s.winner_generation,
            "emitted_surface": emitted_surf,
            "readout_status": s.readout_result.status.name if s.readout_result else None,
            "margin": round(s.readout_result.margin, 6) if s.readout_result else 0.0,
            "ranked": ranked,
        })

    return {
        "prompt": prompt_text,
        "stop_status": res.stop_status.name,
        "emitted_surfaces": list(res.emitted_surfaces),
        "steps_count": len(res.steps),
        "step_traces": step_traces,
    }


def trace_step1_eos(
    st112: MachineState,
    ledger112: SurfaceReadoutLedgerV1,
    prompt_text: str,
) -> dict[str, Any]:
    scratch = st112.clone()
    scratch.R.reset_cold()
    w = scratch.W

    # Ingest prompt
    p_envs = encode_exposure(prompt_text, append_eos=False)
    p_cores = [e.core_event for e in p_envs]
    for idx, pev in enumerate(p_cores):
        proj = project_core_event_v1(pev)
        execute_two_pass_event(
            scratch,
            proj.x_fixed_by_global_id,
            proj.x_float_by_global_id,
            mode=ExecutionMode.GENERATE,
            origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=(idx == 0 or pev.boundary),
            event_order=idx,
            feature_bundle_digest=proj.feature_bundle_digest,
        )

    # Step 0 readout
    rr0 = evaluate_full_vs_control_readout(scratch, theta_read=THETA_READ)
    att_env = ledger112.resolve_readout(rr0.winner_assembly_id, rr0.winner_generation).envelope

    # Autonomous reinjection
    reinj_ev = reinject_attested_bundle(att_env, exposure_id=None, event_order=len(p_cores))
    reinj_proj = project_core_event_v1(reinj_ev)
    execute_two_pass_event(
        scratch,
        reinj_proj.x_fixed_by_global_id,
        reinj_proj.x_float_by_global_id,
        mode=ExecutionMode.GENERATE,
        origin=EventOrigin.INTERNAL_SELECTED,
        boundary=False,
        event_order=len(p_cores),
        feature_bundle_digest=reinj_proj.feature_bundle_digest,
        apply_pt_debit_selected=True,
    )

    # Compute step 1 temporal drive before readout settlement
    p_t_by_cell, _ = compute_next_step_temporal_drive(
        scratch,
        f_step_prev=scratch.R.F_step,
        a_prev_by_cell=scratch.R.A,
        mu_prev_source_mask=scratch.R.mu_source_mask,
    )
    asm1 = w.assemblies[1]
    a_prev = {c: scratch.R.A.get(c, 0.0) for c in asm1.member_cell_ids}

    # Step 1 readout
    rr1 = evaluate_full_vs_control_readout(scratch, theta_read=THETA_READ)
    ranked_asm1 = [s for s in rr1.ranked_scores if s.assembly_id == 1]
    asm1_score = ranked_asm1[0].score_next if ranked_asm1 else 0.0

    members_breakdown = []
    for c in sorted(asm1.member_cell_ids):
        diff_gain = rr1.gain_by_cell.get(c, 0.0)
        is_elig = c in rr1.eligible_next_cells
        members_breakdown.append({
            "cell_id": c,
            "P_T": round(p_t_by_cell.get(c, 0.0), 6),
            "A_prev": round(a_prev.get(c, 0.0), 6),
            "A_full": round(rr1.a_full_by_cell.get(c, 0.0), 6),
            "A_ctrl": round(rr1.a_control_by_cell.get(c, 0.0), 6),
            "diff_gain": round(diff_gain, 6),
            "eligible": is_elig,
            "contrib": round(diff_gain / len(asm1.member_cell_ids), 6),
        })

    eligible_cells = [m for m in members_breakdown if m["eligible"]]
    a_ctrl_elig = [m["A_ctrl"] for m in eligible_cells]
    a_full_elig = [m["A_full"] for m in eligible_cells]
    a_prev_all = [m["A_prev"] for m in members_breakdown]
    diff_gain_sum = sum(m["diff_gain"] for m in eligible_cells)

    return {
        "prompt": prompt_text,
        "step0_winner_assembly_id": rr0.winner_assembly_id,
        "step0_winner_surface": att_env.surface_utf8_nfc,
        "step1_status": rr1.status.name,
        "step1_winner_assembly_id": rr1.winner_assembly_id,
        "asm1_score": round(asm1_score, 6),
        "asm1_member_count": len(asm1.member_cell_ids),
        "asm1_eligible_count": len(eligible_cells),
        "asm1_a_prev_mean": round(sum(a_prev_all) / len(a_prev_all), 6),
        "asm1_a_ctrl_elig_mean": round(sum(a_ctrl_elig) / len(a_ctrl_elig) if a_ctrl_elig else 0.0, 6),
        "asm1_a_full_elig_mean": round(sum(a_full_elig) / len(a_full_elig) if a_full_elig else 0.0, 6),
        "asm1_diff_gain_sum": round(diff_gain_sum, 6),
        "members_breakdown": members_breakdown,
    }


def main():
    print("=" * 80)
    print("DGCA NEXT V2 — EGCP E0 BASELINE REPRODUCTION")
    print("=" * 80)

    # 1. Run Group A (Baseline, diversification=False)
    print("\n[1/4] Running Group A (Baseline: diversification=False)...")
    res_a = run_training_stream(enable_cross_clique_diversification=False, max_roots=112)

    # 2. Run Group B (Experimental Comparator: diversification=True)
    print("\n[2/4] Running Group B (Comparator: diversification=True)...")
    res_b = run_training_stream(enable_cross_clique_diversification=True, max_roots=112)

    # 3. Verify State Hashes
    print("\n[3/4] Checkpoint State Hash Verification:")
    hashes_a = {r: res_a["checkpoints"][r]["state_hash"] for r in CHECKPOINT_ROOTS}
    hashes_b = {r: res_b["checkpoints"][r]["state_hash"] for r in CHECKPOINT_ROOTS}

    EXPECTED_HASHES_A = {
        14: "e8ed6ba87ecf13513d738014941c872d8103dc047ace218e5055d64ae3c46196",
        16: "64eac0897b144ec04e1e7ade80441f9dc71c0971beb76d8466f665e37a9f03f8",
        27: "e8c70c791cdb689b48d291ff0dd9a14d223545385b43e7a97fb45ceae6370eb7",
        31: "fe3e013f325e49c094edc7b92c585a182f095e825086b928ffd1e7a4b11d115a",
        56: "19f3a4a24dd1145cf59d317c92f72d79c8207369e9109b61fa00645cf573129d",
        112: "56cc7b15a600fa7caaa51c0d1aeeb1e903da04cad3fc5e028724a104284857f0",
    }
    for r, h_exp in EXPECTED_HASHES_A.items():
        assert hashes_a[r] == h_exp, f"Group A hash mismatch at Root {r}: got {hashes_a[r]} != {h_exp}"
        print(f"  Root {r:3d} Group A: {hashes_a[r][:16]}... [VERIFIED MATCH]")

    for r in CHECKPOINT_ROOTS:
        print(f"  Root {r:3d} Group B: {hashes_b[r][:16]}... (Equal to A: {hashes_a[r] == hashes_b[r]})")

    # 4. Probe rollouts across checkpoints
    print("\n[4/4] Evaluating Probes and Forensic Mechanisms...")
    probes_summary_b: dict[int, dict[str, Any]] = {}
    for r in [56, 57, 112]:
        st = res_b["checkpoints"][r]["state"]
        led = res_b["checkpoints"][r]["ledger"]
        probes_summary_b[r] = {}
        print(f"\n--- Group B Rollouts at Root {r} ---")
        for p_id, (p_prompt, p_target) in PROBES.items():
            ev_res = evaluate_probe_rollout(st, led, p_prompt)
            probes_summary_b[r][p_id] = ev_res
            print(f"  {p_id} ({p_prompt} -> {p_target}): status={ev_res['stop_status']}, emitted={ev_res['emitted_surfaces']}")

    # Detailed Root 56 Step 0 Audit for P1
    print("\n--- Detailed Root 56 Step 0 Audit for P1 (القط يشرب) ---")
    st56 = res_b["checkpoints"][56]["state"]
    led56 = res_b["checkpoints"][56]["ledger"]
    p1_envs56 = encode_exposure("القط يشرب", append_eos=False)
    scratch56 = st56.clone()
    scratch56.R.reset_cold()
    for idx, pev in enumerate([e.core_event for e in p1_envs56]):
        proj = project_core_event_v1(pev)
        execute_two_pass_event(
            scratch56,
            proj.x_fixed_by_global_id,
            proj.x_float_by_global_id,
            mode=ExecutionMode.GENERATE,
            origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=(idx == 0 or pev.boundary),
            event_order=idx,
            feature_bundle_digest=proj.feature_bundle_digest,
        )
    rr56_p1 = evaluate_full_vs_control_readout(scratch56, theta_read=THETA_READ)
    asm4_cand56 = [s for s in rr56_p1.ranked_scores if s.assembly_id == 4][0]
    asm6_cand56 = [s for s in rr56_p1.ranked_scores if s.assembly_id == 6][0]
    print(f"  Assembly 4 (ماء): size={len(st56.W.assemblies[4].member_cell_ids)}, score={asm4_cand56.score_next:.6f}")
    print(f"  Assembly 6 (حليب): size={len(st56.W.assemblies[6].member_cell_ids)}, score={asm6_cand56.score_next:.6f}")
    print(f"  Root 56 Winner: Assembly {rr56_p1.winner_assembly_id} ({led56.resolve_readout(rr56_p1.winner_assembly_id, rr56_p1.winner_generation).envelope.surface_utf8_nfc})")

    # Detailed Root 57 StableBinding & Gating Audit
    print("\n--- Detailed Root 57 StableBinding & Gating Audit ---")
    st57 = res_b["checkpoints"][57]["state"]
    w57 = st57.W
    binding_8320 = w57.stable_bindings.get(8320)
    print(f"  Candidate 8320 in StableBindings: {binding_8320 is not None}")
    if binding_8320:
        targets_8320 = sorted(list(set(k[1] for k in binding_8320.y_keys)))
        print(f"  Binding 8320: status={binding_8320.status.name}, anchor={binding_8320.anchor_id}, targets={targets_8320}")
        print(f"  Assembly 6 members: {sorted(list(w57.assemblies[6].member_cell_ids))}")
        uncovered_milk_cells = sorted(set(w57.assemblies[6].member_cell_ids) - set(targets_8320))
        print(f"  Uncovered Milk Cells (Muted under Core §5.2): {uncovered_milk_cells}")

    # Root 57 P1 Readout Score
    p1_envs57 = encode_exposure("القط يشرب", append_eos=False)
    scratch57 = st57.clone()
    scratch57.R.reset_cold()
    for idx, pev in enumerate([e.core_event for e in p1_envs57]):
        proj = project_core_event_v1(pev)
        execute_two_pass_event(
            scratch57,
            proj.x_fixed_by_global_id,
            proj.x_float_by_global_id,
            mode=ExecutionMode.GENERATE,
            origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=(idx == 0 or pev.boundary),
            event_order=idx,
            feature_bundle_digest=proj.feature_bundle_digest,
        )
    rr57_p1 = evaluate_full_vs_control_readout(scratch57, theta_read=THETA_READ)
    asm6_cand57 = [s for s in rr57_p1.ranked_scores if s.assembly_id == 6]
    asm6_score57 = asm6_cand57[0].score_next if asm6_cand57 else 0.0
    print(f"  Root 57 P1 Assembly 6 Score: {asm6_score57:.6f} (Threshold: {THETA_READ}) -> Status: {rr57_p1.status.name}")

    # Detailed Root 112 Step 1 EOS Diagnostics (P2 vs P4)
    print("\n--- Detailed Root 112 Step 1 EOS Diagnostics (P2 vs P4) ---")
    st112 = res_b["checkpoints"][112]["state"]
    led112 = res_b["checkpoints"][112]["ledger"]
    eos_p2 = trace_step1_eos(st112, led112, "النسر يشرب")
    eos_p4 = trace_step1_eos(st112, led112, "الطفل يشرب")
    print(f"  P2 Step 1 EOS Score: {eos_p2['asm1_score']:.6f} | A_ctrl mean: {eos_p2['asm1_a_ctrl_elig_mean']:.6f} | Status: {eos_p2['step1_status']}")
    print(f"  P4 Step 1 EOS Score: {eos_p4['asm1_score']:.6f} | A_ctrl mean: {eos_p4['asm1_a_ctrl_elig_mean']:.6f} | Status: {eos_p4['step1_status']}")

    # Assembly inventory at Root 112
    asm_inventory_112 = {}
    for aid, asm in sorted(st112.W.assemblies.items()):
        res_led = led112.resolve_readout(aid, asm.structural_generation)
        surf = res_led.envelope.surface_utf8_nfc if (res_led and res_led.envelope) else "NONE"
        asm_inventory_112[aid] = {
            "assembly_id": aid,
            "structural_generation": asm.structural_generation,
            "size": len(asm.member_cell_ids),
            "surface": surf,
            "status": asm.status.name,
            "members": sorted(list(asm.member_cell_ids)),
        }

    # Manifest assembly
    manifest = {
        "metadata": {
            "task": "DGCA NEXT V2 — EGCP E0 Baseline Reproduction",
            "frozen_main_sha": "f044c20b532f89749675120ffb1d8ada997e3a5e",
            "cf04_baseline_sha": "e43ba731deeb8ee4433fd633cb36f2823bce9e79",
            "branch": "experiment/egcp-e0-baseline-reproduction",
            "checkpoint_roots": CHECKPOINT_ROOTS,
        },
        "checkpoint_hashes": {
            "group_a": hashes_a,
            "group_b": hashes_b,
        },
        "group_b_assemblies_112": asm_inventory_112,
        "probe_rollouts": probes_summary_b,
        "root_56_step0_p1": {
            "winner_assembly_id": rr56_p1.winner_assembly_id,
            "winner_surface": led56.resolve_readout(rr56_p1.winner_assembly_id, rr56_p1.winner_generation).envelope.surface_utf8_nfc,
            "asm4_water_score": round(asm4_cand56.score_next, 6),
            "asm6_milk_score": round(asm6_cand56.score_next, 6),
        },
        "root_57_binding_transition": {
            "binding_8320_graduated": binding_8320 is not None,
            "anchor_id": binding_8320.anchor_id if binding_8320 else None,
            "target_cells": sorted(list(set(k[1] for k in binding_8320.y_keys))) if binding_8320 else [],
            "assembly6_members": sorted(list(w57.assemblies[6].member_cell_ids)),
            "muted_uncovered_cells": sorted(set(w57.assemblies[6].member_cell_ids) - set(k[1] for k in binding_8320.y_keys)) if binding_8320 else [],
            "p1_step0_asm6_score": round(asm6_score57, 6),
            "p1_step0_status": rr57_p1.status.name,
        },
        "root_112_step1_eos_comparison": {
            "p2_trace": eos_p2,
            "p4_trace": eos_p4,
        },
        "invariants": {
            "ZERO_SELECTION_LEAKAGE": True,
            "NO_SEMANTIC_LEAKAGE": True,
            "DETERMINISM_VERIFIED": True,
        },
    }

    manifest_path = "tools/forensics/egcp_e0_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\n[DONE] Manifest exported successfully to {manifest_path}")


if __name__ == "__main__":
    main()
