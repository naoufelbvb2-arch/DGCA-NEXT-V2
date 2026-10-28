"""Unit and contract tests for Phase 3: Atomic Exposure Transactions, Witnesses, and LLA Base Learning.

Covers:
- FIFR-B01, FIFR-B02, FIFR-B03, FIFR-B06
- LLA-T01 through LLA-T06, LLA-T13 through LLA-T21, LLA-T24, LLA-T30, LLA-T34
"""

from __future__ import annotations

import math
import pytest

from dgca.common import Region, StatusCode
from dgca.core import (
    AttractorRuntimeState,
    EventExecutionResult,
    ExecutionMode,
    HSlowState,
    MachineState,
    Synapse,
    SynapseScope,
    SynapseState,
)
from dgca.encoder import EventOrigin, encode_exposure, encode_lexical_token_event
from dgca.lifecycle import (
    ExposureStatus,
    ExposureTransactionManager,
    compute_pred_score,
    run_read_only_episode,
)
from dgca.lla import (
    LinkProposal,
    ObservationScope,
    ObservationWitness,
    apply_internal_replay_step,
    apply_root_proposals_to_shadow_w,
    compute_raw_evidence_q,
    evaluate_distinguishable,
    generate_event_link_proposals,
    reduce_within_root_proposals,
)


def _make_dummy_event_result(
    *,
    event_order: int = 0,
    exposure_id: int = 1,
    boundary: bool = True,
    committed_before: set[int],
    obs_eligible: set[int],
    e1_frontier: set[int],
    l_frontier: set[int],
    f_step: set[int],
    a1_by_cell: dict[int, float],
    a_plus_by_cell: dict[int, float],
) -> EventExecutionResult:
    return EventExecutionResult(
        event_order=event_order,
        exposure_id=exposure_id,
        mode=ExecutionMode.LEARN,
        origin=EventOrigin.EXTERNAL_DIRECT,
        boundary=boundary,
        committed_before_event=frozenset(committed_before),
        newly_committed_sensory_cells=(),
        obs_direct_cells=frozenset(obs_eligible),
        obs_eligible_cells=frozenset(obs_eligible),
        ctx_event_match_cells=frozenset(),
        ctx_runtime_match_cells=frozenset(),
        pt_by_cell={},
        ps_by_cell={},
        sigma_by_cell={},
        d1_by_cell={},
        a1_by_cell=dict(a1_by_cell),
        d2_by_cell={},
        a_plus_by_cell=dict(a_plus_by_cell),
        e1_frontier=frozenset(e1_frontier),
        l_frontier=frozenset(l_frontier),
        lx_frontier=frozenset(),
        f_step=frozenset(f_step),
        g_ctx_by_z={},
        g_probe_by_z={},
        mu_source_mask={},
        fresh_by_cell={},
        m_fresh_by_assembly={},
        typed_supports={},
        contributions=(),
        diagnostics=(),
    )


