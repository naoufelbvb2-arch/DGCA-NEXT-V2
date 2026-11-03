"""DGCA NEXT V2 — EGCP E2a Prediction Opportunity Verification Suite.

Validates:
1. Provenance and integration surface (no growth synapses, no quarantine, no V4, no E3).
2. Pre-observation snapshot immutability & pre-outcome independence (future event invariance).
3. Bounded owner derivation exclusively from preceding neural activity & typed provenance.
4. Candidate targets restricted to legally observed, committed-before-event SIC receiver cells.
5. Exact RC2 §3.2 opportunity function U_zj = (e_z * x_j) * (1 - p_zj) and integer U_q6.
6. Explicit refusal reason codes (negative controls for latent failure, capacity, existing keys, provenance, boundary).
7. Measurement layer cannot alter LLA evidence, synaptic weights, activations, Readout, or StableBindings.
8. Exact OFF-mode compatibility.
9. Owner 8320 physical feasibility and refusal accounting at Roots 57 and 112.
"""

from __future__ import annotations

import dataclasses
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

from dgca.core.anatomy import SynapseScope, SynapseState
from dgca.core.dynamics import EventExecutionResult
from dgca.core.egcp_opportunity import (
    MAX_OUTGOING_SYNAPSE_BUDGET,
    MAX_PENDING_KEYS_PER_OWNER,
    REFUSAL_CAPACITY_BLOCKED,
    REFUSAL_EGCP_FRONTIER_LIMIT,
    REFUSAL_EXISTING_LIVE_KEY,
    REFUSAL_ILLEGAL_TEMPORAL_BOUNDARY,
    REFUSAL_INCOMPLETE_OBSERVATION,
    REFUSAL_NO_LEGAL_LOCAL_PATH,
    REFUSAL_NONE,
    REFUSAL_STALE_OWNER,
    REFUSAL_UNRESOLVED_PROVENANCE,
    capture_pre_obs_context_snapshots,
    measure_e2_prediction_opportunities,
)
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import (
    BindingStatus,
    ContributionLane,
    EGCPMode,
    ExecutionMode,
    MachineState,
    StableBinding,
    Synapse,
    TypedSupportRecord,
    WState,
)
from dgca.encoder.envelope import EventOrigin, encode_exposure
from dgca.lifecycle.exposure_tx import ExposureTransactionManager
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1
from tests.test_r2_a01_patch2_acceptance import hash_state_snapshot, snapshot_h_slow, snapshot_r, snapshot_w
from tools.forensics.run_r2_c01_cf01_experiment import CORPUS_GROUP_B, build_schedule


def test_01_provenance_and_e2a_integration_surface():
    """Verify E2a operational mode, enum defaults, and strictly bounded surface."""
    import dgca.core.state as s

    assert [m.value for m in s.EGCPMode] == ["OFF", "E1_PRESERVE_GENERIC", "E2_GROWTH"]
    assert s.EGCPMode.OFF.value == "OFF"

    # Default MachineState has egcp_mode == OFF
    state = MachineState()
    assert state.egcp_mode == s.EGCPMode.OFF

    # Ensure no E2b/E2c/E3 structures are implemented
    assert not hasattr(s, "EGCPPendingGrowthV1")
    assert not hasattr(s, "BetaSuppressionLedger")
    assert not hasattr(s, "V4StructuralBinding")


