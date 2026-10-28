"""Weighted Synapse Strength Update, Dual Evidence Ledgers (E_ext, E_int), Consolidation, and Replay.

Normative references:
- DGCA_LLA_RC4_1.md §4.3 (Weighted update and bounded dual evidence ledgers)
- DGCA_LLA_RC4_1.md §4.4 (Consolidation, episodic support and lifetime)
- DGCA_LLA_RC4_1.md §5 (First creation from latent pair: exact legal transition)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math

from dgca.common.errors import StatusCode
from dgca.core.anatomy import (
    E_MAX,
    PHI_INT_CAP,
    Synapse,
    SynapseKey,
    SynapseScope,
    SynapseState,
    THETA_E,
    THETA_S,
)
from dgca.core.sic_v1 import CellAddress
from dgca.core.state import WState
from dgca.lla.proposals import (
    LinkProposal,
    OMEGA_ROOT_REPLAY,
    compute_positive_target_y,
    compute_raw_evidence_q,
    is_candidate_reserved_key,
    reduce_within_root_proposals,
)

W_CONF_ORDINARY: int = 100
W_CONF_CONTEXT: int = 240
W_EPISODIC: int = 2000
ALPHA_REC_REPLAY: float = 0.05


@dataclass(frozen=True, slots=True)
class ProposalApplicationOutcome:
    """Audit result of applying or rejecting a single root-reduced LinkProposal at END_EXPOSURE."""

    proposal: LinkProposal
    status: StatusCode
    created_new: bool
    consolidated_now: bool


def apply_weighted_synapse_update(
    syn: Synapse,
    q: float,
    y: float,
    *,
    is_external: bool,
    exposure_id: int | None = None,
    event_id: int = 0,
) -> bool:
    """Apply the weighted strength and bounded dual ledger update to an existing Synapse (LLA §4.3, §4.4).

    Formula:
        S' = (E * S + q * y) / (E + q)
        E_ext' = min(E_max, E_ext + q_ext)
        E_int' = min(phi * E_max, E_int + q_int)
        E_int'' = min(E_int', E_max - E_ext')
        E' = E_ext' + E_int'' <= E_max

    Returns True if the synapse transitioned to CONSOLIDATED on this update.
    """
    if q <= 0.0:
        return False

    if is_external:
        if exposure_id is not None and exposure_id in syn.confirmed_roots:
            # LLA §4.2 & §4.3: at most one external confirmation per completed root
            return False
        q_ext = q
        q_int = 0.0
    else:
        q_ext = 0.0
        q_int = q

    pre_e = syn.E
    if pre_e <= 0.0:
        new_s = y
    else:
        new_s = (pre_e * syn.S + q * y) / (pre_e + q)

    new_e_ext = min(E_MAX, syn.E_ext + q_ext)
    new_e_int_1 = min(PHI_INT_CAP * E_MAX, syn.E_int + q_int)
    new_e_int_2 = min(new_e_int_1, E_MAX - new_e_ext)

    syn.S = new_s
    syn.E_ext = new_e_ext
    syn.E_int = new_e_int_2
    syn.internally_supported = new_e_int_2 > new_e_ext

    if is_external:
        syn.external_count += 1
        syn.last_external_event_id = event_id
        if exposure_id is not None:
            syn.last_evidence_root = exposure_id
            syn.confirmed_roots = syn.confirmed_roots + (exposure_id,)

    was_consolidated = syn.state == SynapseState.CONSOLIDATED
    if (
        syn.S >= THETA_S
        and (syn.E / E_MAX) >= THETA_E
        and syn.external_count >= 2
    ):
        syn.state = SynapseState.CONSOLIDATED

    return (not was_consolidated) and (syn.state == SynapseState.CONSOLIDATED)


def apply_root_proposals_to_shadow_w(
    staged_proposals: Sequence[LinkProposal],
    w_pre_close: WState,
    w_shadow: WState,
    *,
    w_conf: int = W_CONF_ORDINARY,
    w_conf_context: int = W_CONF_CONTEXT,
) -> tuple[list[ProposalApplicationOutcome], list[StatusCode]]:
    """Reduce and apply staged root proposals to w_shadow at END_EXPOSURE (Core §10.2, LLA §5).

    Checks D_close == 1 against frozen w_pre_close, enforces outgoing capacity B_i (64) and
    cross capacity B_i^x (12) without double-debiting reserved candidate keys.
    """
    winners = reduce_within_root_proposals(staged_proposals)
    outcomes: list[ProposalApplicationOutcome] = []
    diagnostics: list[StatusCode] = []

    for prop in winners:
        key = prop.link_key
        src_id, tgt_id, scope = key

        # LLA §5 check 5: Recheck D_close == 1 on frozen pre-close W snapshot
        if not w_pre_close.latent_table.is_eligible(src_id, tgt_id):
            outcomes.append(
                ProposalApplicationOutcome(
                    proposal=prop,
                    status=StatusCode.STALE_LATENT_ELIGIBILITY,
                    created_new=False,
                    consolidated_now=False,
                )
            )
            diagnostics.append(StatusCode.STALE_LATENT_ELIGIBILITY)
            continue

        existing_syn = w_shadow.synapses.get(key)
        if existing_syn is not None:
            # Update existing synapse
            consolidated_now = apply_weighted_synapse_update(
                existing_syn,
                prop.q_raw,
                prop.y_positive,
                is_external=True,
                exposure_id=prop.exposure_id,
                event_id=w_shadow.global_event_clock,
            )
            outcomes.append(
                ProposalApplicationOutcome(
                    proposal=prop,
                    status=StatusCode.OK,
                    created_new=False,
                    consolidated_now=consolidated_now,
                )
            )
            continue

        # First creation of a new synapse: check source outgoing capacity in w_shadow
        # Note: if key is already reserved by an active contextual candidate, it is already in
        # unique_claimed_outgoing_keys(src_id) and transfers its claim without extra debit!
        already_claimed = key in w_shadow.unique_claimed_outgoing_keys(src_id)
        if not already_claimed:
            if w_shadow.available_outgoing_headroom(src_id) <= 0:
                outcomes.append(
                    ProposalApplicationOutcome(
                        proposal=prop,
                        status=StatusCode.SOURCE_OUTGOING_CAPACITY,
                        created_new=False,
                        consolidated_now=False,
                    )
                )
                diagnostics.append(StatusCode.SOURCE_OUTGOING_CAPACITY)
                continue

            is_cross = (
                scope == SynapseScope.CROSS_TERRITORY
                or CellAddress.from_global_id(src_id).region
                != CellAddress.from_global_id(tgt_id).region
            )
            if is_cross and w_shadow.available_cross_outgoing_headroom(src_id) <= 0:
                outcomes.append(
                    ProposalApplicationOutcome(
                        proposal=prop,
                        status=StatusCode.SOURCE_OUTGOING_CAPACITY,
                        created_new=False,
                        consolidated_now=False,
                    )
                )
                diagnostics.append(StatusCode.SOURCE_OUTGOING_CAPACITY)
                continue

        is_ctx_owned = is_candidate_reserved_key(key, w_shadow)
        deadline_window = w_conf_context if is_ctx_owned else w_conf
        new_syn = Synapse(
            key=key,
            S=prop.y_positive,
            E_ext=min(E_MAX, prop.q_raw),
            E_int=0.0,
            external_count=1,
            state=SynapseState.CANDIDATE,
            created_event_id=w_shadow.global_event_clock,
            created_exposure_id=prop.exposure_id,
            last_external_event_id=w_shadow.global_event_clock,
            last_evidence_root=prop.exposure_id,
            candidate_deadline=w_shadow.completed_external_events_count + deadline_window,
            internally_supported=False,
            confirmed_roots=(prop.exposure_id,),
        )
        w_shadow.add_or_replace_synapse(new_syn)
        outcomes.append(
            ProposalApplicationOutcome(
                proposal=prop,
                status=StatusCode.OK,
                created_new=True,
                consolidated_now=False,
            )
        )

    return outcomes, diagnostics


def compute_replay_priority(syn: Synapse, current_event_clock: int) -> float:
    """Compute Replay scheduling priority Priority(e) = S_e * (1 - E_e / E_max) * exp(-alpha_rec * (t - t_last_ext)) (LLA §4.4)."""
    age = max(0, current_event_clock - syn.last_external_event_id)
    return syn.S * (1.0 - (syn.E / E_MAX)) * math.exp(-ALPHA_REC_REPLAY * float(age))


def apply_internal_replay_step(
    syn: Synapse,
    a_source: float,
    a_target: float,
    theta_active_target: float,
    w: WState,
    *,
    replay_enabled: bool = False,
) -> float:
    """Execute a declared internal Replay evidence update on an external-rooted candidate link (LLA §4.1, §4.4, FIFR-B02).

    Baseline has replay_enabled=False (returns 0.0).
    When replay_enabled=True in a declared comparator:
    - Applies omega_root = omega_P * omega_R = 0.25 exactly once to q_int.
    - Updates E_int (capped by phi * E_max = 5.0 and E_max - E_ext).
    - Never increments E_ext or external_count.
    """
    if not replay_enabled:
        return 0.0
    if syn.external_count < 1:
        return 0.0
    src_id, tgt_id, scope = syn.key
    if not w.latent_table.is_eligible(src_id, tgt_id):
        return 0.0

    q_int = compute_raw_evidence_q(
        a_source,
        a_target,
        scope,
        omega_root=OMEGA_ROOT_REPLAY,
        d_ij=True,
    )
    if q_int <= 0.0:
        return 0.0

    y_pos = compute_positive_target_y(a_target, theta_active_target)
    apply_weighted_synapse_update(
        syn,
        q_int,
        y_pos,
        is_external=False,
    )
    return q_int


def prune_expired_candidate_synapses(w: WState) -> list[SynapseKey]:
    """Prune expired unprotected candidate links whose candidate_deadline < completed_external_events_count (LLA §4.4).

    Never deletes a CONSOLIDATED link or an active candidate-pinned link before its W_conf_context deadline.
    """
    pruned: list[SynapseKey] = []
    cur_events = w.completed_external_events_count

    for key in sorted(w.synapses.keys()):
        syn = w.synapses[key]
        if syn.state == SynapseState.CONSOLIDATED:
            continue
        if is_candidate_reserved_key(key, w):
            # Active candidate-owned link is protected up to its W_conf_context deadline
            if cur_events <= syn.candidate_deadline:
                continue
        if cur_events > syn.candidate_deadline:
            w.remove_synapse(key)
            pruned.append(key)

    return pruned
