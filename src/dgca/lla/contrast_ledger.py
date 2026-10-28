"""Bounded Contrast Ledger, Weighted Footprint Distance, and Counterfactual Reuse Check.

Normative references:
- DGCA_LLA_RC4_1.md §6.1 (Reuse-first novelty evidence)
- DGCA_CORE_RC4_1.md §7.1 & §7.2 (Repeated real contrast, reuse failure, ComparisonBranchKey)
- DGCA_CORE_RC4_1.md §9.1 (READ_ONLY_EPISODE & PredScore_W(Y | P, B))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

from dgca.common.errors import StatusCode
from dgca.common.hashing import (
    Role,
    RoleV2Record,
    WitnessSourceKind,
    compute_fp_role_v1,
    compute_fp_role_v2,
)
from dgca.common.numeric import MILLION, q6_from_binary64
from collections.abc import Sequence
from dgca.core.dynamics import (
    EventExecutionResult,
    compute_next_step_temporal_drive,
    compute_pred_score,
    execute_two_pass_event,
)
from dgca.core.state import (
    BindingStatus,
    ExecutionMode,
    MachineState,
    ParentContextRef,
    TypedSupportRecord,
    WState,
)
from dgca.encoder.envelope import EventOrigin
from dgca.lla.witness import (
    ObservationWitness,
    eligible_external_p,
)

CONTRAST_LEDGER_CAP_PER_ANCHOR: int = 16
CONTRAST_LEDGER_TTL_EVENTS: int = 2000
N_BRANCH_MIN: int = 2
D_P_MIN: float = 0.40
D_Y_MIN: float = 0.40
NU_CTX_MIN: float = 0.30
M_REUSE: float = 0.05
M_P_Q6: int = 50_000


def compute_weighted_footprint_distance(
    u: dict[int, float] | dict[int, int],
    v: dict[int, float] | dict[int, int],
) -> float:
    """Compute weighted observed neural footprint distance d_w(U, V) (LLA §6.1, Core §7.1).

    Formula:
        d_w(U, V) = 1 - (sum_i min(U_i, V_i)) / (sum_i max(U_i, V_i))
        d_w(0, 0) = 0.0
        d_w(0, V) = 1.0  (for V != 0)
    """
    all_keys = sorted(set(u.keys()) | set(v.keys()))
    if not all_keys:
        return 0.0

    num = Fraction(0)
    den = Fraction(0)
    for k in all_keys:
        uk = Fraction(u.get(k, 0))
        vk = Fraction(v.get(k, 0))
        if uk < 0 or vk < 0:
            raise ValueError("Footprint supports must be non-negative")
        num += min(uk, vk)
        den += max(uk, vk)

    if den == 0:
        return 0.0
    return float(Fraction(1) - (num / den))


def compute_role_footprint_digest(
    role: Role,
    supports_u: dict[int, int],
    source_kinds: dict[int, WitnessSourceKind] | None = None,
    parent_refs: dict[int, ParentContextRef] | None = None,
) -> bytes:
    """Compute canonical FP-ROLE-V1 or FP-ROLE-V2 digest for a role support map (Core §3.1, LLA §6.6).

    Uses FP-ROLE-V2 when role == Role.P and any source has DERIVED_EXTERNAL_CONTEXT kind;
    otherwise uses FP-ROLE-V1.
    """
    nonzero_items = sorted((cid, sup) for cid, sup in supports_u.items() if sup > 0)
    if role == Role.P and source_kinds is not None:
        has_derived = any(
            source_kinds.get(cid, WitnessSourceKind.DIRECT)
            == WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT
            for cid, _ in nonzero_items
        )
        if has_derived:
            v2_items: list[RoleV2Record] = []
            for cid, sup in nonzero_items:
                kind = source_kinds.get(cid, WitnessSourceKind.DIRECT)
                if kind == WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT:
                    ref = (parent_refs or {}).get(cid)
                    if ref is None:
                        raise ValueError(f"Missing ParentContextRef for derived P source {cid}")
                    v2_items.append(
                        RoleV2Record(
                            global_cell_id=cid,
                            support_millionths=sup,
                            kind=WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT,
                            parent_anchor_global_cell_id=ref.parent_anchor_id,
                            parent_owner_counter=ref.parent_owner_seq,
                            parent_binding_generation=ref.parent_binding_generation,
                        )
                    )
                else:
                    v2_items.append(
                        RoleV2Record(
                            global_cell_id=cid,
                            support_millionths=sup,
                            kind=WitnessSourceKind.DIRECT,
                        )
                    )
            return compute_fp_role_v2(role, v2_items)

    return compute_fp_role_v1(role, nonzero_items)


@dataclass(frozen=True, order=True, slots=True)
class ComparisonBranchKey:
    """Temporary comparison key for discovery ordering only (Core §7.2, LLA §6.2).

    Never used as permanent owner identity.
    """

    anchor_id: int
    p_digest: bytes
    c_digest: bytes
    y_digest: bytes
    earliest_root_id: int
    earliest_event_order: int


@dataclass(slots=True)
class ContrastEpisodeRecord:
    """Single observed (P, C, Y) transition recorded in the bounded contrast ledger (LLA §6.1)."""

    anchor_id: int
    exposure_id: int
    event_order_b: int
    completed_event_clock: int
    p_supports_u: dict[int, int]
    c_supports_u: dict[int, int]
    y_supports_u: dict[int, int]
    p_source_kinds: dict[int, WitnessSourceKind] = field(default_factory=dict)
    p_parent_refs: dict[int, ParentContextRef] = field(default_factory=dict)
    p_digest: bytes = b""
    c_digest: bytes = b""
    y_digest: bytes = b""
    p_bundle_digest: bytes = b""
    c_bundle_digest: bytes = b""
    y_bundle_digest: bytes = b""
    p_direct_x_u: dict[int, int] = field(default_factory=dict)
    c_direct_x_u: dict[int, int] = field(default_factory=dict)
    has_collision: bool = False

    def __post_init__(self) -> None:
        if not self.p_digest and self.p_supports_u:
            self.p_digest = compute_role_footprint_digest(
                Role.P, self.p_supports_u, self.p_source_kinds, self.p_parent_refs
            )
        if not self.c_digest and self.c_supports_u:
            self.c_digest = compute_role_footprint_digest(Role.C, self.c_supports_u)
        if not self.y_digest and self.y_supports_u:
            self.y_digest = compute_role_footprint_digest(Role.Y, self.y_supports_u)
        if not self.p_direct_x_u:
            self.p_direct_x_u = {
                cid: sup
                for cid, sup in self.p_supports_u.items()
                if self.p_source_kinds.get(cid, WitnessSourceKind.DIRECT) == WitnessSourceKind.DIRECT
            }
        if not self.c_direct_x_u:
            self.c_direct_x_u = dict(self.c_supports_u)

    def clone(self) -> ContrastEpisodeRecord:
        return ContrastEpisodeRecord(
            anchor_id=self.anchor_id,
            exposure_id=self.exposure_id,
            event_order_b=self.event_order_b,
            completed_event_clock=self.completed_event_clock,
            p_supports_u=dict(self.p_supports_u),
            c_supports_u=dict(self.c_supports_u),
            y_supports_u=dict(self.y_supports_u),
            p_source_kinds=dict(self.p_source_kinds),
            p_parent_refs=dict(self.p_parent_refs),
            p_digest=self.p_digest,
            c_digest=self.c_digest,
            y_digest=self.y_digest,
            p_bundle_digest=self.p_bundle_digest,
            c_bundle_digest=self.c_bundle_digest,
            y_bundle_digest=self.y_bundle_digest,
            p_direct_x_u=dict(self.p_direct_x_u),
            c_direct_x_u=dict(self.c_direct_x_u),
            has_collision=self.has_collision,
        )


@dataclass(slots=True)
class BranchSummary:
    """Aggregated physical branch observations across independent completed roots (Core §7.1–7.3)."""

    anchor_id: int
    p_digest: bytes
    c_digest: bytes
    y_digest: bytes
    episodes: list[ContrastEpisodeRecord]

    @property
    def distinct_roots(self) -> tuple[int, ...]:
        return tuple(sorted({ep.exposure_id for ep in self.episodes}))

    @property
    def independent_root_count(self) -> int:
        return len(self.distinct_roots)

    @property
    def comparison_key(self) -> ComparisonBranchKey:
        first_ep = min(self.episodes, key=lambda e: (e.exposure_id, e.event_order_b))
        return ComparisonBranchKey(
            anchor_id=self.anchor_id,
            p_digest=self.p_digest,
            c_digest=self.c_digest,
            y_digest=self.y_digest,
            earliest_root_id=first_ep.exposure_id,
            earliest_event_order=first_ep.event_order_b,
        )

    @property
    def qualifying_two_episodes(self) -> tuple[ContrastEpisodeRecord, ContrastEpisodeRecord]:
        """Return the earliest two episodes from distinct completed roots."""
        by_root: dict[int, ContrastEpisodeRecord] = {}
        for ep in sorted(self.episodes, key=lambda e: (e.exposure_id, e.event_order_b)):
            if ep.exposure_id not in by_root:
                by_root[ep.exposure_id] = ep
            if len(by_root) == 2:
                break
        vals = list(by_root.values())
        if len(vals) < 2:
            raise ValueError("BranchSummary has fewer than 2 independent root episodes")
        return vals[0], vals[1]

    @property
    def representative_p_supports_u(self) -> dict[int, int]:
        """Minimum witnessed support across the qualifying root episodes per P cell."""
        all_p = set()
        for ep in self.episodes:
            all_p.update(ep.p_supports_u.keys())
        return {
            cid: min(ep.p_supports_u.get(cid, 0) for ep in self.episodes)
            for cid in sorted(all_p)
            if min(ep.p_supports_u.get(cid, 0) for ep in self.episodes) > 0
        }

    @property
    def representative_c_supports_u(self) -> dict[int, int]:
        all_c = set()
        for ep in self.episodes:
            all_c.update(ep.c_supports_u.keys())
        return {
            cid: min(ep.c_supports_u.get(cid, 0) for ep in self.episodes)
            for cid in sorted(all_c)
            if min(ep.c_supports_u.get(cid, 0) for ep in self.episodes) > 0
        }

    @property
    def representative_y_supports_u(self) -> dict[int, int]:
        all_y = set()
        for ep in self.episodes:
            all_y.update(ep.y_supports_u.keys())
        return {
            cid: min(ep.y_supports_u.get(cid, 0) for ep in self.episodes)
            for cid in sorted(all_y)
            if min(ep.y_supports_u.get(cid, 0) for ep in self.episodes) > 0
        }

    @property
    def y_target_cells(self) -> set[int]:
        return set(self.representative_y_supports_u.keys())


@dataclass(frozen=True, slots=True)
class ContrastPairEvaluation:
    """Result of comparing two contrasting branches (B_1, B_2) under an anchor."""

    anchor_id: int
    branch_1: BranchSummary
    branch_2: BranchSummary
    d_p: float
    d_y: float
    c_ext: float
    nu_ctx: float
    branch_1_pred_margin: float
    branch_2_pred_margin: float
    branch_1_needs_recruitment: bool
    branch_2_needs_recruitment: bool
    status: StatusCode


@dataclass(frozen=True, slots=True)
class ContrastDiscoveryResult:
    """Summary of contrast discovery for an anchor at END_EXPOSURE."""

    anchor_id: int
    status: StatusCode
    qualifying_pairs: tuple[ContrastPairEvaluation, ...]
    failing_branches_ordered: tuple[ tuple[BranchSummary, tuple[BranchSummary, ...]], ... ]


def prune_expired_contrast_episodes(w_state: WState, current_ext_events: int) -> int:
    """Remove contrast episodes older than CONTRAST_LEDGER_TTL_EVENTS (2000) (LLA §6.1, Core §7.1)."""
    removed = 0
    for anchor_id in list(w_state.contrast_episodes_by_anchor.keys()):
        eps: list[ContrastEpisodeRecord] = w_state.contrast_episodes_by_anchor[anchor_id]  # type: ignore[assignment]
        kept = [
            ep
            for ep in eps
            if (current_ext_events - ep.completed_event_clock) <= CONTRAST_LEDGER_TTL_EVENTS
        ]
        removed += len(eps) - len(kept)
        if kept:
            w_state.contrast_episodes_by_anchor[anchor_id] = kept  # type: ignore[assignment]
        else:
            del w_state.contrast_episodes_by_anchor[anchor_id]
    return removed


def record_contrast_episode(w_state: WState, episode: ContrastEpisodeRecord) -> None:
    """Insert a ContrastEpisodeRecord into the bounded contrast ledger (max 16/anchor, TTL 2000)."""
    prune_expired_contrast_episodes(w_state, episode.completed_event_clock)
    eps: list[ContrastEpisodeRecord] = w_state.contrast_episodes_by_anchor.setdefault(
        episode.anchor_id, []
    )  # type: ignore[assignment]
    eps.append(episode.clone())
    if len(eps) > CONTRAST_LEDGER_CAP_PER_ANCHOR:
        # Retain latest 16 qualified observations per anchor
        del eps[: len(eps) - CONTRAST_LEDGER_CAP_PER_ANCHOR]


def extract_contrast_episodes_from_root(
    event_results: Sequence[EventExecutionResult],
    w_state: WState,
    completed_event_clock: int,
    *,
    observation_witnesses: Sequence[ObservationWitness] | None = None,
    explicit_anchor_id: int | None = None,
) -> list[ContrastEpisodeRecord]:
    """Extract observed (P, C, Y) contrast episodes from a completed root's events (LLA §6.1)."""
    episodes: list[ContrastEpisodeRecord] = []
    if len(event_results) < 3:
        return episodes

    for idx in range(1, len(event_results) - 1):
        ev_prev = event_results[idx - 1]
        ev_curr = event_results[idx]
        ev_next = event_results[idx + 1]

        if (
            ev_curr.boundary
            or ev_next.boundary
            or ev_prev.origin != EventOrigin.EXTERNAL_DIRECT
            or ev_curr.origin != EventOrigin.EXTERNAL_DIRECT
            or ev_next.origin != EventOrigin.EXTERNAL_DIRECT
            or ev_prev.exposure_id != ev_curr.exposure_id
            or ev_curr.exposure_id != ev_next.exposure_id
        ):
            continue

        # Collect eligible P supports from ev_prev (DIRECT or COMPLETE no-probe DERIVED_EXTERNAL_CONTEXT)
        p_supports_u: dict[int, int] = {}
        p_kinds: dict[int, WitnessSourceKind] = {}
        p_parent_refs: dict[int, ParentContextRef] = {}
        p_direct_x_u: dict[int, int] = {
            cid: ev_prev.typed_supports[cid].q6_train
            for cid in sorted(ev_prev.obs_eligible_cells)
            if cid in ev_prev.typed_supports and ev_prev.typed_supports[cid].q6_train > 0
        }

        candidate_p_cells = sorted(
            set(ev_prev.obs_eligible_cells)
            | (set(ev_prev.f_step) & set(w_state.stable_bindings.keys()))
        )
        for pid in candidate_p_cells:
            kind, sup_flt = eligible_external_p(pid, ev_prev, w_state)
            sup_q6 = q6_from_binary64(sup_flt)
            if kind is not None and sup_q6 > 0:
                p_supports_u[pid] = sup_q6
                p_kinds[pid] = kind
                if kind == WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT:
                    bind = w_state.stable_bindings.get(pid)
                    if bind is not None:
                        p_parent_refs[pid] = ParentContextRef(
                            parent_z_cell_id=pid,
                            parent_anchor_id=bind.anchor_id,
                            parent_owner_seq=bind.owner_seq,
                            parent_binding_generation=bind.binding_generation,
                            depth=bind.depth,
                        )

        c_supports_u = {
            cid: ev_curr.typed_supports[cid].q6_train
            for cid in sorted(ev_curr.obs_eligible_cells)
            if cid in ev_curr.typed_supports and ev_curr.typed_supports[cid].q6_train > 0
        }
        y_supports_u = {
            cid: ev_next.typed_supports[cid].q6_train
            for cid in sorted(ev_next.obs_eligible_cells)
            if cid in ev_next.typed_supports and ev_next.typed_supports[cid].q6_train > 0
        }

        if len(p_supports_u) < 2 or len(c_supports_u) < 2 or len(y_supports_u) < 2:
            continue

        p_b_dig = b""
        c_b_dig = b""
        y_b_dig = b""
        has_coll = False
        if observation_witnesses is not None and len(observation_witnesses) > idx + 1:
            ow_prev = observation_witnesses[idx - 1]
            ow_curr = observation_witnesses[idx]
            ow_next = observation_witnesses[idx + 1]
            p_b_dig = ow_prev.feature_digest
            c_b_dig = ow_curr.feature_digest
            y_b_dig = ow_next.feature_digest
            has_coll = bool(
                ow_prev.status == StatusCode.UNRESOLVED_COLLISION
                or ow_curr.status == StatusCode.UNRESOLVED_COLLISION
                or ow_next.status == StatusCode.UNRESOLVED_COLLISION
            )

        anchor_id = explicit_anchor_id if explicit_anchor_id is not None else min(c_supports_u.keys())
        ep = ContrastEpisodeRecord(
            anchor_id=anchor_id,
            exposure_id=int(ev_curr.exposure_id or 0),
            event_order_b=ev_curr.event_order,
            completed_event_clock=completed_event_clock,
            p_supports_u=p_supports_u,
            c_supports_u=c_supports_u,
            y_supports_u=y_supports_u,
            p_source_kinds=p_kinds,
            p_parent_refs=p_parent_refs,
            p_bundle_digest=p_b_dig,
            c_bundle_digest=c_b_dig,
            y_bundle_digest=y_b_dig,
            p_direct_x_u=p_direct_x_u,
            c_direct_x_u=dict(c_supports_u),
            has_collision=has_coll,
        )
        episodes.append(ep)

    return episodes


