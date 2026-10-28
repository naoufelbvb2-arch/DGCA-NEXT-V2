"""Capacity-Aware Bounded 2/2/2 Source Selection and Contextual Candidate Recruitment.

Normative references:
- DGCA_CORE_RC4_1.md §5.1 & §7.3 (Predecessor calibration triple & bounded 2/2/2 source selection)
- DGCA_LLA_RC4_1.md §6.2 & §6.6 (Capacity pre-filtering, radius-2 search, hierarchical P provenance)
"""

from __future__ import annotations

from dataclasses import dataclass

from dgca.common.errors import DGCAError, StatusCode
from dgca.common.hashing import WitnessSourceKind
from dgca.core.anatomy import SynapseKey, SynapseScope
from dgca.core.context_gate import (
    ANCHOR_SOURCE_MAX,
    MAX_CHAIN_DEPTH,
    M_P_Q6,
    is_valid_calibration_triple,
    validate_parent_hierarchy,
)
from dgca.core.latent_index import COACTIVE_INTRA_SLOTS
from dgca.core.sic_v1 import CELLS_PER_MICROCOLUMN, CellAddress
from dgca.core.state import (
    BindingStatus,
    CandidatePhase,
    ContextCandidateDescriptor,
    OwnerState,
    ParentContextRef,
    WState,
)
from dgca.lla.contrast_ledger import BranchSummary
from dgca.lla.owner_registry import CompactWitnessProfile, OwnerProfile

TOP_K_ROLE_POOL: int = 8


@dataclass(frozen=True, slots=True)
class RankedRoleCandidate:
    """Ranked candidate cell for a P, C, or Y role in 2/2/2 selection (Core §7.3)."""

    cell_id: int
    independent_root_count: int
    min_support_q6: int
    available_outgoing_headroom: int
    source_kind: WitnessSourceKind = WitnessSourceKind.DIRECT
    parent_ref: ParentContextRef | None = None


@dataclass(frozen=True, slots=True)
class RecruitmentGateCounts:
    """Per-gate diagnostic counts during 2/2/2 triple enumeration (Core §7.3)."""

    raw_p_count: int = 0
    raw_c_count: int = 0
    raw_y_count: int = 0
    feasible_p_count: int = 0
    feasible_c_count: int = 0
    feasible_y_count: int = 0
    p_pairs_tested: int = 0
    p_pairs_discriminative: int = 0
    triples_tested: int = 0
    z_cells_in_frontier: int = 0


@dataclass(frozen=True, slots=True)
class RecruitmentResult:
    """Result of attempting to recruit a new contextual candidate cell z at END_EXPOSURE."""

    status: StatusCode
    descriptor: ContextCandidateDescriptor | None = None
    owner_profile: OwnerProfile | None = None
    gate_counts: RecruitmentGateCounts = RecruitmentGateCounts()
    diagnostic_detail: str = ""


def find_candidate_z_cells_within_radius2(
    anchor_id: int,
    w_state: WState,
) -> list[int]:
    """Find uncommitted, unprotected candidate z cells within Manhattan radius <= 2 of anchor_id (Core §7.3, LLA-T33).

    Search order:
    Radius band 1 (distance 0 = own microcolumn, then distance 1) before Radius band 2 (distance 2),
    ordered stably by (radius_band, manhattan_distance, committed_slots_in_mc, cell_id).
    """
    anchor_addr = CellAddress.from_global_id(anchor_id)
    region_base = int(anchor_addr.region) * 4096

    # Precompute number of committed slots per microcolumn in the anchor's region
    committed_slots_by_mc: dict[int, int] = {}
    for cid in w_state.committed_cells:
        if region_base <= cid < region_base + 4096:
            mc_idx = (cid - region_base) // CELLS_PER_MICROCOLUMN
            committed_slots_by_mc[mc_idx] = committed_slots_by_mc.get(mc_idx, 0) + 1

    candidates_with_sort_key: list[tuple[int, int, int, int]] = []
    for dr in range(-2, 3):
        for dc in range(-2, 3):
            dist = abs(dr) + abs(dc)
            if dist > 2:
                continue
            r = anchor_addr.mc_row + dr
            c = anchor_addr.mc_col + dc
            if not (0 <= r < 32 and 0 <= c < 16):
                continue
            mc_idx = r * 16 + c
            comm_count = committed_slots_by_mc.get(mc_idx, 0)
            radius_band = 1 if dist <= 1 else 2

            for slot in range(CELLS_PER_MICROCOLUMN):
                local_idx = mc_idx * CELLS_PER_MICROCOLUMN + slot
                cid = region_base + local_idx
                if cid in w_state.committed_cells:
                    continue
                if cid in w_state.context_candidates or cid in w_state.stable_bindings:
                    continue
                if any(w_state.latent_table.is_slot_pinned(cid, idx) for idx in COACTIVE_INTRA_SLOTS):
                    continue
                candidates_with_sort_key.append((radius_band, dist, comm_count, cid))

    candidates_with_sort_key.sort()
    return [item[3] for item in candidates_with_sort_key]