class TestFIFRB02B03AndEvidenceMath:
    """Verify FIFR-B01, FIFR-B02 Replay, FIFR-B03 Creation Coactivity, LLA-T18..T21, and LLA-T30."""

    def test_lla_t18_t19_t20_exact_q_and_replay_comparator(self) -> None:
        """LLA-T18, T19, T20 & FIFR-B01/B02: A=0.8, A_target=0.6 => q_ASSOC=0.3555927459272246; Replay q=0.08889818648180615."""
        q_local = compute_raw_evidence_q(0.80, 0.60, SynapseScope.LOCAL)
        assert pytest.approx(q_local, abs=1e-16) == 0.48

        q_assoc = compute_raw_evidence_q(0.80, 0.60, SynapseScope.ASSOCIATIVE)
        assert q_assoc == 0.80 * 0.60 * 0.7408182206817179
        assert pytest.approx(q_assoc, abs=1e-16) == 0.3555927459272246

        # Test Replay comparator on an existing external-rooted synapse
        state = MachineState()
        src_id, tgt_id = 8200, 8300
        state.W.commit_cell(src_id, 0)
        state.W.commit_cell(tgt_id, 0)
        state.W.latent_table.admit_or_recycle_coactive_partner(src_id, tgt_id)

        syn = Synapse(
            key=(src_id, tgt_id, SynapseScope.ASSOCIATIVE),
            S=0.75,
            E_ext=0.3555927459272246,
            E_int=0.0,
            external_count=1,
            state=SynapseState.CANDIDATE,
            confirmed_roots=(1,),
        )
        state.W.add_or_replace_synapse(syn)

        # Baseline Replay OFF => returns 0.0 and leaves E_int=0.0
        q_off = apply_internal_replay_step(
            syn, 0.80, 0.60, 0.20, state.W, replay_enabled=False
        )
        assert q_off == 0.0
        assert syn.E_int == 0.0

        # Declared Replay comparator ON => omega = 0.25 exactly once
        q_on = apply_internal_replay_step(
            syn, 0.80, 0.60, 0.20, state.W, replay_enabled=True
        )
        assert pytest.approx(q_on, abs=1e-16) == 0.08889818648180615
        assert pytest.approx(syn.E_int, abs=1e-16) == 0.08889818648180615
        # External count and E_ext remain strictly unchanged
        assert syn.external_count == 1
        assert pytest.approx(syn.E_ext, abs=1e-16) == 0.3555927459272246

    def test_lla_t21_fifr_b03_same_event_creation_coactivity(self) -> None:
        """LLA-T21 & FIFR-B03: Same-event Pass1=.40, final source=.80, target=.50 => coactivity=.40 (subject to Pass1 gate)."""
        state = MachineState()
        c1, c2 = 8200, 8300
        state.W.commit_cell(c1, 0)
        state.W.commit_cell(c2, 0)
        state.W.latent_table.admit_or_recycle_coactive_partner(c1, c2)

        # Case 1: c1 is in Pass-1 E1_frontier (A^(1)=0.40 >= 0.23), final A^+=0.80, c2 final A^+=0.50
        ev_valid = _make_dummy_event_result(
            committed_before={c1, c2},
            obs_eligible={c1, c2},
            e1_frontier={c1, c2},
            l_frontier={c1, c2},
            f_step={c1, c2},
            a1_by_cell={c1: 0.40, c2: 0.50},
            a_plus_by_cell={c1: 0.80, c2: 0.50},
        )
        props, _ = generate_event_link_proposals(ev_valid, None, None, state.W, state.H_slow)
        p_12 = [p for p in props if p.link_key == (c1, c2, SynapseScope.LOCAL)][0]
        assert pytest.approx(p_12.create_coactivity, abs=1e-15) == 0.40  # 0.80 * 0.50, NOT 0.40 * 0.50 = 0.20!
        assert pytest.approx(p_12.q_raw, abs=1e-15) == 0.40

        # Case 2: If c1 did NOT meet E1_frontier in Pass 1, proposal fails despite 0.40 final coactivity!
        ev_no_e1 = _make_dummy_event_result(
            committed_before={c1, c2},
            obs_eligible={c1, c2},
            e1_frontier={c2},  # c1 missing from E1_frontier!
            l_frontier={c1, c2},
            f_step={c1, c2},
            a1_by_cell={c1: 0.15, c2: 0.50},
            a_plus_by_cell={c1: 0.80, c2: 0.50},
        )
        props_no_e1, _ = generate_event_link_proposals(ev_no_e1, None, None, state.W, state.H_slow)
        assert not any(p.link_key == (c1, c2, SynapseScope.LOCAL) for p in props_no_e1)

    def test_lla_t30_coactivity_threshold_and_17_root_mass(self) -> None:
        """LLA-T30: A_src=A_tgt=.50 => create_coactivity=.25 >= .20; q_ASSOC=.18520455517; E>=3 needs 17 roots."""
        q_assoc = compute_raw_evidence_q(0.50, 0.50, SynapseScope.ASSOCIATIVE)
        assert pytest.approx(q_assoc, abs=1e-15) == 0.1852045551704295
        assert math.ceil(3.0 / q_assoc) == 17