def evaluate_counterfactual_pred_margin(
    branch: BranchSummary,
    rival_branch: BranchSummary,
    state: MachineState,
    *,
    mask_nonconsolidated: bool = False,
) -> float:
    """Run counterfactual read-only cold-run PredScore(Y_correct | P, B) - PredScore(Y_alt | P, B) (Core §9.1, LLA §6.1).

    Starts from R_cold with frozen W and H_slow, PROBE=OFF, feeds P then B (never Y as neural input),
    immediately after B computes P_T(next) using frozen mu(B), and evaluates PredScore difference.
    """
    ep = branch.episodes[-1]
    scratch = state.clone()
    scratch.R.reset_cold()

    # Step 0: feed P (with boundary=True at start of cold episode)
    p_x_fixed = dict(ep.p_direct_x_u)
    p_x_float = {cid: float(u) / float(MILLION) for cid, u in p_x_fixed.items()}
    execute_two_pass_event(
        scratch,
        p_x_fixed,
        p_x_float,
        mode=ExecutionMode.RETRIEVE,
        origin=EventOrigin.READ_ONLY_OBSERVED,
        boundary=True,
        exposure_id=None,
        event_order=0,
        allow_candidate_probe=False,
        mask_nonconsolidated_candidate_links=mask_nonconsolidated,
        admit_uncommitted_sensory=False,
    )

    # If any P source in ep.p_supports_u is DERIVED_EXTERNAL_CONTEXT with an ACTIVE parent binding,
    # populate its verified runtime support for 2-step compact witness replay
    if ep.p_source_kinds:
        for pid, kind in ep.p_source_kinds.items():
            if kind == WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT and ep.p_supports_u.get(pid, 0) > 0:
                parent_bind = scratch.W.stable_bindings.get(pid)
                if parent_bind is not None and parent_bind.status == BindingStatus.ACTIVE:
                    sup_u = ep.p_supports_u[pid]
                    sup_flt = float(sup_u) / float(MILLION)
                    scratch.R.A[pid] = max(scratch.R.A.get(pid, 0.0), sup_flt)
                    scratch.R.F_step = frozenset(set(scratch.R.F_step) | {pid})
                    scratch.R.typed_supports_current[pid] = TypedSupportRecord(
                        cell_id=pid,
                        event_order=0,
                        origin_kind="DERIVED_RUNTIME_CONTEXT",
                        o_train=0.0,
                        o_runtime=sup_flt,
                        q6_train=0,
                        q6_runtime=sup_u,
                        depth=parent_bind.depth,
                        owner_id=parent_bind.owner_id,
                        binding_generation=parent_bind.binding_generation,
                        parent_proof_verified=True,
                    )

    # Step 1: feed B (boundary=False)
    c_x_fixed = dict(ep.c_direct_x_u)
    c_x_float = {cid: float(u) / float(MILLION) for cid, u in c_x_fixed.items()}
    res_b = execute_two_pass_event(
        scratch,
        c_x_fixed,
        c_x_float,
        mode=ExecutionMode.RETRIEVE,
        origin=EventOrigin.READ_ONLY_OBSERVED,
        boundary=False,
        exposure_id=None,
        event_order=1,
        allow_candidate_probe=False,
        mask_nonconsolidated_candidate_links=mask_nonconsolidated,
        admit_uncommitted_sensory=False,
    )

    # Compute P_T(next) from B's frozen F_step and frozen mu(B)
    pt_next, _ = compute_next_step_temporal_drive(
        scratch,
        f_step_prev=res_b.f_step,
        a_prev_by_cell=res_b.a_plus_by_cell,
        mu_prev_source_mask=res_b.mu_source_mask,
        mask_nonconsolidated=mask_nonconsolidated,
    )

    _, score_correct = compute_pred_score(pt_next, branch.y_target_cells)
    _, score_alt = compute_pred_score(pt_next, rival_branch.y_target_cells)
    return score_correct - score_alt


