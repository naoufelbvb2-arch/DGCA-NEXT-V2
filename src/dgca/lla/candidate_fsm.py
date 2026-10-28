"""Two-Clock Contextual Candidate Probation State Machine and Expiration Settlement.

Normative references:
- DGCA_CORE_RC4_1.md §7.4 & §7.4.1 (Immutable role sets, probation stages, two clocks, transition table)
- DGCA_CORE_RC4_1.md §7.5 (LEARN-only Bootstrap inside the permanent gate)
- DGCA_LLA_RC4_1.md §6.3 (LEARN-only candidate probe, permanence and separated evidence clocks)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from dgca.common.errors import StatusCode
from dgca.common.numeric import q6_from_binary64
from dgca.core.anatomy import SynapseKey, SynapseScope, SynapseState
from dgca.core.dynamics import EventExecutionResult
from dgca.core.sic_v1 import CellAddress
from dgca.core.state import (
    BindingStatus,
    CandidatePhase,
    ContextCandidateDescriptor,
    HSlowState,
    MachineState,
    OwnerState,
    WState,
)
from dgca.encoder.envelope import EventOrigin
from dgca.lla.contrast_ledger import (
    discover_anchor_contrasts,
    extract_contrast_episodes_from_root,
    record_contrast_episode,
)
from dgca.lla.graduation_c04 import (
    GraduationEvaluationResult,
    check_c04_durable_path,
    commit_c04_graduation,
    evaluate_c04_graduation,
)
from dgca.lla.owner_registry import CompactWitnessProfile, OwnerProfile, resolve_owner
from dgca.lla.recruitment import RecruitmentResult, recruit_contextual_candidate
from dgca.lla.witness import ObservationWitness, eligible_external_p

MAX_PROBE_MATCHES: int = 8
MAX_CONSOLIDATION_MATCHES: int = 32
MAX_CANDIDATE_AGE_EVENTS: int = 240
W_CONF_CONTEXT: int = 240


@dataclass(frozen=True, slots=True)
class CandidateRootObservation:
    """Summary of how a completed external root interacted with an active contextual candidate z (Core §7.4)."""

    is_post_admission: bool
    is_qualified_owned_root: bool
    z_emitted_in_f_step: bool
    accepted_incoming_evidence: bool
    accepted_outcome_evidence: bool
    matched_event_order_b: int | None = None


@dataclass(frozen=True, slots=True)
class CandidateSettlementResult:
    """Result of settling a contextual candidate's clocks, phase transitions, and expiration at END_EXPOSURE."""

    z_cell_id: int
    owner_id: tuple[int, int]
    initial_phase: CandidatePhase
    final_phase: CandidatePhase
    transitions: tuple[tuple[CandidatePhase, CandidatePhase], ...]
    probe_matches: int
    consolidation_matches: int
    age_events: int
    status: StatusCode
    graduation_result: GraduationEvaluationResult | None = None