class TestWitnessProposalsAndCapacityGates:
    """Verify LLA-T02, T03, T04, T05, T06, T17, and T34."""

    def test_lla_t02_t03_distinguishable_and_collision(self) -> None:
        w1 = ObservationWitness(
            witness_id=(1, 0, b"feat-digest-1"),
            exposure_id=1,
            event_order=0,
            direct_sources=((8200, 1_000_000), (8300, 800_000)),
            direct_float_sources={8200: 1.0, 8300: 0.8},
            feature_digest=b"feat-digest-1",
            sic_config_digest=b"cfg",
            origin=EventOrigin.EXTERNAL_DIRECT,
            scope=ObservationScope.COMPLETE_NEXT_EVENT,
            status=StatusCode.OK,
            aliased_cells=(),
        )
        # LLA-T02: No comparator -> NOT_EVALUATED_NO_COMPARATOR
        code_no_comp, _ = evaluate_distinguishable(w1, None)
        assert code_no_comp == StatusCode.NOT_EVALUATED_NO_COMPARATOR

        # LLA-T03: Identical neural SIC footprint but different canonical observed features -> UNRESOLVED_COLLISION
        w_collision = ObservationWitness(
            witness_id=(2, 0, b"feat-digest-2"),
            exposure_id=2,
            event_order=0,
            direct_sources=((8200, 1_000_000), (8300, 800_000)),
            direct_float_sources={8200: 1.0, 8300: 0.8},
            feature_digest=b"feat-digest-2",
            sic_config_digest=b"cfg",
            origin=EventOrigin.EXTERNAL_DIRECT,
            scope=ObservationScope.COMPLETE_NEXT_EVENT,
            status=StatusCode.OK,
            aliased_cells=(),
        )
        code_coll, _ = evaluate_distinguishable(w1, w_collision)
        assert code_coll == StatusCode.UNRESOLVED_COLLISION

    def test_lla_t04_predicted_only_cell_gets_zero_external_proof(self) -> None:
        """LLA-T04: Prediction-only E alongside externally observed C => external proof for E=0, valid for C."""
        state = MachineState()
        src_b, obs_c, pred_e = 8200, 8300, 8400
        for cid in (src_b, obs_c, pred_e):
            state.W.commit_cell(cid, 0)
        state.W.latent_table.admit_or_recycle_coactive_partner(src_b, obs_c)
        state.W.latent_table.admit_or_recycle_coactive_partner(src_b, pred_e)

        ev_prev = _make_dummy_event_result(
            event_order=0,
            committed_before={src_b, obs_c, pred_e},
            obs_eligible={src_b},
            e1_frontier={src_b},
            l_frontier={src_b},
            f_step={src_b},
            a1_by_cell={src_b: 0.70},
            a_plus_by_cell={src_b: 0.70},
        )
        # In event 1, obs_c is externally observed (in obs_eligible), whereas pred_e is ONLY predicted
        # (in l_frontier with high A^+=0.60, but NOT in obs_eligible)!
        ev_curr = _make_dummy_event_result(
            event_order=1,
            boundary=False,
            committed_before={src_b, obs_c, pred_e},
            obs_eligible={obs_c},
            e1_frontier={obs_c, pred_e},
            l_frontier={obs_c, pred_e},
            f_step={obs_c},
            a1_by_cell={obs_c: 0.70, pred_e: 0.60},
            a_plus_by_cell={obs_c: 0.70, pred_e: 0.60},
        )
        props, _ = generate_event_link_proposals(ev_curr, ev_prev, None, state.W, state.H_slow)
        keys = {p.link_key for p in props}
        assert (src_b, obs_c, SynapseScope.ASSOCIATIVE) in keys
        assert (src_b, pred_e, SynapseScope.ASSOCIATIVE) not in keys

    def test_lla_t05_within_root_reduction_takes_max_q_with_paired_y(self) -> None:
        """LLA-T05: Two q proposals .20, .50 same link/root => one q=.50 with paired y; one external confirmation."""
        key = (8200, 8300, SynapseScope.LOCAL)
        p1 = LinkProposal(
            link_key=key,
            exposure_id=1,
            event_order=0,
            source_event_order=0,
            a_source=0.50,
            a_target=0.40,
            create_coactivity=0.20,
            q_raw=0.20,
            y_positive=0.95,  # higher y on lower q!
            d_event=True,
            v_ext=True,
            priority_class=1,
            proposal_ordinal=0,
        )
        p2 = LinkProposal(
            link_key=key,
            exposure_id=1,
            event_order=2,
            source_event_order=2,
            a_source=1.0,
            a_target=0.50,
            create_coactivity=0.50,
            q_raw=0.50,
            y_positive=0.75,  # paired y for max q=0.50
            d_event=True,
            v_ext=True,
            priority_class=1,
            proposal_ordinal=1,
        )
        winners = reduce_within_root_proposals([p1, p2])
        assert len(winners) == 1
        assert winners[0].q_raw == 0.50
        # Must use paired y (0.75), NEVER separately maximize y (0.95)!
        assert winners[0].y_positive == 0.75

    def test_lla_t06_stale_latent_eligibility_at_close(self) -> None:
        """LLA-T06: Provisional link lost D_close by latent recycling => STALE_LATENT_ELIGIBILITY, no q/E/root count."""
        state = MachineState()
        c1, c2 = 8200, 9000
        state.W.commit_cell(c1, 0)
        state.W.commit_cell(c2, 0)
        state.W.latent_table.admit_or_recycle_coactive_partner(c1, c2, event_clock=1)

        prop = LinkProposal(
            link_key=(c1, c2, SynapseScope.LOCAL),
            exposure_id=1,
            event_order=0,
            source_event_order=0,
            a_source=0.70,
            a_target=0.70,
            create_coactivity=0.49,
            q_raw=0.49,
            y_positive=0.85,
            d_event=True,
            v_ext=True,
            priority_class=1,
            proposal_ordinal=0,
        )

        # Simulate unprotected latent slots of c1 being recycled by 6 other cells before root close
        for idx in range(6):
            other_cell = 9100 + idx * 8
            state.W.commit_cell(other_cell, 0)
            state.W.latent_table.admit_or_recycle_coactive_partner(c1, other_cell, event_clock=2)

        assert not state.W.latent_table.is_eligible(c1, c2)
        w_shadow = state.W.clone()
        outcomes, diags = apply_root_proposals_to_shadow_w([prop], state.W, w_shadow)
        assert outcomes[0].status == StatusCode.STALE_LATENT_ELIGIBILITY
        assert StatusCode.STALE_LATENT_ELIGIBILITY in diags
        assert (c1, c2, SynapseScope.LOCAL) not in w_shadow.synapses

    def test_lla_t34_source_outgoing_capacity_enforced(self) -> None:
        """LLA-T34: Feature receiver has 64 live outgoing => cannot exceed B_i; SOURCE_OUTGOING_CAPACITY."""
        state = MachineState()
        src = 8200
        state.W.commit_cell(src, 0)

        # Fill all 64 outgoing slots of src
        for k in range(64):
            tgt = 8300 + k
            state.W.commit_cell(tgt, 0)
            state.W.add_or_replace_synapse(
                Synapse(
                    key=(src, tgt, SynapseScope.ASSOCIATIVE),
                    S=0.80,
                    E_ext=5.0,
                    external_count=2,
                    state=SynapseState.CONSOLIDATED,
                )
            )
        assert state.W.available_outgoing_headroom(src) == 0

        # Propose 65th outgoing link to a fixed local neighbor (so D_close == 1 holds!)
        local_neighbor = state.W.latent_table.get_slots(src)[6]
        assert local_neighbor is not None
        state.W.commit_cell(local_neighbor, 0)

        prop = LinkProposal(
            link_key=(src, local_neighbor, SynapseScope.LOCAL),
            exposure_id=2,
            event_order=0,
            source_event_order=0,
            a_source=0.80,
            a_target=0.80,
            create_coactivity=0.64,
            q_raw=0.64,
            y_positive=0.90,
            d_event=True,
            v_ext=True,
            priority_class=1,
            proposal_ordinal=0,
        )
        w_shadow = state.W.clone()
        outcomes, diags = apply_root_proposals_to_shadow_w([prop], state.W, w_shadow)
        assert outcomes[0].status == StatusCode.SOURCE_OUTGOING_CAPACITY
        assert StatusCode.SOURCE_OUTGOING_CAPACITY in diags
        assert len(w_shadow.outgoing_by_source[src]) == 64


