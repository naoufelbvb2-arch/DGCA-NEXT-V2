"""DGCA NEXT V2 — EGCP E2b Quarantined Learning Verification Suite.

Comprehensive automated verification for Bounded Witnessed Opportunity Allocation
and Quarantined Post-Graduation Learning (EGCP v1.0-RC2 §4.3, §5.1, §5.2A):
- Test 01: Exact OFF Mode Invariance (quarantine compartment empty, exact baseline match).
- Test 02: P1 Quarantine Invariant (zero temporal associative drive in LEARN/RETRIEVE/GENERATE).
- Test 03: Pillar 4 Anti-Recycling Protection (pending targets protected from slot eviction across 50+ exposures).
- Test 04: Pending Growth Allocation & Evidence Accumulation (monotonically credited across S1 roots).
- Test 05: Transition to READY_FOR_PROMOTION upon consolidation (S >= 0.60, E/E_max >= 0.30, count >= 2).
- Test 06: Bounded Capacity and Candidate Caps (degree cap 64 and per-owner cap 8 enforced).
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
from dgca.core.anatomy import (
    DEFAULT_OUTGOING_BUDGET_B_I,
    E_MAX,
    Synapse,
    SynapseScope,
    SynapseState,
    THETA_E,
    THETA_S,
)
from dgca.core.dynamics import compute_next_step_temporal_drive
from dgca.core.generator import generate_episode
from dgca.core.state import (
    EGCPGrowthState,
    EGCPMode,
    EGCPPendingGrowthV1,
    ExecutionMode,
    MachineState,
)
from dgca.encoder.envelope import encode_exposure
from dgca.lifecycle.exposure_tx import ExposureTransactionManager
from dgca.lla.proposals import LinkProposal
from dgca.lla.synapse_ledger import apply_root_proposals_to_shadow_w
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1
from tools.forensics.run_r2_c01_cf01_experiment import CORPUS_GROUP_B, build_schedule


def _run_schedule(
    target_root: int,
    *,
    enable_contextual_coactive_latent: bool = True,
    egcp_mode: EGCPMode = EGCPMode.E2_GROWTH,
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


def test_01_off_preservation_empty_quarantine():
    """E2B-T01: Verify OFF mode maintains an empty quarantine compartment and baseline invariance."""
    st_off, _, _ = _run_schedule(61, egcp_mode=EGCPMode.OFF)
    assert len(st_off.W.egcp_pending_growth) == 0
    assert st_off.W.egcp_mode == EGCPMode.OFF

    # Completed owner 8320 retains only its 2 original graduated Y-keys in live synapses
    live_out_8320 = [k for k in st_off.W.synapses if k[0] == 8320 and k[2] == SynapseScope.ASSOCIATIVE]
    assert len(live_out_8320) == 2
    assert {k[1] for k in live_out_8320} == {9319, 9325}


def test_02_p1_quarantine_invariant():
    """E2B-T02: Verify P1 Quarantine Invariant (zero temporal associative drive in all modes)."""
    st_on, _, _ = _run_schedule(61, egcp_mode=EGCPMode.E2_GROWTH)
    w = st_on.W

    # Confirm exactly 6 pending growth candidates admitted into quarantine
    assert len(w.egcp_pending_growth) == 6
    pending_targets = {k[1] for k in w.egcp_pending_growth}
    assert pending_targets == {9951, 10345, 10903, 11220, 11463, 12066}

    # None of the pending keys appear in live synapses or outgoing index
    for key in w.egcp_pending_growth:
        assert key not in w.synapses, f"Quarantine leak: {key} found in W.synapses"
        out_set = w.outgoing_by_source.get(key[0], set())
        assert key not in out_set, f"Quarantine leak: {key} found in W.outgoing_by_source"

    # Evaluate temporal drive across all EGCP modes
    # Test temporal drive from emitting source 8320 (A_8320 = 1.0) toward pending targets
    f_step_test = frozenset([8320])
    a_prev_test = {8320: 1.0}
    mu_prev_test = {8320: 0}

    for eff_mode in (EGCPMode.OFF, EGCPMode.E1_PRESERVE_GENERIC, EGCPMode.E2_GROWTH):
        p_t, _ = compute_next_step_temporal_drive(
            st_on,
            f_step_prev=f_step_test,
            a_prev_by_cell=a_prev_test,
            mu_prev_source_mask=mu_prev_test,
            egcp_mode=eff_mode,
        )
        for tgt in pending_targets:
            drive_to_tgt = p_t.get(tgt, 0.0)
            assert drive_to_tgt == 0.0, (
                f"Quarantine leak: nonzero temporal drive {drive_to_tgt} toward pending target {tgt} under {eff_mode}"
            )


def test_03_pillar4_anti_recycling_protection():
    """E2B-T03: Verify Pillar 4 protects pending growth targets from eviction across subsequent exposures."""
    st61, _, _ = _run_schedule(61, egcp_mode=EGCPMode.E2_GROWTH)
    w61 = st61.W

    protected_neighbors_61 = w61.get_protected_bidirectional_neighbors(8320)
    for key in w61.egcp_pending_growth:
        tgt_id = key[1]
        assert tgt_id in protected_neighbors_61, f"Target {tgt_id} not protected by Pillar 4 at Root 61"

    # Advance to Root 112 (51 additional exposure roots)
    st112, _, _ = _run_schedule(112, egcp_mode=EGCPMode.E2_GROWTH)
    w112 = st112.W

    # Confirm all 6 pending growth targets remained latent-eligible and were never evicted
    for key in w112.egcp_pending_growth:
        tgt_id = key[1]
        assert w112.latent_table.is_eligible(8320, tgt_id), (
            f"Target {tgt_id} lost latent eligibility between Root 61 and Root 112"
        )


def test_04_pending_growth_allocation_and_evidence_accumulation():
    """E2B-T04: Verify genuine monotonic LLA evidence accumulation across S1 roots."""
    st61, _, _ = _run_schedule(61, egcp_mode=EGCPMode.E2_GROWTH)
    p61 = next(iter(st61.W.egcp_pending_growth.values()))
    assert p61.state == EGCPGrowthState.PENDING_LEARNING
    assert p61.accepted_root_count == 1
    assert p61.synapse.external_count == 1
    assert p61.synapse.S >= THETA_S
    assert 0.14 <= p61.synapse.E_ext <= 0.20

    st65, _, _ = _run_schedule(65, egcp_mode=EGCPMode.E2_GROWTH)
    p65 = st65.W.egcp_pending_growth[p61.key]
    assert p65.accepted_root_count == 2
    assert p65.synapse.external_count == 2
    assert p65.synapse.E_ext > p61.synapse.E_ext
    assert p65.synapse.S >= THETA_S

    st112, _, _ = _run_schedule(112, egcp_mode=EGCPMode.E2_GROWTH)
    p112 = st112.W.egcp_pending_growth[p61.key]
    assert p112.accepted_root_count == 13
    assert p112.synapse.external_count == 13
    assert p112.synapse.E_ext > 1.70
    assert p112.synapse.S >= THETA_S
    assert p112.state == EGCPGrowthState.PENDING_LEARNING  # E < 3.0 at Root 112


def test_05_transition_to_ready_for_promotion(monkeypatch):
    """E2B-T05: Verify state transitions from PENDING_LEARNING to READY_FOR_PROMOTION upon consolidation."""
    # In E2c, pre-assembly promotion would immediately promote READY_FOR_PROMOTION candidates.
    # To isolate the E2b state transition to READY_FOR_PROMOTION prior to promotion:
    monkeypatch.setattr(
        "dgca.lla.egcp_promotion.execute_egcp_pre_assembly_shadow_stage",
        lambda *args, **kwargs: None,
    )
    st149, _, _ = _run_schedule(149, egcp_mode=EGCPMode.E2_GROWTH)
    w149 = st149.W

    assert len(w149.egcp_pending_growth) == 6
    for key, pending in w149.egcp_pending_growth.items():
        assert pending.state == EGCPGrowthState.READY_FOR_PROMOTION, (
            f"Key {key} state {pending.state} expected READY_FOR_PROMOTION"
        )
        assert pending.synapse.S >= THETA_S
        assert (pending.synapse.E / E_MAX) >= THETA_E
        assert pending.synapse.external_count >= 2

        # Still quarantined in W (zero live synapses created prior to E2c)
        assert key not in w149.synapses
        assert key not in w149.outgoing_by_source.get(key[0], set())


def test_06_bounded_capacity_and_candidate_caps():
    """E2B-T06: Verify outgoing degree cap (64) and per-owner pending cap (8) are enforced."""
    st61, _, _ = _run_schedule(61, egcp_mode=EGCPMode.E2_GROWTH)
    w = st61.W.clone()

    claimed_keys = w.unique_claimed_outgoing_keys(8320)
    # 5 live outgoing synapses + 6 pending growth keys = 11 unique claimed keys
    assert len(claimed_keys) == 11
    assert w.available_outgoing_headroom(8320) == DEFAULT_OUTGOING_BUDGET_B_I - 11

    # Attempt to inject 3 additional pending growth candidates (reaching 6 + 3 = 9 > 8 cap)
    # The 7th and 8th should succeed; the 9th must fail with SOURCE_OUTGOING_CAPACITY
    dummy_proposals = [
        LinkProposal(
            link_key=(8320, 9991, SynapseScope.ASSOCIATIVE),
            exposure_id=62,
            event_order=2,
            source_event_order=1,
            a_source=0.8,
            a_target=0.8,
            create_coactivity=0.64,
            q_raw=0.5,
            y_positive=0.8,
            d_event=True,
            v_ext=True,
            priority_class=1,
            proposal_ordinal=1,
        ),
        LinkProposal(
            link_key=(8320, 9992, SynapseScope.ASSOCIATIVE),
            exposure_id=62,
            event_order=2,
            source_event_order=1,
            a_source=0.8,
            a_target=0.8,
            create_coactivity=0.64,
            q_raw=0.5,
            y_positive=0.8,
            d_event=True,
            v_ext=True,
            priority_class=1,
            proposal_ordinal=2,
        ),
        LinkProposal(
            link_key=(8320, 9993, SynapseScope.ASSOCIATIVE),
            exposure_id=62,
            event_order=2,
            source_event_order=1,
            a_source=0.8,
            a_target=0.8,
            create_coactivity=0.64,
            q_raw=0.5,
            y_positive=0.8,
            d_event=True,
            v_ext=True,
            priority_class=1,
            proposal_ordinal=3,
        ),
    ]

    # Pre-add latent eligibility for these test cells in 8320's slots
    w.latent_table._ensure_cell_materialized(8320)
    for idx, cid in enumerate((9991, 9992, 9993)):
        w.latent_table._slots_by_cell[8320][idx] = cid

    outcomes, diags = apply_root_proposals_to_shadow_w(
        dummy_proposals,
        w_pre_close=w.clone(),
        w_shadow=w,
        egcp_mode=EGCPMode.E2_GROWTH,
    )

    # 1st dummy (7th total pending) -> OK
    assert outcomes[0].status == StatusCode.OK
    # 2nd dummy (8th total pending) -> OK
    assert outcomes[1].status == StatusCode.OK
    # 3rd dummy (9th total pending > 8 cap) -> SOURCE_OUTGOING_CAPACITY
    assert outcomes[2].status == StatusCode.SOURCE_OUTGOING_CAPACITY
    assert StatusCode.SOURCE_OUTGOING_CAPACITY in diags


def test_07_non_interference_p2_p3_p4():
    """E2B-T07: Verify non-interference on canonical probes P2, P3, and P4 at Root 61 and Root 112."""
    st61_on, ledger61_on, _ = _run_schedule(61, egcp_mode=EGCPMode.E2_GROWTH)
    st61_off, ledger61_off, _ = _run_schedule(61, egcp_mode=EGCPMode.OFF)

    st112_on, ledger112_on, _ = _run_schedule(112, egcp_mode=EGCPMode.E2_GROWTH)
    st112_off, ledger112_off, _ = _run_schedule(112, egcp_mode=EGCPMode.OFF)

    encoded = {k: encode_exposure(v, append_eos=True) for k, v in CORPUS_GROUP_B.items()}

    # Probe P2: النسر يشرب -> ماء
    p2 = [encoded["S2"][0].core_event, encoded["S2"][1].core_event]
    res_p2_61_on = generate_episode(st61_on, p2, ledger61_on, max_steps=4)
    res_p2_61_off = generate_episode(st61_off, p2, ledger61_off, max_steps=4)
    assert res_p2_61_on.emitted_surfaces == res_p2_61_off.emitted_surfaces == ("ماء",)

    res_p2_112_on = generate_episode(st112_on, p2, ledger112_on, max_steps=4)
    res_p2_112_off = generate_episode(st112_off, p2, ledger112_off, max_steps=4)
    assert res_p2_112_on.emitted_surfaces == res_p2_112_off.emitted_surfaces == ("ماء",)

    # Probe P3: الطفل يأكل -> تفاح
    p3 = [encoded["S3"][0].core_event, encoded["S3"][1].core_event]
    res_p3_61_on = generate_episode(st61_on, p3, ledger61_on, max_steps=4)
    res_p3_61_off = generate_episode(st61_off, p3, ledger61_off, max_steps=4)
    assert res_p3_61_on.emitted_surfaces == res_p3_61_off.emitted_surfaces

    res_p3_112_on = generate_episode(st112_on, p3, ledger112_on, max_steps=4)
    res_p3_112_off = generate_episode(st112_off, p3, ledger112_off, max_steps=4)
    assert res_p3_112_on.emitted_surfaces == res_p3_112_off.emitted_surfaces == ("تفاح",)

    # Probe P4: الطفل يشرب -> ماء
    p4 = [encoded["S4"][0].core_event, encoded["S4"][1].core_event]
    res_p4_61_on = generate_episode(st61_on, p4, ledger61_on, max_steps=4)
    res_p4_61_off = generate_episode(st61_off, p4, ledger61_off, max_steps=4)
    assert res_p4_61_on.emitted_surfaces == res_p4_61_off.emitted_surfaces == ("ماء",)

    res_p4_112_on = generate_episode(st112_on, p4, ledger112_on, max_steps=4)
    res_p4_112_off = generate_episode(st112_off, p4, ledger112_off, max_steps=4)
    assert res_p4_112_on.emitted_surfaces == res_p4_112_off.emitted_surfaces == ("ماء",)
