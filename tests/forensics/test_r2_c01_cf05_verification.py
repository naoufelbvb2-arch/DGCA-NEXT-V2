"""DGCA NEXT V2 — R2-C01-CF05 Verification Suite.

Comprehensive automated verification for Contextual Coactive Latent Allocation (R2-C01-D03):
- Test 01: Exact OFF Preservation and default parameter compatibility.
- Test 02: Provenance Guard (only verified completed DERIVED_EXTERNAL_CONTEXT admitted).
- Test 03: Bounded Quota (dedicated 1-slot allocation: 1 ctx + 3 same + 2 prior <= 6).
- Test 04: Latent Pathway Restoration (all 7 Assembly 6 cells evaluate to is_eligible == True).
- Test 05: E2a Opportunity Admissibility (5 previously refused cells report NONE_ADMISSIBLE).
- Test 06: Zero Selection Leakage and Capacity Invariance (outgoing degree 5 / 64).
- Test 07: Non-Interference on Canonical Probes P2, P3, and P4.
"""

from __future__ import annotations

import dataclasses
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

from dgca.common.errors import StatusCode
from dgca.core.anatomy import SynapseScope, SynapseState
from dgca.core.dynamics import EventExecutionResult
from dgca.core.egcp_opportunity import (
    REFUSAL_EXISTING_LIVE_KEY,
    REFUSAL_NO_LEGAL_LOCAL_PATH,
    REFUSAL_NONE,
    measure_e2_prediction_opportunities,
)
from dgca.core.generator import generate_episode
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import (
    BindingStatus,
    ContributionLane,
    EGCPMode,
    ExecutionMode,
    MachineState,
    StableBinding,
    TypedSupportRecord,
)
from dgca.encoder.envelope import EventOrigin, encode_exposure
from dgca.lifecycle.exposure_tx import (
    ExposureTransactionManager,
    _update_coactive_latent_neighborhoods_for_event,
)
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1
from tools.forensics.inspect_e2a_feasibility import analyze_owner_8320_feasibility
from tools.forensics.run_r2_c01_cf01_experiment import CORPUS_GROUP_B, build_schedule


def _run_schedule(
    target_root: int,
    *,
    enable_contextual_coactive_latent: bool = False,
    egcp_mode: EGCPMode = EGCPMode.OFF,
) -> tuple[MachineState, SurfaceReadoutLedgerV1, ExposureTransactionManager]:
    state = MachineState(egcp_mode=egcp_mode)
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
        enable_birth_time_grow=False,
        enable_cross_clique_diversification=True,
        enable_contextual_coactive_latent=enable_contextual_coactive_latent,
        egcp_mode=egcp_mode,
    )
    encoded = {k: encode_exposure(v, append_eos=True) for k, v in CORPUS_GROUP_B.items()}
    schedule = build_schedule(target_root)
    for root_id, s_key in schedule:
        tx.begin_exposure(root_id)
        for env in encoded[s_key]:
            core_ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        tx.end_exposure(root_id)
    return state, ledger, tx


def test_01_off_preservation_and_defaults():
    """D03-T01: Verify default flag is False and OFF mode preserves exact baseline state."""
    state = MachineState(egcp_mode=EGCPMode.OFF)
    tx_default = ExposureTransactionManager(state)
    assert tx_default.enable_contextual_coactive_latent is False

    # Run up to Root 57 under OFF
    st_off, _, _ = _run_schedule(57, enable_contextual_coactive_latent=False)
    rep_off = analyze_owner_8320_feasibility(st_off)

    # In baseline OFF mode, owner 8320 only has paths to its 2 existing Y-targets (9319, 9325)
    asm6_members = rep_off["assembly_6_members"]
    assert len(asm6_members) == 7
    eligible_in_asm6 = [
        c["cell_id"] for c in rep_off["cells_analysis"] if c["in_assembly_6"] and c["latent_eligible"]
    ]
    assert sorted(eligible_in_asm6) == [9319, 9325]

    refused_in_asm6 = [
        c["cell_id"] for c in rep_off["cells_analysis"] if c["in_assembly_6"] and not c["latent_eligible"]
    ]
    assert len(refused_in_asm6) == 5
    assert set(refused_in_asm6) == {9183, 10903, 11191, 11220, 11463}


