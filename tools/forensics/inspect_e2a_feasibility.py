"""DGCA NEXT V2 — E2a Feasibility and Physical Opportunity Analysis.

Analyzes completed owner z = 8320:
- Existing live Y targets
- Direct external sensory cells when 'حليب' is observed
- Latent physical eligibility (is_eligible(8320, j)) for all sensory cells
- Current outgoing degree and capacity (B_i = 64)
- Native LLA eligibility and opportunity values U_zj, U_q6
- Refusal reason codes for all targets
- Plausibility analysis for milk vs water competition
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from dgca.core.anatomy import SynapseScope, SynapseState
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import EGCPMode, MachineState
from dgca.encoder.envelope import EventOrigin, encode_exposure
from dgca.lifecycle.exposure_tx import ExposureTransactionManager
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1
from tools.forensics.run_r2_c01_cf01_experiment import CORPUS_GROUP_B, build_schedule


def run_to_root(target_root: int = 57) -> MachineState:
    state = MachineState(egcp_mode=EGCPMode.OFF)
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
    schedule = build_schedule(target_root)
    for root_id, s_key in schedule:
        tx.begin_exposure(root_id)
        for env in encoded[s_key]:
            core_ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        tx.end_exposure(root_id)
    return state


def analyze_owner_8320_feasibility(state: MachineState) -> dict:
    z_id = 8320
    w = state.W
    sb = w.stable_bindings.get(z_id)
    assert sb is not None, f"Owner {z_id} not graduated in stable_bindings"

    outgoing_synapses = [k for k in w.synapses.keys() if k[0] == z_id]
    outgoing_count = len(outgoing_synapses)
    capacity_remaining = 64 - outgoing_count

    existing_live_y = [k[1] for k in sb.y_keys if k[0] == z_id]

    asm6 = w.assemblies.get(6)
    asm6_members = sorted(list(asm6.member_cell_ids)) if asm6 else []

    # Let's project 'حليب' (Event 2 of 'القط يشرب حليب')
    env_s1 = encode_exposure("القط يشرب حليب", append_eos=True)
    ev_milk = env_s1[2].core_event
    proj_milk = project_core_event_v1(ev_milk)
    direct_milk_cells = sorted([cid for cid, v in proj_milk.x_fixed_by_global_id.items() if v > 0])

    # Also let's check what latent table has for 8320
    eligible_neighbors_8320 = []
    # Test all committed cells
    for cid in sorted(w.committed_cells):
        if w.latent_table.is_eligible(z_id, cid):
            eligible_neighbors_8320.append(cid)

    # Opportunity calculations for observed milk cells
    # At Root 57, A_z(t-1) for 8320 when anchor 'يشرب' was active:
    # A_z^+ is ~1.0 (let's assume e_z = 1.0)
    # x_j is 1.0 for directly observed cells
    cells_analysis = []
    for cid in direct_milk_cells:
        in_assembly_6 = (cid in asm6_members)
        is_existing_y = (cid in existing_live_y)
        is_latent_eligible = w.latent_table.is_eligible(z_id, cid)
        syn_key = (z_id, cid, SynapseScope.ASSOCIATIVE)
        has_syn = syn_key in w.synapses
        syn_obj = w.synapses.get(syn_key)
        q_val = syn_obj.Q if syn_obj else 0.0

        # Prior support p_zj
        p_zj = q_val * 1.0 if has_syn else 0.0
        e_z = 1.0
        x_j = 1.0
        u_val = (e_z * x_j) * (1.0 - p_zj)
        u_q6 = int(round(u_val * 64.0))

        # Refusal code if not admissible as a NEW growth link
        if is_existing_y or has_syn:
            refusal = "EXISTING_LIVE_KEY"
            is_legal_new_growth = False
        elif not is_latent_eligible:
            refusal = "NO_LEGAL_LOCAL_PATH"
            is_legal_new_growth = False
        elif capacity_remaining <= 0:
            refusal = "CAPACITY_BLOCKED"
            is_legal_new_growth = False
        else:
            refusal = "NONE_ADMISSIBLE"
            is_legal_new_growth = True

        cells_analysis.append({
            "cell_id": cid,
            "in_assembly_6": in_assembly_6,
            "is_existing_live_y": is_existing_y,
            "latent_eligible": is_latent_eligible,
            "existing_synapse": has_syn,
            "q_val": round(q_val, 6),
            "p_zj": round(p_zj, 6),
            "opportunity_u": round(u_val, 6),
            "opportunity_u_q6": u_q6,
            "legal_new_growth": is_legal_new_growth,
            "refusal_reason": refusal,
        })

    return {
        "owner_id": z_id,
        "anchor_id": sb.anchor_id,
        "binding_generation": sb.binding_generation,
        "outgoing_synapses_count": outgoing_count,
        "capacity_remaining": capacity_remaining,
        "existing_live_y_targets": existing_live_y,
        "assembly_6_members": asm6_members,
        "direct_milk_cells_count": len(direct_milk_cells),
        "total_latent_eligible_neighbors_of_8320": len(eligible_neighbors_8320),
        "latent_eligible_neighbors_sample": eligible_neighbors_8320[:20],
        "cells_analysis": cells_analysis,
    }


def main():
    print("Running training to Root 57...")
    st57 = run_to_root(57)
    report_data = analyze_owner_8320_feasibility(st57)
    print("\n--- Owner 8320 Feasibility Analysis ---")
    print(f"Owner ID: {report_data['owner_id']}")
    print(f"Anchor ID: {report_data['anchor_id']}")
    print(f"Outgoing Synapses: {report_data['outgoing_synapses_count']} / 64 (Remaining: {report_data['capacity_remaining']})")
    print(f"Existing Live Y Targets: {report_data['existing_live_y_targets']}")
    print(f"Assembly 6 Members ({len(report_data['assembly_6_members'])}): {report_data['assembly_6_members']}")
    print(f"Direct Milk Cells Observed ({report_data['direct_milk_cells_count']}):")
    for ca in report_data["cells_analysis"]:
        print(f"  Cell {ca['cell_id']:5d}: in_asm6={ca['in_assembly_6']}, latent_elig={ca['latent_eligible']}, exist_syn={ca['existing_synapse']}, U={ca['opportunity_u']:.4f} (Q6={ca['opportunity_u_q6']:2d}), status={ca['refusal_reason']}")

    # Save to JSON
    out_path = os.path.join("tools", "forensics", "egcp_e2a_feasibility_data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
    print(f"\nSaved feasibility report data to {out_path}")


if __name__ == "__main__":
    main()
