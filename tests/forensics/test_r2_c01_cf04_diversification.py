"""DGCA NEXT V2 — R2-C01-CF04 Controlled Local Partner Diversification Tests.

Verifies:
- Test 1: Preflight consistency assertions (reciprocal counts 6, 24, 39; formation roots 14, 15, 16, 27, 28, 31).
- Test 2: Default-off invariant (enable_cross_clique_diversification=False produces 100% byte-for-byte identical state hashes to frozen baseline).
- Test 3: Group B cross-clique admissions occur lawfully via CROSS_CLIQUE_DIVERSIFICATION without exceeding slot capacity (max 6) or violating protected live links, eliminating duplicate assembly formation.
- Test 4: Pre-trained post-assembly transactional rollback test (FP_02) under Group B to verify zero shadow leakage.
"""

from __future__ import annotations

import dataclasses
import os
import sys
from typing import Any
import pytest

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

from dgca.core.anatomy import SynapseScope, SynapseState
from dgca.core.assembly import (
    K_MAX,
    D_MIN,
    RHO_G,
    SIGMA_G,
    SIGMA_KEEP,
    THETA_A,
    compute_mutual_support_r_b,
)
from dgca.core.latent_index import COACTIVE_INTRA_SLOTS
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


def _count_reciprocal_pairs_and_components(w, cells):
    recip = set()
    adj = {c: set() for c in cells}
    for i in range(len(cells)):
        ci = cells[i]
        for j in range(i + 1, len(cells)):
            cj = cells[j]
            rb = compute_mutual_support_r_b(ci, cj, w)
            if rb >= THETA_A:
                recip.add((min(ci, cj), max(ci, cj)))
                adj[ci].add(cj)
                adj[cj].add(ci)

    visited = set()
    comps = 0
    for c in cells:
        if c not in visited:
            comps += 1
            queue = [c]
            visited.add(c)
            while queue:
                curr = queue.pop()
                for neighbor in adj[curr]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
    return len(recip), comps


def test_1_preflight_baseline_reconciliation():
    """Verify preflight topological recomputations and formation chronology on canonical baseline."""
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
        enable_birth_time_grow=False,
        enable_cross_clique_diversification=False,
    )
    encoded = {k: encode_exposure(v, append_eos=True) for k, v in CORPUS_GROUP_B.items()}
    schedule = build_schedule(112)

    topologies = {}
    for root_id, s_key in schedule:
        tx.begin_exposure(root_id)
        for env in encoded[s_key]:
            core_ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        tx.end_exposure(root_id)

        if root_id in [14, 16, 112]:
            rp, comps = _count_reciprocal_pairs_and_components(state.W, WATER_CELLS)
            topologies[root_id] = (rp, comps)

    # 1. Undirected reciprocal edge counts and formal component counts (including singletons)
    assert topologies[14] == (6, 13), f"Expected (6, 13) at Root 14, got {topologies[14]}"
    assert topologies[16] == (24, 6), f"Expected (24, 6) at Root 16, got {topologies[16]}"
    assert topologies[112] == (39, 1), f"Expected (39, 1) at Root 112, got {topologies[112]}"

    # 2. Historical formation chronology
    w = state.W
    # Asm 7 born at Root 14, grew at Root 15 to size 4
    assert 7 in w.assemblies
    assert sorted(list(w.assemblies[7].member_cell_ids)) == [8242, 9854, 11638, 11984]
    assert w.assemblies[7].structural_generation == 2

    # Asm 9 born at Root 16
    assert 9 in w.assemblies
    assert sorted(list(w.assemblies[9].member_cell_ids)) == [8809, 9734, 9740, 10044, 10308, 10634, 11193]
    assert w.assemblies[9].structural_generation == 5

    # Asm 14 born at Root 27, grew at Root 28 to size 4
    assert 14 in w.assemblies
    assert sorted(list(w.assemblies[14].member_cell_ids)) == [9334, 9468, 10457, 11289]
    assert w.assemblies[14].structural_generation == 2

    # Asm 17 born at Root 31
    assert 17 in w.assemblies
    assert sorted(list(w.assemblies[17].member_cell_ids)) == [8513, 8961, 10181, 10363, 10616, 10737, 11830]
    assert w.assemblies[17].structural_generation == 5