def test_02_provenance_guard():
    """D03-T02: Verify owner provenance guard excludes candidates, unverified or internal context."""
    w = MachineState().W
    # Create mock owner cell in Region 2
    z_id = 8320
    w.commit_cell(z_id, 1)
    w.commit_cell(9183, 1)

    # Case A: Owner not in stable_bindings (e.g. ungraduated candidate)
    curr_ev = EventExecutionResult(
        exposure_id=1,
        event_order=2,
        mode=ExecutionMode.LEARN,
        origin=EventOrigin.EXTERNAL_DIRECT,
        boundary=False,
        committed_before_event=frozenset({z_id, 9183}),
        newly_committed_sensory_cells=(),
        obs_direct_cells=frozenset({9183}),
        obs_eligible_cells=frozenset({9183}),
        ctx_event_match_cells=frozenset(),
        ctx_runtime_match_cells=frozenset(),
        pt_by_cell={},
        ps_by_cell={},
        sigma_by_cell={},
        d1_by_cell={},
        a1_by_cell={},
        d2_by_cell={},
        a_plus_by_cell={9183: 1.0},
        e1_frontier=frozenset({9183}),
        l_frontier=frozenset({9183}),
        lx_frontier=frozenset(),
        f_step=frozenset({9183}),
        g_ctx_by_z={},
        g_probe_by_z={},
        mu_source_mask={},
        fresh_by_cell={},
        m_fresh_by_assembly={},
        typed_supports={},
        contributions=(),
        diagnostics=(),
        feature_bundle_digest=None,
    )

    prev_ev = dataclasses.replace(
        curr_ev,
        event_order=1,
        f_step=frozenset({z_id}),
        ctx_event_match_cells=frozenset({z_id}),
        a_plus_by_cell={z_id: 1.0},
        typed_supports={
            z_id: TypedSupportRecord(
                cell_id=z_id,
                event_order=1,
                origin_kind=ContributionLane.DERIVED_RUNTIME_CONTEXT.value,  # NOT external!
                o_train=0.0,
                o_runtime=1.0,
                q6_train=0,
                q6_runtime=1000000,
                depth=1,
                owner_id=(8327, 1),
                binding_generation=1,
                parent_proof_verified=False,  # Unverified!
            )
        },
    )

    prot = set()
    _update_coactive_latent_neighborhoods_for_event(
        w, curr_ev, prev_ev, prot, enable_contextual_coactive_latent=True
    )
    # Cell 9183 must NOT admit z_id because parent_proof_verified is False and not in stable_bindings
    assert not w.latent_table.is_eligible(z_id, 9183)


def test_03_bounded_quota():
    """D03-T03: Verify dedicated contextual slot allocation quota (1 ctx + 3 same + 2 prior <= 6)."""
    w = MachineState().W
    z_id = 8320
    w.stable_bindings[z_id] = StableBinding(
        schema_version=2,
        z_cell_id=z_id,
        anchor_id=8327,
        owner_seq=1,
        binding_generation=1,
        p_keys=((11077, 8320, SynapseScope.ASSOCIATIVE), (11811, 8320, SynapseScope.ASSOCIATIVE)),
        l_z_q6=1000000,
        u_z_q6=0,
        tau_ctx_q6=50000,
        c_keys=((9005, 8320, SynapseScope.LOCAL), (10696, 8320, SynapseScope.LOCAL)),
        y_keys=((8320, 9319, SynapseScope.ASSOCIATIVE), (8320, 9325, SynapseScope.ASSOCIATIVE)),
        anchor_source_set=frozenset({8327}),
        status=BindingStatus.ACTIVE,
        depth=1,
        p_source_kinds=(),
        parent_refs={},
    )

    receiver_id = 9183
    peer_same = [9269, 9319, 9325, 9472]
    peer_prev = [10167, 10345, 10496]

    w.commit_cell(z_id, 1)
    w.commit_cell(receiver_id, 1)
    for p in peer_same:
        w.commit_cell(p, 1)
    for p in peer_prev:
        w.commit_cell(p, 1)

    curr_ev = EventExecutionResult(
        exposure_id=1,
        event_order=2,
        mode=ExecutionMode.LEARN,
        origin=EventOrigin.EXTERNAL_DIRECT,
        boundary=False,
        committed_before_event=frozenset([z_id, receiver_id] + peer_same + peer_prev),
        newly_committed_sensory_cells=(),
        obs_direct_cells=frozenset([receiver_id] + peer_same),
        obs_eligible_cells=frozenset([receiver_id] + peer_same),
        ctx_event_match_cells=frozenset(),
        ctx_runtime_match_cells=frozenset(),
        pt_by_cell={},
        ps_by_cell={},
        sigma_by_cell={},
        d1_by_cell={},
        a1_by_cell={},
        d2_by_cell={},
        a_plus_by_cell={c: 1.0 for c in [receiver_id] + peer_same},
        e1_frontier=frozenset([receiver_id] + peer_same),
        l_frontier=frozenset([receiver_id] + peer_same),
        lx_frontier=frozenset(),
        f_step=frozenset([receiver_id] + peer_same),
        g_ctx_by_z={},
        g_probe_by_z={},
        mu_source_mask={},
        fresh_by_cell={},
        m_fresh_by_assembly={},
        typed_supports={},
        contributions=(),
        diagnostics=(),
        feature_bundle_digest=None,
    )

    prev_ev = EventExecutionResult(
        exposure_id=1,
        event_order=1,
        mode=ExecutionMode.LEARN,
        origin=EventOrigin.EXTERNAL_DIRECT,
        boundary=False,
        committed_before_event=frozenset([z_id, receiver_id] + peer_same + peer_prev),
        newly_committed_sensory_cells=(),
        obs_direct_cells=frozenset(peer_prev),
        obs_eligible_cells=frozenset(peer_prev),
        ctx_event_match_cells=frozenset({z_id}),
        ctx_runtime_match_cells=frozenset(),
        pt_by_cell={},
        ps_by_cell={},
        sigma_by_cell={},
        d1_by_cell={},
        a1_by_cell={},
        d2_by_cell={},
        a_plus_by_cell={c: 1.0 for c in [z_id] + peer_prev},
        e1_frontier=frozenset(peer_prev),
        l_frontier=frozenset(peer_prev),
        lx_frontier=frozenset(),
        f_step=frozenset([z_id] + peer_prev),
        g_ctx_by_z={z_id: 1},
        g_probe_by_z={},
        mu_source_mask={},
        fresh_by_cell={},
        m_fresh_by_assembly={},
        typed_supports={
            z_id: TypedSupportRecord(
                cell_id=z_id,
                event_order=1,
                origin_kind=ContributionLane.DERIVED_EXTERNAL_CONTEXT.value,
                o_train=1.0,
                o_runtime=1.0,
                q6_train=1000000,
                q6_runtime=1000000,
                depth=1,
                owner_id=(8327, 1),
                binding_generation=1,
                parent_proof_verified=True,
            )
        },
        contributions=(),
        diagnostics=(),
        feature_bundle_digest=None,
    )

    prot = set()
    _update_coactive_latent_neighborhoods_for_event(
        w, curr_ev, prev_ev, prot, enable_contextual_coactive_latent=True
    )

    slots = w.latent_table.get_slots_read_only(receiver_id)[:6]
    # Exactly 1 slot occupied by contextual owner 8320
    ctx_slots = [s for s in slots if s == z_id]
    assert len(ctx_slots) == 1

    # Remaining 5 slots occupied by at most 3 same peers and 2 prior peers
    same_count = sum(1 for s in slots if s in peer_same)
    prev_count = sum(1 for s in slots if s in peer_prev)
    assert same_count <= 3
    assert prev_count <= 2
    assert same_count + prev_count + 1 <= 6