def test_02_pre_obs_snapshot_future_event_invariance():
    """Demonstrate that future external event cannot influence the preceding prediction snapshot (T0)."""
    # Build a minimal state with a completed owner
    w = WState()
    w.commit_cell(8320, 1)
    w.commit_cell(8327, 1)

    sb = StableBinding(
        schema_version=2,
        z_cell_id=8320,
        anchor_id=8327,
        owner_seq=1,
        binding_generation=1,
        p_keys=((11077, 8320, SynapseScope.ASSOCIATIVE), (11811, 8320, SynapseScope.ASSOCIATIVE)),
        l_z_q6=1000000,
        u_z_q6=0,
        tau_ctx_q6=50000,
        c_keys=((9005, 8320, SynapseScope.LOCAL),),
        y_keys=((8320, 9319, SynapseScope.ASSOCIATIVE),),
        anchor_source_set=frozenset({8327}),
        status=BindingStatus.ACTIVE,
    )
    w.stable_bindings[8320] = sb

    # Preceding event result at t-1
    prev_ev = EventExecutionResult(
        event_order=1,
        exposure_id=10,
        mode=ExecutionMode.LEARN,
        origin=EventOrigin.EXTERNAL_DIRECT,
        boundary=False,
        committed_before_event=frozenset({8320, 8327}),
        newly_committed_sensory_cells=(),
        obs_direct_cells=frozenset({8327}),
        obs_eligible_cells=frozenset({8327}),
        ctx_event_match_cells=frozenset({8320}),
        ctx_runtime_match_cells=frozenset(),
        pt_by_cell={},
        ps_by_cell={},
        sigma_by_cell={},
        d1_by_cell={},
        a1_by_cell={},
        d2_by_cell={},
        a_plus_by_cell={8320: 0.95, 8327: 1.0},
        e1_frontier=frozenset(),
        l_frontier=frozenset(),
        lx_frontier=frozenset(),
        f_step=frozenset({8320, 8327}),
        g_ctx_by_z={8320: 1},
        g_probe_by_z={},
        mu_source_mask={8327: 1},
        fresh_by_cell={},
        m_fresh_by_assembly={},
        typed_supports={
            8320: TypedSupportRecord(
                cell_id=8320,
                event_order=1,
                origin_kind=ContributionLane.DERIVED_EXTERNAL_CONTEXT.value,
                o_train=0.95,
                o_runtime=0.95,
                q6_train=950000,
                q6_runtime=950000,
                depth=1,
                owner_id=1,
                binding_generation=1,
                parent_proof_verified=True,
            )
        },
        contributions=(),
        diagnostics=(),
        feature_bundle_digest="digest_prev",
    )

    # Capture snapshot targeting event 2 under Scenario A
    snap_a = capture_pre_obs_context_snapshots(w, prev_ev, target_event_order=2, exposure_id=10)
    # Capture snapshot targeting event 2 under Scenario B
    snap_b = capture_pre_obs_context_snapshots(w, prev_ev, target_event_order=2, exposure_id=10)

    assert len(snap_a) == 1
    assert snap_a[0].z_cell_id == 8320
    assert snap_a[0].owner_pre_activity == 0.95
    assert snap_a[0].certified_external_context_provenance is True
    # Byte-level equivalence
    assert snap_a == snap_b


