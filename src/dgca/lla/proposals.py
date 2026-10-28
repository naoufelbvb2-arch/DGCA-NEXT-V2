"""Link Proposals, Creation Coactivity (FIFR-B03), Evidence q/y, and Within-Root Reduction.

Normative references:
- DGCA_LLA_RC4_1.md §3 (Eligibility traces and canonical temporal learning)
- DGCA_LLA_RC4_1.md §4.1 (Quality, local prediction and positive evidence: FIFR-B01/B02)
- DGCA_LLA_RC4_1.md §4.2 (Within-root evidence reduction, paired target and sign conflicts)
- DGCA_LLA_RC4_1.md §5 (First creation from latent pair: FIFR-B03 single source activity convention)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from dgca.common.numeric import clip_float64, validate_finite_binary64
from dgca.core.anatomy import (
    SynapseKey,
    SynapseScope,
    THETA_S,
    get_k_evidence,
)
from dgca.core.dynamics import EventExecutionResult
from dgca.core.sic_v1 import CellAddress
from dgca.core.state import ExecutionMode, HSlowState, WState
from dgca.lla.witness import validate_v_ext

THETA_CREATE_DEFAULT: float = 0.20  # RC3/RC4.1 LAB default (RC2 comparator = 0.30)
THETA_CREATE_CROSS: float = 0.39
OMEGA_ROOT_EXTERNAL: float = 1.0
OMEGA_P_REPLAY: float = 0.50
OMEGA_R_REPLAY: float = 0.50
OMEGA_ROOT_REPLAY: float = OMEGA_P_REPLAY * OMEGA_R_REPLAY  # 0.25 exactly once (FIFR-B02)


@dataclass(frozen=True, slots=True)
class LinkProposal:
    """Staged LINK_PROPOSAL record in an OPEN exposure root's journal (LLA §5)."""

    link_key: SynapseKey
    exposure_id: int
    event_order: int
    source_event_order: int
    a_source: float
    a_target: float
    create_coactivity: float
    q_raw: float
    y_positive: float
    d_event: bool
    v_ext: bool
    priority_class: int  # 0 for valid contextual pinned claim, else 1
    proposal_ordinal: int

    @property
    def source_id(self) -> int:
        return self.link_key[0]

    @property
    def target_id(self) -> int:
        return self.link_key[1]

    @property
    def scope(self) -> SynapseScope:
        return self.link_key[2]


def compute_raw_evidence_q(
    a_source: float,
    a_target: float,
    scope: SynapseScope,
    *,
    omega_root: float = OMEGA_ROOT_EXTERNAL,
    d_ij: bool = True,
) -> float:
    """Compute q_ij^raw = omega_root * D_ij * A_i^learn(Delta) * A_j^+(t) * k_evidence(s, Delta) (LLA §4.1)."""
    if not d_ij or omega_root <= 0.0:
        return 0.0
    a_src = validate_finite_binary64(a_source)
    a_tgt = validate_finite_binary64(a_target)
    if a_src <= 0.0 or a_tgt <= 0.0:
        return 0.0
    delta = 1 if scope == SynapseScope.ASSOCIATIVE else 0
    k_ev = get_k_evidence(scope, delta)
    return omega_root * a_src * a_tgt * k_ev


def compute_positive_target_y(
    a_target: float,
    theta_active_r: float,
    *,
    theta_s: float = THETA_S,
) -> float:
    """Compute y_ij^positive = clip(theta_S + (1 - theta_S) * (A_j^+ - theta_active) / (1 - theta_active), theta_S, 1) (LLA §4.1)."""
    a_tgt = validate_finite_binary64(a_target)
    denom = 1.0 - theta_active_r
    if denom <= 0.0:
        return 1.0
    raw_y = theta_s + (1.0 - theta_s) * ((a_tgt - theta_active_r) / denom)
    return clip_float64(raw_y, theta_s, 1.0)


def is_candidate_reserved_key(key: SynapseKey, w: WState) -> bool:
    """Return True if key is a reserved P/C/Y role key of an active contextual candidate in W."""
    for z_id, reserved_set in w.reserved_keys_by_candidate.items():
        if key in reserved_set:
            cand = w.context_candidates.get(z_id)
            if cand is not None and cand.status.value == "ACTIVE":
                return True
    return False


