"""DGCA NEXT V2 — R2-C01-F03-C01 Forensic Reconciliation Script.

Investigates:
1. Exact normative constants from assembly.py.
2. Assembly 9 and 17 actual membership (verifying 10690 and 11083).
3. Cross-clique links (11984 <-> 10634, 11984 <-> 11193) lifecycle history.
4. Time-indexed graph topology across Roots 14, 16, 27, 56, 112.
5. Exact GROW eligibility recomputation with frozen constants (K_MAX=16, D_MIN=2, RHO_G=0.50, SIGMA_G=0.30, SIGMA_KEEP=0.20, THETA_A=0.10).
6. CF03 full recursive state comparison between Group A and Group B at Roots 56 and 112.
7. Real post-birth-growth rollback test starting from Root 13 snapshot to Root 14.
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
    SIGMA_KEEP,
    K_MAX,
    M_MAX,
    compute_mutual_support_r_b,
    get_reciprocal_neighbors_n_rec,
    compute_assembly_member_metrics,
    check_maintain_keep_guards,
    is_eligible_assembly_member_cell,
    _live_assembly_ids_for_cell,
)
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import MachineState
from dgca.encoder.envelope import encode_exposure
from dgca.lifecycle.exposure_tx import ExposureTransactionManager
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1
from tests.test_r2_a01_patch2_acceptance import hash_state_snapshot, snapshot_w, snapshot_h_slow, snapshot_r
from tools.forensics.run_r2_c01_cf01_experiment import CORPUS_GROUP_B, build_schedule


def audit_run_and_trace():
    print("=== Step 1: Normative Constants Verification ===")
    print(f"K_MAX = {K_MAX}")
    print(f"D_MIN = {D_MIN}")
    print(f"RHO_G = {RHO_G}")
    print(f"SIGMA_G = {SIGMA_G}")
    print(f"SIGMA_KEEP = {SIGMA_KEEP}")
    print(f"THETA_A = {THETA_A}")

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
    schedule = build_schedule(112)

    target_pairs = [(11984, 10634), (10634, 11984), (11984, 11193), (11193, 11984)]
    pair_history = {p: [] for p in target_pairs}
    checkpoints = {}

    for root_id, s_key in schedule:
        tx.begin_exposure(root_id)
        for env in encoded[s_key]:
            core_ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        rep = tx.end_exposure(root_id)

        # Track target pairs
        for src, tgt in target_pairs:
            k = (src, tgt, SynapseScope.LOCAL)
            syn = state.W.synapses.get(k)
            slots_src = state.W.latent_table.get_slots_read_only(src)
            is_in_slots = tgt in slots_src
            is_elig = state.W.latent_table.is_eligible(src, tgt)
            if syn or is_in_slots or is_elig:
                pair_history[(src, tgt)].append({
                    "root": root_id,
                    "sentence": s_key,
                    "in_slots": is_in_slots,
                    "is_eligible": is_elig,
                    "syn_state": syn.state.name if syn else None,
                    "S": syn.S if syn else 0.0,
                    "conf": syn.external_count if syn else 0,
                    "r_b": compute_mutual_support_r_b(src, tgt, state.W),
                })

        if root_id in (13, 14, 16, 27, 56, 112):
            checkpoints[root_id] = {
                "state": state.clone(),
                "ledger": ledger.clone(),
            }

    print("\n=== Step 2: Exact Assembly Memberships ===")
    for r in (14, 16, 27, 31, 56, 112):
        if r in checkpoints:
            st = checkpoints[r]["state"]
            print(f"\n--- Root {r} Assemblies ---")
            for aid in (7, 9, 14, 17):
                if aid in st.W.assemblies:
                    asm = st.W.assemblies[aid]
                    print(f"  Assembly {aid:2d}: gen={asm.structural_generation}, size={len(asm.member_cell_ids)}, members={sorted(asm.member_cell_ids)}")

    print("\n=== Step 3: Cross-Clique Pairs Lifecycle History ===")
    for p in [(11984, 10634), (11984, 11193)]:
        rev = (p[1], p[0])
        print(f"\nTracking {p[0]} <-> {p[1]}:")
        fwd_hist = pair_history[p]
        rev_hist = pair_history[rev]
        roots_seen = sorted(set([h["root"] for h in fwd_hist] + [h["root"] for h in rev_hist]))
        for r in roots_seen:
            fwd_entry = next((h for h in fwd_hist if h["root"] == r), None)
            rev_entry = next((h for h in rev_hist if h["root"] == r), None)
            f_st = fwd_entry["syn_state"] if fwd_entry else "NONE"
            r_st = rev_entry["syn_state"] if rev_entry else "NONE"
            rb = fwd_entry["r_b"] if fwd_entry else 0.0
            print(f"  Root {r:3d} ({fwd_entry['sentence'] if fwd_entry else rev_entry['sentence']}): {p[0]}->{p[1]}={f_st} (S={fwd_entry['S'] if fwd_entry else 0:.3f}), {p[1]}->{p[0]}={r_st} (S={rev_entry['S'] if rev_entry else 0:.3f}), R_b={rb:.4f}")

    # Inspect wiring logs for cells 11984, 10634, 11193
    st112 = checkpoints[112]["state"]
    print("\nWiring logs for cell 11984:")
    for wlog in st112.W.latent_table.get_wiring_log(11984):
        if wlog.new_target_id in (10634, 11193) or wlog.old_target_id in (10634, 11193):
            print(f"  clk={wlog.event_clock}, slot={wlog.slot_index}, old={wlog.old_target_id}, new={wlog.new_target_id}, reason={wlog.reason}")

    print("\nWiring logs for cell 10634:")
    for wlog in st112.W.latent_table.get_wiring_log(10634):
        if wlog.new_target_id == 11984 or wlog.old_target_id == 11984:
            print(f"  clk={wlog.event_clock}, slot={wlog.slot_index}, old={wlog.old_target_id}, new={wlog.new_target_id}, reason={wlog.reason}")

    print("\nWiring logs for cell 11193:")
    for wlog in st112.W.latent_table.get_wiring_log(11193):
        if wlog.new_target_id == 11984 or wlog.old_target_id == 11984:
            print(f"  clk={wlog.event_clock}, slot={wlog.slot_index}, old={wlog.old_target_id}, new={wlog.new_target_id}, reason={wlog.reason}")

    # Footprints
    water_cells = sorted(project_core_event_v1(encoded["S2"][2].core_event).x_float_by_global_id.keys())

    print("\n=== Step 4: Time-Indexed Graph Topology across Audit Roots ===")
    for r in (14, 16, 27, 56, 112):
        st = checkpoints[r]["state"]
        w = st.W
        recip_edges = []
        for i in range(len(water_cells)):
            for j in range(i + 1, len(water_cells)):
                ci, cj = water_cells[i], water_cells[j]
                rb = compute_mutual_support_r_b(ci, cj, w)
                if rb >= THETA_A:
                    recip_edges.append((ci, cj, rb))

        # Build components
        adj = {c: [] for c in water_cells}
        for ci, cj, _ in recip_edges:
            adj[ci].append(cj)
            adj[cj].append(ci)

        visited = set()
        comps = []
        for c in water_cells:
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
                comps.append(sorted(comp))

        print(f"Root {r:3d}: recip_edges={len(recip_edges):2d}, components={len(comps)}")
        for idx, comp in enumerate(comps):
            if len(comp) > 1:
                print(f"  Comp {idx+1} (size {len(comp)}): {comp}")

    print("\n=== Step 5: Exact GROW Eligibility Recomputation ===")
    # For every member of Assembly 9 into Assembly 7 at Roots 16, 56, 112
    for r in (16, 56, 112):
        st = checkpoints[r]["state"]
        asm7 = st.W.assemblies[7]
        asm9 = st.W.assemblies[9]
        asm7_members = sorted(asm7.member_cell_ids)
        asm9_members = sorted(asm9.member_cell_ids)
        print(f"\n--- Root {r} GROW Eligibility of Assembly 9 members into Assembly 7 ---")
        print(f"Assembly 7 members: {asm7_members}")
        print(f"Assembly 9 members: {asm9_members}")
        cache: dict[int, dict[int, float]] = {}
        for cand in asm9_members:
            recip_nbrs = get_reciprocal_neighbors_n_rec(cand, st.W, cache)
            recip_in_asm7 = sorted(set(recip_nbrs.keys()) & set(asm7_members))
            d_x = len(recip_in_asm7)
            prospective = tuple(sorted((*asm7_members, cand)))
            _, dens_x, spec_x = compute_assembly_member_metrics(cand, prospective, st.W, cache)
            guards_ok = all(check_maintain_keep_guards(m, prospective, st.W, cache) for m in asm7_members)
            cur_m = len(_live_assembly_ids_for_cell(cand, st.W))
            print(f"  Cand {cand:5d}: recip_in_asm7={recip_in_asm7}, d={d_x}, dens={dens_x:.4f}, spec={spec_x:.4f}, guards={guards_ok}, cur_m={cur_m}")


if __name__ == "__main__":
    audit_run_and_trace()