def compute_p_pair_calibration(
    p0: int,
    p1: int,
    owned_branch: BranchSummary,
    confirmed_rivals: tuple[BranchSummary, ...],
    retained_owners: list[OwnerProfile],
) -> tuple[bool, int, int, int]:
    """Compute and validate (L_z, U_z, tau_ctx_q6) for a candidate P pair (p0, p1) (Core §5.1, §7.3, LLA-T36/T37).

    Formula:
        T_z(r) = min(o_{p0}(r), o_{p1}(r))
        L_z = min_{r in owned} Q6(T_z(r))
        U_z = max_{r in confirmed_rivals U retained_owners} Q6(T_z(r))
        Require L_z - U_z >= 50,000 (M_P_Q6)
        tau_ctx_q6 = U_z + 50,000 <= L_z
    """
    ep1, ep2 = owned_branch.qualifying_two_episodes
    t_owned_1 = min(ep1.p_supports_u.get(p0, 0), ep1.p_supports_u.get(p1, 0))
    t_owned_2 = min(ep2.p_supports_u.get(p0, 0), ep2.p_supports_u.get(p1, 0))
    l_z_q6 = min(t_owned_1, t_owned_2)
    if l_z_q6 < M_P_Q6:
        return False, l_z_q6, 0, 0

    rival_t_values: list[int] = []
    for riv in confirmed_rivals:
        for rep in riv.episodes:
            t_riv = min(rep.p_supports_u.get(p0, 0), rep.p_supports_u.get(p1, 0))
            rival_t_values.append(t_riv)

    for prof in retained_owners:
        if prof.state in (OwnerState.ACTIVE, OwnerState.COMPLETE, OwnerState.EXPIRED_VALIDATED):
            pw1, pw2 = prof.witness_profiles
            rival_t_values.append(
                min(pw1.top8_p_supports_u.get(p0, 0), pw1.top8_p_supports_u.get(p1, 0))
            )
            rival_t_values.append(
                min(pw2.top8_p_supports_u.get(p0, 0), pw2.top8_p_supports_u.get(p1, 0))
            )

    if not rival_t_values:
        return False, l_z_q6, 0, 0

    u_z_q6 = max(rival_t_values)
    if (l_z_q6 - u_z_q6) < M_P_Q6:
        return False, l_z_q6, u_z_q6, 0

    tau_ctx_q6 = u_z_q6 + M_P_Q6
    if not is_valid_calibration_triple(l_z_q6, u_z_q6, tau_ctx_q6):
        return False, l_z_q6, u_z_q6, tau_ctx_q6

    return True, l_z_q6, u_z_q6, tau_ctx_q6