def generate_event_link_proposals(
    curr_event: EventExecutionResult,
    prev_event: EventExecutionResult | None,
    prev_prev_event: EventExecutionResult | None,
    w: WState,
    h_slow_pre_event: HSlowState,
    *,
    theta_create: float = THETA_CREATE_DEFAULT,
    theta_create_x: float = THETA_CREATE_CROSS,
    starting_ordinal: int = 0,
) -> tuple[list[LinkProposal], int]:
    """Generate all valid LINK_PROPOSALs for curr_event across LOCAL, CROSS_TERRITORY, and ASSOCIATIVE (LLA §3, §5).

    Enforces FIFR-B03:
    - LOCAL/CROSS: source must be in frozen E_t^(1), but a_source = A_i^+(t) final and a_target = A_j^+(t) final!
    - ASSOCIATIVE: source in prior frozen F_step(t-1), a_source = A_i^+(t-1) saved from prev_event, a_target = A_j^+(t) final!
    """
    if (
        curr_event.mode != ExecutionMode.LEARN
        or curr_event.exposure_id is None
        or curr_event.origin.value != "EXTERNAL_DIRECT"
    ):
        return [], starting_ordinal

    proposals: list[LinkProposal] = []
    ordinal = starting_ordinal
    exp_id = curr_event.exposure_id
    ev_order = curr_event.event_order

    # Precompute target y_positive for all active eligible targets j in L_t
    y_by_target: dict[int, float] = {}
    reg_by_cell: dict[int, int] = {}
    for tgt_id in sorted(curr_event.l_frontier):
        addr = CellAddress.from_global_id(tgt_id)
        reg_by_cell[tgt_id] = int(addr.region)
        theta_act = h_slow_pre_event.get_theta_active(addr.region)
        y_by_target[tgt_id] = compute_positive_target_y(
            curr_event.a_plus_by_cell[tgt_id], theta_act
        )

    # 1. Same-event LOCAL and CROSS_TERRITORY proposals (sources in frozen E_t^(1))
    for src_id in sorted(curr_event.e1_frontier):
        if src_id not in reg_by_cell:
            reg_by_cell[src_id] = int(CellAddress.from_global_id(src_id).region)
        src_reg = reg_by_cell[src_id]
        a_src_final = curr_event.a_plus_by_cell.get(src_id, 0.0)
        if a_src_final <= 0.0:
            continue

        for tgt_id in sorted(curr_event.l_frontier):
            if src_id == tgt_id:
                continue
            tgt_reg = reg_by_cell[tgt_id]
            scope = (
                SynapseScope.LOCAL
                if src_reg == tgt_reg
                else SynapseScope.CROSS_TERRITORY
            )
            key: SynapseKey = (src_id, tgt_id, scope)

            # Check latent eligibility and V_ext
            if not w.latent_table.is_eligible(src_id, tgt_id):
                continue
            if not validate_v_ext(key, curr_event, prev_event, prev_prev_event, w):
                continue

            a_tgt_final = curr_event.a_plus_by_cell[tgt_id]
            coactivity = a_src_final * a_tgt_final
            req_theta = theta_create if scope == SynapseScope.LOCAL else theta_create_x

            # For first creation, create_coactivity must meet threshold;
            # LLA §5 check 4 requires create_coactivity >= theta_create on proposals
            if coactivity < req_theta:
                continue

            q_raw = compute_raw_evidence_q(
                a_src_final, a_tgt_final, scope, omega_root=OMEGA_ROOT_EXTERNAL, d_ij=True
            )
            if q_raw <= 0.0:
                continue

            prio = 0 if is_candidate_reserved_key(key, w) else 1
            proposals.append(
                LinkProposal(
                    link_key=key,
                    exposure_id=exp_id,
                    event_order=ev_order,
                    source_event_order=ev_order,
                    a_source=a_src_final,
                    a_target=a_tgt_final,
                    create_coactivity=coactivity,
                    q_raw=q_raw,
                    y_positive=y_by_target[tgt_id],
                    d_event=True,
                    v_ext=True,
                    priority_class=prio,
                    proposal_ordinal=ordinal,
                )
            )
            ordinal += 1

    # 2. Next-event ASSOCIATIVE proposals (sources in prior frozen F_step(t-1), no boundary)
    if not curr_event.boundary and prev_event is not None:
        for src_id in sorted(prev_event.f_step):
            a_src_prev_final = prev_event.a_plus_by_cell.get(src_id, 0.0)
            if a_src_prev_final <= 0.0:
                continue

            for tgt_id in sorted(curr_event.l_frontier):
                if src_id == tgt_id:
                    continue
                key = (src_id, tgt_id, SynapseScope.ASSOCIATIVE)
                if not w.latent_table.is_eligible(src_id, tgt_id):
                    continue
                if not validate_v_ext(key, curr_event, prev_event, prev_prev_event, w):
                    continue

                a_tgt_final = curr_event.a_plus_by_cell[tgt_id]
                coactivity = a_src_prev_final * a_tgt_final
                if coactivity < theta_create:
                    continue

                q_raw = compute_raw_evidence_q(
                    a_src_prev_final,
                    a_tgt_final,
                    SynapseScope.ASSOCIATIVE,
                    omega_root=OMEGA_ROOT_EXTERNAL,
                    d_ij=True,
                )
                if q_raw <= 0.0:
                    continue

                prio = 0 if is_candidate_reserved_key(key, w) else 1
                proposals.append(
                    LinkProposal(
                        link_key=key,
                        exposure_id=exp_id,
                        event_order=ev_order,
                        source_event_order=prev_event.event_order,
                        a_source=a_src_prev_final,
                        a_target=a_tgt_final,
                        create_coactivity=coactivity,
                        q_raw=q_raw,
                        y_positive=y_by_target[tgt_id],
                        d_event=True,
                        v_ext=True,
                        priority_class=prio,
                        proposal_ordinal=ordinal,
                    )
                )
                ordinal += 1

    return proposals, ordinal


def reduce_within_root_proposals(proposals: Sequence[LinkProposal]) -> list[LinkProposal]:
    """Reduce staged proposals by (link_key, exposure_id) taking max q with paired y (LLA §4.2, Core §10.2).

    Within each link_key, sorts by (-q_raw, event_order, proposal_ordinal) ascending and picks the first.
    Then returns the winning proposals sorted in canonical arbitration order (LLA §5 step 6):
        (priority_class, -create_coactivity, -q_raw, source_id, target_id, int(scope))
    """
    by_key: dict[SynapseKey, list[LinkProposal]] = {}
    for prop in proposals:
        if not prop.v_ext or not prop.d_event or prop.q_raw <= 0.0:
            continue
        by_key.setdefault(prop.link_key, []).append(prop)

    winners: list[LinkProposal] = []
    for key, group in by_key.items():
        group.sort(key=lambda p: (-p.q_raw, p.event_order, p.proposal_ordinal))
        winners.append(group[0])

    winners.sort(
        key=lambda p: (
            p.priority_class,
            -p.create_coactivity,
            -p.q_raw,
            p.source_id,
            p.target_id,
            int(p.scope),
        )
    )
    return winners
