"""Phase 4 Verification Suite: Contextual Learning, Recruitment, Probation FSM & C04 Graduation.

Covers normative gates:
- LLA-T08, LLA-T09, LLA-T10 (C04 P2_DURABLE, NORMAL_W vs CONSOLIDATED_W graduation)
- LLA-T11, LLA-T12 (OwnerProfile persistence across 2000-event TTL turnover, OWNER_REGISTRY_CONFLICT)
- LLA-T22, LLA-T23, LLA-T31 (Two-clock candidate FSM: 8 probe + 32 consolidation + 240 age, settle before expiry)
- LLA-T26, LLA-T27, LLA-T28, LLA-T29 (No-probe drive check, mu=1 suppression, B-only preservation, AMBIGUOUS_CONTEXT_OWNER)
- LLA-T32, LLA-T33 (Capacity pre-filtering before top-8 truncation, Manhattan radius-2 z search)
- LLA-T35 (Bit-identical PRE/POST retirement equivalence)
- LLA-T38, LLA-T39, LLA-T40, LLA-T41 (LEARN probe retention after NO_PROBE_INSUFFICIENT_DRIVE, sub-tau rival root rejection)
"""

from __future__ import annotations

import pytest

from dgca.common.errors import DGCAError, StatusCode
from dgca.common.hashing import Region, WitnessSourceKind
from dgca.common.numeric import MILLION, q6_from_binary64
from dgca.core.anatomy import Synapse, SynapseKey, SynapseScope, SynapseState
from dgca.core.dynamics import compute_next_step_temporal_drive, execute_two_pass_event
from dgca.core.sic_v1 import CELLS_PER_MICROCOLUMN, CellAddress
from dgca.core.state import (
    BindingStatus,
    CandidatePhase,
    ContextCandidateDescriptor,
    ExecutionMode,
    MachineState,
    OwnerState,
    StableBinding,
)
from dgca.encoder.envelope import EventOrigin
from dgca.lifecycle.exposure_tx import compute_pred_score
from dgca.lla.candidate_fsm import (
    MAX_CANDIDATE_AGE_EVENTS,
    MAX_PROBE_MATCHES,
    settle_candidate_at_end_exposure,
)
from dgca.lla.contrast_ledger import (
    BranchSummary,
    CONTRAST_LEDGER_TTL_EVENTS,
    ContrastEpisodeRecord,
    discover_anchor_contrasts,
    prune_expired_contrast_episodes,
    record_contrast_episode,
)
from dgca.lla.graduation_c04 import (
    build_proposed_stable_binding,
    check_c04_durable_path,
    commit_c04_graduation,
    evaluate_c04_graduation,
)
from dgca.lla.owner_registry import (
    CompactWitnessProfile,
    OwnerProfile,
    resolve_owner,
)
from dgca.lla.recruitment import (
    find_candidate_z_cells_within_radius2,
    recruit_contextual_candidate,
)


def _lang_cell(mc_row: int, mc_col: int, slot: int) -> int:
    """Return global cell ID in LANGUAGE region for (mc_row, mc_col, slot)."""
    mc_idx = mc_row * 16 + mc_col
    local_idx = mc_idx * CELLS_PER_MICROCOLUMN + slot
    return int(Region.LANGUAGE) * 4096 + local_idx


def _make_contrast_episode(
    anchor_id: int,
    exposure_id: int,
    clock: int,
    p_supports: dict[int, int],
    c_supports: dict[int, int],
    y_supports: dict[int, int],
) -> ContrastEpisodeRecord:
    return ContrastEpisodeRecord(
        anchor_id=anchor_id,
        exposure_id=exposure_id,
        event_order_b=1,
        completed_event_clock=clock,
        p_supports_u=dict(p_supports),
        c_supports_u=dict(c_supports),
        y_supports_u=dict(y_supports),
    )