def test_2_default_off_invariant():
    """Verify enable_cross_clique_diversification=False produces 100% byte-for-byte identical state hashes."""
    # Baseline run
    state_a = MachineState()
    ledger_a = SurfaceReadoutLedgerV1()
    tx_a = ExposureTransactionManager(
        state_a,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger_a,
        enable_birth_time_grow=False,
        enable_cross_clique_diversification=False,
    )
    encoded = {k: encode_exposure(v, append_eos=True) for k, v in CORPUS_GROUP_B.items()}
    schedule = build_schedule(112)

    hashes_a = {}
    for root_id, s_key in schedule:
        tx_a.begin_exposure(root_id)
        for env in encoded[s_key]:
            ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx_a.process_event(ev, peripheral_envelope=env.peripheral_surface)
        tx_a.end_exposure(root_id)

        if root_id in CHECKPOINT_ROOTS:
            hashes_a[root_id] = hash_state_snapshot({
                "W": snapshot_w(state_a.W),
                "H_slow": snapshot_h_slow(state_a.H_slow),
                "R": snapshot_r(state_a.R),
            })

    # Reference hashes from frozen baseline
    EXPECTED_HASHES = {
        14: "e8ed6ba87ecf13513d738014941c872d8103dc047ace218e5055d64ae3c46196",
        16: "64eac0897b144ec04e1e7ade80441f9dc71c0971beb76d8466f665e37a9f03f8",
        27: "e8c70c791cdb689b48d291ff0dd9a14d223545385b43e7a97fb45ceae6370eb7",
        31: "fe3e013f325e49c094edc7b92c585a182f095e825086b928ffd1e7a4b11d115a",
        56: "19f3a4a24dd1145cf59d317c92f72d79c8207369e9109b61fa00645cf573129d",
        112: "56cc7b15a600fa7caaa51c0d1aeeb1e903da04cad3fc5e028724a104284857f0",
    }
    for r in CHECKPOINT_ROOTS:
        assert hashes_a[r] == EXPECTED_HASHES[r], f"Hash mismatch at Root {r}: got {hashes_a[r]}"