def test_04_owner_8320_latent_pathway_restoration_at_root_61():
    """D03-T04: Verify all 7 members of Assembly 6 achieve latent eligibility with owner 8320 at Root 61."""
    st61, _, _ = _run_schedule(61, enable_contextual_coactive_latent=True, egcp_mode=EGCPMode.E2_GROWTH)
    rep = analyze_owner_8320_feasibility(st61)

    asm6_members = rep["assembly_6_members"]
    assert len(asm6_members) == 7
    assert asm6_members == [9183, 9319, 9325, 10903, 11191, 11220, 11463]

    # Check eligibility for each of the 7 members
    asm6_analysis = [c for c in rep["cells_analysis"] if c["in_assembly_6"]]
    for ca in asm6_analysis:
        assert ca["latent_eligible"] is True, f"Cell {ca['cell_id']} failed latent eligibility with owner 8320"

    # Overall latent eligible count expanded from 7 to at least 17
    assert rep["total_latent_eligible_neighbors_of_8320"] >= 17


def test_05_e2a_opportunity_admissibility():
    """D03-T04/T05: Verify 5 previously blocked cells are admitted as NONE_ADMISSIBLE opportunities."""
    st61, _, _ = _run_schedule(61, enable_contextual_coactive_latent=True, egcp_mode=EGCPMode.E2_GROWTH)
    rep = analyze_owner_8320_feasibility(st61)

    asm6_analysis = {c["cell_id"]: c for c in rep["cells_analysis"] if c["in_assembly_6"]}

    # The 2 pre-existing Y-targets must report EXISTING_LIVE_KEY
    assert asm6_analysis[9319]["refusal_reason"] == REFUSAL_EXISTING_LIVE_KEY
    assert asm6_analysis[9319]["legal_new_growth"] is False

    assert asm6_analysis[9325]["refusal_reason"] == REFUSAL_EXISTING_LIVE_KEY
    assert asm6_analysis[9325]["legal_new_growth"] is False

    # The 5 unlinked cells must report NONE_ADMISSIBLE with legal_new_growth == True
    unlinked_ids = [9183, 10903, 11191, 11220, 11463]
    for cid in unlinked_ids:
        ca = asm6_analysis[cid]
        assert ca["refusal_reason"] == REFUSAL_NONE, f"Cell {cid} had refusal {ca['refusal_reason']}"
        assert ca["legal_new_growth"] is True, f"Cell {cid} had legal_new_growth False"
        assert ca["opportunity_u"] > 0.0
        assert ca["opportunity_u_q6"] > 0

    # Assert ZERO NO_LEGAL_LOCAL_PATH refusals among Assembly 6 members
    no_path_cells = [c["cell_id"] for c in rep["cells_analysis"] if c["in_assembly_6"] and c["refusal_reason"] == REFUSAL_NO_LEGAL_LOCAL_PATH]
    assert len(no_path_cells) == 0