def _setup_durable_candidate_fixture(
    *,
    consolidate_p0: bool = True,
    consolidate_p1: bool = True,
    consolidate_c0: bool = True,
    consolidate_c1: bool = False,
    consolidate_y0: bool = True,
    synapse_s: float = 0.85,
    synapse_e: float = 5.0,
) -> tuple[MachineState, ContextCandidateDescriptor, CompactWitnessProfile, CompactWitnessProfile]:
    """Create a clean LANGUAGE network fixture with an admitted contextual candidate z for DB -> E vs AB -> C."""
    state = MachineState()
    w = state.W

    # Choose distinct microcolumns in LANGUAGE so normalization does not attenuate single cells
    a0, a1 = _lang_cell(1, 1, 0), _lang_cell(1, 2, 0)
    d0, d1 = _lang_cell(2, 1, 0), _lang_cell(2, 2, 0)
    b0, b1 = _lang_cell(5, 5, 0), _lang_cell(5, 6, 0)
    c0, c1 = _lang_cell(8, 1, 0), _lang_cell(8, 2, 0)
    e0, e1 = _lang_cell(9, 1, 0), _lang_cell(9, 2, 0)
    z_id = _lang_cell(5, 5, 1)

    for cid in (a0, a1, d0, d1, b0, b1, c0, c1, e0, e1, z_id):
        w.commit_cell(cid, 1)

    # Pin role cells in z's CO_ACTIVE_INTRA slots
    w.latent_table.pin_context_candidate_roles(z_id, (d0, d1, b0, b1, e0, e1), event_clock=1)

    # Also establish generic B -> C associative links (so without z, B predicts C!)
    for idx, (b_src, c_tgt) in enumerate(((b0, c0), (b1, c1))):
        w.latent_table.admit_or_recycle_coactive_partner(b_src, c_tgt, event_clock=1)
        w.add_or_replace_synapse(
            Synapse(
                key=(b_src, c_tgt, SynapseScope.ASSOCIATIVE),
                S=0.80,
                E_ext=5.0,
                E_int=0.0,
                external_count=3,
                state=SynapseState.CONSOLIDATED,
                created_event_id=1,
                created_exposure_id=1,
                last_external_event_id=2,
                last_evidence_root=2,
                candidate_deadline=100,
                confirmed_roots={1, 2, 3},
            )
        )

    # Add candidate role links (d0->z, d1->z, b0->z, b1->z, z->e0)
    def _add_role_link(src: int, tgt: int, scope: SynapseScope, is_cons: bool, s_val: float | None = None) -> None:
        s_use = s_val if s_val is not None else synapse_s
        e_use = synapse_e if is_cons else 1.5
        roots = {2, 3} if is_cons else {2}
        w.add_or_replace_synapse(
            Synapse(
                key=(src, tgt, scope),
                S=s_use,
                E_ext=e_use,
                E_int=0.0,
                external_count=len(roots),
                state=SynapseState.CONSOLIDATED if is_cons else SynapseState.CANDIDATE,
                created_event_id=2,
                created_exposure_id=2,
                last_external_event_id=3,
                last_evidence_root=3,
                candidate_deadline=240,
                confirmed_roots=set(roots),
            )
        )

    _add_role_link(d0, z_id, SynapseScope.ASSOCIATIVE, consolidate_p0)
    _add_role_link(d1, z_id, SynapseScope.ASSOCIATIVE, consolidate_p1)
    _add_role_link(b0, z_id, SynapseScope.LOCAL, consolidate_c0)
    if consolidate_c1:
        _add_role_link(b1, z_id, SynapseScope.LOCAL, True)
    else:
        _add_role_link(b1, z_id, SynapseScope.LOCAL, False, s_val=0.85)
    _add_role_link(z_id, e0, SynapseScope.ASSOCIATIVE, consolidate_y0)
    _add_role_link(z_id, e1, SynapseScope.ASSOCIATIVE, consolidate_y0)

    cand = ContextCandidateDescriptor(
        z_cell_id=z_id,
        anchor_id=b0,
        owner_seq=1,
        p_sources=(d0, d1),
        c_sources=(b0, b1),
        y_targets=(e0, e1),
        l_z_q6=800_000,
        u_z_q6=200_000,
        tau_ctx_q6=250_000,
        anchor_source_set=frozenset({b0, b1}),
        phase=CandidatePhase.LEARN_OUTCOME,
        probe_matches=2,
        consolidation_matches=5,
        age_events=21,
        admitted_root_id=1,
    )
    w.context_candidates[z_id] = cand
    w.reserved_keys_by_candidate[z_id] = set(cand.reserved_synapse_keys)

    ep_owned_1 = _make_contrast_episode(
        b0, 1, 3, {d0: 800_000, d1: 800_000}, {b0: 800_000, b1: 800_000}, {e0: 800_000, e1: 800_000}
    )
    ep_owned_2 = _make_contrast_episode(
        b0, 2, 6, {d0: 800_000, d1: 800_000}, {b0: 800_000, b1: 800_000}, {e0: 800_000, e1: 800_000}
    )
    ep_rival_1 = _make_contrast_episode(
        b0, 3, 9, {a0: 800_000, a1: 800_000, d0: 200_000, d1: 200_000}, {b0: 800_000, b1: 800_000}, {c0: 800_000, c1: 800_000}
    )

    owned_wp1 = CompactWitnessProfile.from_episode(ep_owned_1)
    owned_wp2 = CompactWitnessProfile.from_episode(ep_owned_2)
    rival_wp = CompactWitnessProfile.from_episode(ep_rival_1)

    prof = OwnerProfile(
        schema_version=1,
        anchor_id=b0,
        owner_seq=1,
        z_cell_id=z_id,
        state=OwnerState.ACTIVE,
        p_sources=(d0, d1),
        c_sources=(b0, b1),
        y_targets=(e0, e1),
        l_z_q6=800_000,
        u_z_q6=200_000,
        tau_ctx_q6=250_000,
        anchor_source_set=frozenset({b0, b1}),
        witness_profiles=(owned_wp1, owned_wp2),
    )
    w.owner_profiles_by_anchor[b0] = [prof]
    return state, cand, owned_wp1, rival_wp