def check_root_qualification_for_candidate(
    cand: ContextCandidateDescriptor,
    event_results: Sequence[EventExecutionResult],
    accepted_keys: set[SynapseKey],
    w_state: WState,
    h_slow: HSlowState | None = None,
) -> CandidateRootObservation:
    """Determine if a completed root is a qualified owned root for cand and inspect its evidence (Core §7.4, LLA-T41).

    Core §7.4:
    A qualified owned root is a completed, independent external exposure *after* admission
    containing the two selected P either directly witnessed or (only for depth > 1) COMPLETE
    derived-external witnessed in event P with Q6(min(P supports)) >= tau_ctx_q6(z),
    >= 1 selected C directly witnessed at the subsequent event B, no collision or boundary,
    and z already committed before B. Positive-but-subthreshold P support is NOT a qualified
    owned contextual root or candidate-clock match.
    """
    if not event_results:
        return CandidateRootObservation(
            is_post_admission=False,
            is_qualified_owned_root=False,
            z_emitted_in_f_step=False,
            accepted_incoming_evidence=False,
            accepted_outcome_evidence=False,
        )

    exp_id = int(event_results[0].exposure_id or 0)
    if exp_id <= cand.admitted_root_id:
        return CandidateRootObservation(
            is_post_admission=False,
            is_qualified_owned_root=False,
            z_emitted_in_f_step=False,
            accepted_incoming_evidence=False,
            accepted_outcome_evidence=False,
        )

    z_id = cand.z_cell_id
    z_region = CellAddress.from_global_id(z_id).region
    p0, p1 = cand.p_sources
    incoming_keys: set[SynapseKey] = {
        (p0, z_id, SynapseScope.ASSOCIATIVE),
        (p1, z_id, SynapseScope.ASSOCIATIVE),
        (cand.c_sources[0], z_id, SynapseScope.LOCAL),
        (cand.c_sources[1], z_id, SynapseScope.LOCAL),
    }
    outcome_keys: set[SynapseKey] = {
        (z_id, cand.y_targets[0], SynapseScope.ASSOCIATIVE),
        (z_id, cand.y_targets[1], SynapseScope.ASSOCIATIVE),
    }

    accepted_incoming = bool(accepted_keys & incoming_keys)
    accepted_outcome = bool(accepted_keys & outcome_keys)

    is_qualified = False
    z_emitted = False
    matched_b_order: int | None = None

    for idx in range(1, len(event_results)):
        ev_prev = event_results[idx - 1]
        ev_curr = event_results[idx]

        if (
            ev_curr.boundary
            or ev_prev.origin != EventOrigin.EXTERNAL_DIRECT
            or ev_curr.origin != EventOrigin.EXTERNAL_DIRECT
            or ev_prev.exposure_id != ev_curr.exposure_id
            or ev_prev.event_order != ev_curr.event_order - 1
        ):
            continue
        if z_id not in ev_curr.committed_before_event:
            continue

        # Check both selected P at ev_prev with exact expected source kind and Q6(min) >= tau_ctx_q6
        kind0, sup0 = eligible_external_p(p0, ev_prev, w_state)
        kind1, sup1 = eligible_external_p(p1, ev_prev, w_state)
        if kind0 is None or kind1 is None or sup0 <= 0.0 or sup1 <= 0.0:
            continue
        if (
            kind0 != cand.p_source_kinds[0]
            or kind1 != cand.p_source_kinds[1]
        ):
            continue

        t_q6 = min(q6_from_binary64(sup0), q6_from_binary64(sup1))
        if t_q6 < cand.tau_ctx_q6:
            # Positive-but-subthreshold P support is NOT a qualified owned root (LLA-T41)
            continue

        # Check >= 1 selected C directly witnessed at ev_curr
        has_c = any(
            cid in ev_curr.obs_eligible_cells
            and cid in ev_curr.typed_supports
            and ev_curr.typed_supports[cid].q6_train > 0
            for cid in cand.c_sources
        )
        if not has_c:
            continue

        is_qualified = True
        matched_b_order = ev_curr.event_order
        theta_emit = h_slow.get_theta_emit(z_region) if h_slow is not None else 0.23
        if (
            z_id in ev_curr.f_step
            and ev_curr.a_plus_by_cell.get(z_id, 0.0) >= theta_emit
        ):
            z_emitted = True

        # Also verify if next event ev_next witnessed an actual selected Y
        if idx + 1 < len(event_results):
            ev_next = event_results[idx + 1]
            if (
                not ev_next.boundary
                and ev_next.origin == EventOrigin.EXTERNAL_DIRECT
                and ev_next.exposure_id == ev_curr.exposure_id
                and ev_next.event_order == ev_curr.event_order + 1
            ):
                has_y_witness = any(
                    yid in ev_next.obs_eligible_cells
                    and yid in ev_next.typed_supports
                    and ev_next.typed_supports[yid].q6_train > 0
                    for yid in cand.y_targets
                )
                if not has_y_witness:
                    accepted_outcome = False
            else:
                accepted_outcome = False
        else:
            accepted_outcome = False
        break

    return CandidateRootObservation(
        is_post_admission=True,
        is_qualified_owned_root=is_qualified,
        z_emitted_in_f_step=z_emitted,
        accepted_incoming_evidence=accepted_incoming,
        accepted_outcome_evidence=accepted_outcome,
        matched_event_order_b=matched_b_order,
    )