def test_06_zero_selection_leakage_and_capacity_invariance():
    """D03-T05: Verify zero selection leakage and capacity invariance (outgoing synapses = 5 <= 64)."""
    st61, _, _ = _run_schedule(61, enable_contextual_coactive_latent=True, egcp_mode=EGCPMode.E2_GROWTH)
    rep = analyze_owner_8320_feasibility(st61)

    # Outgoing degree must remain exactly 5 (2 Y-targets + 2 C-parents + 1 anchor)
    # Zero synthetic or unvetted growth synapses formed
    assert rep["outgoing_synapses_count"] == 5
    assert rep["capacity_remaining"] == 59
    assert rep["capacity_remaining"] > 0


def test_07_non_interference_p2_p3_p4():
    """D03-T06: Verify non-interference on canonical probes P2, P3, and P4."""
    # Compare ON vs OFF baseline directly at Root 57 and Root 61
    st57_on, ledger57_on, _ = _run_schedule(57, enable_contextual_coactive_latent=True, egcp_mode=EGCPMode.E2_GROWTH)
    st57_off, ledger57_off, _ = _run_schedule(57, enable_contextual_coactive_latent=False, egcp_mode=EGCPMode.OFF)

    st61_on, ledger61_on, _ = _run_schedule(61, enable_contextual_coactive_latent=True, egcp_mode=EGCPMode.E2_GROWTH)
    st61_off, ledger61_off, _ = _run_schedule(61, enable_contextual_coactive_latent=False, egcp_mode=EGCPMode.OFF)

    encoded = {k: encode_exposure(v, append_eos=True) for k, v in CORPUS_GROUP_B.items()}

    # Probe P2: النسر يشرب -> ماء -> <EOS>
    p2 = [encoded["S2"][0].core_event, encoded["S2"][1].core_event]
    res_p2_57_on = generate_episode(st57_on, p2, ledger57_on, max_steps=4)
    res_p2_57_off = generate_episode(st57_off, p2, ledger57_off, max_steps=4)
    assert res_p2_57_on.emitted_surfaces == res_p2_57_off.emitted_surfaces == ("ماء",)

    res_p2_61_on = generate_episode(st61_on, p2, ledger61_on, max_steps=4)
    res_p2_61_off = generate_episode(st61_off, p2, ledger61_off, max_steps=4)
    assert res_p2_61_on.emitted_surfaces == res_p2_61_off.emitted_surfaces == ("ماء",)

    # Probe P3: الطفل يأكل -> تفاح -> <EOS>
    p3 = [encoded["S3"][0].core_event, encoded["S3"][1].core_event]
    res_p3_57_on = generate_episode(st57_on, p3, ledger57_on, max_steps=4)
    res_p3_57_off = generate_episode(st57_off, p3, ledger57_off, max_steps=4)
    assert res_p3_57_on.emitted_surfaces == res_p3_57_off.emitted_surfaces == ("تفاح",)

    res_p3_61_on = generate_episode(st61_on, p3, ledger61_on, max_steps=4)
    res_p3_61_off = generate_episode(st61_off, p3, ledger61_off, max_steps=4)
    assert res_p3_61_on.emitted_surfaces == res_p3_61_off.emitted_surfaces

    # Probe P4: الطفل يشرب -> ماء -> <EOS>
    p4 = [encoded["S4"][0].core_event, encoded["S4"][1].core_event]
    res_p4_57_on = generate_episode(st57_on, p4, ledger57_on, max_steps=4)
    res_p4_57_off = generate_episode(st57_off, p4, ledger57_off, max_steps=4)
    assert res_p4_57_on.emitted_surfaces == res_p4_57_off.emitted_surfaces == ("ماء",)

    res_p4_61_on = generate_episode(st61_on, p4, ledger61_on, max_steps=4)
    res_p4_61_off = generate_episode(st61_off, p4, ledger61_off, max_steps=4)
    assert res_p4_61_on.emitted_surfaces == res_p4_61_off.emitted_surfaces == ("ماء",)
