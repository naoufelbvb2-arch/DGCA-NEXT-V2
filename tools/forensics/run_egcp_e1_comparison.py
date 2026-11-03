"""DGCA NEXT V2 — EGCP E1 Controlled Comparison Runner.

Executes:
1. Training stream under canonical Group B up to Root 112 (with checkpoints at Roots 56, 57, 112).
2. Controlled comparison of the SAME frozen neural state at Roots 56, 57, and 112 under:
   - EGCP_MODE = OFF (legacy directed attenuation)
   - EGCP_MODE = E1_PRESERVE_GENERIC (generic prediction preserved)
3. Genuine multi-step autonomous generation for all 4 canonical probes (P1, P2, P3, P4).
4. Detailed capture of:
   - Effective mu_ij values (anchor 8327 -> milk cells vs water cells)
   - Step 0 Readout scores for Assembly 4 (ماء) vs Assembly 6 (حليب)
   - Step 1 Rollout EOS dynamics for Assembly 1 (<EOS>) in P2 vs P4
   - Autonomous trajectories, stop statuses, and margins
5. Serialization to tools/forensics/egcp_e1_comparison_data.json.
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
from dgca.core.context_gate import compute_directed_mu_ij
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
from dgca.core.state import EGCPMode, ExecutionMode, MachineState
from dgca.encoder.envelope import EventOrigin, encode_exposure
from dgca.lifecycle.exposure_tx import ExposureTransactionManager
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1
from tools.forensics.run_r2_c01_cf01_experiment import CORPUS_GROUP_B, build_schedule

CHECKPOINT_ROOTS = [56, 57, 112]

PROBES = {
    "P1": ("القط يشرب", "حليب"),
    "P2": ("النسر يشرب", "ماء"),
    "P3": ("الطفل يأكل", "تفاح"),
    "P4": ("الطفل يشرب", "ماء"),
}

MILK_CELLS = [9183, 9319, 9325, 10903, 11191, 11220, 11463]
WATER_CELLS = [8242, 8809, 9854, 11638, 11984]


def run_canonical_training(max_roots: int = 112) -> dict[int, dict[str, Any]]:
    """Run Group B training stream with EGCP_MODE=OFF."""
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
        enable_birth_time_grow=False,
        enable_cross_clique_diversification=True,
        egcp_mode=EGCPMode.OFF,
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

        if root_id in CHECKPOINT_ROOTS:
            checkpoints[root_id] = {
                "state": state.clone(),
                "ledger": ledger.clone(),
            }

    return checkpoints


def evaluate_probe_under_mode(
    state: MachineState,
    ledger: SurfaceReadoutLedgerV1,
    prompt_text: str,
    mode: EGCPMode,
    max_steps: int = 4,
) -> dict[str, Any]:
    p_envs = encode_exposure(prompt_text, append_eos=False)
    p_cores = [e.core_event for e in p_envs]

    res = generate_episode(
        state,
        p_cores,
        ledger,
        max_steps=max_steps,
        egcp_mode=mode,
    )

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
        "egcp_mode": mode.value,
        "stop_status": res.stop_status.name,
        "emitted_surfaces": list(res.emitted_surfaces),
        "steps_count": len(res.steps),
        "step_traces": step_traces,
    }


def trace_step0_mu_and_readout(
    state: MachineState,
    ledger: SurfaceReadoutLedgerV1,
    prompt_text: str,
    mode: EGCPMode,
) -> dict[str, Any]:
    scratch = state.clone()
    scratch.R.reset_cold()
    scratch.egcp_mode = mode

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

    # Inspect effective mu_ij from anchor 8327
    anchor_id = 8327
    mu_prev = scratch.R.mu_source_mask
    w = scratch.W

    mu_milk = {
        c: compute_directed_mu_ij(anchor_id, c, mu_prev, w, egcp_mode=mode)
        for c in MILK_CELLS
    }
    mu_water = {
        c: compute_directed_mu_ij(anchor_id, c, mu_prev, w, egcp_mode=mode)
        for c in WATER_CELLS
    }

    # Evaluate Step 0 Readout
    rr0 = evaluate_full_vs_control_readout(scratch, theta_read=THETA_READ, egcp_mode=mode)

    ranked_dict = {}
    for cand in rr0.ranked_scores:
        asm = w.assemblies.get(cand.assembly_id)
        res_led = ledger.resolve_readout(cand.assembly_id, cand.structural_generation)
        surf = res_led.envelope.surface_utf8_nfc if (res_led and res_led.envelope) else "NONE"
        ranked_dict[cand.assembly_id] = {
            "assembly_id": cand.assembly_id,
            "surface": surf,
            "score": round(cand.score_next, 6),
            "size": len(asm.member_cell_ids) if asm else 0,
            "eligible_count": cand.eligible_member_count,
        }

    # Cell-level metrics for Assembly 4 (water) and Assembly 6 (milk)
    cell_metrics_asm4 = []
    if 4 in w.assemblies:
        for c in sorted(w.assemblies[4].member_cell_ids):
            cell_metrics_asm4.append({
                "cell_id": c,
                "a_full": round(rr0.a_full_by_cell.get(c, 0.0), 6),
                "a_ctrl": round(rr0.a_control_by_cell.get(c, 0.0), 6),
                "gain": round(rr0.gain_by_cell.get(c, 0.0), 6),
                "eligible": c in rr0.eligible_next_cells,
            })

    cell_metrics_asm6 = []
    if 6 in w.assemblies:
        for c in sorted(w.assemblies[6].member_cell_ids):
            cell_metrics_asm6.append({
                "cell_id": c,
                "a_full": round(rr0.a_full_by_cell.get(c, 0.0), 6),
                "a_ctrl": round(rr0.a_control_by_cell.get(c, 0.0), 6),
                "gain": round(rr0.gain_by_cell.get(c, 0.0), 6),
                "eligible": c in rr0.eligible_next_cells,
            })

    winner_surf = "NONE"
    if rr0.winner_assembly_id is not None:
        w_led = ledger.resolve_readout(rr0.winner_assembly_id, rr0.winner_generation)
        if w_led and w_led.envelope:
            winner_surf = w_led.envelope.surface_utf8_nfc

    return {
        "prompt": prompt_text,
        "egcp_mode": mode.value,
        "anchor_id": anchor_id,
        "anchor_mu_source": mu_prev.get(anchor_id, 0),
        "mu_directed_milk": mu_milk,
        "mu_directed_water": mu_water,
        "readout_status": rr0.status.name,
        "winner_assembly_id": rr0.winner_assembly_id,
        "winner_surface": winner_surf,
        "top_score": round(rr0.top_score, 6),
        "margin": round(rr0.margin, 6),
        "asm4_water": ranked_dict.get(4),
        "asm6_milk": ranked_dict.get(6),
        "cell_metrics_asm4": cell_metrics_asm4,
        "cell_metrics_asm6": cell_metrics_asm6,
    }


def main():
    print("=" * 80)
    print("DGCA NEXT V2 — EGCP E1 CONTROLLED EXPERIMENTAL COMPARISON")
    print("=" * 80)

    # 1. Train canonical baseline stream to get frozen states at Roots 56, 57, 112
    print("\n[1/3] Generating Frozen Checkpoints across Group B...")
    checkpoints = run_canonical_training(max_roots=112)
    print(f"Captured checkpoints at roots: {sorted(checkpoints.keys())}")

    # 2. Evaluate controlled comparison across Roots 56, 57, 112
    print("\n[2/3] Evaluating Controlled Comparisons (OFF vs E1_PRESERVE_GENERIC)...")
    comparison_results: dict[str, Any] = {}

    for r in CHECKPOINT_ROOTS:
        st = checkpoints[r]["state"]
        led = checkpoints[r]["ledger"]
        comparison_results[str(r)] = {"OFF": {}, "E1_PRESERVE_GENERIC": {}}
        print(f"\n==================== ROOT {r} EVALUATION ====================")

        for mode in [EGCPMode.OFF, EGCPMode.E1_PRESERVE_GENERIC]:
            print(f"\n--- MODE: {mode.value} ---")
            # Trace Step 0 for P1
            p1_step0 = trace_step0_mu_and_readout(st, led, "القط يشرب", mode)
            print(f"  P1 Step 0: Winner={p1_step0['winner_surface']} (Asm {p1_step0['winner_assembly_id']}), Status={p1_step0['readout_status']}")
            if p1_step0['asm4_water']:
                print(f"    Asm 4 (ماء): score={p1_step0['asm4_water']['score']:.6f}, elig={p1_step0['asm4_water']['eligible_count']}")
            if p1_step0['asm6_milk']:
                print(f"    Asm 6 (حليب): score={p1_step0['asm6_milk']['score']:.6f}, elig={p1_step0['asm6_milk']['eligible_count']}")
            print(f"    mu_directed to milk: {p1_step0['mu_directed_milk']}")

            # Rollouts for all 4 probes
            probes_data = {}
            for p_id, (p_prompt, p_target) in PROBES.items():
                ev = evaluate_probe_under_mode(st, led, p_prompt, mode, max_steps=4)
                probes_data[p_id] = ev
                print(f"  {p_id} ({p_prompt} -> {p_target}): status={ev['stop_status']}, emitted={ev['emitted_surfaces']}")

            comparison_results[str(r)][mode.value] = {
                "p1_step0": p1_step0,
                "probe_rollouts": probes_data,
            }

    # 3. Test ExposureTransactionManager Mode Guard Invariant
    print("\n[3/3] Testing ExposureTransactionManager Mode Guard Invariant...")
    test_st = MachineState()
    tx = ExposureTransactionManager(test_st, egcp_mode=EGCPMode.OFF)
    assert tx.egcp_mode == EGCPMode.OFF
    assert test_st.egcp_mode == EGCPMode.OFF

    # Boundary switch allowed when CLOSED
    tx.set_egcp_mode(EGCPMode.E1_PRESERVE_GENERIC)
    assert tx.egcp_mode == EGCPMode.E1_PRESERVE_GENERIC
    assert test_st.egcp_mode == EGCPMode.E1_PRESERVE_GENERIC

    # Switching during OPEN exposure must raise ValueError
    tx.begin_exposure(1)
    open_switch_failed = False
    try:
        tx.set_egcp_mode(EGCPMode.OFF)
    except ValueError as e:
        open_switch_failed = True
        print(f"  Verified mode switch during OPEN root correctly raised: {e}")
    assert open_switch_failed, "Expected ValueError when switching mode during OPEN root!"
    tx.abort_exposure(1)
    print("  Mode guard invariant verified successfully.")

    # Save manifest
    manifest_payload = {
        "metadata": {
            "task": "DGCA NEXT V2 — EGCP E1 Controlled Comparison",
            "branch": "experiment/egcp-e1-generic-preservation",
            "checkpoint_roots": CHECKPOINT_ROOTS,
        },
        "comparison_by_root": comparison_results,
    }

    out_path = "tools/forensics/egcp_e1_comparison_data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest_payload, f, indent=2, ensure_ascii=False)
    print(f"\n[DONE] Comparison data exported successfully to {out_path}")


if __name__ == "__main__":
    main()
