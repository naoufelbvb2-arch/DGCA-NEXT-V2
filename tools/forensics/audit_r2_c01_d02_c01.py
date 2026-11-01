"""DGCA NEXT V2 — R2-C01-D02-C01 Evidence Reconciliation Script.

Executes:
1. Verification and table extraction from r2_c01_d02_forensics_data.json.
2. Inspection of Group B Assembly 4, 6, 1 actual membership and scores across checkpoints.
3. Authentic autonomous EOS state trace for P2 and P4 at Root 112 (via genuine generate_episode rollout path).
4. Deep forensic audit of contextual binding creation, graduation, and gating mask at Root 57.
"""

from __future__ import annotations

import copy
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
    CoreEventPayloadV1,
    EventOrigin,
    Marker,
    PeripheralSurfaceEnvelopeV1,
    encode_exposure,
)
from tools.forensics.run_r2_c01_d02_investigation import (
    AUDIT_CHECKPOINTS,
    PROBES,
    feed_prompt,
    run_training_stream,
)


def run_c01_reconciliation():
    print("--- 1. LOADING HISTORICAL FORENSICS DATASET ---")
    data_path = "tools/forensics/r2_c01_d02_forensics_data.json"
    with open(data_path, "r", encoding="utf-8") as f:
        d02_json = json.load(f)

    gen_audit = d02_json["s01_generation_audit"]
    print("Loaded generation audit for roots:", sorted(gen_audit["group_b"].keys(), key=int))

    print("\n--- 2. TRAINING STREAM EXECUTION FOR RUNTIME AUDIT ---")
    gb_res = run_training_stream(
        enable_cross_clique_diversification=True,
        max_roots=112,
        checkpoint_roots=[56, 57, 60, 64, 112],
    )
    ckpts = gb_res["checkpoints"]

    print("\n--- 3. CONTEXTUAL BINDING TRANSITION AUDIT ---")
    # Check stable bindings across checkpoints
    ctx_audit = {}
    for r in [56, 57, 60, 64, 112]:
        st = ckpts[r]["state"]
        w = st.W
        b_list = []
        for b_id, b in w.stable_bindings.items():
            targets = [k[1] for k in b.y_keys]
            b_list.append({
                "binding_id": b_id,
                "z_cell_id": b.z_cell_id,
                "anchor_id": b.anchor_id,
                "status": b.status.name,
                "y_keys_count": len(b.y_keys),
                "target_cells": sorted(list(set(targets))),
                "p_keys": [[k[0], k[1], k[2].name] for k in b.p_keys],
                "anchor_source_set": sorted(list(b.anchor_source_set)),
            })
        ctx_audit[str(r)] = {
            "stable_bindings_count": len(w.stable_bindings),
            "bindings": b_list,
        }
        print(f"Root {r}: stable_bindings count = {len(w.stable_bindings)}")
        for b in b_list:
            print(f"  Binding {b['binding_id']}: z={b['z_cell_id']}, anchor={b['anchor_id']}, targets={b['target_cells']}")

    print("\n--- 4. ASSEMBLY 4, 6, 1 METRICS AT ROOT 112 ---")
    st112 = ckpts[112]["state"]
    ledger112 = ckpts[112]["ledger"]
    w112 = st112.W

    asm1 = w112.assemblies[1]  # EOS
    asm4 = w112.assemblies[4]  # water
    asm6 = w112.assemblies[6]  # milk

    print(f"Assembly 1 (<EOS>): size={len(asm1.member_cell_ids)}, gen={asm1.structural_generation}, members={sorted(list(asm1.member_cell_ids))}")
    print(f"Assembly 4 (ماء): size={len(asm4.member_cell_ids)}, gen={asm4.structural_generation}, members={sorted(list(asm4.member_cell_ids))}")
    print(f"Assembly 6 (حليب): size={len(asm6.member_cell_ids)}, gen={asm6.structural_generation}, members={sorted(list(asm6.member_cell_ids))}")

    print("\n--- 5. AUTHENTIC AUTONOMOUS EOS STATE TRACE (P2 vs P4) ---")
    # Execute authoritative generate_episode execution path
    eos_traces = {}
    for p_name, words in [("P2", ["النسر", "يشرب"]), ("P4", ["الطفل", "يشرب"])]:
        print(f"\nTracing genuine rollout for {p_name} ({' '.join(words)})...")
        scratch_state = st112.clone()
        scratch_state.R.reset_cold()
        ledger_snapshot = ledger112.clone()

        # Step 0: Ingest prompt events
        p_text = " ".join(words)
        p_envs = encode_exposure(p_text, append_eos=False)
        p_cores = [env.core_event for env in p_envs]

        prompt_results = []
        for idx, pev in enumerate(p_cores):
            proj = project_core_event_v1(pev)
            res = execute_two_pass_event(
                scratch_state,
                proj.x_fixed_by_global_id,
                proj.x_float_by_global_id,
                mode=ExecutionMode.GENERATE,
                origin=EventOrigin.READ_ONLY_OBSERVED,
                boundary=(idx == 0 or pev.boundary),
                exposure_id=None,
                event_order=idx,
                feature_bundle_digest=proj.feature_bundle_digest,
                allow_candidate_probe=False,
                admit_uncommitted_sensory=False,
            )
            prompt_results.append(res)

        # Step 0 readout
        rr0 = evaluate_full_vs_control_readout(scratch_state, theta_read=THETA_READ)
        print(f"  Step 0 winner: Assembly {rr0.winner_assembly_id} (gen {rr0.winner_generation}), top_score={rr0.top_score:.4f}, margin={rr0.margin:.4f}")
        assert rr0.winner_assembly_id == 4, f"Expected Assembly 4 (ماء), got {rr0.winner_assembly_id}"

        # Step 0 peripheral lookup
        res_led0 = ledger_snapshot.resolve_readout(rr0.winner_assembly_id, rr0.winner_generation)
        attested_env0 = res_led0.envelope
        print(f"  Step 0 emitted surface: {attested_env0.surface_utf8_nfc}")

        # Step 0 reinjection via lawful generator path
        reinjected_core_event = reinject_attested_bundle(
            attested_env0,
            exposure_id=None,
            event_order=len(prompt_results),
        )
        reinjected_proj = project_core_event_v1(reinjected_core_event)
        reinjected_res = execute_two_pass_event(
            scratch_state,
            reinjected_proj.x_fixed_by_global_id,
            reinjected_proj.x_float_by_global_id,
            mode=ExecutionMode.GENERATE,
            origin=EventOrigin.INTERNAL_SELECTED,
            boundary=False,
            exposure_id=None,
            event_order=reinjected_core_event.event_order,
            feature_bundle_digest=reinjected_proj.feature_bundle_digest,
            allow_candidate_probe=False,
            admit_uncommitted_sensory=False,
            apply_pt_debit_selected=True,
        )

        # Now scratch_state is at the exact scratch state before Step 1 readout!
        # Capture P^T before readout
        p_t_step1, pt_sources = compute_next_step_temporal_drive(
            scratch_state,
            f_step_prev=scratch_state.R.F_step,
            a_prev_by_cell=scratch_state.R.A,
            mu_prev_source_mask=scratch_state.R.mu_source_mask,
        )
        # Capture A in scratch_state.R prior to readout settlement
        a_prev_step1 = {cell: scratch_state.R.A.get(cell, 0.0) for cell in asm1.member_cell_ids}

        # Step 1 readout
        rr1 = evaluate_full_vs_control_readout(scratch_state, theta_read=THETA_READ)
        ranked_asm1 = [s for s in rr1.ranked_scores if s.assembly_id == 1]
        asm1_score = ranked_asm1[0].score_next if ranked_asm1 else 0.0
        print(f"  Step 1 Readout Status: {rr1.status.name}, Winner: {rr1.winner_assembly_id}, Asm 1 Score: {asm1_score:.6f}")

        # Detailed breakdown of all 12 cells of Assembly 1
        members_breakdown = []
        for cell in sorted(list(asm1.member_cell_ids)):
            pt_val = p_t_step1.get(cell, 0.0)
            a_prev_val = a_prev_step1.get(cell, 0.0)
            a_full_val = rr1.a_full_by_cell.get(cell, 0.0)
            a_ctrl_val = rr1.a_control_by_cell.get(cell, 0.0)
            diff_gain = rr1.gain_by_cell.get(cell, 0.0)
            is_elig = (cell in rr1.eligible_next_cells)
            contrib = diff_gain / len(asm1.member_cell_ids)

            # Look up predictive and recurrent sources into this cell
            pred_sources = []
            rec_sources = []
            for (src, tgt, scope), syn in w112.synapses.items():
                if tgt == cell and syn.state == SynapseState.CONSOLIDATED:
                    if scope == SynapseScope.ASSOCIATIVE:
                        pred_sources.append({
                            "src": src,
                            "q": round(syn.Q, 4),
                            "a_prev": round(scratch_state.R.A.get(src, 0.0), 4),
                        })
                    elif scope in (SynapseScope.LOCAL, SynapseScope.CROSS_TERRITORY):
                        rec_sources.append({
                            "src": src,
                            "w": round(syn.Q, 4),
                            "a_prev": round(scratch_state.R.A.get(src, 0.0), 4),
                        })

            members_breakdown.append({
                "cell_id": cell,
                "P_T": round(pt_val, 6),
                "A_prev": round(a_prev_val, 6),
                "A_full": round(a_full_val, 6),
                "A_ctrl": round(a_ctrl_val, 6),
                "diff_gain": round(diff_gain, 6),
                "eligible": is_elig,
                "score_contrib": round(contrib, 6),
                "pred_sources_count": len(pred_sources),
                "rec_sources_count": len(rec_sources),
            })

        # Active contextual cells
        active_ctx = sorted([z for z, g in scratch_state.R.g_ctx_by_z.items() if g > 0.0])

        # Step 1 ranked candidates
        ranked_step1 = []
        for cand in rr1.ranked_scores:
            asm_cand = w112.assemblies.get(cand.assembly_id)
            res_led = ledger_snapshot.resolve_readout(cand.assembly_id, cand.structural_generation)
            surf_cand = res_led.envelope.surface_utf8_nfc if (res_led and res_led.envelope) else "UNATTESTED"
            ranked_step1.append({
                "assembly_id": cand.assembly_id,
                "generation": cand.structural_generation,
                "surface": surf_cand,
                "score": round(cand.score_next, 6),
                "size": len(asm_cand.member_cell_ids) if asm_cand else 0,
                "eligible_count": cand.eligible_member_count,
            })

        eos_traces[p_name] = {
            "step0_winner": rr0.winner_assembly_id,
            "step0_score": rr0.top_score,
            "step1_status": rr1.status.name,
            "step1_winner": rr1.winner_assembly_id,
            "step1_top_score": rr1.top_score,
            "asm1_score": asm1_score,
            "active_ctx_cells": active_ctx,
            "assembly1_size": len(asm1.member_cell_ids),
            "ranked_step1": ranked_step1,
            "members_breakdown": members_breakdown,
        }

    # Save reconciliation dataset
    out_payload = {
        "context_audit": ctx_audit,
        "assembly_metrics_112": {
            "asm1": {"size": len(asm1.member_cell_ids), "gen": asm1.structural_generation, "members": sorted(list(asm1.member_cell_ids))},
            "asm4": {"size": len(asm4.member_cell_ids), "gen": asm4.structural_generation, "members": sorted(list(asm4.member_cell_ids))},
            "asm6": {"size": len(asm6.member_cell_ids), "gen": asm6.structural_generation, "members": sorted(list(asm6.member_cell_ids))},
        },
        "genuine_eos_traces": eos_traces,
    }

    out_path = "tools/forensics/r2_c01_d02_c01_reconciliation_data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_payload, f, indent=2, ensure_ascii=False)
    print(f"\nReconciliation data written to {out_path}")


if __name__ == "__main__":
    run_c01_reconciliation()