def discover_anchor_contrasts(
    anchor_id: int,
    state: MachineState,
    *,
    min_additional_opportunities: int = 0,
) -> ContrastDiscoveryResult:
    """Evaluate an anchor's bounded contrast ledger for qualifying novelty and reuse failure (LLA §6.1, Core §7.1–7.2).

    Enforces:
    - Unresolved SIC footprint collision check (LLA-T03) -> UNRESOLVED_COLLISION
    - Single branch with no comparator (LLA-T02) -> NOT_EVALUATED_NO_COMPARATOR
    - Each contrasting branch has >= N_BRANCH_MIN (2) + min_additional_opportunities independent roots
    - d_P >= 0.40, d_Y >= 0.40, nu_ctx >= 0.30
    - Counterfactual cold-run PredScore margin < m_reuse (0.05); if both branches >= 0.05, reuse existing W!
    """
    prune_expired_contrast_episodes(state.W, state.W.completed_external_events_count)
    episodes: list[ContrastEpisodeRecord] = state.W.contrast_episodes_by_anchor.get(
        anchor_id, []
    )  # type: ignore[assignment]

    if not episodes:
        return ContrastDiscoveryResult(
            anchor_id=anchor_id,
            status=StatusCode.NOT_EVALUATED_NO_COMPARATOR,
            qualifying_pairs=(),
            failing_branches_ordered=(),
        )

    # Check for explicit collision flag or distinct feature bundle digest producing identical neural role digest (LLA-T03)
    for i, ep1 in enumerate(episodes):
        if ep1.has_collision:
            return ContrastDiscoveryResult(
                anchor_id=anchor_id,
                status=StatusCode.UNRESOLVED_COLLISION,
                qualifying_pairs=(),
                failing_branches_ordered=(),
            )
        for ep2 in episodes[i + 1 :]:
            if (
                ep1.y_bundle_digest
                and ep2.y_bundle_digest
                and ep1.y_bundle_digest != ep2.y_bundle_digest
                and ep1.y_digest == ep2.y_digest
            ):
                return ContrastDiscoveryResult(
                    anchor_id=anchor_id,
                    status=StatusCode.UNRESOLVED_COLLISION,
                    qualifying_pairs=(),
                    failing_branches_ordered=(),
                )
            if (
                ep1.p_bundle_digest
                and ep2.p_bundle_digest
                and ep1.p_bundle_digest != ep2.p_bundle_digest
                and ep1.p_digest == ep2.p_digest
            ):
                return ContrastDiscoveryResult(
                    anchor_id=anchor_id,
                    status=StatusCode.UNRESOLVED_COLLISION,
                    qualifying_pairs=(),
                    failing_branches_ordered=(),
                )

    # Group episodes by physical branch (p_digest, c_digest, y_digest)
    by_branch_digests: dict[tuple[bytes, bytes, bytes], list[ContrastEpisodeRecord]] = {}
    for ep in episodes:
        key = (ep.p_digest, ep.c_digest, ep.y_digest)
        by_branch_digests.setdefault(key, []).append(ep)

    branches = [
        BranchSummary(
            anchor_id=anchor_id,
            p_digest=k[0],
            c_digest=k[1],
            y_digest=k[2],
            episodes=eps,
        )
        for k, eps in by_branch_digests.items()
    ]
    branches.sort(key=lambda b: b.comparison_key)

    if len(branches) < 2:
        return ContrastDiscoveryResult(
            anchor_id=anchor_id,
            status=StatusCode.NOT_EVALUATED_NO_COMPARATOR,
            qualifying_pairs=(),
            failing_branches_ordered=(),
        )

    required_roots = N_BRANCH_MIN + min_additional_opportunities
    qualifying_pairs: list[ContrastPairEvaluation] = []
    failing_rivals_by_key: dict[ComparisonBranchKey, tuple[BranchSummary, list[BranchSummary]]] = {}

    for i in range(len(branches)):
        for j in range(i + 1, len(branches)):
            b1 = branches[i]
            b2 = branches[j]
            n1 = b1.independent_root_count
            n2 = b2.independent_root_count
            if n1 < required_roots or n2 < required_roots:
                continue

            d_p = compute_weighted_footprint_distance(
                b1.representative_p_supports_u, b2.representative_p_supports_u
            )
            d_y = compute_weighted_footprint_distance(
                b1.representative_y_supports_u, b2.representative_y_supports_u
            )
            c_ext = min(1.0, float(n1) / 2.0, float(n2) / 2.0) * 1.0
            nu_ctx = c_ext * d_p * d_y

            if d_p < D_P_MIN or d_y < D_Y_MIN or nu_ctx < NU_CTX_MIN:
                continue

            margin_1 = evaluate_counterfactual_pred_margin(b1, b2, state)
            margin_2 = evaluate_counterfactual_pred_margin(b2, b1, state)
            b1_fails = margin_1 < M_REUSE
            b2_fails = margin_2 < M_REUSE

            pair_eval = ContrastPairEvaluation(
                anchor_id=anchor_id,
                branch_1=b1,
                branch_2=b2,
                d_p=d_p,
                d_y=d_y,
                c_ext=c_ext,
                nu_ctx=nu_ctx,
                branch_1_pred_margin=margin_1,
                branch_2_pred_margin=margin_2,
                branch_1_needs_recruitment=b1_fails,
                branch_2_needs_recruitment=b2_fails,
                status=StatusCode.OK if (b1_fails or b2_fails) else StatusCode.REUSE,
            )
            qualifying_pairs.append(pair_eval)

            if b1_fails:
                entry1 = failing_rivals_by_key.setdefault(b1.comparison_key, (b1, []))
                if b2 not in entry1[1]:
                    entry1[1].append(b2)
            if b2_fails:
                entry2 = failing_rivals_by_key.setdefault(b2.comparison_key, (b2, []))
                if b1 not in entry2[1]:
                    entry2[1].append(b1)

    if not qualifying_pairs:
        return ContrastDiscoveryResult(
            anchor_id=anchor_id,
            status=StatusCode.UNRESOLVED_BRANCH_MATCH,
            qualifying_pairs=(),
            failing_branches_ordered=(),
        )

    ordered_failing = tuple(
        (b_sum, tuple(rivals))
        for _, (b_sum, rivals) in sorted(failing_rivals_by_key.items(), key=lambda item: item[0])
    )
    final_status = StatusCode.OK if ordered_failing else StatusCode.REUSE
    return ContrastDiscoveryResult(
        anchor_id=anchor_id,
        status=final_status,
        qualifying_pairs=tuple(qualifying_pairs),
        failing_branches_ordered=ordered_failing,
    )