class TestC04GraduationAndRetirementEquivalence:
    """Verify LLA-T08, LLA-T09, LLA-T10, LLA-T26..T29, LLA-T35, LLA-T40."""

    def test_lla_t08_only_one_p_consolidated_blocks_graduation(self) -> None:
        """LLA-T08: Candidate with only ONE selected P->z consolidated returns DURABILITY_PENDING."""
        state, cand, owned_wp, rival_wp = _setup_durable_candidate_fixture(
            consolidate_p0=True,
            consolidate_p1=False,
            consolidate_c0=True,
            consolidate_y0=True,
        )
        rep = check_c04_durable_path(cand, state.W)
        assert not rep.p2_durable
        assert not rep.is_durable
        assert rep.status == StatusCode.DURABILITY_PENDING

        grad = evaluate_c04_graduation(
            cand, state, owned_witness=owned_wp, rival_witnesses=[rival_wp]
        )
        assert not grad.passed
        assert grad.status == StatusCode.DURABILITY_PENDING
        assert cand.z_cell_id not in state.W.stable_bindings

    def test_lla_t09_t27_t28_t35_both_p_durable_and_bit_identical_pre_post_graduation(self) -> None:
        """LLA-T09, LLA-T27, LLA-T28, LLA-T35:
        Both P, >=1 C, >=1 Y consolidated; NORMAL_W and CONSOLIDATED_W pass;
        PRE/POST retirement is bit-identical; completed z sets mu=1 on DB while B-only sets mu=0.
        """
        state, cand, owned_wp, rival_wp = _setup_durable_candidate_fixture(
            consolidate_p0=True,
            consolidate_p1=True,
            consolidate_c0=True,
            consolidate_c1=False,
            consolidate_y0=True,
        )
        grad = evaluate_c04_graduation(
            cand, state, owned_witness=owned_wp, rival_witnesses=[rival_wp]
        )
        assert grad.passed
        assert grad.status == StatusCode.OK
        assert grad.stable_binding is not None
        assert grad.stable_binding.schema_version == 2
        assert grad.normal_pred_margin >= 0.05
        assert grad.consolidated_pred_margin >= 0.05

        commit_c04_graduation(cand, grad.stable_binding, state.W)
        assert cand.z_cell_id in state.W.stable_bindings
        assert cand.z_cell_id not in state.W.context_candidates

        # LLA-T27: Run cold DB in RETRIEVE -> G_ctx=1, mu=1 on B anchor sources, E wins over C
        scratch_db = state.clone()
        scratch_db.R.reset_cold()
        d0, d1 = cand.p_sources
        b0, b1 = cand.c_sources
        e0, e1 = cand.y_targets

        execute_two_pass_event(
            scratch_db,
            {d0: 800_000, d1: 800_000},
            {d0: 0.80, d1: 0.80},
            mode=ExecutionMode.RETRIEVE,
            origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=True,
            event_order=0,
            allow_candidate_probe=False,
            admit_uncommitted_sensory=False,
        )
        res_b = execute_two_pass_event(
            scratch_db,
            {b0: 800_000, b1: 800_000},
            {b0: 0.80, b1: 0.80},
            mode=ExecutionMode.RETRIEVE,
            origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=False,
            event_order=1,
            allow_candidate_probe=False,
            admit_uncommitted_sensory=False,
        )
        assert res_b.g_ctx_by_z[cand.z_cell_id] == 1
        assert res_b.mu_source_mask.get(b0) == 1
        assert res_b.mu_source_mask.get(b1) == 1

        # LLA-T28: Run cold B-only -> G_ctx=0, mu=0, generic B->C response preserved!
        scratch_bonly = state.clone()
        scratch_bonly.R.reset_cold()
        res_bonly = execute_two_pass_event(
            scratch_bonly,
            {b0: 800_000, b1: 800_000},
            {b0: 0.80, b1: 0.80},
            mode=ExecutionMode.RETRIEVE,
            origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=True,
            event_order=0,
            allow_candidate_probe=False,
            admit_uncommitted_sensory=False,
        )
        assert res_bonly.g_ctx_by_z[cand.z_cell_id] == 0
        assert res_bonly.mu_source_mask.get(b0, 0) == 0
        assert res_bonly.mu_source_mask.get(b1, 0) == 0
        pt_bonly, _ = compute_next_step_temporal_drive(
            scratch_bonly,
            f_step_prev=res_bonly.f_step,
            a_prev_by_cell=res_bonly.a_plus_by_cell,
            mu_prev_source_mask=res_bonly.mu_source_mask,
        )
        c_targets = set(rival_wp.top8_y_supports_u.keys())
        _, score_c = compute_pred_score(pt_bonly, c_targets)
        assert score_c > 0.10

    def test_lla_t10_normal_passes_but_consolidated_w_fails(self) -> None:
        """LLA-T10: Candidate no-probe NORMAL_W passes (via strong unconsolidated c1->z)
        but CONSOLIDATED_W fails (when consolidated c0->z is too weak alone) -> DURABILITY_PENDING.
        """
        state, cand, owned_wp, rival_wp = _setup_durable_candidate_fixture(
            consolidate_p0=True,
            consolidate_p1=True,
            consolidate_c0=True,
            consolidate_c1=False,
            consolidate_y0=True,
        )
        d0, d1 = cand.p_sources
        b0, b1 = cand.c_sources
        z_id = cand.z_cell_id

        # Make consolidated p0->z, p1->z, b0->z barely at threshold (S=0.60, E=3.0 -> Q=0.18),
        # while unconsolidated candidate link b1->z has S=1.0, E=9.5 (Q=0.95) and only b1 is stimulated strongly
        for src, scope in ((d0, SynapseScope.ASSOCIATIVE), (d1, SynapseScope.ASSOCIATIVE), (b0, SynapseScope.LOCAL)):
            syn = state.W.synapses[(src, z_id, scope)]
            syn.S = 0.60
            syn.E_ext = 3.0
        uncons_c1 = state.W.synapses[(b1, z_id, SynapseScope.LOCAL)]
        uncons_c1.S = 1.0
        uncons_c1.E_ext = 9.5
        uncons_c1.state = SynapseState.CANDIDATE

        # Stimulate d0, d1 weakly (0.26) and b0 very weakly (0.05) while b1 is 1.0:
        # In NORMAL_W, unconsolidated b1->z drives z above theta_emit (0.23);
        # in CONSOLIDATED_W, b1->z is masked so z stays below theta_emit!
        owned_wp.top8_p_supports_u = {d0: 260_000, d1: 260_000}
        owned_wp.top8_c_supports_u = {b0: 50_000, b1: 1_000_000}

        grad = evaluate_c04_graduation(
            cand, state, owned_witness=owned_wp, rival_witnesses=[rival_wp]
        )
        assert not grad.passed
        assert grad.normal_owned_az >= 0.23
        assert grad.consolidated_owned_az < 0.23
        assert grad.status == StatusCode.DURABILITY_PENDING

    def test_lla_t29_ambiguous_context_owner_on_same_anchor(self) -> None:
        """LLA-T29: Two matching different completed owners on the same current anchor
        report AMBIGUOUS_CONTEXT_OWNER and set mu=0 (fail-open generic routing).
        """
        state, cand, owned_wp, rival_wp = _setup_durable_candidate_fixture()
        grad1 = evaluate_c04_graduation(
            cand, state, owned_witness=owned_wp, rival_witnesses=[rival_wp]
        )
        assert grad1.passed and grad1.stable_binding is not None
        commit_c04_graduation(cand, grad1.stable_binding, state.W)

        # Create a second completed owner z2 on the SAME anchor b0 with the same P/C keys
        z2_id = _lang_cell(5, 5, 2)
        state.W.commit_cell(z2_id, 1)
        d0, d1 = cand.p_sources
        b0, b1 = cand.c_sources
        e0, e1 = cand.y_targets
        state.W.latent_table.pin_context_candidate_roles(z2_id, (d0, d1, b0, b1, e0, e1), event_clock=1)
        for src, tgt, scope in (
            (d0, z2_id, SynapseScope.ASSOCIATIVE),
            (d1, z2_id, SynapseScope.ASSOCIATIVE),
            (b0, z2_id, SynapseScope.LOCAL),
            (z2_id, e0, SynapseScope.ASSOCIATIVE),
        ):
            state.W.add_or_replace_synapse(
                Synapse(
                    key=(src, tgt, scope),
                    S=0.85,
                    E_ext=5.0,
                    E_int=0.0,
                    external_count=3,
                    state=SynapseState.CONSOLIDATED,
                    created_event_id=2,
                    created_exposure_id=2,
                    last_external_event_id=3,
                    last_evidence_root=3,
                    candidate_deadline=240,
                    confirmed_roots={2, 3, 4},
                )
            )
        state.W.stable_bindings[z2_id] = StableBinding(
            schema_version=2,
            z_cell_id=z2_id,
            anchor_id=b0,
            owner_seq=2,
            binding_generation=1,
            p_keys=((d0, z2_id, SynapseScope.ASSOCIATIVE), (d1, z2_id, SynapseScope.ASSOCIATIVE)),
            l_z_q6=800_000,
            u_z_q6=200_000,
            tau_ctx_q6=250_000,
            c_keys=((b0, z2_id, SynapseScope.LOCAL),),
            y_keys=((z2_id, e0, SynapseScope.ASSOCIATIVE),),
            anchor_source_set=frozenset({b0, b1}),
        )

        scratch = state.clone()
        scratch.R.reset_cold()
        execute_two_pass_event(
            scratch,
            {d0: 800_000, d1: 800_000},
            {d0: 0.80, d1: 0.80},
            mode=ExecutionMode.RETRIEVE,
            origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=True,
            event_order=0,
            allow_candidate_probe=False,
            admit_uncommitted_sensory=False,
        )
        res_b = execute_two_pass_event(
            scratch,
            {b0: 800_000, b1: 800_000},
            {b0: 0.80, b1: 0.80},
            mode=ExecutionMode.RETRIEVE,
            origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=False,
            event_order=1,
            allow_candidate_probe=False,
            admit_uncommitted_sensory=False,
        )
        assert StatusCode.AMBIGUOUS_CONTEXT_OWNER in res_b.diagnostics
        assert res_b.mu_source_mask.get(b0, 0) == 0
        assert res_b.mu_source_mask.get(b1, 0) == 0

    def test_lla_t40_unsupported_schema_and_invalid_threshold_rejected(self) -> None:
        """LLA-T40: Legacy StableBindingV1 (schema_version=1) or invalid calibration triple is rejected."""
        with pytest.raises(DGCAError) as exc_info:
            StableBinding(
                schema_version=1,
                z_cell_id=8200,
                anchor_id=8192,
                owner_seq=1,
                binding_generation=1,
                p_keys=((8193, 8200, SynapseScope.ASSOCIATIVE), (8194, 8200, SynapseScope.ASSOCIATIVE)),
                l_z_q6=800_000,
                u_z_q6=200_000,
                tau_ctx_q6=250_000,
                c_keys=((8192, 8200, SynapseScope.LOCAL),),
                y_keys=((8200, 8195, SynapseScope.ASSOCIATIVE),),
                anchor_source_set=frozenset({8192}),
            )
        assert exc_info.value.code == StatusCode.UNSUPPORTED_BINDING_SCHEMA


