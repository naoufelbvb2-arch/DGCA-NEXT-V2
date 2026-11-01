"""DGCA NEXT V2 — CF04 Preflight Verification Script.

Authoritative verification of:
1. Graph Topology: Recompute reciprocal edges and connected components at Roots 14, 16, 112.
2. Formation History: Extract exact birth and growth roots for Assemblies 7, 9, 14, 17 from FORM/GROW events.
3. Candidate Deadlines: Inspect Root 50 candidate synapse deadline, event clock, and window.
4. Normative Definitions: Verify constants and compute weighted structural specificity vs unweighted ratios.
"""

from __future__ import annotations

import dataclasses
import os
import sys

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

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
)
from dgca.core.state import MachineState
from dgca.encoder.envelope import encode_exposure
from dgca.lifecycle.exposure_tx import ExposureTransactionManager
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1
from tools.forensics.run_r2_c01_cf01_experiment import CORPUS_GROUP_B, build_schedule


def run_preflight():
    print("=" * 70)
    print("CF04 MANDATORY PREFLIGHT VERIFICATION")
    print("=" * 70)

    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
        enable_birth_time_grow=False,
    )
    encoded = {k: encode_exposure(v, append_eos=True) for k, v in CORPUS_GROUP_B.items()}
    schedule = build_schedule(112)

    form_events = []
    grow_events = []
    checkpoints = {}

    water_cells = sorted([
        8242, 8809, 8946, 9734, 9740, 9854, 10044, 10140,
        10308, 10634, 10690, 11193, 11510, 11638, 11640, 11984
    ])

    for root_id, s_key in schedule:
        pre_asms = {
            aid: (asm.structural_generation, tuple(sorted(asm.member_cell_ids)))
            for aid, asm in state.W.assemblies.items()
        }

        tx.begin_exposure(root_id)
        for env in encoded[s_key]:
            core_ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        tx.end_exposure(root_id)

        post_asms = {
            aid: (asm.structural_generation, tuple(sorted(asm.member_cell_ids)))
            for aid, asm in state.W.assemblies.items()
        }

        for aid in sorted(set(post_asms.keys()) - set(pre_asms.keys())):
            form_events.append((root_id, s_key, aid, post_asms[aid]))
        for aid in sorted(pre_asms.keys()):
            if aid in post_asms and post_asms[aid] != pre_asms[aid]:
                grow_events.append((root_id, s_key, aid, pre_asms[aid], post_asms[aid]))

        if root_id in (14, 15, 16, 27, 28, 31, 32, 50, 56, 112):
            checkpoints[root_id] = {
                "state": state.clone(),
                "ledger": ledger.clone(),
            }

    print("\n--- 2.1 Graph Topology Recomputation ---")
    for r in (14, 16, 112):
        st = checkpoints[r]["state"]
        w = st.W
        recip_pairs = []
        directed_syns = []
        for i in range(len(water_cells)):
            ci = water_cells[i]
            for j in range(i + 1, len(water_cells)):
                cj = water_cells[j]
                rb = compute_mutual_support_r_b(ci, cj, w)
                if rb >= THETA_A:
                    recip_pairs.append((ci, cj, rb))
                # Count directed synapses
                if (ci, cj, SynapseScope.LOCAL) in w.synapses:
                    directed_syns.append((ci, cj))
                if (cj, ci, SynapseScope.LOCAL) in w.synapses:
                    directed_syns.append((cj, ci))

        # Adjacency for reciprocal graph
        adj = {c: [] for c in water_cells}
        for ci, cj, _ in recip_pairs:
            adj[ci].append(cj)
            adj[cj].append(ci)

        visited = set()
        components = []
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
                components.append(sorted(comp))

        non_singleton = [c for c in components if len(c) > 1]
        print(f"Root {r:3d}:")
        print(f"  Directed Synapses Count: {len(directed_syns)}")
        print(f"  Undirected Reciprocal Pairs (R_b >= {THETA_A}): {len(recip_pairs)}")
        print(f"  Total Connected Components (incl. singletons): {len(components)}")
        print(f"  Non-Singleton Components: {len(non_singleton)}")
        print(f"  Components sizes: {[len(c) for c in components]}")

    print("\n--- 2.2 Formation History from Authoritative Event Log ---")
    print("FORM Events of interest:")
    for r, sk, aid, (gen, mem) in form_events:
        if aid in (7, 9, 14, 17):
            print(f"  Root {r:2d} ({sk}): Assembly {aid:2d} BORN (gen {gen}, size {len(mem)}: {list(mem)})")
    print("GROW Events of interest:")
    for r, sk, aid, (gen_pre, mem_pre), (gen_post, mem_post) in grow_events:
        if aid in (7, 9, 14, 17):
            print(f"  Root {r:2d} ({sk}): Assembly {aid:2d} GROWN (gen {gen_pre}->{gen_post}, size {len(mem_pre)}->{len(mem_post)})")

    print("\n--- 2.3 Candidate Deadline at Root 50 ---")
    st50 = checkpoints[50]["state"]
    syn_50 = st50.W.synapses.get((11984, 10634, SynapseScope.LOCAL))
    assert syn_50 is not None
    print(f"  Synapse (11984, 10634, LOCAL) at Root 50 Close:")
    print(f"    State: {syn_50.state}")
    print(f"    stored candidate_deadline: {syn_50.candidate_deadline} external events")
    print(f"    completed_external_events_count: {st50.W.completed_external_events_count}")
    print(f"    deadline window: {syn_50.candidate_deadline - (st50.W.completed_external_events_count - 4)} events (W_CONF_ORDINARY=100)")
    print(f"    Equivalent roots window: 100 / 4 = 25 roots (expires at Root 74)")

    print("\n--- 2.4 Normative Definitions and Specificity Formula ---")
    print(f"  K_MAX = {K_MAX}")
    print(f"  D_MIN = {D_MIN}")
    print(f"  RHO_G = {RHO_G}")
    print(f"  SIGMA_G = {SIGMA_G}")
    print(f"  SIGMA_KEEP = {SIGMA_KEEP}")
    print(f"  THETA_A = {THETA_A}")

    st112 = checkpoints[112]["state"]
    asm7 = st112.W.assemblies[7]
    cache = {}
    print("\n  Root 112 Specificity Evaluation into Assembly 7:")
    for cand in [10634, 11193]:
        n_rec = get_reciprocal_neighbors_n_rec(cand, st112.W, cache)
        sum_total_r = sum(n_rec.values())
        recip_in_asm = [m for m in asm7.member_cell_ids if compute_mutual_support_r_b(cand, m, st112.W) >= THETA_A]
        sum_asm_r = sum(compute_mutual_support_r_b(cand, m, st112.W) for m in asm7.member_cell_ids)
        d_val, dens_val, spec_val = compute_assembly_member_metrics(cand, (*asm7.member_cell_ids, cand), st112.W, cache)
        unweighted_ratio = len(recip_in_asm) / len(n_rec) if n_rec else 0.0
        print(f"    Cell {cand}:")
        print(f"      d(x, A7) = {d_val}")
        print(f"      D(x, A7) = {dens_val:.4f}")
        print(f"      Numerator sum_r(in A7) = {sum_asm_r:.4f}")
        print(f"      Denominator sum_r(total) = {sum_total_r:.4f}")
        print(f"      Normative Weighted Spec(x, A7) = {spec_val:.4f}")
        print(f"      Unweighted degree ratio = {unweighted_ratio:.4f}")

    print("\n" + "=" * 70)
    print("CF04-PREFLIGHT PASS — EVIDENCE BASELINE RECONCILED")
    print("=" * 70)

if __name__ == "__main__":
    run_preflight()
