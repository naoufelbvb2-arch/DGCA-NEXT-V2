"""DGCA NEXT V2 — R2-C01-F03 Forensic Investigation Tool.

Sensory Cross-Clique Connectivity, Synaptic Evidence & Structural Reuse Forensics.

Audits:
- F03-S01: Complete reciprocal graph audit at Roots 12, 14, 15, 16, 17, 27, 28, 31, 32, 56, 112.
- F03-S02: Component and clique topology (connected components, 3-cliques, density).
- F03-S03: GROW eligibility decomposition for candidate cells outside existing assemblies.
- F03-S04: FORM eligibility decomposition (U_t, triangle enumeration, seed assignment).
- F03-S05: Synaptic learning pathway tracing (latent table partitioning, proposal generation).
- F03-S06: CF03 evidence reconciliation (state hash diff breakdown and FP_02 rollback verification).
- F03-S07: Scientific hypothesis matrix evaluation.
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

from dgca.common.errors import StatusCode, DGCAError
from dgca.core.anatomy import Region, SynapseScope, SynapseState
from dgca.core.assembly import (
    AssemblyStatus,
    THETA_A,
    THETA_MERGE,
    D_MIN,
    RHO_G,
    SIGMA_G,
    K_MAX,
    M_MAX,
    compute_mutual_support_r_b,
    get_reciprocal_neighbors_n_rec,
    compute_assembly_member_metrics,
    check_maintain_keep_guards,
    is_eligible_assembly_member_cell,
    _live_assembly_ids_for_cell,
)
from dgca.core.generator import generate_episode
from dgca.core.readout import M_READ, THETA_READ
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import MachineState
from dgca.encoder.envelope import encode_exposure
from dgca.lifecycle.exposure_tx import ExposureTransactionManager
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1
from tests.test_r2_a01_patch2_acceptance import hash_state_snapshot, snapshot_w, snapshot_h_slow, snapshot_r
from tools.forensics.run_r2_c01_cf01_experiment import CORPUS_GROUP_B, build_schedule

AUDIT_ROOTS = [12, 14, 15, 16, 17, 27, 28, 31, 32, 56, 112]


def run_training_audit(total_roots: int = 112):
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
    )

    encoded = {
        k: encode_exposure(v, append_eos=True)
        for k, v in CORPUS_GROUP_B.items()
    }
    schedule = build_schedule(total_roots)

    checkpoints = {}
    reports = {}

    for root_id, s_key in schedule:
        tx.begin_exposure(root_id)
        for env in encoded[s_key]:
            core_ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        rep = tx.end_exposure(root_id)
        reports[root_id] = rep

        if root_id in AUDIT_ROOTS:
            checkpoints[root_id] = {
                "state": state.clone(),
                "ledger": ledger.clone(),
            }

    return checkpoints, reports, encoded


def extract_sensory_footprints(encoded: dict[str, Any]):
    footprints = {}
    # 'ماء' is token 2 in S2 ('النسر يشرب ماء')
    water_ev = encoded["S2"][2].core_event
    proj_water = project_core_event_v1(water_ev)
    footprints["ماء"] = sorted(proj_water.x_float_by_global_id.keys())

    # 'تفاح' is token 2 in S3 ('الطفل يأكل تفاح')
    apple_ev = encoded["S3"][2].core_event
    proj_apple = project_core_event_v1(apple_ev)
    footprints["تفاح"] = sorted(proj_apple.x_float_by_global_id.keys())

    # 'حليب' is token 2 in S1 ('القط يشرب حليب')
    milk_ev = encoded["S1"][2].core_event
    proj_milk = project_core_event_v1(milk_ev)
    footprints["حليب"] = sorted(proj_milk.x_float_by_global_id.keys())

    return footprints


def audit_subgraph(state: MachineState, cell_ids: list[int]):
    w = state.W
    cells = sorted(cell_ids)
    n = len(cells)

    directed_synapses = {}
    reciprocal_pairs_tuple = {}
    pair_classifications = {
        "NO_EDGE": 0,
        "CANDIDATE_ONLY": 0,
        "ONE_WAY_CONSOLIDATED": 0,
        "RECIPROCAL_BELOW_THRESHOLD": 0,
        "RECIPROCAL_STRUCTURALLY_ELIGIBLE": 0,
    }

    cache: dict[int, dict[int, float]] = {}

    for i in range(n):
        c_i = cells[i]
        for j in range(i + 1, n):
            c_j = cells[j]
            k_ij = (c_i, c_j, SynapseScope.LOCAL)
            k_ji = (c_j, c_i, SynapseScope.LOCAL)

            s_ij = w.synapses.get(k_ij)
            s_ji = w.synapses.get(k_ji)

            if s_ij:
                directed_synapses[f"{c_i}->{c_j}"] = {
                    "source": c_i,
                    "target": c_j,
                    "state": s_ij.state.name,
                    "S": round(s_ij.S, 4),
                    "conf": s_ij.external_count,
                }
            if s_ji:
                directed_synapses[f"{c_j}->{c_i}"] = {
                    "source": c_j,
                    "target": c_i,
                    "state": s_ji.state.name,
                    "S": round(s_ji.S, 4),
                    "conf": s_ji.external_count,
                }

            r_b = compute_mutual_support_r_b(c_i, c_j, w)
            reciprocal_pairs_tuple[(c_i, c_j)] = round(r_b, 4)

            # Classification
            if not s_ij and not s_ji:
                pair_classifications["NO_EDGE"] += 1
            elif (s_ij and s_ij.state == SynapseState.CANDIDATE and not s_ji) or \
                 (s_ji and s_ji.state == SynapseState.CANDIDATE and not s_ij) or \
                 (s_ij and s_ji and s_ij.state == SynapseState.CANDIDATE and s_ji.state == SynapseState.CANDIDATE):
                pair_classifications["CANDIDATE_ONLY"] += 1
            elif (s_ij and s_ij.state == SynapseState.CONSOLIDATED and (not s_ji or s_ji.state != SynapseState.CONSOLIDATED)) or \
                 (s_ji and s_ji.state == SynapseState.CONSOLIDATED and (not s_ij or s_ij.state != SynapseState.CONSOLIDATED)):
                pair_classifications["ONE_WAY_CONSOLIDATED"] += 1
            elif s_ij and s_ji and s_ij.state == SynapseState.CONSOLIDATED and s_ji.state == SynapseState.CONSOLIDATED:
                if r_b < THETA_A:
                    pair_classifications["RECIPROCAL_BELOW_THRESHOLD"] += 1
                else:
                    pair_classifications["RECIPROCAL_STRUCTURALLY_ELIGIBLE"] += 1
            else:
                pair_classifications["NO_EDGE"] += 1

    # Graph components from reciprocal edges (r_b >= THETA_A)
    adj = {c: [] for c in cells}
    for (ci, cj), r_val in reciprocal_pairs_tuple.items():
        if r_val >= THETA_A:
            adj[ci].append(cj)
            adj[cj].append(ci)

    visited = set()
    components = []
    for c in cells:
        if c not in visited:
            comp = []
            queue = [c]
            visited.add(c)
            while queue:
                curr = queue.pop(0)
                comp.append(curr)
                for neighbor in adj[curr]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            components.append(sorted(comp))

    # 3-cliques
    triangles = []
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(j + 1, n):
                ci, cj, ck = cells[i], cells[j], cells[k]
                if reciprocal_pairs_tuple.get((ci, cj), 0.0) >= THETA_A and \
                   reciprocal_pairs_tuple.get((cj, ck), 0.0) >= THETA_A and \
                   reciprocal_pairs_tuple.get((ci, ck), 0.0) >= THETA_A:
                    triangles.append([ci, cj, ck])

    total_possible_pairs = n * (n - 1) // 2
    recip_edge_count = sum(1 for r in reciprocal_pairs_tuple.values() if r >= THETA_A)
    density = recip_edge_count / total_possible_pairs if total_possible_pairs else 0.0

    reciprocal_pairs_str = {f"{ci}<->{cj}": r for (ci, cj), r in reciprocal_pairs_tuple.items()}

    return {
        "cell_count": n,
        "total_possible_pairs": total_possible_pairs,
        "directed_synapse_count": len(directed_synapses),
        "reciprocal_eligible_edge_count": recip_edge_count,
        "pair_classifications": pair_classifications,
        "components": components,
        "triangles": triangles,
        "density": round(density, 4),
        "directed_synapses": directed_synapses,
        "reciprocal_pairs": reciprocal_pairs_str,
    }


def decompose_grow_eligibility(state: MachineState, asm_id: int, external_cells: list[int]):
    w = state.W
    if asm_id not in w.assemblies:
        return {}

    asm = w.assemblies[asm_id]
    members = sorted(list(asm.member_cell_ids))
    initial_set = set(members)
    n_rec_cache: dict[int, dict[int, float]] = {}

    results = {}
    for cand in external_cells:
        if cand in initial_set:
            continue

        # Check reciprocal neighbors
        recip_neighbors = get_reciprocal_neighbors_n_rec(cand, w, n_rec_cache)
        recip_with_asm = sorted(set(recip_neighbors.keys()) & initial_set)
        sum_r = sum(compute_mutual_support_r_b(cand, j, w) for j in members)

        # Check eligibility as assembly member
        is_cell_elig = is_eligible_assembly_member_cell(cand, w)
        cur_memberships = len(_live_assembly_ids_for_cell(cand, w))

        prospective = tuple(sorted((*members, cand)))
        d_x, dens_x, spec_x = compute_assembly_member_metrics(cand, prospective, w, n_rec_cache)
        guards_ok = all(check_maintain_keep_guards(m, prospective, w, n_rec_cache) for m in members)

        # First failed condition
        failed_reason = "ELIGIBLE"
        if len(members) >= K_MAX:
            failed_reason = "K_MAX_EXCEEDED"
        elif not is_cell_elig:
            failed_reason = "CELL_NOT_ELIGIBLE"
        elif cur_memberships >= M_MAX:
            failed_reason = "M_MAX_EXCEEDED"
        elif len(recip_with_asm) < D_MIN:
            failed_reason = f"DEGREE_BELOW_D_MIN (d={len(recip_with_asm)} < {D_MIN})"
        elif dens_x < RHO_G:
            failed_reason = f"DENSITY_BELOW_RHO_G (dens={dens_x:.4f} < {RHO_G})"
        elif spec_x < SIGMA_G:
            failed_reason = f"SPEC_BELOW_SIGMA_G (spec={spec_x:.4f} < {SIGMA_G})"
        elif not guards_ok:
            failed_reason = "KEEP_GUARDS_INVALIDATED"

        results[cand] = {
            "reciprocal_neighbors_in_asm": recip_with_asm,
            "d_x": d_x,
            "dens_x": round(dens_x, 4),
            "spec_x": round(spec_x, 4),
            "sum_r": round(sum_r, 4),
            "membership_count": cur_memberships,
            "guards_ok": guards_ok,
            "verdict": failed_reason,
        }

    return results


def main():
    print("=== DGCA NEXT V2 — R2-C01-F03 Forensics Runner ===")
    checkpoints, reports, encoded = run_training_audit(112)
    footprints = extract_sensory_footprints(encoded)

    print("\n========================================================")
    print("F03-S01 & S02: SENSORY FOOTPRINT SUBGRAPH TOPOLOGY")
    print("========================================================")

    for word, cells in footprints.items():
        print(f"\n--- Subgraph Topology for '{word}' ({len(cells)} cells) ---")
        for r in AUDIT_ROOTS:
            st = checkpoints[r]["state"]
            sg = audit_subgraph(st, cells)
            print(f"  Root {r:3d}: directed_syns={sg['directed_synapse_count']:2d}, "
                  f"recip_edges={sg['reciprocal_eligible_edge_count']:2d}, "
                  f"density={sg['density']:.4f}, components={len(sg['components'])}, "
                  f"triangles={len(sg['triangles'])}")
            if r in (14, 16, 27, 31, 112):
                print(f"    Classifications: {sg['pair_classifications']}")
                print(f"    Components: {sg['components']}")

    print("\n========================================================")
    print("F03-S03: GROW ELIGIBILITY DECOMPOSITION")
    print("========================================================")
    # At Root 14 close: Inspect Assembly 7 on remaining water cells
    st14 = checkpoints[14]["state"]
    water_cells = footprints["ماء"]
    grow_asm7_r14 = decompose_grow_eligibility(st14, 7, water_cells)
    print("\nEligibility of non-member water cells for Assembly 7 at Root 14 Close:")
    for c, info in sorted(grow_asm7_r14.items()):
        print(f"  Cell {c}: verdict={info['verdict']}, d={info['d_x']}, dens={info['dens_x']}, recip_in_asm={info['reciprocal_neighbors_in_asm']}")

    # At Root 16 close: Inspect Assembly 7 on remaining water cells
    st16 = checkpoints[16]["state"]
    grow_asm7_r16 = decompose_grow_eligibility(st16, 7, water_cells)
    print("\nEligibility of non-member water cells for Assembly 7 at Root 16 Close:")
    for c, info in sorted(grow_asm7_r16.items()):
        print(f"  Cell {c}: verdict={info['verdict']}, d={info['d_x']}, dens={info['dens_x']}, recip_in_asm={info['reciprocal_neighbors_in_asm']}")

    # At Root 27 close: Inspect Assembly 14 on remaining apple cells
    st27 = checkpoints[27]["state"]
    apple_cells = footprints["تفاح"]
    grow_asm14_r27 = decompose_grow_eligibility(st27, 14, apple_cells)
    print("\nEligibility of non-member apple cells for Assembly 14 at Root 27 Close:")
    for c, info in sorted(grow_asm14_r27.items()):
        print(f"  Cell {c}: verdict={info['verdict']}, d={info['d_x']}, dens={info['dens_x']}, recip_in_asm={info['reciprocal_neighbors_in_asm']}")

    print("\n========================================================")
    print("F03-S05: SYNAPTIC LEARNING PATHWAY & LATENT PARTITIONING")
    print("========================================================")
    # Inspect top_curr_clique vs secondary_curr_clique for water event
    s2_water_ev = encoded["S2"][2]
    proj = project_core_event_v1(s2_water_ev.core_event)
    # Find active cells ordered by (-activity, cell_id)
    # At Root 14, inspect latent table eligibility across all 16 water cells
    st14 = checkpoints[14]["state"]
    w14 = st14.W
    top_clique = [8242, 9854, 11638, 11984]
    sec_clique = [c for c in water_cells if c not in top_clique]

    print(f"Top Clique (Assembly 7 footprint): {top_clique}")
    print(f"Secondary Clique (Assembly 9 footprint): {sec_clique}")

    intra_top_latent = 0
    intra_sec_latent = 0
    cross_latent = 0
    for c1 in water_cells:
        for c2 in water_cells:
            if c1 >= c2:
                continue
            el = w14.latent_table.is_eligible(c1, c2) or w14.latent_table.is_eligible(c2, c1)
            if el:
                if c1 in top_clique and c2 in top_clique:
                    intra_top_latent += 1
                elif c1 in sec_clique and c2 in sec_clique:
                    intra_sec_latent += 1
                else:
                    cross_latent += 1

    print(f"Intra-Top Latent Pairs: {intra_top_latent} / {len(top_clique)*(len(top_clique)-1)//2}")
    print(f"Intra-Secondary Latent Pairs: {intra_sec_latent} / {len(sec_clique)*(len(sec_clique)-1)//2}")
    print(f"Cross-Clique Latent Pairs: {cross_latent} / {len(top_clique)*len(sec_clique)}")

    print("\n========================================================")
    print("F03-S06: CF03 EVIDENCE RECONCILIATION")
    print("========================================================")
    # Compare Group A and Group B from CF03
    from tools.forensics.run_r2_c01_cf03_experiment import train_and_instrument_cf03
    ga = train_and_instrument_cf03("Group A", enable_birth_time_grow=False, total_roots=112)
    gb = train_and_instrument_cf03("Group B", enable_birth_time_grow=True, total_roots=112)

    sta56 = ga["checkpoints"][56]["state"]
    stb56 = gb["checkpoints"][56]["state"]
    sta112 = ga["checkpoints"][112]["state"]
    stb112 = gb["checkpoints"][112]["state"]

    print("\nState diff at Root 56:")
    print(f"  close_serial: A={sta56.W.close_serial}, B={stb56.W.close_serial}")
    for aid in sorted(set(sta56.W.assemblies.keys()) | set(stb56.W.assemblies.keys())):
        asma = sta56.W.assemblies.get(aid)
        asmb = stb56.W.assemblies.get(aid)
        if asma and asmb:
            if asma.member_cell_ids != asmb.member_cell_ids or asma.structural_generation != asmb.structural_generation:
                print(f"  Asm {aid} mismatch: A members={asma.member_cell_ids} gen={asma.structural_generation} vs B members={asmb.member_cell_ids} gen={asmb.structural_generation}")

    print("\nState diff at Root 112:")
    print(f"  close_serial: A={sta112.W.close_serial}, B={stb112.W.close_serial}")
    for aid in sorted(set(sta112.W.assemblies.keys()) | set(stb112.W.assemblies.keys())):
        asma = sta112.W.assemblies.get(aid)
        asmb = stb112.W.assemblies.get(aid)
        if asma and asmb:
            if asma.member_cell_ids != asmb.member_cell_ids or asma.structural_generation != asmb.structural_generation:
                print(f"  Asm {aid} mismatch: A members={asma.member_cell_ids} gen={asma.structural_generation} vs B members={asmb.member_cell_ids} gen={asmb.structural_generation}")

    # Transactional Rollback test with FP_02
    print("\n--- FP_02 Post-Assembly Transactional Rollback Verification ---")
    st_rb = MachineState()
    tx_rb = ExposureTransactionManager(
        st_rb,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        enable_birth_time_grow=True,
    )
    tx_rb._fault_injection_point = "FP_02"

    tx_rb.begin_exposure(14)
    for env in encoded["S2"]:
        ev = dataclasses.replace(env.core_event, exposure_id=14)
        tx_rb.process_event(ev, peripheral_envelope=env.peripheral_surface)

    rollback_ok = False
    try:
        tx_rb.end_exposure(14)
    except RuntimeError as ex:
        if "FP-02" in str(ex):
            rollback_ok = True
            print("  Successfully trapped injected fault at FP-02.")

    # Verify no partial publication into st_rb.W
    print(f"  Root 14 published in completed_roots: {14 in tx_rb.publication_view.completed_roots}")
    print(f"  State.W assemblies count: {len(st_rb.W.assemblies)}")
    print(f"  State.W high watermark: {st_rb.W.completed_roots_high_watermark}")

    # Dump full JSON dataset
    out_path = "tools/forensics/r2_c01_f03_connectivity_data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        export_data = {
            "sensory_footprints": footprints,
            "water_topology_r14": audit_subgraph(checkpoints[14]["state"], footprints["ماء"]),
            "water_topology_r16": audit_subgraph(checkpoints[16]["state"], footprints["ماء"]),
            "water_topology_r112": audit_subgraph(checkpoints[112]["state"], footprints["ماء"]),
            "apple_topology_r27": audit_subgraph(checkpoints[27]["state"], footprints["تفاح"]),
            "apple_topology_r31": audit_subgraph(checkpoints[31]["state"], footprints["تفاح"]),
            "apple_topology_r112": audit_subgraph(checkpoints[112]["state"], footprints["تفاح"]),
            "grow_asm7_r14": grow_asm7_r14,
            "grow_asm7_r16": grow_asm7_r16,
            "grow_asm14_r27": grow_asm14_r27,
        }
        json.dump(export_data, f, indent=2, ensure_ascii=False)
    print(f"\nSaved structured forensic data to {out_path}")


if __name__ == "__main__":
    main()