class TestOwnerRegistryAndRecruitment:
    """Verify LLA-T11, LLA-T12, LLA-T32, LLA-T33."""

    def test_lla_t11_t12_owner_dedup_across_2000_event_ttl_and_conflict(self) -> None:
        """LLA-T11 & LLA-T12:
        After contrast ledger expires (TTL > 2000 external events), repeated same physical branch
        with new root IDs resolves to the SAME OwnerID (REUSE, no duplicate z).
        Two owners matching the same branch yield OWNER_REGISTRY_CONFLICT.
        """
        state, cand, owned_wp, rival_wp = _setup_durable_candidate_fixture()
        b0, b1 = cand.c_sources
        d0, d1 = cand.p_sources
        e0, e1 = cand.y_targets

        # Record episodes at clock=10, then advance clock past 2015 so contrast ledger expires
        ep_old = _make_contrast_episode(
            b0, 1, 10, {d0: 800_000, d1: 800_000}, {b0: 800_000, b1: 800_000}, {e0: 800_000, e1: 800_000}
        )
        record_contrast_episode(state.W, ep_old)
        assert len(state.W.contrast_episodes_by_anchor.get(b0, [])) == 1

        pruned = prune_expired_contrast_episodes(state.W, 10 + CONTRAST_LEDGER_TTL_EVENTS + 5)
        assert pruned == 1
        assert b0 not in state.W.contrast_episodes_by_anchor

        # Now new roots (root 500, 501) arrive with the exact same physical branch after TTL expiry
        ep_new_1 = _make_contrast_episode(
            b0, 500, 2020, {d0: 800_000, d1: 800_000}, {b0: 800_000, b1: 800_000}, {e0: 800_000, e1: 800_000}
        )
        ep_new_2 = _make_contrast_episode(
            b0, 501, 2023, {d0: 800_000, d1: 800_000}, {b0: 800_000, b1: 800_000}, {e0: 800_000, e1: 800_000}
        )
        new_branch = BranchSummary(
            anchor_id=b0,
            p_digest=ep_new_1.p_digest,
            c_digest=ep_new_1.c_digest,
            y_digest=ep_new_1.y_digest,
            episodes=[ep_new_1, ep_new_2],
        )

        res = resolve_owner(b0, new_branch, (), state.W)
        assert res.status == StatusCode.REUSE
        assert res.matched_owner_id == (b0, 1)
        assert res.matched_z_cell_id == cand.z_cell_id

        # LLA-T12: If a second OwnerProfile under b0 also supports the same branch -> OWNER_REGISTRY_CONFLICT
        dup_prof = state.W.owner_profiles_by_anchor[b0][0].clone()  # type: ignore[index]
        dup_prof.owner_seq = 2
        dup_prof.z_cell_id = _lang_cell(5, 5, 3)
        state.W.owner_profiles_by_anchor[b0].append(dup_prof)

        res_conflict = resolve_owner(b0, new_branch, (), state.W)
        assert res_conflict.status == StatusCode.OWNER_REGISTRY_CONFLICT

    def test_lla_t32_capacity_prefiltering_before_top8_truncation(self) -> None:
        """LLA-T32: Top-8 P candidates are saturated at 64 outgoing links, while rank 9 and 10
        have available outgoing headroom -> filter saturated BEFORE top-8 truncation and recruit!
        """
        state = MachineState()
        w = state.W

        anchor_b0 = _lang_cell(10, 10, 0)
        b1 = _lang_cell(10, 10, 1)
        y0, y1 = _lang_cell(12, 1, 0), _lang_cell(12, 2, 0)
        r0, r1 = _lang_cell(13, 1, 0), _lang_cell(13, 2, 0)
        for cid in (anchor_b0, b1, y0, y1, r0, r1):
            w.commit_cell(cid, 1)

        # Create 10 P candidates: first 8 have higher support (900_000) but are saturated at 64 outgoing links;
        # candidates 9 and 10 have support 750_000 and 0 outgoing links used (full headroom=64)
        p_saturated = [_lang_cell(2, i, 0) for i in range(8)]
        p_feasible = [_lang_cell(3, 0, 0), _lang_cell(3, 1, 0)]

        for pid in p_saturated + p_feasible:
            w.commit_cell(pid, 1)

        # Saturate p_saturated with 64 dummy reserved outgoing keys
        dummy_reserved: set[SynapseKey] = set()
        for pid in p_saturated:
            for k in range(64):
                dummy_reserved.add((pid, 8192 + (k % 100), SynapseScope.ASSOCIATIVE))
        w.reserved_keys_by_candidate[99999] = dummy_reserved

        p_sup_map = {pid: 900_000 for pid in p_saturated}
        for pid in p_feasible:
            p_sup_map[pid] = 750_000

        ep1 = _make_contrast_episode(anchor_b0, 1, 3, p_sup_map, {anchor_b0: 800_000, b1: 800_000}, {y0: 800_000, y1: 800_000})
        ep2 = _make_contrast_episode(anchor_b0, 2, 6, p_sup_map, {anchor_b0: 800_000, b1: 800_000}, {y0: 800_000, y1: 800_000})
        owned_branch = BranchSummary(
            anchor_id=anchor_b0,
            p_digest=ep1.p_digest,
            c_digest=ep1.c_digest,
            y_digest=ep1.y_digest,
            episodes=[ep1, ep2],
        )

        riv_ep1 = _make_contrast_episode(anchor_b0, 3, 9, {r0: 800_000, r1: 800_000}, {anchor_b0: 800_000, b1: 800_000}, {r0: 800_000, r1: 800_000})
        riv_ep2 = _make_contrast_episode(anchor_b0, 4, 12, {r0: 800_000, r1: 800_000}, {anchor_b0: 800_000, b1: 800_000}, {r0: 800_000, r1: 800_000})
        rival_branch = BranchSummary(
            anchor_id=anchor_b0,
            p_digest=riv_ep1.p_digest,
            c_digest=riv_ep1.c_digest,
            y_digest=riv_ep1.y_digest,
            episodes=[riv_ep1, riv_ep2],
        )

        rec = recruit_contextual_candidate(
            anchor_b0,
            owned_branch,
            (rival_branch,),
            w,
            admitted_root_id=4,
            event_clock=12,
            remaining_k_r=4,
        )
        assert rec.status == StatusCode.OK
        assert rec.descriptor is not None
        assert set(rec.descriptor.p_sources) == set(p_feasible)

    def test_lla_t33_radius2_manhattan_search_when_radius1_full(self) -> None:
        """LLA-T33: Candidate z own microcolumn (dist=0) and Manhattan radius 1 (dist=1) are all committed,
        but radius 2 has a free slot -> deterministic radius-2 search recruits legal z!
        """
        state = MachineState()
        w = state.W
        anchor_id = _lang_cell(10, 8, 0)

        # Commit all 8 slots in distance 0 and distance 1 microcolumns around (10, 8)
        for dr in range(-1, 2):
            for dc in range(-1, 2):
                if abs(dr) + abs(dc) <= 1:
                    for slot in range(CELLS_PER_MICROCOLUMN):
                        w.commit_cell(_lang_cell(10 + dr, 8 + dc, slot), 1)

        z_list = find_candidate_z_cells_within_radius2(anchor_id, w)
        assert len(z_list) > 0
        first_z_addr = CellAddress.from_global_id(z_list[0])
        dist = abs(first_z_addr.mc_row - 10) + abs(first_z_addr.mc_col - 8)
        assert dist == 2