class TestExposureTransactionsAndRollback:
    """Verify LLA-T13, LLA-T14, LLA-T15, LLA-T16, LLA-T24, and FIFR-B06."""

    def test_lla_t13_t14_t24_fifr_b06_begin_abort_rollback_and_isolation(self) -> None:
        state = MachineState()
        tx = ExposureTransactionManager(state)

        # Populate residual attractor and activity before BEGIN_EXPOSURE
        state.R.A[8200] = 0.75
        state.R.A_hist[8200] = (0.50, 0.75)
        state.R.active_attractors[1] = AttractorRuntimeState(assembly_id=1, strength_c=0.80, age=5)

        # First root commits sensory cells for "كتب" and "درس"
        envelopes_r1 = encode_exposure("كتب درس.", exposure_id=1)
        tx.begin_exposure(1)
        # LLA-T13: Full cold isolation before event 0
        assert state.R.A == {}
        assert state.R.A_hist == {}
        assert state.R.active_attractors == {}

        for env in envelopes_r1:
            tx.process_event(env.core_event)
        rep1 = tx.end_exposure(1)
        assert rep1.status == ExposureStatus.COMPLETED
        committed_after_r1 = set(state.W.committed_cells.keys())
        assert len(committed_after_r1) >= 6

        # Snapshot H_slow before root 2
        h_before_r2 = state.H_slow.clone()

        # Root 2: process events (which adapt H_slow and stage link proposals, plus commit a new word "علم"), then ABORT
        envelopes_r2 = encode_exposure("كتب درس علم.", exposure_id=2)
        tx.begin_exposure(2)
        for env in envelopes_r2:
            tx.process_event(env.core_event)

        # Verify H_slow was modified during root 2 OPEN events and proposals were staged
        assert state.H_slow.r_bar != h_before_r2.r_bar
        assert len(tx.open_journal.staged_proposals) > 0
        assert len(state.W.synapses) == 0  # No S/E/count published while OPEN

        # Execute ABORT_EXPOSURE(2)
        status = tx.abort_exposure(2)
        assert status == ExposureStatus.ABORTED

        # FIFR-B06 & LLA-T14 & LLA-T24: H_slow is exactly restored to H_slow_BEGIN!
        assert state.H_slow.r_bar == h_before_r2.r_bar
        assert state.H_slow.g == h_before_r2.g
        assert state.H_slow.rho_bar_by_region == h_before_r2.rho_bar_by_region
        assert state.H_slow.theta_active_by_region == h_before_r2.theta_active_by_region
        assert len(state.W.synapses) == 0
        assert state.R.A == {}
        # Lawful sensory admissions from root 2 MAY remain in W.committed_cells
        assert len(state.W.committed_cells) > len(committed_after_r1)

        # Duplicate ABORT request for root 2 is idempotent and does not fail
        assert tx.abort_exposure(2) == ExposureStatus.ABORTED

    def test_lla_t15_t16_end_idempotency_and_read_only_immutability(self) -> None:
        state = MachineState()
        tx = ExposureTransactionManager(state)

        # Root 1: commit cells for "A B."
        for env in encode_exposure("A B.", exposure_id=1):
            if tx.status == ExposureStatus.CLOSED:
                tx.begin_exposure(1)
            tx.process_event(env.core_event)
        tx.end_exposure(1)

        # Roots 2..9 (8 post-commitment roots so both LOCAL and ASSOCIATIVE reach E_ext >= 3.0)
        for root_id in range(2, 10):
            tx.begin_exposure(root_id)
            for env in encode_exposure("A B.", exposure_id=root_id):
                tx.process_event(env.core_event)
            rep = tx.end_exposure(root_id)
            # LLA-T15: Retry of END_EXPOSURE on same root is idempotent
            rep_retry = tx.end_exposure(root_id)
            assert rep_retry == rep

        consolidated_links = [
            s for s in state.W.synapses.values() if s.state == SynapseState.CONSOLIDATED
        ]
        assert len(consolidated_links) > 0

        # LLA-T16: READ_ONLY_EPISODE does not mutate W, H_slow, or caller R
        w_snapshot_syns = {k: (s.S, s.E_ext, s.external_count) for k, s in state.W.synapses.items()}
        h_snapshot_rbar = dict(state.H_slow.r_bar)
        r_caller_a = dict(state.R.A)

        prompt_a = encode_lexical_token_event("A", event_order=0, origin=EventOrigin.READ_ONLY_OBSERVED)
        ro_res = run_read_only_episode(state, [prompt_a.core_event])

        assert {k: (s.S, s.E_ext, s.external_count) for k, s in state.W.synapses.items()} == w_snapshot_syns
        assert state.H_slow.r_bar == h_snapshot_rbar
        assert state.R.A == r_caller_a
        assert len(ro_res.next_step_pt_by_cell) > 0

        # Check PredScore for target B
        env_b = encode_lexical_token_event("B")
        from dgca.core import project_core_event_v1

        proj_b = project_core_event_v1(env_b.core_event)
        code, score_b = compute_pred_score(ro_res.next_step_pt_by_cell, list(proj_b.x_fixed_by_global_id.keys()))
        assert code == StatusCode.OK
        assert score_b > 0.0