def recruit_contextual_candidate(
    anchor_id: int,
    owned_branch: BranchSummary,
    confirmed_rivals: tuple[BranchSummary, ...],
    w_state: WState,
    *,
    admitted_root_id: int,
    event_clock: int,
    remaining_k_r: int,
    newly_graduated_z_ids: set[int] | None = None,
) -> RecruitmentResult:
    """Execute deterministic capacity-aware bounded 2/2/2 source selection and candidate z recruitment (Core §7.3, LLA §6.2).

    Enforces:
    - AnchorSourceSet size <= 64 (ANCHOR_CONTEXT_TOO_WIDE)
    - remaining_k_r >= 1 (NO_FREE_CONTEXT_CELL)
    - Capacity pre-filtering on P and C before top-8 truncation (LLA-T32, LLA-T34 -> SOURCE_OUTGOING_CAPACITY)
    - Predecessor calibration L_z - U_z >= 50,000 (NO_DISCRIMINATIVE_PREDECESSOR_WITHIN_FRONTIER)
    - Radius-2 Manhattan search for free z cell (LLA-T33 -> NO_FREE_CONTEXT_CELL)
    - Hierarchy depth <= 8 and parent COMPLETE before this close (LG-T06)
    """
    graduated_now = newly_graduated_z_ids or set()
    ep1, ep2 = owned_branch.qualifying_two_episodes

    # 1. Validate AnchorSourceSet (union of directly observed committed current SIC receiver IDs in ep1, ep2)
    anchor_source_set = frozenset(
        cid
        for cid in (set(ep1.c_supports_u.keys()) | set(ep2.c_supports_u.keys()))
        if cid in w_state.committed_cells
    )
    if len(anchor_source_set) > ANCHOR_SOURCE_MAX:
        return RecruitmentResult(
            status=StatusCode.ANCHOR_CONTEXT_TOO_WIDE,
            diagnostic_detail=f"AnchorSourceSet size {len(anchor_source_set)} > {ANCHOR_SOURCE_MAX}",
        )

    # 2. Build raw committed role candidate pools supported in at least 2 independent roots
    p_root_counts: dict[int, set[int]] = {}
    c_root_counts: dict[int, set[int]] = {}
    y_root_counts: dict[int, set[int]] = {}
    for ep in owned_branch.episodes:
        for pid, sup in ep.p_supports_u.items():
            if sup > 0 and pid in w_state.committed_cells:
                p_root_counts.setdefault(pid, set()).add(ep.exposure_id)
        for cid, sup in ep.c_supports_u.items():
            if sup > 0 and cid in w_state.committed_cells:
                c_root_counts.setdefault(cid, set()).add(ep.exposure_id)
        for yid, sup in ep.y_supports_u.items():
            if sup > 0 and yid in w_state.committed_cells:
                y_root_counts.setdefault(yid, set()).add(ep.exposure_id)

    raw_p_ids = sorted(pid for pid, roots in p_root_counts.items() if len(roots) >= 2)
    raw_c_ids = sorted(cid for cid, roots in c_root_counts.items() if len(roots) >= 2)
    raw_y_ids = sorted(yid for yid, roots in y_root_counts.items() if len(roots) >= 2)

    # Check hierarchy constraints on derived P candidates before pooling (Core §6.1, LLA §6.6, LG-T06)
    valid_raw_p_ids: list[int] = []
    hierarchy_error: StatusCode | None = None
    for pid in raw_p_ids:
        kind1 = ep1.p_source_kinds.get(pid, WitnessSourceKind.DIRECT)
        kind2 = ep2.p_source_kinds.get(pid, WitnessSourceKind.DIRECT)
        if kind1 != kind2:
            hierarchy_error = StatusCode.DERIVED_PROVENANCE_UNVERIFIED
            break
        if kind1 == WitnessSourceKind.DIRECT and w_state.is_contextual_cell(pid):
            # Never fallback to DIRECT for a contextual cell (Core §6.1, LG-T06, LG-T13)
            hierarchy_error = StatusCode.DERIVED_PROVENANCE_UNVERIFIED
            break
        if kind1 == WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT:
            if pid in graduated_now or pid in w_state.context_candidates or pid not in w_state.stable_bindings:
                hierarchy_error = StatusCode.PARENT_NOT_COMPLETE
                break
            parent_bind = w_state.stable_bindings[pid]
            ref1 = ep1.p_parent_refs.get(pid)
            ref2 = ep2.p_parent_refs.get(pid)
            if ref1 is None or ref1 != ref2:
                hierarchy_error = StatusCode.DERIVED_PROVENANCE_UNVERIFIED
                break
            if (
                parent_bind.status != BindingStatus.ACTIVE
                or parent_bind.owner_id != (ref1.parent_anchor_id, ref1.parent_owner_seq)
                or parent_bind.binding_generation != ref1.parent_binding_generation
                or parent_bind.depth != ref1.depth
            ):
                hierarchy_error = StatusCode.PARENT_BINDING_STALE
                break
            if parent_bind.depth + 1 > MAX_CHAIN_DEPTH:
                hierarchy_error = StatusCode.CONTEXT_CHAIN_DEPTH_EXCEEDED
                break
            ok_anc, anc_code = validate_parent_hierarchy(
                parent_bind.depth,
                parent_bind.p_sources,
                parent_bind.p_source_kinds,
                parent_bind.parent_refs,
                w_state,
                {pid},
            )
            if not ok_anc:
                hierarchy_error = anc_code
                break
        valid_raw_p_ids.append(pid)

    if hierarchy_error is not None:
        return RecruitmentResult(
            status=hierarchy_error,
            diagnostic_detail="Derived P candidate failed hierarchy validation (no fallback to DIRECT)",
        )

    if len(valid_raw_p_ids) < 2 or len(raw_c_ids) < 2 or len(raw_y_ids) < 2:
        return RecruitmentResult(
            status=StatusCode.NO_FEASIBLE_2_2_2_WITHIN_FRONTIER,
            gate_counts=RecruitmentGateCounts(
                raw_p_count=len(valid_raw_p_ids),
                raw_c_count=len(raw_c_ids),
                raw_y_count=len(raw_y_ids),
            ),
            diagnostic_detail="Fewer than 2 committed witnessed sources in P, C, or Y",
        )

    # 3. CRITICAL RC3 RULE (LLA-T32, LLA-T34, Core §7.3):
    # Filter P and C candidates with available_outgoing_headroom == 0 BEFORE ranking and truncating to top 8!
    feasible_p_pool: list[RankedRoleCandidate] = []
    for pid in valid_raw_p_ids:
        headroom = w_state.available_outgoing_headroom(pid)
        if headroom < 1:
            continue
        min_sup = min(ep1.p_supports_u.get(pid, 0), ep2.p_supports_u.get(pid, 0))
        if min_sup <= 0:
            continue
        kind = ep1.p_source_kinds.get(pid, WitnessSourceKind.DIRECT)
        ref = ep1.p_parent_refs.get(pid) if kind == WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT else None
        feasible_p_pool.append(
            RankedRoleCandidate(
                cell_id=pid,
                independent_root_count=len(p_root_counts[pid]),
                min_support_q6=min_sup,
                available_outgoing_headroom=headroom,
                source_kind=kind,
                parent_ref=ref,
            )
        )

    feasible_c_pool: list[RankedRoleCandidate] = []
    for cid in raw_c_ids:
        headroom = w_state.available_outgoing_headroom(cid)
        if headroom < 1:
            continue
        min_sup = min(ep1.c_supports_u.get(cid, 0), ep2.c_supports_u.get(cid, 0))
        if min_sup <= 0:
            continue
        feasible_c_pool.append(
            RankedRoleCandidate(
                cell_id=cid,
                independent_root_count=len(c_root_counts[cid]),
                min_support_q6=min_sup,
                available_outgoing_headroom=headroom,
            )
        )

    feasible_y_pool: list[RankedRoleCandidate] = []
    for yid in raw_y_ids:
        min_sup = min(ep1.y_supports_u.get(yid, 0), ep2.y_supports_u.get(yid, 0))
        if min_sup <= 0:
            continue
        feasible_y_pool.append(
            RankedRoleCandidate(
                cell_id=yid,
                independent_root_count=len(y_root_counts[yid]),
                min_support_q6=min_sup,
                available_outgoing_headroom=w_state.available_outgoing_headroom(yid),
            )
        )

    if len(feasible_p_pool) < 2 or len(feasible_c_pool) < 2:
        return RecruitmentResult(
            status=StatusCode.SOURCE_OUTGOING_CAPACITY,
            gate_counts=RecruitmentGateCounts(
                raw_p_count=len(valid_raw_p_ids),
                raw_c_count=len(raw_c_ids),
                raw_y_count=len(raw_y_ids),
                feasible_p_count=len(feasible_p_pool),
                feasible_c_count=len(feasible_c_pool),
                feasible_y_count=len(feasible_y_pool),
            ),
            diagnostic_detail="Outgoing budget B_i exhausted on witnessed P or C candidates",
        )

    if len(feasible_y_pool) < 2:
        return RecruitmentResult(
            status=StatusCode.NO_FEASIBLE_2_2_2_WITHIN_FRONTIER,
            diagnostic_detail="Fewer than 2 witnessed Y targets",
        )

    # Rank and truncate to top 8 per role (Core §7.3)
    feasible_p_pool.sort(
        key=lambda r: (
            -r.independent_root_count,
            -r.min_support_q6,
            -r.available_outgoing_headroom,
            r.cell_id,
        )
    )
    top8_p = feasible_p_pool[:TOP_K_ROLE_POOL]

    feasible_c_pool.sort(
        key=lambda r: (
            -r.independent_root_count,
            -r.min_support_q6,
            -r.available_outgoing_headroom,
            r.cell_id,
        )
    )
    top8_c = feasible_c_pool[:TOP_K_ROLE_POOL]

    feasible_y_pool.sort(
        key=lambda r: (
            -r.independent_root_count,
            -r.min_support_q6,
            r.cell_id,
        )
    )
    top8_y = feasible_y_pool[:TOP_K_ROLE_POOL]

    # 4. Pre-evaluate P pairs in canonical rank-index order for Q6 discrimination L_z - U_z >= 50,000
    retained_owners: list[OwnerProfile] = list(
        w_state.owner_profiles_by_anchor.get(anchor_id, [])  # type: ignore[arg-type]
    )
    p_pairs_tested = 0
    discriminative_p_pairs: list[
        tuple[RankedRoleCandidate, RankedRoleCandidate, int, int, int]
    ] = []

    for i in range(len(top8_p)):
        for j in range(i + 1, len(top8_p)):
            p_pairs_tested += 1
            cand_p0, cand_p1 = top8_p[i], top8_p[j]
            # Order physical P pair canonically by cell_id for deterministic binding keys
            if cand_p0.cell_id > cand_p1.cell_id:
                cand_p0, cand_p1 = cand_p1, cand_p0
            ok_cal, l_z, u_z, tau_q6 = compute_p_pair_calibration(
                cand_p0.cell_id,
                cand_p1.cell_id,
                owned_branch,
                confirmed_rivals,
                retained_owners,
            )
            if ok_cal:
                discriminative_p_pairs.append((cand_p0, cand_p1, l_z, u_z, tau_q6))

    if not discriminative_p_pairs:
        return RecruitmentResult(
            status=StatusCode.NO_DISCRIMINATIVE_PREDECESSOR_WITHIN_FRONTIER,
            gate_counts=RecruitmentGateCounts(
                raw_p_count=len(valid_raw_p_ids),
                raw_c_count=len(raw_c_ids),
                raw_y_count=len(raw_y_ids),
                feasible_p_count=len(top8_p),
                feasible_c_count=len(top8_c),
                feasible_y_count=len(top8_y),
                p_pairs_tested=p_pairs_tested,
                p_pairs_discriminative=0,
            ),
            diagnostic_detail="No P pair in top-8 pool met L_z - U_z >= 50,000",
        )

    # 5. Check remaining K_R and find candidate z cells within Manhattan radius <= 2 of anchor_id
    z_candidates = find_candidate_z_cells_within_radius2(anchor_id, w_state)
    if remaining_k_r <= 0 or not z_candidates:
        return RecruitmentResult(
            status=StatusCode.NO_FREE_CONTEXT_CELL,
            gate_counts=RecruitmentGateCounts(
                raw_p_count=len(valid_raw_p_ids),
                raw_c_count=len(raw_c_ids),
                raw_y_count=len(raw_y_ids),
                feasible_p_count=len(top8_p),
                feasible_c_count=len(top8_c),
                feasible_y_count=len(top8_y),
                p_pairs_tested=p_pairs_tested,
                p_pairs_discriminative=len(discriminative_p_pairs),
                z_cells_in_frontier=len(z_candidates),
            ),
            diagnostic_detail="No free uncommitted z cell within Manhattan radius <= 2 or K_R exhausted",
        )

    # 6. Enumerate <= choose(8,2)^3 = 21,952 triples in canonical rank-index order across candidate z cells
    triples_tested = 0
    saw_overlap_capacity_failure = False

    for z_id in z_candidates:
        for cand_p0, cand_p1, l_z, u_z, tau_q6 in discriminative_p_pairs:
            p0, p1 = cand_p0.cell_id, cand_p1.cell_id
            if z_id in (p0, p1):
                continue

            # Compute hierarchy depth and parent references for (cand_p0, cand_p1)
            p_kinds = (cand_p0.source_kind, cand_p1.source_kind)
            parent_refs: dict[int, ParentContextRef] = {}
            max_parent_depth = 0
            for pcand in (cand_p0, cand_p1):
                if pcand.source_kind == WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT and pcand.parent_ref is not None:
                    parent_refs[pcand.cell_id] = pcand.parent_ref
                    max_parent_depth = max(max_parent_depth, pcand.parent_ref.depth)
            depth = 1 + max_parent_depth
            if depth > 1:
                ok_h, _ = validate_parent_hierarchy(
                    depth, (p0, p1), p_kinds, parent_refs, w_state, {z_id}
                )
                if not ok_h:
                    continue

            for ci in range(len(top8_c)):
                for cj in range(ci + 1, len(top8_c)):
                    c0, c1 = top8_c[ci].cell_id, top8_c[cj].cell_id
                    if c0 > c1:
                        c0, c1 = c1, c0
                    if z_id in (c0, c1):
                        continue

                    # Check outgoing capacity when P and C overlap on the same source cell:
                    # (src, z, ASSOCIATIVE) and (src, z, LOCAL) are two distinct directed keys!
                    required_keys_by_src: dict[int, set[SynapseKey]] = {}
                    for pid in (p0, p1):
                        required_keys_by_src.setdefault(pid, set()).add(
                            (pid, z_id, SynapseScope.ASSOCIATIVE)
                        )
                    for cid in (c0, c1):
                        required_keys_by_src.setdefault(cid, set()).add(
                            (cid, z_id, SynapseScope.LOCAL)
                        )

                    capacity_ok = True
                    for src_id, new_keys in required_keys_by_src.items():
                        existing_claimed = w_state.unique_claimed_outgoing_keys(src_id)
                        net_new = len(new_keys - existing_claimed)
                        if w_state.available_outgoing_headroom(src_id) < net_new:
                            capacity_ok = False
                            saw_overlap_capacity_failure = True
                            break
                    if not capacity_ok:
                        continue

                    for yi in range(len(top8_y)):
                        for yj in range(yi + 1, len(top8_y)):
                            triples_tested += 1
                            y0, y1 = top8_y[yi].cell_id, top8_y[yj].cell_id
                            if y0 > y1:
                                y0, y1 = y1, y0
                            if z_id in (y0, y1):
                                continue

                            # Verify that all distinct role partners {p0, p1, c0, c1, y0, y1}
                            # can be placed and pinned in z's 6 CO_ACTIVE_INTRA latent slots
                            distinct_role_cells = sorted({p0, p1, c0, c1, y0, y1})
                            test_latent = w_state.latent_table.clone()
                            try:
                                test_latent.pin_context_candidate_roles(
                                    z_id,
                                    distinct_role_cells,
                                    protected_bidirectional_neighbors=w_state.get_protected_bidirectional_neighbors(
                                        z_id
                                    ),
                                    event_clock=event_clock,
                                )
                            except DGCAError:
                                continue

                            # All gates passed! Commit z, apply latent pins, allocate OwnerID, and publish descriptor + profile
                            owner_seq = w_state.next_owner_seq_by_anchor.get(anchor_id, 1)
                            w_state.next_owner_seq_by_anchor[anchor_id] = owner_seq + 1

                            w_state.commit_cell(z_id, event_clock)
                            w_state.latent_table = test_latent
                            for partner_id in distinct_role_cells:
                                w_state.last_referenced_event[partner_id] = event_clock

                            desc = ContextCandidateDescriptor(
                                z_cell_id=z_id,
                                anchor_id=anchor_id,
                                owner_seq=owner_seq,
                                p_sources=(p0, p1),
                                c_sources=(c0, c1),
                                y_targets=(y0, y1),
                                l_z_q6=l_z,
                                u_z_q6=u_z,
                                tau_ctx_q6=tau_q6,
                                anchor_source_set=anchor_source_set,
                                phase=CandidatePhase.WIRED,
                                probe_matches=0,
                                consolidation_matches=0,
                                age_events=0,
                                admitted_root_id=admitted_root_id,
                                depth=depth,
                                p_source_kinds=p_kinds,
                                parent_refs=parent_refs,
                                status=BindingStatus.ACTIVE,
                            )
                            w_state.context_candidates[z_id] = desc
                            w_state.reserved_keys_by_candidate[z_id] = set(desc.reserved_synapse_keys)

                            w1_prof = CompactWitnessProfile.from_episode(ep1)
                            w2_prof = CompactWitnessProfile.from_episode(ep2)
                            owner_prof = OwnerProfile(
                                schema_version=1 if depth == 1 else 2,
                                anchor_id=anchor_id,
                                owner_seq=owner_seq,
                                z_cell_id=z_id,
                                state=OwnerState.ACTIVE,
                                p_sources=(p0, p1),
                                c_sources=(c0, c1),
                                y_targets=(y0, y1),
                                l_z_q6=l_z,
                                u_z_q6=u_z,
                                tau_ctx_q6=tau_q6,
                                anchor_source_set=anchor_source_set,
                                witness_profiles=(w1_prof, w2_prof),
                                binding_generation=1,
                                depth=depth,
                                p_source_kinds=p_kinds,
                                parent_refs=parent_refs,
                            )
                            w_state.owner_profiles_by_anchor.setdefault(anchor_id, []).append(
                                owner_prof
                            )

                            return RecruitmentResult(
                                status=StatusCode.OK,
                                descriptor=desc,
                                owner_profile=owner_prof,
                                gate_counts=RecruitmentGateCounts(
                                    raw_p_count=len(valid_raw_p_ids),
                                    raw_c_count=len(raw_c_ids),
                                    raw_y_count=len(raw_y_ids),
                                    feasible_p_count=len(top8_p),
                                    feasible_c_count=len(top8_c),
                                    feasible_y_count=len(top8_y),
                                    p_pairs_tested=p_pairs_tested,
                                    p_pairs_discriminative=len(discriminative_p_pairs),
                                    triples_tested=triples_tested,
                                    z_cells_in_frontier=len(z_candidates),
                                ),
                            )

    failure_code = (
        StatusCode.SOURCE_OUTGOING_CAPACITY
        if saw_overlap_capacity_failure
        else StatusCode.NO_FEASIBLE_2_2_2_WITHIN_FRONTIER
    )
    return RecruitmentResult(
        status=failure_code,
        gate_counts=RecruitmentGateCounts(
            raw_p_count=len(valid_raw_p_ids),
            raw_c_count=len(raw_c_ids),
            raw_y_count=len(raw_y_ids),
            feasible_p_count=len(top8_p),
            feasible_c_count=len(top8_c),
            feasible_y_count=len(top8_y),
            p_pairs_tested=p_pairs_tested,
            p_pairs_discriminative=len(discriminative_p_pairs),
            triples_tested=triples_tested,
            z_cells_in_frontier=len(z_candidates),
        ),
        diagnostic_detail="No feasible 2/2/2 triple found across candidate z frontier",
    )