def expire_contextual_candidate(
    cand: ContextCandidateDescriptor,
    w_state: WState,
) -> None:
    """Transition candidate to FAILED_OR_EXPIRED, release unprotected claims, and update OwnerProfile (Core §7.4.1)."""
    z_id = cand.z_cell_id
    cand.phase = CandidatePhase.FAILED_OR_EXPIRED
    cand.status = BindingStatus.STALE

    has_consolidated_knowledge = False
    for key in list(cand.reserved_synapse_keys):
        syn = w_state.synapses.get(key)
        if syn is not None:
            if syn.state == SynapseState.CONSOLIDATED:
                has_consolidated_knowledge = True
            else:
                w_state.remove_synapse(key)

    w_state.reserved_keys_by_candidate.pop(z_id, None)

    # Release temporary candidate pins (live consolidated links remain protected by get_protected_bidirectional_neighbors)
    w_state.latent_table.release_candidate_pins(z_id)

    # Update OwnerProfile state: EXPIRED_VALIDATED if partial consolidated links exist, else EXPIRED_EMPTY
    profiles: list[OwnerProfile] = list(
        w_state.owner_profiles_by_anchor.get(cand.anchor_id, [])  # type: ignore[arg-type]
    )
    for prof in profiles:
        if prof.owner_id == cand.owner_id:
            prof.state = (
                OwnerState.EXPIRED_VALIDATED
                if has_consolidated_knowledge
                else OwnerState.EXPIRED_EMPTY
            )
            break