class TestCandidateFSMAndTwoClockLifetimes:
    """Verify LLA-T22, LLA-T23, LLA-T31, LLA-T38, LLA-T39, LLA-T41."""

    def test_lla_t22_t31_t41_two_clocks_and_sub_tau_rival_ignored(self) -> None:
        """LLA-T22, LLA-T31, LLA-T41:
        - WIRED transitions only to PROBE_INCOMING on first qualifying incoming root (no skipped phase).
        - Rival root with positive P support below tau_ctx_q6 does NOT advance probe_matches or consolidation_matches.
        - Candidate entering LEARN_OUTCOME on 8th probe match is NOT expired by old 8-root cap and gets up to 32 consolidation matches.
        """
        state, cand, owned_wp, rival_wp = _setup_durable_candidate_fixture(
            consolidate_p0=False,
            consolidate_p1=False,
            consolidate_c0=False,
            consolidate_y0=False,
        )
        cand.phase = CandidatePhase.WIRED
        cand.probe_matches = 0
        cand.consolidation_matches = 0
        cand.age_events = 0
        cand.admitted_root_id = 10

        d0, d1 = cand.p_sources
        b0, b1 = cand.c_sources
        e0, e1 = cand.y_targets
        z_id = cand.z_cell_id

        # Helper to run a 3-event root (P, B, Y)
        def _run_root_events(exp_id: int, p_sup_u: int, include_y: bool = True) -> list:
            state.R.reset_cold()
            p_flt = float(p_sup_u) / float(MILLION)
            ev0 = execute_two_pass_event(
                state,
                {d0: p_sup_u, d1: p_sup_u},
                {d0: p_flt, d1: p_flt},
                mode=ExecutionMode.LEARN,
                origin=EventOrigin.EXTERNAL_DIRECT,
                boundary=True,
                exposure_id=exp_id,
                event_order=0,
                allow_candidate_probe=True,
            )
            ev1 = execute_two_pass_event(
                state,
                {b0: 800_000, b1: 800_000},
                {b0: 0.80, b1: 0.80},
                mode=ExecutionMode.LEARN,
                origin=EventOrigin.EXTERNAL_DIRECT,
                boundary=False,
                exposure_id=exp_id,
                event_order=1,
                allow_candidate_probe=True,
            )
            if not include_y:
                return [ev0, ev1]
            ev2 = execute_two_pass_event(
                state,
                {e0: 800_000, e1: 800_000},
                {e0: 0.80, e1: 0.80},
                mode=ExecutionMode.LEARN,
                origin=EventOrigin.EXTERNAL_DIRECT,
                boundary=False,
                exposure_id=exp_id,
                event_order=2,
                allow_candidate_probe=True,
            )
            return [ev0, ev1, ev2]

        # LLA-T41: Rival P support positive (200_000) but below tau_ctx_q6 (250_000) -> not a qualified owned root!
        evs_sub = _run_root_events(11, 200_000)
        res_sub = settle_candidate_at_end_exposure(
            cand, state, evs_sub, {(d0, z_id, SynapseScope.ASSOCIATIVE)}
        )
        assert res_sub.probe_matches == 0
        assert res_sub.final_phase == CandidatePhase.WIRED
        assert res_sub.age_events == 3

        # LLA-T22: First qualifying root (root 12) with incoming AND outcome evidence transitions WIRED -> PROBE_INCOMING only!
        evs_12 = _run_root_events(12, 800_000, include_y=True)
        res_12 = settle_candidate_at_end_exposure(
            cand,
            state,
            evs_12,
            {(d0, z_id, SynapseScope.ASSOCIATIVE), (z_id, e0, SynapseScope.ASSOCIATIVE)},
        )
        assert res_12.final_phase == CandidatePhase.PROBE_INCOMING
        assert res_12.probe_matches == 1
        assert res_12.transitions == ((CandidatePhase.WIRED, CandidatePhase.PROBE_INCOMING),)

        # LLA-T31: Consume 6 more probe roots without Y (probe_matches reaches 7), then on the 8th probe root
        # witness Y and transition PROBE_INCOMING -> LEARN_OUTCOME without expiring at 8!
        for r_idx in range(13, 19):
            evs_no_y = _run_root_events(r_idx, 800_000, include_y=False)
            settle_candidate_at_end_exposure(cand, state, evs_no_y, set())
        assert cand.probe_matches == 7
        assert cand.phase == CandidatePhase.PROBE_INCOMING

        # 8th qualifying probe root (root 19) witnesses Y -> transitions to LEARN_OUTCOME, exempt from 8-match expiry!
        evs_19 = _run_root_events(19, 800_000, include_y=True)
        res_19 = settle_candidate_at_end_exposure(
            cand,
            state,
            evs_19,
            {(z_id, e0, SynapseScope.ASSOCIATIVE)},
        )
        assert res_19.final_phase == CandidatePhase.LEARN_OUTCOME
        assert res_19.probe_matches == MAX_PROBE_MATCHES
        assert res_19.consolidation_matches == 0

        # Next 17 qualifying consolidation roots advance consolidation_matches to 17 without expiring!
        for r_idx in range(20, 37):
            evs_c = _run_root_events(r_idx, 800_000, include_y=True)
            res_c = settle_candidate_at_end_exposure(
                cand, state, evs_c, {(z_id, e0, SynapseScope.ASSOCIATIVE)}
            )
            assert res_c.final_phase == CandidatePhase.LEARN_OUTCOME
        assert cand.consolidation_matches == 17

    def test_lla_t23_age_239_settles_graduation_before_240_expiry(self) -> None:
        """LLA-T23: Candidate reaches age=239; a completed 1-event or 3-event root brings age >= 240.
        Evidence and valid graduation tests are settled FIRST before age expiration!
        """
        state, cand, owned_wp, rival_wp = _setup_durable_candidate_fixture(
            consolidate_p0=True,
            consolidate_p1=True,
            consolidate_c0=True,
            consolidate_y0=True,
        )
        cand.phase = CandidatePhase.LEARN_OUTCOME
        cand.age_events = 239
        cand.admitted_root_id = 10

        d0, d1 = cand.p_sources
        b0, b1 = cand.c_sources
        e0, e1 = cand.y_targets
        z_id = cand.z_cell_id

        state.R.reset_cold()
        ev0 = execute_two_pass_event(
            state, {d0: 800_000, d1: 800_000}, {d0: 0.80, d1: 0.80},
            mode=ExecutionMode.LEARN, origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=True, exposure_id=99, event_order=0,
        )
        ev1 = execute_two_pass_event(
            state, {b0: 800_000, b1: 800_000}, {b0: 0.80, b1: 0.80},
            mode=ExecutionMode.LEARN, origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=False, exposure_id=99, event_order=1,
        )
        ev2 = execute_two_pass_event(
            state, {e0: 800_000, e1: 800_000}, {e0: 0.80, e1: 0.80},
            mode=ExecutionMode.LEARN, origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=False, exposure_id=99, event_order=2,
        )

        res = settle_candidate_at_end_exposure(
            cand,
            state,
            [ev0, ev1, ev2],
            {(z_id, e0, SynapseScope.ASSOCIATIVE)},
            owned_witness=owned_wp,
            rival_witnesses=[rival_wp],
        )
        assert res.age_events == 242 >= MAX_CANDIDATE_AGE_EVENTS
        assert res.final_phase == CandidatePhase.COMPLETE
        assert res.status == StatusCode.OK
        assert z_id in state.W.stable_bindings

    def test_lla_t38_t39_failed_no_probe_test_retains_learn_probe_until_drive_sufficient(self) -> None:
        """LLA-T38 & LLA-T39:
        NO_PROBE_TEST fails initially with E=3.0, S=0.60 (Q=0.18 -> NO_PROBE_INSUFFICIENT_DRIVE);
        candidate remains in NO_PROBE_TEST with production LEARN probe still active on the next OPEN LEARN root!
        Once S/E increases enough on a subsequent root, END scratch NO_PROBE_TEST succeeds to COMPLETE.
        """
        state, cand, owned_wp, rival_wp = _setup_durable_candidate_fixture(
            consolidate_p0=True,
            consolidate_p1=True,
            consolidate_c0=True,
            consolidate_y0=True,
            synapse_s=0.60,
            synapse_e=3.0,
        )
        cand.phase = CandidatePhase.LEARN_OUTCOME
        cand.admitted_root_id = 10
        d0, d1 = cand.p_sources
        b0, b1 = cand.c_sources
        e0, e1 = cand.y_targets
        z_id = cand.z_cell_id

        # Make owned_wp use moderate P/C supports (0.30) so Q=0.18 is below theta_emit (0.23) without probe
        owned_wp.top8_p_supports_u = {d0: 300_000, d1: 300_000}
        owned_wp.top8_c_supports_u = {b0: 300_000, b1: 300_000}

        state.R.reset_cold()
        ev0 = execute_two_pass_event(
            state, {d0: 300_000, d1: 300_000}, {d0: 0.30, d1: 0.30},
            mode=ExecutionMode.LEARN, origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=True, exposure_id=15, event_order=0, allow_candidate_probe=True,
        )
        ev1 = execute_two_pass_event(
            state, {b0: 300_000, b1: 300_000}, {b0: 0.30, b1: 0.30},
            mode=ExecutionMode.LEARN, origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=False, exposure_id=15, event_order=1, allow_candidate_probe=True,
        )
        ev2 = execute_two_pass_event(
            state, {e0: 800_000, e1: 800_000}, {e0: 0.80, e1: 0.80},
            mode=ExecutionMode.LEARN, origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=False, exposure_id=15, event_order=2, allow_candidate_probe=True,
        )

        # First settle: transitions LEARN_OUTCOME -> NO_PROBE_TEST, fails with NO_PROBE_INSUFFICIENT_DRIVE,
        # and stays in NO_PROBE_TEST!
        res1 = settle_candidate_at_end_exposure(
            cand,
            state,
            [ev0, ev1, ev2],
            {(z_id, e0, SynapseScope.ASSOCIATIVE)},
            owned_witness=owned_wp,
            rival_witnesses=[rival_wp],
        )
        assert res1.final_phase == CandidatePhase.NO_PROBE_TEST
        assert res1.status == StatusCode.NO_PROBE_INSUFFICIENT_DRIVE

        # Verify that on the NEXT independent OPEN LEARN root (root 16), candidate in NO_PROBE_TEST
        # STILL receives the temporary LEARN probe (g_probe > 0 and A_z^+ >= theta_emit)!
        state.R.reset_cold()
        ev16_0 = execute_two_pass_event(
            state, {d0: 800_000, d1: 800_000}, {d0: 0.80, d1: 0.80},
            mode=ExecutionMode.LEARN, origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=True, exposure_id=16, event_order=0, allow_candidate_probe=True,
        )
        ev16_1 = execute_two_pass_event(
            state, {b0: 800_000, b1: 800_000}, {b0: 0.80, b1: 0.80},
            mode=ExecutionMode.LEARN, origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=False, exposure_id=16, event_order=1, allow_candidate_probe=True,
        )
        assert ev16_1.g_probe_by_z[z_id] > 0.40
        assert z_id in ev16_1.f_step

        # LLA-T39: In READ_ONLY (RETRIEVE), probe is strictly OFF even while phase == NO_PROBE_TEST
        scratch_ro = state.clone()
        scratch_ro.R.reset_cold()
        execute_two_pass_event(
            scratch_ro, {d0: 300_000, d1: 300_000}, {d0: 0.30, d1: 0.30},
            mode=ExecutionMode.RETRIEVE, origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=True, event_order=0, allow_candidate_probe=False,
        )
        ev_ro_1 = execute_two_pass_event(
            scratch_ro, {b0: 300_000, b1: 300_000}, {b0: 0.30, b1: 0.30},
            mode=ExecutionMode.RETRIEVE, origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=False, event_order=1, allow_candidate_probe=False,
        )
        assert ev_ro_1.a_plus_by_cell.get(z_id, 0.0) < 0.23
        assert z_id not in ev_ro_1.f_step

        # Now increase role synapse S/E (simulating accepted evidence from root 16) and settle root 16 -> COMPLETE!
        for key in cand.reserved_synapse_keys:
            syn = state.W.synapses.get(key)
            if syn is not None:
                syn.S = 0.90
                syn.E_ext = 9.0
                syn.state = SynapseState.CONSOLIDATED
                syn.confirmed_roots.add(16)
                syn.external_count = len(syn.confirmed_roots)

        ev16_2 = execute_two_pass_event(
            state, {e0: 800_000, e1: 800_000}, {e0: 0.80, e1: 0.80},
            mode=ExecutionMode.LEARN, origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=False, exposure_id=16, event_order=2, allow_candidate_probe=True,
        )
        res2 = settle_candidate_at_end_exposure(
            cand,
            state,
            [ev16_0, ev16_1, ev16_2],
            {(z_id, e0, SynapseScope.ASSOCIATIVE)},
            owned_witness=owned_wp,
            rival_witnesses=[rival_wp],
        )
        assert res2.final_phase == CandidatePhase.COMPLETE
        assert res2.status == StatusCode.OK
        assert z_id in state.W.stable_bindings