def test_3_group_b_partner_diversification_structural_effects():
    """Verify Group B diversification admissions, slot bounds, and duplicate assembly elimination."""
    state_b = MachineState()
    ledger_b = SurfaceReadoutLedgerV1()
    tx_b = ExposureTransactionManager(
        state_b,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger_b,
        enable_birth_time_grow=False,
        enable_cross_clique_diversification=True,
    )
    encoded = {k: encode_exposure(v, append_eos=True) for k, v in CORPUS_GROUP_B.items()}
    schedule = build_schedule(112)

    for root_id, s_key in schedule:
        tx_b.begin_exposure(root_id)
        for env in encoded[s_key]:
            ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx_b.process_event(ev, peripheral_envelope=env.peripheral_surface)
        tx_b.end_exposure(root_id)

    w = state_b.W

    # 1. Total assemblies formed reduced from 17 to 11
    assert len(w.assemblies) == 11, f"Expected exactly 11 assemblies in Group B, got {len(w.assemblies)}"

    # 2. Water assembly: ONLY ONE assembly (Assembly 4), containing 8809 alongside primary clique
    water_asms = [
        aid for aid, a in w.assemblies.items()
        if ledger_b.resolve_readout(aid, a.structural_generation)
        and ledger_b.resolve_readout(aid, a.structural_generation).envelope
        and ledger_b.resolve_readout(aid, a.structural_generation).envelope.surface_utf8_nfc == "ماء"
    ]
    assert water_asms == [4], f"Expected only Assembly 4 for 'ماء', got {water_asms}"
    asm4 = w.assemblies[4]
    assert sorted(list(asm4.member_cell_ids)) == [8242, 8809, 9854, 11638, 11984]
    assert asm4.structural_generation == 3

    # 3. Duplicate water assembly 9 was never formed
    assert 9 not in w.assemblies or ledger_b.resolve_readout(9, w.assemblies[9].structural_generation).envelope.surface_utf8_nfc != "ماء"

    # 4. Latent table contains lawful cross-clique entries
    cross_entries = [
        entry
        for cid in w.committed_cells
        for entry in w.latent_table.get_wiring_log(cid)
        if "CROSS_CLIQUE_DIVERSIFICATION" in entry.reason
    ]
    assert len(cross_entries) > 0, "Expected cross-clique diversification wiring log entries!"

    # 5. Intra slot capacity strictly bounded (slots 0..5 in 24-slot array)
    for cid in w.committed_cells:
        slots = w.latent_table.get_slots_read_only(cid)
        assert len(slots) == 24
        # Assert non-empty coactive intra slots count <= 6
        coactive_count = sum(1 for idx in COACTIVE_INTRA_SLOTS if slots[idx] is not None)
        assert coactive_count <= 6, f"Cell {cid} has {coactive_count} coactive intra slots (max 6)!"

    # 6. Pinned / protected synapses were never evicted
    for aid, asm in w.assemblies.items():
        for m in asm.member_cell_ids:
            for p in w.get_protected_bidirectional_neighbors(m):
                assert w.latent_table.is_eligible(m, p), f"Protected neighbor {p} of assembly member {m} lost eligibility!"


def test_4_transactional_rollback_fp02_under_group_b():
    """Verify FP_02 abort under Group B causes zero shadow state leakage into active MachineState."""
    state = MachineState()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        enable_birth_time_grow=False,
        enable_cross_clique_diversification=True,
    )
    encoded = {k: encode_exposure(v, append_eos=True) for k, v in CORPUS_GROUP_B.items()}
    schedule = build_schedule(14)

    # Train authentic roots 1..13
    for r, s_key in schedule[:13]:
        tx.begin_exposure(r)
        for env in encoded[s_key]:
            ev = dataclasses.replace(env.core_event, exposure_id=r)
            tx.process_event(ev, peripheral_envelope=env.peripheral_surface)
        tx.end_exposure(r)

    pre_asms = {
        aid: (asm.structural_generation, tuple(sorted(asm.member_cell_ids)))
        for aid, asm in state.W.assemblies.items()
    }
    pre_syns_count = len(state.W.synapses)
    pre_slots = {
        cid: state.W.latent_table.get_slots_read_only(cid)
        for cid in state.W.committed_cells
    }

    # Set fault injection point at FP_02
    tx._fault_injection_point = "FP_02"

    # Execute Root 14
    tx.begin_exposure(14)
    s_key = schedule[13][1]
    for env in encoded[s_key]:
        ev = dataclasses.replace(env.core_event, exposure_id=14)
        tx.process_event(ev, peripheral_envelope=env.peripheral_surface)

    # FP_02 fires during end_exposure
    with pytest.raises(RuntimeError, match="FP-02"):
        tx.end_exposure(14)

    # Rollback abort
    tx.abort_exposure(14)

    # Assert active state is 100% restored
    post_asms = {
        aid: (asm.structural_generation, tuple(sorted(asm.member_cell_ids)))
        for aid, asm in state.W.assemblies.items()
    }
    assert post_asms == pre_asms, "Active assemblies mutated despite FP_02 abort!"
    assert len(state.W.synapses) == pre_syns_count, "Synapses count mutated despite FP_02 abort!"
    post_slots = {
        cid: state.W.latent_table.get_slots_read_only(cid)
        for cid in state.W.committed_cells
    }
    assert post_slots == pre_slots, "Latent slots mutated despite FP_02 abort!"
    assert 14 not in tx.publication_view.completed_roots