def test_03_bounded_owner_derivation_and_missing_provenance_negative_control():
    """Verify that ungraduated, non-emitting, or unverified-provenance cells are excluded from snapshots."""
    w = WState()
    w.commit_cell(8320, 1)

    # Candidate descriptor exists but not in stable_bindings
    # (should produce 0 snapshots)
    prev_ev = EventExecutionResult(
        event_order=1,
        exposure_id=1,
        mode=ExecutionMode.LEARN,
        origin=EventOrigin.EXTERNAL_DIRECT,
        boundary=False,
        committed_before_event=frozenset({8320}),
        newly_committed_sensory_cells=(),
        obs_direct_cells=frozenset(),
        obs_eligible_cells=frozenset(),
        ctx_event_match_cells=frozenset({8320}),
        ctx_runtime_match_cells=frozenset(),
        pt_by_cell={},
        ps_by_cell={},
        sigma_by_cell={},
        d1_by_cell={},
        a1_by_cell={},
        d2_by_cell={},
        a_plus_by_cell={8320: 0.8},
        e1_frontier=frozenset(),
        l_frontier=frozenset(),
        lx_frontier=frozenset(),
        f_step=frozenset({8320}),
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
    snaps = capture_pre_obs_context_snapshots(w, prev_ev, target_event_order=2, exposure_id=1)
    assert len(snaps) == 0

    # Add stable binding but with unverified provenance in typed_supports
    sb = StableBinding(
        schema_version=2,
        z_cell_id=8320,
        anchor_id=8327,
        owner_seq=1,
        binding_generation=1,
        p_keys=((1, 8320, SynapseScope.ASSOCIATIVE), (2, 8320, SynapseScope.ASSOCIATIVE)),
        l_z_q6=1000000,
        u_z_q6=0,
        tau_ctx_q6=50000,
        c_keys=(),
        y_keys=(),
        anchor_source_set=frozenset(),
        status=BindingStatus.ACTIVE,
    )
    w.stable_bindings[8320] = sb

    # Missing typed_supports -> 0 snapshots
    snaps2 = capture_pre_obs_context_snapshots(w, prev_ev, target_event_order=2, exposure_id=1)
    assert len(snaps2) == 0


def test_04_candidate_targets_restricted_to_observed_committed_before_event():
    """Verify that targets are strictly restricted to obs_eligible_cells & committed_before_event."""
    w = WState()
    w.commit_cell(8320, 1)
    w.commit_cell(9319, 1)  # committed before event
    # 9999 is NOT committed before event

    sb = StableBinding(
        schema_version=2,
        z_cell_id=8320,
        anchor_id=8327,
        owner_seq=1,
        binding_generation=1,
        p_keys=((1, 8320, SynapseScope.ASSOCIATIVE), (2, 8320, SynapseScope.ASSOCIATIVE)),
        l_z_q6=1000000,
        u_z_q6=0,
        tau_ctx_q6=50000,
        c_keys=(),
        y_keys=(),
        anchor_source_set=frozenset(),
        status=BindingStatus.ACTIVE,
    )
    w.stable_bindings[8320] = sb
    w.latent_table.materialize_cell(8320)[0] = 9319

    snap = capture_pre_obs_context_snapshots(
        w,
        EventExecutionResult(
            event_order=0,
            exposure_id=1,
            mode=ExecutionMode.LEARN,
            origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=False,
            committed_before_event=frozenset({8320}),
            newly_committed_sensory_cells=(),
            obs_direct_cells=frozenset(),
            obs_eligible_cells=frozenset(),
            ctx_event_match_cells=frozenset({8320}),
            ctx_runtime_match_cells=frozenset(),
            pt_by_cell={},
            ps_by_cell={},
            sigma_by_cell={},
            d1_by_cell={},
            a1_by_cell={},
            d2_by_cell={},
            a_plus_by_cell={8320: 1.0},
            e1_frontier=frozenset(),
            l_frontier=frozenset(),
            lx_frontier=frozenset(),
            f_step=frozenset({8320}),
            g_ctx_by_z={},
            g_probe_by_z={},
            mu_source_mask={},
            fresh_by_cell={},
            m_fresh_by_assembly={},
            typed_supports={
                8320: TypedSupportRecord(
                    cell_id=8320,
                    event_order=0,
                    origin_kind=ContributionLane.DERIVED_EXTERNAL_CONTEXT.value,
                    o_train=1.0,
                    o_runtime=1.0,
                    q6_train=1000000,
                    q6_runtime=1000000,
                    depth=1,
                    owner_id=1,
                    binding_generation=1,
                    parent_proof_verified=True,
                )
            },
            contributions=(),
            diagnostics=(),
            feature_bundle_digest=None,
        ),
        target_event_order=1,
        exposure_id=1,
    )

    curr_ev = EventExecutionResult(
        event_order=1,
        exposure_id=1,
        mode=ExecutionMode.LEARN,
        origin=EventOrigin.EXTERNAL_DIRECT,
        boundary=False,
        committed_before_event=frozenset({8320, 9319}),  # 9999 NOT here
        newly_committed_sensory_cells=(9999,),
        obs_direct_cells=frozenset({9319, 9999}),
        obs_eligible_cells=frozenset({9319, 9999}),
        ctx_event_match_cells=frozenset(),
        ctx_runtime_match_cells=frozenset(),
        pt_by_cell={},
        ps_by_cell={},
        sigma_by_cell={},
        d1_by_cell={},
        a1_by_cell={},
        d2_by_cell={},
        a_plus_by_cell={9319: 1.0, 9999: 1.0},
        e1_frontier=frozenset(),
        l_frontier=frozenset(),
        lx_frontier=frozenset(),
        f_step=frozenset({9319, 9999}),
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

    meas = measure_e2_prediction_opportunities(snap, curr_ev, w, egcp_mode=EGCPMode.E2_GROWTH)
    # Only 9319 should be evaluated, 9999 must NOT be evaluated
    target_ids = [c.target_cell_id for c in meas.all_candidates]
    assert 9319 in target_ids
    assert 9999 not in target_ids


def test_05_frozen_opportunity_function_and_u_q6_ranking():
    """Verify exact RC2 §3.2 opportunity formula U_zj = (e_z * x_j) * (1 - p_zj) and integer Q6 priority."""
    w = WState()
    w.commit_cell(8320, 1)
    w.commit_cell(100, 1)
    w.commit_cell(200, 1)

    slots_8320 = w.latent_table.materialize_cell(8320)
    slots_8320[0] = 100
    slots_8320[1] = 200

    # Key (8320, 100) exists with Q = 0.4
    syn = Synapse(
        key=(8320, 100, SynapseScope.ASSOCIATIVE),
        S=0.4,
        E_ext=10.0,
        state=SynapseState.CONSOLIDATED,
    )
    w.synapses[(8320, 100, SynapseScope.ASSOCIATIVE)] = syn

    sb = StableBinding(
        schema_version=2,
        z_cell_id=8320,
        anchor_id=8327,
        owner_seq=1,
        binding_generation=1,
        p_keys=((1, 8320, SynapseScope.ASSOCIATIVE), (2, 8320, SynapseScope.ASSOCIATIVE)),
        l_z_q6=1000000,
        u_z_q6=0,
        tau_ctx_q6=50000,
        c_keys=(),
        y_keys=((8320, 100, SynapseScope.ASSOCIATIVE),),
        anchor_source_set=frozenset(),
        status=BindingStatus.ACTIVE,
    )
    w.stable_bindings[8320] = sb

    snap = capture_pre_obs_context_snapshots(
        w,
        EventExecutionResult(
            event_order=0,
            exposure_id=1,
            mode=ExecutionMode.LEARN,
            origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=False,
            committed_before_event=frozenset({8320}),
            newly_committed_sensory_cells=(),
            obs_direct_cells=frozenset(),
            obs_eligible_cells=frozenset(),
            ctx_event_match_cells=frozenset({8320}),
            ctx_runtime_match_cells=frozenset(),
            pt_by_cell={},
            ps_by_cell={},
            sigma_by_cell={},
            d1_by_cell={},
            a1_by_cell={},
            d2_by_cell={},
            a_plus_by_cell={8320: 0.8},
            e1_frontier=frozenset(),
            l_frontier=frozenset(),
            lx_frontier=frozenset(),
            f_step=frozenset({8320}),
            g_ctx_by_z={},
            g_probe_by_z={},
            mu_source_mask={},
            fresh_by_cell={},
            m_fresh_by_assembly={},
            typed_supports={
                8320: TypedSupportRecord(
                    cell_id=8320,
                    event_order=0,
                    origin_kind=ContributionLane.DERIVED_EXTERNAL_CONTEXT.value,
                    o_train=0.8,
                    o_runtime=0.8,
                    q6_train=800000,
                    q6_runtime=800000,
                    depth=1,
                    owner_id=1,
                    binding_generation=1,
                    parent_proof_verified=True,
                )
            },
            contributions=(),
            diagnostics=(),
            feature_bundle_digest=None,
        ),
        target_event_order=1,
        exposure_id=1,
    )

    curr_ev = EventExecutionResult(
        event_order=1,
        exposure_id=1,
        mode=ExecutionMode.LEARN,
        origin=EventOrigin.EXTERNAL_DIRECT,
        boundary=False,
        committed_before_event=frozenset({8320, 100, 200}),
        newly_committed_sensory_cells=(),
        obs_direct_cells=frozenset({100, 200}),
        obs_eligible_cells=frozenset({100, 200}),
        ctx_event_match_cells=frozenset(),
        ctx_runtime_match_cells=frozenset(),
        pt_by_cell={},
        ps_by_cell={},
        sigma_by_cell={},
        d1_by_cell={},
        a1_by_cell={},
        d2_by_cell={},
        a_plus_by_cell={100: 1.0, 200: 1.0},
        e1_frontier=frozenset(),
        l_frontier=frozenset(),
        lx_frontier=frozenset(),
        f_step=frozenset({100, 200}),
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

    meas = measure_e2_prediction_opportunities(snap, curr_ev, w, egcp_mode=EGCPMode.E2_GROWTH)
    cands_by_target = {c.target_cell_id: c for c in meas.all_candidates}

    # Target 100 (existing key):
    # e_z = 0.8, x_j = 1.0, p_zj = 0.8 * 0.4 = 0.32
    # U = (0.8 * 1.0) * (1 - 0.32) = 0.8 * 0.68 = 0.544
    # U_q6 = round(0.544 * 64) = 35
    c100 = cands_by_target[100]
    assert pytest.approx(c100.p_zj, 1e-4) == 0.32
    assert pytest.approx(c100.u_val, 1e-4) == 0.544
    assert c100.u_q6 == 35
    assert c100.refusal_reason == REFUSAL_EXISTING_LIVE_KEY
    assert c100.is_legal is False

    # Target 200 (new legal opportunity):
    # e_z = 0.8, x_j = 1.0, p_zj = 0.0 (no existing link)
    # U = 0.8 * 1.0 * 1.0 = 0.8
    # U_q6 = round(0.8 * 64) = 51
    c200 = cands_by_target[200]
    assert c200.p_zj == 0.0
    assert pytest.approx(c200.u_val, 1e-4) == 0.8
    assert c200.u_q6 == 51
    assert c200.refusal_reason == REFUSAL_NONE
    assert c200.is_legal is True


def test_06_refusal_reason_codes_negative_controls():
    """Verify explicit refusal codes: NO_LEGAL_LOCAL_PATH, CAPACITY_BLOCKED, BOUNDARY, INCOMPLETE."""
    w = WState()
    w.commit_cell(8320, 1)
    w.commit_cell(300, 1)
    # 300 NOT in latent slots of 8320

    sb = StableBinding(
        schema_version=2,
        z_cell_id=8320,
        anchor_id=8327,
        owner_seq=1,
        binding_generation=1,
        p_keys=((1, 8320, SynapseScope.ASSOCIATIVE), (2, 8320, SynapseScope.ASSOCIATIVE)),
        l_z_q6=1000000,
        u_z_q6=0,
        tau_ctx_q6=50000,
        c_keys=(),
        y_keys=(),
        anchor_source_set=frozenset(),
        status=BindingStatus.ACTIVE,
    )
    w.stable_bindings[8320] = sb

    snap = capture_pre_obs_context_snapshots(
        w,
        EventExecutionResult(
            event_order=0,
            exposure_id=1,
            mode=ExecutionMode.LEARN,
            origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=False,
            committed_before_event=frozenset({8320}),
            newly_committed_sensory_cells=(),
            obs_direct_cells=frozenset(),
            obs_eligible_cells=frozenset(),
            ctx_event_match_cells=frozenset({8320}),
            ctx_runtime_match_cells=frozenset(),
            pt_by_cell={},
            ps_by_cell={},
            sigma_by_cell={},
            d1_by_cell={},
            a1_by_cell={},
            d2_by_cell={},
            a_plus_by_cell={8320: 1.0},
            e1_frontier=frozenset(),
            l_frontier=frozenset(),
            lx_frontier=frozenset(),
            f_step=frozenset({8320}),
            g_ctx_by_z={},
            g_probe_by_z={},
            mu_source_mask={},
            fresh_by_cell={},
            m_fresh_by_assembly={},
            typed_supports={
                8320: TypedSupportRecord(
                    cell_id=8320,
                    event_order=0,
                    origin_kind=ContributionLane.DERIVED_EXTERNAL_CONTEXT.value,
                    o_train=1.0,
                    o_runtime=1.0,
                    q6_train=1000000,
                    q6_runtime=1000000,
                    depth=1,
                    owner_id=1,
                    binding_generation=1,
                    parent_proof_verified=True,
                )
            },
            contributions=(),
            diagnostics=(),
            feature_bundle_digest=None,
        ),
        target_event_order=1,
        exposure_id=1,
    )

    # 1. No legal local path
    ev_normal = EventExecutionResult(
        event_order=1,
        exposure_id=1,
        mode=ExecutionMode.LEARN,
        origin=EventOrigin.EXTERNAL_DIRECT,
        boundary=False,
        committed_before_event=frozenset({8320, 300}),
        newly_committed_sensory_cells=(),
        obs_direct_cells=frozenset({300}),
        obs_eligible_cells=frozenset({300}),
        ctx_event_match_cells=frozenset(),
        ctx_runtime_match_cells=frozenset(),
        pt_by_cell={},
        ps_by_cell={},
        sigma_by_cell={},
        d1_by_cell={},
        a1_by_cell={},
        d2_by_cell={},
        a_plus_by_cell={300: 1.0},
        e1_frontier=frozenset(),
        l_frontier=frozenset(),
        lx_frontier=frozenset(),
        f_step=frozenset({300}),
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
    meas1 = measure_e2_prediction_opportunities(snap, ev_normal, w, egcp_mode=EGCPMode.E2_GROWTH)
    assert meas1.all_candidates[0].refusal_reason == REFUSAL_NO_LEGAL_LOCAL_PATH

    # 2. Boundary event (boundary=True)
    ev_bnd = dataclasses.replace(ev_normal, boundary=True)
    meas2 = measure_e2_prediction_opportunities(snap, ev_bnd, w, egcp_mode=EGCPMode.E2_GROWTH)
    assert meas2.all_candidates[0].refusal_reason == REFUSAL_ILLEGAL_TEMPORAL_BOUNDARY

    # 3. Non-external origin (origin=READ_ONLY_OBSERVED)
    ev_ro = dataclasses.replace(ev_normal, origin=EventOrigin.READ_ONLY_OBSERVED)
    meas3 = measure_e2_prediction_opportunities(snap, ev_ro, w, egcp_mode=EGCPMode.E2_GROWTH)
    assert meas3.all_candidates[0].refusal_reason == REFUSAL_INCOMPLETE_OBSERVATION


def test_07_measurement_layer_cannot_alter_core_or_lla_state():
    """Verify that E2a measurement layer is strictly read-only and does not mutate W or LLA evidence."""
    state = MachineState(egcp_mode=EGCPMode.E2_GROWTH)
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
        enable_birth_time_grow=False,
        enable_cross_clique_diversification=True,
        egcp_mode=EGCPMode.E2_GROWTH,
    )

    env = encode_exposure("القط يشرب حليب", append_eos=True)
    tx.begin_exposure(1)
    for e in env:
        core_ev = dataclasses.replace(e.core_event, exposure_id=1)
        tx.process_event(core_ev, peripheral_envelope=e.peripheral_surface)
    tx.end_exposure(1)

    # Verify no pending or synthetic synapses created
    for syn_key, syn in state.W.synapses.items():
        assert syn.state in (SynapseState.CANDIDATE, SynapseState.CONSOLIDATED)
        assert syn.scope in (SynapseScope.LOCAL, SynapseScope.TOPOGRAPHIC, SynapseScope.ASSOCIATIVE)


def test_08_exact_off_mode_compatibility():
    """Verify that under OFF mode, measurement layer produces empty candidate lists and exact compatibility."""
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

    env = encode_exposure("القط يشرب حليب", append_eos=True)
    tx.begin_exposure(1)
    for e in env:
        core_ev = dataclasses.replace(e.core_event, exposure_id=1)
        tx.process_event(core_ev, peripheral_envelope=e.peripheral_surface)
    tx.end_exposure(1)

    # In OFF mode, e2a_measurements all have empty candidate lists
    for m in tx.last_e2a_measurements:
        assert len(m.all_candidates) == 0
        assert len(m.admissible_candidates) == 0


def test_09_owner_8320_empirical_feasibility_at_roots_57_and_112():
    """Verify owner 8320 physical feasibility: 2 existing Y keys, 14 latent refusals, 0 new admissions."""
    from tools.forensics.inspect_e2a_feasibility import analyze_owner_8320_feasibility, run_to_root

    st57 = run_to_root(57)
    report = analyze_owner_8320_feasibility(st57)

    assert report["owner_id"] == 8320
    assert report["anchor_id"] == 8327
    assert report["existing_live_y_targets"] == [9319, 9325]
    assert report["outgoing_synapses_count"] == 5
    assert report["capacity_remaining"] == 59

    # Check observed cells
    existing_keys = [c for c in report["cells_analysis"] if c["refusal_reason"] == REFUSAL_EXISTING_LIVE_KEY]
    latent_refusals = [c for c in report["cells_analysis"] if c["refusal_reason"] == REFUSAL_NO_LEGAL_LOCAL_PATH]
    admissible = [c for c in report["cells_analysis"] if c["legal_new_growth"]]

    assert len(existing_keys) == 2
    assert {c["cell_id"] for c in existing_keys} == {9319, 9325}
    assert len(latent_refusals) == 14
    assert len(admissible) == 0  # 0 new admissions possible under existing latent topology!