def settle_candidate_at_end_exposure(
    cand: ContextCandidateDescriptor,
    state: MachineState,
    event_results: Sequence[EventExecutionResult],
    accepted_keys: set[SynapseKey],
    *,
    owned_witness: CompactWitnessProfile | None = None,
    rival_witnesses: Sequence[CompactWitnessProfile] | None = None,
    force_no_probe_retest: bool = False,
) -> CandidateSettlementResult:
    """Settle candidate clocks, phase transitions, C04 graduation, and expiration at END_EXPOSURE (Core §7.4.1, LLA §6.3).

    Enforces:
    - Settle evidence and finite transition table FIRST before checking expiration caps (LLA-T23)
    - WIRED -> PROBE_INCOMING cannot skip phases in one END (LLA-T22)
    - Root entering LEARN_OUTCOME charges probe_matches, starts consolidation_matches at 0, and is exempt
      from the 8-match discovery expiration just met (Core §7.4.1, LLA-T31)
    - LEARN_OUTCOME can transition to NO_PROBE_TEST and immediately run scratch preflight to COMPLETE in same END
    - Failed NO_PROBE_TEST leaves candidate in NO_PROBE_TEST with production LEARN probe enabled for future roots (LLA-T38)
    """
    initial_phase = cand.phase
    if initial_phase in (CandidatePhase.COMPLETE, CandidatePhase.FAILED_OR_EXPIRED):
        return CandidateSettlementResult(
            z_cell_id=cand.z_cell_id,
            owner_id=cand.owner_id,
            initial_phase=initial_phase,
            final_phase=initial_phase,
            transitions=(),
            probe_matches=cand.probe_matches,
            consolidation_matches=cand.consolidation_matches,
            age_events=cand.age_events,
            status=StatusCode.IDEMPOTENT_NOOP,
        )

    obs = check_root_qualification_for_candidate(
        cand, event_results, accepted_keys, state.W, state.H_slow
    )
    if not obs.is_post_admission:
        return CandidateSettlementResult(
            z_cell_id=cand.z_cell_id,
            owner_id=cand.owner_id,
            initial_phase=initial_phase,
            final_phase=cand.phase,
            transitions=(),
            probe_matches=cand.probe_matches,
            consolidation_matches=cand.consolidation_matches,
            age_events=cand.age_events,
            status=StatusCode.OK,
        )

    # Advance total age by external events in this completed root
    cand.age_events += len(event_results)

    transitions: list[tuple[CandidatePhase, CandidatePhase]] = []
    grad_result: GraduationEvaluationResult | None = None
    last_status = StatusCode.OK

    # 1. Finite State Machine Transitions (settled BEFORE expiration check per Core §7.4.1 & LLA-T23)
    if initial_phase == CandidatePhase.WIRED:
        if obs.is_qualified_owned_root:
            cand.probe_matches += 1
            if obs.z_emitted_in_f_step and obs.accepted_incoming_evidence:
                cand.phase = CandidatePhase.PROBE_INCOMING
                transitions.append((CandidatePhase.WIRED, CandidatePhase.PROBE_INCOMING))

    elif initial_phase == CandidatePhase.PROBE_INCOMING:
        if obs.is_qualified_owned_root:
            # Qualifying root consumed while entering LEARN_OUTCOME is charged ONLY to the probe clock
            cand.probe_matches += 1
            if obs.z_emitted_in_f_step and obs.accepted_outcome_evidence:
                cand.phase = CandidatePhase.LEARN_OUTCOME
                cand.consolidation_matches = 0
                transitions.append((CandidatePhase.PROBE_INCOMING, CandidatePhase.LEARN_OUTCOME))

    elif initial_phase == CandidatePhase.LEARN_OUTCOME:
        if obs.is_qualified_owned_root:
            cand.consolidation_matches += 1
        durable = check_c04_durable_path(cand, state.W)
        if durable.is_durable:
            cand.phase = CandidatePhase.NO_PROBE_TEST
            transitions.append((CandidatePhase.LEARN_OUTCOME, CandidatePhase.NO_PROBE_TEST))
            # Immediately perform scratch preflight in the same END (Core §7.4.1)
            grad_result = evaluate_c04_graduation(
                cand,
                state,
                owned_witness=owned_witness,
                rival_witnesses=rival_witnesses,
            )
            if grad_result.passed and grad_result.stable_binding is not None:
                commit_c04_graduation(cand, grad_result.stable_binding, state.W)
                transitions.append((CandidatePhase.NO_PROBE_TEST, CandidatePhase.COMPLETE))
                last_status = StatusCode.OK
            else:
                last_status = grad_result.status
        else:
            last_status = StatusCode.DURABILITY_PENDING

    elif initial_phase == CandidatePhase.NO_PROBE_TEST:
        if obs.is_qualified_owned_root:
            cand.consolidation_matches += 1
        w_star_changed = bool(accepted_keys & cand.reserved_synapse_keys) or force_no_probe_retest
        if w_star_changed:
            grad_result = evaluate_c04_graduation(
                cand,
                state,
                owned_witness=owned_witness,
                rival_witnesses=rival_witnesses,
            )
            if grad_result.passed and grad_result.stable_binding is not None:
                commit_c04_graduation(cand, grad_result.stable_binding, state.W)
                transitions.append((CandidatePhase.NO_PROBE_TEST, CandidatePhase.COMPLETE))
                last_status = StatusCode.OK
            else:
                last_status = grad_result.status
        else:
            last_status = StatusCode.NO_PROBE_INSUFFICIENT_DRIVE

    # 2. Expiration Check AFTER Evidence & Attempted Legal Test (Core §7.4.1, LLA-T23, LLA-T31)
    if cand.phase != CandidatePhase.COMPLETE:
        # Note: if candidate just transitioned into LEARN_OUTCOME on the 8th probe match,
        # cand.phase is now LEARN_OUTCOME so it is exempt from the probe-cap expiration!
        expired_by_probe_cap = (
            cand.phase in (CandidatePhase.WIRED, CandidatePhase.PROBE_INCOMING)
            and cand.probe_matches >= MAX_PROBE_MATCHES
        )
        expired_by_consolidation_cap = (
            cand.phase in (CandidatePhase.LEARN_OUTCOME, CandidatePhase.NO_PROBE_TEST)
            and cand.consolidation_matches >= MAX_CONSOLIDATION_MATCHES
        )
        expired_by_age_cap = cand.age_events >= MAX_CANDIDATE_AGE_EVENTS

        if expired_by_probe_cap or expired_by_consolidation_cap or expired_by_age_cap:
            prev_p = cand.phase
            expire_contextual_candidate(cand, state.W)
            transitions.append((prev_p, CandidatePhase.FAILED_OR_EXPIRED))
            last_status = StatusCode.CANDIDATE_EXPIRED

    return CandidateSettlementResult(
        z_cell_id=cand.z_cell_id,
        owner_id=cand.owner_id,
        initial_phase=initial_phase,
        final_phase=cand.phase,
        transitions=tuple(transitions),
        probe_matches=cand.probe_matches,
        consolidation_matches=cand.consolidation_matches,
        age_events=cand.age_events,
        status=last_status,
        graduation_result=grad_result,
    )


