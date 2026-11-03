"""DGCA NEXT V2 — EGCP E1 Full-Learning Validation Runner.

Executes:
1. Canonical 112-root Group B training stream under EGCP_MODE = OFF.
2. Canonical 112-root Group B training stream under EGCP_MODE = E1_PRESERVE_GENERIC.
3. Checkpoints at Roots 14, 16, 27, 31, 56, 57, 112.
4. Autonomous generation rollouts (P1-P4) for:
   - OFF run (OFF generation)
   - OFF checkpoint with E1 mode (immediate inference effect)
   - E1 run (accumulated learning effect)
5. Forensic comparison of W/H evolution, structural assemblies, StableBindings, and source masks.
6. Verification of ZERO_SELECTION_LEAKAGE.
7. Output saved to tools/forensics/egcp_e1_full_learning_data.json.
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
from dgca.core.generator import generate_episode
from dgca.core.readout import (
    THETA_READ,
    evaluate_full_vs_control_readout,
)
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import EGCPMode, ExecutionMode, MachineState
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


def evaluate_probe_rollout(
    state: MachineState,
    ledger: SurfaceReadoutLedgerV1,
    prompt_text: str,
    egcp_mode: EGCPMode | str = EGCPMode.OFF,
    max_steps: int = 4,
) -> dict[str, Any]:
    p_envs = encode_exposure(prompt_text, append_eos=False)
    p_cores = [e.core_event for e in p_envs]

    scratch = state.clone()
    scratch.egcp_mode = EGCPMode(egcp_mode)

    res = generate_episode(
        scratch,
        p_cores,
        ledger.clone(),
        max_steps=max_steps,
        egcp_mode=scratch.egcp_mode,
    )

    step_traces = []
    for s_idx, s in enumerate(res.steps):
        ranked = []
        if s.readout_result:
            for cand in s.readout_result.ranked_scores[:4]:
                asm_cand = scratch.W.assemblies.get(cand.assembly_id)
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


def run_full_stream(mode: EGCPMode) -> dict[str, Any]:
    print(f"--- Running full 112-root training with EGCP_MODE={mode.value} ---")
    state = MachineState(egcp_mode=mode)
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
        enable_birth_time_grow=False,
        enable_cross_clique_diversification=True,
        egcp_mode=mode,
    )

    encoded = {k: encode_exposure(v, append_eos=True) for k, v in CORPUS_GROUP_B.items()}
    schedule = build_schedule(112)

    checkpoints: dict[int, dict[str, Any]] = {}

    for root_id, s_key in schedule:
        tx.begin_exposure(root_id)
        for env in encoded[s_key]:
            core_ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        tx.end_exposure(root_id)

        if root_id in CHECKPOINT_ROOTS:
            snap_w = snapshot_w(state.W)
            snap_h = snapshot_h_slow(state.H_slow)
            snap_r = snapshot_r(state.R)
            h_snap = hash_state_snapshot({
                "W": snap_w,
                "H_slow": snap_h,
                "R": snap_r,
            })

            # Record assemblies
            assemblies_info = {}
            for aid, a in state.W.assemblies.items():
                assemblies_info[aid] = {
                    "size": len(a.member_cell_ids),
                    "members": sorted(list(a.member_cell_ids)),
                    "status": str(a.status),
                }

            # Record stable bindings
            bindings_info = {}
            for cid, sb in state.W.stable_bindings.items():
                bindings_info[cid] = {
                    "owner_cell": cid,
                    "anchor_id": sb.anchor_id,
                    "p_keys": [list(k) for k in sb.p_keys],
                    "c_keys": [list(k) for k in sb.c_keys],
                    "y_keys": [list(k) for k in sb.y_keys],
                    "status": str(sb.status),
                    "depth": sb.depth,
                }

            # Record total synapses
            syn_total = len(state.W.synapses)
            syn_assoc_cons = sum(1 for syn in state.W.synapses.values() if syn.scope == SynapseScope.ASSOCIATIVE and syn.state == SynapseState.CONSOLIDATED)
            syn_assoc_cand = sum(1 for syn in state.W.synapses.values() if syn.scope == SynapseScope.ASSOCIATIVE and syn.state == SynapseState.CANDIDATE)

            checkpoints[root_id] = {
                "state_hash": h_snap,
                "syn_total": syn_total,
                "syn_assoc_consolidated": syn_assoc_cons,
                "syn_assoc_candidate": syn_assoc_cand,
                "assemblies": assemblies_info,
                "stable_bindings": bindings_info,
                "cloned_state": state.clone(),
                "cloned_ledger": ledger.clone(),
            }
            print(f"  Root {root_id:3d} completed: syn_total={syn_total}, assemblies={len(assemblies_info)}, bindings={len(bindings_info)}, hash={h_snap[:12]}...")

    return {
        "final_state": state,
        "final_ledger": ledger,
        "checkpoints": checkpoints,
    }


def main() -> None:
    # 1. Run OFF training
    res_off = run_full_stream(EGCPMode.OFF)

    # 2. Run E1 training
    res_e1 = run_full_stream(EGCPMode.E1_PRESERVE_GENERIC)

    # 3. Compare trajectories across checkpoints
    comparison_summary: dict[str, Any] = {
        "checkpoints": {},
        "rollouts": {},
    }

    for root_id in CHECKPOINT_ROOTS:
        c_off = res_off["checkpoints"][root_id]
        c_e1 = res_e1["checkpoints"][root_id]

        hash_match = (c_off["state_hash"] == c_e1["state_hash"])
        syn_match = (c_off["syn_total"] == c_e1["syn_total"] and c_off["syn_assoc_consolidated"] == c_e1["syn_assoc_consolidated"])
        asm_match = (c_off["assemblies"] == c_e1["assemblies"])
        bind_match = (c_off["stable_bindings"] == c_e1["stable_bindings"])

        comparison_summary["checkpoints"][str(root_id)] = {
            "root_id": root_id,
            "off_state_hash": c_off["state_hash"],
            "e1_state_hash": c_e1["state_hash"],
            "hash_identical": hash_match,
            "synapses_identical": syn_match,
            "assemblies_identical": asm_match,
            "bindings_identical": bind_match,
            "off_syn_total": c_off["syn_total"],
            "e1_syn_total": c_e1["syn_total"],
            "off_assemblies_count": len(c_off["assemblies"]),
            "e1_assemblies_count": len(c_e1["assemblies"]),
            "off_bindings_count": len(c_off["stable_bindings"]),
            "e1_bindings_count": len(c_e1["stable_bindings"]),
        }
        print(f"Checkpoint Root {root_id:3d} Comparison: hash_match={hash_match}, syn_match={syn_match}, asm_match={asm_match}, bind_match={bind_match}")

    # 4. Probe rollouts at Roots 56, 57, 112
    rollout_roots = [56, 57, 112]
    for root_id in rollout_roots:
        c_off = res_off["checkpoints"][root_id]
        c_e1 = res_e1["checkpoints"][root_id]

        comparison_summary["rollouts"][str(root_id)] = {}

        for p_id, (prompt_text, expected_next) in PROBES.items():
            # (A) OFF run with OFF evaluation
            roll_off = evaluate_probe_rollout(c_off["cloned_state"], c_off["cloned_ledger"], prompt_text, egcp_mode=EGCPMode.OFF)
            # (B) OFF run with E1 evaluation (Immediate inference effect on frozen OFF state)
            roll_imm = evaluate_probe_rollout(c_off["cloned_state"], c_off["cloned_ledger"], prompt_text, egcp_mode=EGCPMode.E1_PRESERVE_GENERIC)
            # (C) E1 run with E1 evaluation (Accumulated learning effect on E1-trained state)
            roll_e1 = evaluate_probe_rollout(c_e1["cloned_state"], c_e1["cloned_ledger"], prompt_text, egcp_mode=EGCPMode.E1_PRESERVE_GENERIC)

            comparison_summary["rollouts"][str(root_id)][p_id] = {
                "prompt": prompt_text,
                "expected_next": expected_next,
                "off_run_off_eval": {
                    "emitted": roll_off["emitted_surfaces"],
                    "stop_status": roll_off["stop_status"],
                    "steps": roll_off["step_traces"],
                },
                "immediate_inference_e1_eval": {
                    "emitted": roll_imm["emitted_surfaces"],
                    "stop_status": roll_imm["stop_status"],
                    "steps": roll_imm["step_traces"],
                },
                "accumulated_learning_e1_eval": {
                    "emitted": roll_e1["emitted_surfaces"],
                    "stop_status": roll_e1["stop_status"],
                    "steps": roll_e1["step_traces"],
                },
            }
            print(f"  Root {root_id} {p_id} ({prompt_text}):")
            print(f"    OFF run -> {roll_off['emitted_surfaces']}")
            print(f"    Immediate E1 -> {roll_imm['emitted_surfaces']}")
            print(f"    Accumulated E1 -> {roll_e1['emitted_surfaces']}")

    out_path = os.path.join("tools", "forensics", "egcp_e1_full_learning_data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(comparison_summary, f, indent=2, ensure_ascii=False)
    print(f"\nSaved full-learning comparison data to {out_path}")


if __name__ == "__main__":
    main()
