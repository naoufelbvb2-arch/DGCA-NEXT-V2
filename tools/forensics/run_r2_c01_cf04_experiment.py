"""DGCA NEXT V2 — R2-C01-CF04 Controlled Local Synaptic Partner Diversification Runner.

Compares:
- Group A (Frozen Baseline): enable_cross_clique_diversification=False
- Group B (Experimental Partner Diversification): enable_cross_clique_diversification=True

Both with enable_birth_time_grow=False.
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
from dgca.core.assembly import (
    K_MAX,
    D_MIN,
    RHO_G,
    SIGMA_G,
    SIGMA_KEEP,
    THETA_A,
    compute_mutual_support_r_b,
    compute_assembly_member_metrics,
    get_reciprocal_neighbors_n_rec,
    check_maintain_keep_guards,
    is_eligible_assembly_member_cell,
)
from dgca.core.generator import generate_episode
from dgca.core.readout import M_READ, THETA_READ
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import MachineState
from dgca.encoder.envelope import encode_exposure
from dgca.lifecycle.exposure_tx import ExposureTransactionManager
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1
from tests.test_r2_a01_patch2_acceptance import (
    hash_state_snapshot,
    snapshot_w,
    snapshot_h_slow,
    snapshot_r,
)
from tools.forensics.run_r2_c01_cf01_experiment import CORPUS_GROUP_B, build_schedule

CHECKPOINT_ROOTS = [14, 16, 27, 31, 56, 112]

WATER_CELLS = sorted([
    8242, 8809, 8946, 9734, 9740, 9854, 10044, 10140,
    10308, 10634, 10690, 11193, 11510, 11638, 11640, 11984
])

APPLE_CELLS = sorted([
    8513, 8961, 9334, 9468, 10181, 10363, 10457, 10616,
    10737, 11083, 11289, 11830, 12048, 12053, 12061, 12068
])


def run_experiment_group(
    group_name: str,
    enable_cross_clique_diversification: bool,
    total_roots: int = 112,
) -> dict[str, Any]:
    print(f"\n========================================================")
    print(f"RUNNING {group_name} (enable_cross_clique_diversification={enable_cross_clique_diversification})")
    print(f"========================================================")

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
    schedule = build_schedule(total_roots)

    checkpoints = {}
    history_events = []
    form_events = []
    grow_events = []

    for root_id, s_key in schedule:
        pre_asms = {
            aid: (asm.structural_generation, tuple(sorted(asm.member_cell_ids)), asm.status)
            for aid, asm in state.W.assemblies.items()
        }

        tx.begin_exposure(root_id)
        for env in encoded[s_key]:
            core_ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        rep = tx.end_exposure(root_id)

        post_asms = {
            aid: (asm.structural_generation, tuple(sorted(asm.member_cell_ids)), asm.status)
            for aid, asm in state.W.assemblies.items()
        }

        # Track FORM
        for aid in sorted(set(post_asms.keys()) - set(pre_asms.keys())):
            gen, mem, stat = post_asms[aid]
            form_events.append({
                "root_id": root_id,
                "sentence_key": s_key,
                "assembly_id": aid,
                "generation": gen,
                "members": list(mem),
            })

        # Track GROW
        for aid in sorted(pre_asms.keys()):
            if aid in post_asms and post_asms[aid] != pre_asms[aid]:
                p_gen, p_mem, _ = pre_asms[aid]
                n_gen, n_mem, _ = post_asms[aid]
                grow_events.append({
                    "root_id": root_id,
                    "sentence_key": s_key,
                    "assembly_id": aid,
                    "from_gen": p_gen,
                    "to_gen": n_gen,
                    "from_size": len(p_mem),
                    "to_size": len(n_mem),
                    "added_cells": sorted(set(n_mem) - set(p_mem)),
                })

        if root_id in CHECKPOINT_ROOTS:
            snap_w = snapshot_w(state.W)
            snap_h = snapshot_h_slow(state.H_slow)
            snap_r = snapshot_r(state.R)
            checkpoints[root_id] = {
                "state": state.clone(),
                "ledger": ledger.clone(),
                "state_hash": hash_state_snapshot({
                    "W": snap_w,
                    "H_slow": snap_h,
                    "R": snap_r,
                }),
                "snap_w": snap_w,
                "snap_h": snap_h,
                "snap_r": snap_r,
            }

    return {
        "group_name": group_name,
        "enable_cross_clique_diversification": enable_cross_clique_diversification,
        "checkpoints": checkpoints,
        "form_events": form_events,
        "grow_events": grow_events,
        "encoded_corpus": encoded,
    }


def analyze_sensory_topology(st: MachineState, cell_pool: list[int]) -> dict[str, Any]:
    w = st.W
    cells = sorted(cell_pool)
    recip_pairs = []
    directed_synapses = []
    cache = {}

    for i in range(len(cells)):
        ci = cells[i]
        for j in range(i + 1, len(cells)):
            cj = cells[j]
            rb = compute_mutual_support_r_b(ci, cj, w)
            if rb >= THETA_A:
                recip_pairs.append((ci, cj, round(rb, 4)))
            if (ci, cj, SynapseScope.LOCAL) in w.synapses:
                directed_synapses.append((ci, cj))
            if (cj, ci, SynapseScope.LOCAL) in w.synapses:
                directed_synapses.append((cj, ci))

    adj = {c: [] for c in cells}
    for ci, cj, _ in recip_pairs:
        adj[ci].append(cj)
        adj[cj].append(ci)

    visited = set()
    components = []
    for c in cells:
        if c not in visited:
            comp = []
            q = [c]
            visited.add(c)
            while q:
                curr = q.pop(0)
                comp.append(curr)
                for nbr in adj[curr]:
                    if nbr not in visited:
                        visited.add(nbr)
                        q.append(nbr)
            components.append(sorted(comp))

    return {
        "cell_count": len(cells),
        "directed_synapses_count": len(directed_synapses),
        "reciprocal_pairs_count": len(recip_pairs),
        "components_count": len(components),
        "components": components,
        "reciprocal_pairs": recip_pairs,
    }


def evaluate_assembly_grow_candidates(
    st: MachineState,
    asm_id: int,
    candidate_cells: list[int],
) -> list[dict[str, Any]]:
    asm = st.W.assemblies.get(asm_id)
    if not asm:
        return []
    members = sorted(asm.member_cell_ids)
    cache = {}
    results = []

    for cand in candidate_cells:
        if cand in members:
            continue
        recip_nbrs = get_reciprocal_neighbors_n_rec(cand, st.W, cache)
        recip_in_asm = [m for m in members if compute_mutual_support_r_b(cand, m, st.W) >= THETA_A]
        d_val = len(recip_in_asm)
        prospective = tuple(sorted((*members, cand)))
        _, dens_val, spec_val = compute_assembly_member_metrics(cand, prospective, st.W, cache)
        guards_ok = all(check_maintain_keep_guards(m, prospective, st.W, cache) for m in members)

        deg_pass = d_val >= D_MIN
        dens_pass = dens_val >= RHO_G
        spec_pass = spec_val >= SIGMA_G
        cap_pass = len(prospective) <= K_MAX
        eligible = deg_pass and dens_pass and spec_pass and guards_ok and cap_pass

        results.append({
            "cand_id": cand,
            "d_val": d_val,
            "dens_val": round(dens_val, 4),
            "spec_val": round(spec_val, 4),
            "guards_ok": guards_ok,
            "deg_pass": deg_pass,
            "dens_pass": dens_pass,
            "spec_pass": spec_pass,
            "eligible": eligible,
            "recip_in_asm": recip_in_asm,
        })
    return results


def evaluate_probes(group_data: dict[str, Any], root_id: int) -> dict[str, Any]:
    st: MachineState = group_data["checkpoints"][root_id]["state"]
    led: SurfaceReadoutLedgerV1 = group_data["checkpoints"][root_id]["ledger"]
    encoded = group_data["encoded_corpus"]

    probes = {
        "P1 (القط يشرب)": [encoded["S1"][0].core_event, encoded["S1"][1].core_event],
        "P2 (النسر يشرب)": [encoded["S2"][0].core_event, encoded["S2"][1].core_event],
        "P3 (الطفل يأكل)": [encoded["S3"][0].core_event, encoded["S3"][1].core_event],
        "P4 (الطفل يشرب)": [encoded["S4"][0].core_event, encoded["S4"][1].core_event],
    }

    results = {}
    for p_name, p_events in probes.items():
        res1 = generate_episode(st, p_events, led, max_steps=1)
        step0 = res1.steps[0]
        rr0 = step0.readout_result

        res_full = generate_episode(st, p_events, led, max_steps=4)
        trajectory = []
        for s in res_full.steps:
            if s.emitted_envelope:
                trajectory.append(s.emitted_envelope.surface_utf8_nfc)
            elif s.readout_result and s.readout_result.winner_assembly_id is not None:
                trajectory.append(f"Asm_{s.readout_result.winner_assembly_id}")
            else:
                trajectory.append(s.readout_result.status.name)

        ranked = []
        for cand in rr0.ranked_scores[:4]:
            asm_cand = st.W.assemblies.get(cand.assembly_id)
            res_led = led.resolve_readout(cand.assembly_id, cand.structural_generation)
            surf_cand = res_led.envelope.surface_utf8_nfc if (res_led and res_led.envelope) else "UNATTESTED"
            ranked.append({
                "assembly_id": cand.assembly_id,
                "generation": cand.structural_generation,
                "surface": surf_cand,
                "score": round(cand.score_next, 6),
                "size": len(asm_cand.member_cell_ids) if asm_cand else 0,
            })

        results[p_name] = {
            "first_step_stop_status": res1.stop_status.name,
            "first_step_readout_status": rr0.status.name,
            "winner_assembly_id": rr0.winner_assembly_id,
            "winner_surface": (
                led.resolve_readout(rr0.winner_assembly_id, rr0.winner_generation).envelope.surface_utf8_nfc
                if (rr0.winner_assembly_id is not None and led.resolve_readout(rr0.winner_assembly_id, rr0.winner_generation) and led.resolve_readout(rr0.winner_assembly_id, rr0.winner_generation).envelope)
                else "NONE"
            ),
            "margin": round(rr0.margin, 6),
            "ranked": ranked,
            "full_trajectory": trajectory,
            "full_stop_status": res_full.stop_status.name,
        }
    return results


def main():
    print("Beginning CF04 Benchmark Execution...")
    group_a = run_experiment_group("Group A (Baseline)", enable_cross_clique_diversification=False)
    group_b = run_experiment_group("Group B (Partner Diversification)", enable_cross_clique_diversification=True)

    print("\n========================================================")
    print("COMPARATIVE EVALUATION: GROUP A vs GROUP B")
    print("========================================================")

    # 1. State Hashes
    print("\n--- Checkpoint Hashes ---")
    for r in CHECKPOINT_ROOTS:
        h_a = group_a["checkpoints"][r]["state_hash"]
        h_b = group_b["checkpoints"][r]["state_hash"]
        print(f"Root {r:3d}: A={h_a[:12]}... | B={h_b[:12]}... | Equal={h_a == h_b}")

    # 2. Latent Wiring Logs & Diversification Activity
    print("\n--- Cross-Clique Latent Admissions in Group B ---")
    st_b_112 = group_b["checkpoints"][112]["state"]
    cross_wiring_count = 0
    cross_wiring_by_cell = {}
    for cid, entries in st_b_112.W.latent_table._wiring_logs.items():
        cross_entries = [e for e in entries if "CROSS_CLIQUE_DIVERSIFICATION" in e.reason]
        if cross_entries:
            cross_wiring_by_cell[cid] = cross_entries
            cross_wiring_count += len(cross_entries)
    print(f"Total CROSS_CLIQUE_DIVERSIFICATION wiring log entries in Group B: {cross_wiring_count}")
    print(f"Cells with cross-clique admissions: {len(cross_wiring_by_cell)}")
    for cid in sorted(cross_wiring_by_cell.keys())[:8]:
        for e in cross_wiring_by_cell[cid][:3]:
            print(f"  Cell {cid}: clk={e.event_clock}, slot={e.slot_index}, old={e.old_target_id}, new={e.new_target_id}, reason={e.reason}")

    # 3. Water Subgraph Topology Comparison
    print("\n--- Water Sensory Graph Topology ---")
    for r in [14, 16, 27, 31, 56, 112]:
        top_a = analyze_sensory_topology(group_a["checkpoints"][r]["state"], WATER_CELLS)
        top_b = analyze_sensory_topology(group_b["checkpoints"][r]["state"], WATER_CELLS)
        print(f"Root {r:3d}:")
        print(f"  Group A: recip_pairs={top_a['reciprocal_pairs_count']:2d}, directed={top_a['directed_synapses_count']:2d}, comps={top_a['components_count']}")
        print(f"  Group B: recip_pairs={top_b['reciprocal_pairs_count']:2d}, directed={top_b['directed_synapses_count']:2d}, comps={top_b['components_count']}")

    # 4. Assembly Formations
    print("\n--- Assembly Formations & Growth ---")
    print(f"Group A Form Events: {len(group_a['form_events'])}")
    print(f"Group B Form Events: {len(group_b['form_events'])}")
    print(f"Group A Grow Events: {len(group_a['grow_events'])}")
    print(f"Group B Grow Events: {len(group_b['grow_events'])}")

    print("\nAssemblies at Root 112 Close:")
    st_a_112 = group_a["checkpoints"][112]["state"]
    led_a_112 = group_a["checkpoints"][112]["ledger"]
    led_b_112 = group_b["checkpoints"][112]["ledger"]
    print("  Group A Assemblies:")
    for aid, asm in sorted(st_a_112.W.assemblies.items()):
        res = led_a_112.resolve_readout(aid, asm.structural_generation)
        surf = res.envelope.surface_utf8_nfc if (res and res.envelope) else "NONE"
        print(f"    Asm {aid:2d}: gen={asm.structural_generation}, size={len(asm.member_cell_ids)}, surf={surf}, members={sorted(list(asm.member_cell_ids))}")

    print("  Group B Assemblies:")
    for aid, asm in sorted(st_b_112.W.assemblies.items()):
        res = led_b_112.resolve_readout(aid, asm.structural_generation)
        surf = res.envelope.surface_utf8_nfc if (res and res.envelope) else "NONE"
        print(f"    Asm {aid:2d}: gen={asm.structural_generation}, size={len(asm.member_cell_ids)}, surf={surf}, members={sorted(list(asm.member_cell_ids))}")

    # 5. GROW Eligibility for Water Assemblies at Root 112
    print("\n--- GROW Eligibility for Water Assemblies at Root 112 ---")
    grow_a7 = evaluate_assembly_grow_candidates(st_a_112, 7, WATER_CELLS)
    grow_a9 = evaluate_assembly_grow_candidates(st_a_112, 9, WATER_CELLS)
    grow_b4 = evaluate_assembly_grow_candidates(st_b_112, 4, WATER_CELLS)
    print("  Group A Candidates into Assembly 7 (ماء):")
    for c in grow_a7:
        if c["d_val"] > 0:
            print(f"    Cell {c['cand_id']}: d={c['d_val']}, dens={c['dens_val']:.4f}, spec={c['spec_val']:.4f}, eligible={c['eligible']}, recip={c['recip_in_asm']}")
    print("  Group A Candidates into Assembly 9 (ماء):")
    for c in grow_a9:
        if c["d_val"] > 0:
            print(f"    Cell {c['cand_id']}: d={c['d_val']}, dens={c['dens_val']:.4f}, spec={c['spec_val']:.4f}, eligible={c['eligible']}, recip={c['recip_in_asm']}")
    print("  Group B Candidates into Assembly 4 (ماء):")
    for c in grow_b4:
        if c["d_val"] > 0:
            print(f"    Cell {c['cand_id']}: d={c['d_val']}, dens={c['dens_val']:.4f}, spec={c['spec_val']:.4f}, eligible={c['eligible']}, recip={c['recip_in_asm']}")

    # 6. Probes Evaluation
    print("\n--- Probes Evaluation at Root 112 ---")
    probes_a_112 = evaluate_probes(group_a, 112)
    probes_b_112 = evaluate_probes(group_b, 112)
    for p_name in probes_a_112:
        pa = probes_a_112[p_name]
        pb = probes_b_112[p_name]
        print(f"\n  Probe: {p_name}")
        print(f"    Group A: winner={pa['winner_surface']} (Asm {pa['winner_assembly_id']}), margin={pa['margin']:.4f}, status={pa['first_step_stop_status']}, traj={pa['full_trajectory']}")
        print(f"    Group B: winner={pb['winner_surface']} (Asm {pb['winner_assembly_id']}), margin={pb['margin']:.4f}, status={pb['first_step_stop_status']}, traj={pb['full_trajectory']}")

    # Export full experiment data
    export_data = {
        "group_a": {
            "form_events": group_a["form_events"],
            "grow_events": group_a["grow_events"],
            "state_hashes": {r: group_a["checkpoints"][r]["state_hash"] for r in CHECKPOINT_ROOTS},
            "probes_56": evaluate_probes(group_a, 56),
            "probes_112": probes_a_112,
        },
        "group_b": {
            "form_events": group_b["form_events"],
            "grow_events": group_b["grow_events"],
            "state_hashes": {r: group_b["checkpoints"][r]["state_hash"] for r in CHECKPOINT_ROOTS},
            "probes_56": evaluate_probes(group_b, 56),
            "probes_112": probes_b_112,
        },
    }
    with open("tools/forensics/r2_c01_cf04_experiment_data.json", "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)
    print("\nSaved tools/forensics/r2_c01_cf04_experiment_data.json successfully.")


if __name__ == "__main__":
    main()