def execute_contextual_close_pipeline(
    w_shadow: WState,
    h_slow: HSlowState,
    event_results: Sequence[EventExecutionResult],
    observation_witnesses: Sequence[ObservationWitness] | None,
    accepted_keys: set[SynapseKey],
    *,
    exposure_id: int,
    remaining_k_r: int,
    discover_and_recruit: bool = True,
    min_additional_opportunities: int = 0,
) -> tuple[list[CandidateSettlementResult], list[RecruitmentResult], list[StatusCode]]:
    """Execute Core §10.2 Steps 3 & 4 on post-evidence shadow W*:
    1. Settle existing contextual candidates' phase transitions, C04 graduation, and expiration.
    2. Extract contrast episodes, discover contrasts, call ResolveOwner, and recruit NEW_ELIGIBLE candidates.
    """
    from dgca.core.state import RState

    shadow_state = MachineState(w=w_shadow, r=RState(), h_slow=h_slow.clone())
    settlement_results: list[CandidateSettlementResult] = []
    recruitment_results: list[RecruitmentResult] = []
    diagnostics: list[StatusCode] = []
    newly_graduated_z_ids: set[int] = set()

    # Step 3: Settle all existing contextual candidates in canonical z_cell_id order
    for z_id in sorted(list(w_shadow.context_candidates.keys())):
        cand = w_shadow.context_candidates.get(z_id)
        if cand is None:
            continue
        res = settle_candidate_at_end_exposure(
            cand,
            shadow_state,
            event_results,
            accepted_keys,
        )
        settlement_results.append(res)
        if res.final_phase == CandidatePhase.COMPLETE:
            newly_graduated_z_ids.add(z_id)
        if res.status != StatusCode.OK:
            diagnostics.append(res.status)

    if not discover_and_recruit:
        return settlement_results, recruitment_results, diagnostics

    # Step 4: Extract contrast episodes from this root, discover contrasts, ResolveOwner, and recruit
    new_episodes = extract_contrast_episodes_from_root(
        event_results,
        w_shadow,
        w_shadow.completed_external_events_count,
        observation_witnesses=observation_witnesses,
    )
    affected_anchors: set[int] = set()
    for ep in new_episodes:
        record_contrast_episode(w_shadow, ep)
        affected_anchors.add(ep.anchor_id)

    k_r_left = remaining_k_r
    for anchor_id in sorted(affected_anchors):
        disc = discover_anchor_contrasts(
            anchor_id,
            shadow_state,
            min_additional_opportunities=min_additional_opportunities,
        )
        if disc.status not in (StatusCode.OK, StatusCode.REUSE):
            diagnostics.append(disc.status)
            continue

        for failing_branch, rival_branches in disc.failing_branches_ordered:
            owner_res = resolve_owner(
                anchor_id,
                failing_branch,
                rival_branches,
                w_shadow,
            )
            if owner_res.status == StatusCode.NEW_ELIGIBLE:
                rec_res = recruit_contextual_candidate(
                    anchor_id,
                    failing_branch,
                    rival_branches,
                    w_shadow,
                    admitted_root_id=exposure_id,
                    event_clock=w_shadow.global_event_clock,
                    remaining_k_r=k_r_left,
                    newly_graduated_z_ids=newly_graduated_z_ids,
                )
                recruitment_results.append(rec_res)
                if rec_res.status == StatusCode.OK:
                    k_r_left = max(0, k_r_left - 1)
                else:
                    diagnostics.append(rec_res.status)
            elif owner_res.status != StatusCode.REUSE:
                diagnostics.append(owner_res.status)

    return settlement_results, recruitment_results, diagnostics
