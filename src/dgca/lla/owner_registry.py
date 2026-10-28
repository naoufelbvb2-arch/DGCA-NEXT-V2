"""Persistent Owner Registry (OwnerProfileV1 / OwnerProfileV2) and ResolveOwner Governance.

Normative references:
- DGCA_CORE_RC4_1.md §7.7 (C04 persistent branch ownership across ledger expiration)
- DGCA_LLA_RC4_1.md §6.2, §6.5 & §6.6 (Owner dedup after 2000-event contrast TTL, FP-ROLE-V2)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dgca.common.errors import DGCAError, StatusCode
from dgca.common.hashing import (
    Role,
    RoleV2Record,
    WitnessSourceKind,
    compute_owner_profile_v1_digest,
    compute_owner_profile_v2_digest,
    serialize_fp_role_v1,
    serialize_fp_role_v2,
    sha256_bytes,
)
from dgca.core.context_gate import ANCHOR_SOURCE_MAX, M_P_Q6, validate_parent_hierarchy
from dgca.core.state import (
    BindingStatus,
    OwnerState,
    ParentContextRef,
    WState,
)
from dgca.lla.contrast_ledger import (
    BranchSummary,
    ContrastEpisodeRecord,
    D_Y_MIN,
    compute_role_footprint_digest,
    compute_weighted_footprint_distance,
)

DEFAULT_MAX_OWNERS_PER_ANCHOR: int = 32


def _top_k_support_items(supports_u: dict[int, int], k: int = 8) -> dict[int, int]:
    """Retain up to top-k positive supports ranked by (-support_u, cell_id), returned sorted by cell_id."""
    ranked = sorted(
        ((cid, sup) for cid, sup in supports_u.items() if sup > 0),
        key=lambda item: (-item[1], item[0]),
    )[:k]
    return {cid: sup for cid, sup in sorted(ranked, key=lambda item: item[0])}


@dataclass(slots=True)
class CompactWitnessProfile:
    """Compact completed-root witness profile stored in OwnerProfileV1/V2 (Core §7.7, LLA §6.5).

    Stores top-8 P/C/Y role supports, full observed footprint digests, and audited root ID
    (excluded from identity/equality comparisons).
    """

    top8_p_supports_u: dict[int, int]
    top8_c_supports_u: dict[int, int]
    top8_y_supports_u: dict[int, int]
    full_p_digest: bytes
    full_c_digest: bytes
    full_y_digest: bytes
    p_source_kinds: dict[int, WitnessSourceKind] = field(default_factory=dict)
    p_parent_refs: dict[int, ParentContextRef] = field(default_factory=dict)
    audited_root_id: int = 0
    p_bundle_digest: bytes = b""
    c_bundle_digest: bytes = b""
    y_bundle_digest: bytes = b""

    @classmethod
    def from_episode(cls, ep: ContrastEpisodeRecord) -> CompactWitnessProfile:
        top_p = _top_k_support_items(ep.p_supports_u, 8)
        top_c = _top_k_support_items(ep.c_supports_u, 8)
        top_y = _top_k_support_items(ep.y_supports_u, 8)
        return cls(
            top8_p_supports_u=top_p,
            top8_c_supports_u=top_c,
            top8_y_supports_u=top_y,
            full_p_digest=ep.p_digest,
            full_c_digest=ep.c_digest,
            full_y_digest=ep.y_digest,
            p_source_kinds={cid: ep.p_source_kinds.get(cid, WitnessSourceKind.DIRECT) for cid in top_p},
            p_parent_refs={
                cid: ep.p_parent_refs[cid]
                for cid in top_p
                if cid in ep.p_parent_refs
            },
            audited_root_id=ep.exposure_id,
            p_bundle_digest=ep.p_bundle_digest,
            c_bundle_digest=ep.c_bundle_digest,
            y_bundle_digest=ep.y_bundle_digest,
        )

    def serialize_role_subrecords_v1(self) -> tuple[bytes, bytes, bytes]:
        p_bytes = serialize_fp_role_v1(Role.P, sorted(self.top8_p_supports_u.items()))
        c_bytes = serialize_fp_role_v1(Role.C, sorted(self.top8_c_supports_u.items()))
        y_bytes = serialize_fp_role_v1(Role.Y, sorted(self.top8_y_supports_u.items()))
        return p_bytes, c_bytes, y_bytes

    def build_role_v2_records(self) -> tuple[list[RoleV2Record], list[RoleV2Record], list[RoleV2Record]]:
        p_items: list[RoleV2Record] = []
        for cid, sup in sorted(self.top8_p_supports_u.items()):
            kind = self.p_source_kinds.get(cid, WitnessSourceKind.DIRECT)
            if kind == WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT:
                ref = self.p_parent_refs[cid]
                p_items.append(
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
                p_items.append(
                    RoleV2Record(
                        global_cell_id=cid,
                        support_millionths=sup,
                        kind=WitnessSourceKind.DIRECT,
                    )
                )
        c_items = [
            RoleV2Record(global_cell_id=cid, support_millionths=sup, kind=WitnessSourceKind.DIRECT)
            for cid, sup in sorted(self.top8_c_supports_u.items())
        ]
        y_items = [
            RoleV2Record(global_cell_id=cid, support_millionths=sup, kind=WitnessSourceKind.DIRECT)
            for cid, sup in sorted(self.top8_y_supports_u.items())
        ]
        return p_items, c_items, y_items

    def serialize_role_subrecords_v2(self) -> tuple[bytes, bytes, bytes]:
        p_items, c_items, y_items = self.build_role_v2_records()
        return (
            serialize_fp_role_v2(Role.P, p_items),
            serialize_fp_role_v2(Role.C, c_items),
            serialize_fp_role_v2(Role.Y, y_items),
        )

    def clone(self) -> CompactWitnessProfile:
        return CompactWitnessProfile(
            top8_p_supports_u=dict(self.top8_p_supports_u),
            top8_c_supports_u=dict(self.top8_c_supports_u),
            top8_y_supports_u=dict(self.top8_y_supports_u),
            full_p_digest=self.full_p_digest,
            full_c_digest=self.full_c_digest,
            full_y_digest=self.full_y_digest,
            p_source_kinds=dict(self.p_source_kinds),
            p_parent_refs=dict(self.p_parent_refs),
            audited_root_id=self.audited_root_id,
            p_bundle_digest=self.p_bundle_digest,
            c_bundle_digest=self.c_bundle_digest,
            y_bundle_digest=self.y_bundle_digest,
        )


@dataclass(slots=True)
class OwnerProfile:
    """Persistent OwnerProfileV1 (schema_version=1, depth=1) or OwnerProfileV2 (schema_version=2, depth>1) (Core §7.7, LLA §6.5–6.6)."""

    schema_version: int
    anchor_id: int
    owner_seq: int
    z_cell_id: int
    state: OwnerState
    p_sources: tuple[int, int]
    c_sources: tuple[int, int]
    y_targets: tuple[int, int]
    l_z_q6: int
    u_z_q6: int
    tau_ctx_q6: int
    anchor_source_set: frozenset[int]
    witness_profiles: tuple[CompactWitnessProfile, CompactWitnessProfile]
    binding_generation: int = 1
    depth: int = 1
    p_source_kinds: tuple[WitnessSourceKind, WitnessSourceKind] = (
        WitnessSourceKind.DIRECT,
        WitnessSourceKind.DIRECT,
    )
    parent_refs: dict[int, ParentContextRef] = field(default_factory=dict)
    profile_digest: bytes = b""

    def __post_init__(self) -> None:
        if self.schema_version not in (1, 2):
            raise DGCAError(
                StatusCode.UNSUPPORTED_BINDING_SCHEMA,
                f"OwnerProfile schema_version must be 1 or 2, got {self.schema_version}",
            )
        if self.depth > 1 and self.schema_version != 2:
            raise DGCAError(
                StatusCode.UNSUPPORTED_BINDING_SCHEMA,
                "Depth > 1 OwnerProfile requires OwnerProfileV2 (schema_version=2)",
            )
        if self.depth == 1 and self.schema_version != 1:
            raise DGCAError(
                StatusCode.UNSUPPORTED_BINDING_SCHEMA,
                "Depth = 1 OwnerProfile requires OwnerProfileV1 (schema_version=1)",
            )
        if len(self.anchor_source_set) > ANCHOR_SOURCE_MAX:
            raise DGCAError(
                StatusCode.ANCHOR_CONTEXT_TOO_WIDE,
                f"AnchorSourceSet size {len(self.anchor_source_set)} exceeds {ANCHOR_SOURCE_MAX}",
            )
        if not self.profile_digest:
            self.profile_digest = self.compute_digest()

    @property
    def owner_id(self) -> tuple[int, int]:
        return (self.anchor_id, self.owner_seq)

    def compute_digest(self) -> bytes:
        """Compute canonical DGCA-OWNER-PROFILE-V1 or DGCA-OWNER-PROFILE-V2 SHA-256 digest."""
        w1, w2 = self.witness_profiles
        if self.schema_version == 1:
            d1 = compute_owner_profile_v1_digest(
                sorted(w1.top8_p_supports_u.items()),
                sorted(w1.top8_c_supports_u.items()),
                sorted(w1.top8_y_supports_u.items()),
            )
            d2 = compute_owner_profile_v1_digest(
                sorted(w2.top8_p_supports_u.items()),
                sorted(w2.top8_c_supports_u.items()),
                sorted(w2.top8_y_supports_u.items()),
            )
            return sha256_bytes(d1 + d2)
        p1, c1, y1 = w1.build_role_v2_records()
        p2, c2, y2 = w2.build_role_v2_records()
        d1 = compute_owner_profile_v2_digest(p1, c1, y1)
        d2 = compute_owner_profile_v2_digest(p2, c2, y2)
        return sha256_bytes(d1 + d2)

    def clone(self) -> OwnerProfile:
        return OwnerProfile(
            schema_version=self.schema_version,
            anchor_id=self.anchor_id,
            owner_seq=self.owner_seq,
            z_cell_id=self.z_cell_id,
            state=self.state,
            p_sources=self.p_sources,
            c_sources=self.c_sources,
            y_targets=self.y_targets,
            l_z_q6=self.l_z_q6,
            u_z_q6=self.u_z_q6,
            tau_ctx_q6=self.tau_ctx_q6,
            anchor_source_set=self.anchor_source_set,
            witness_profiles=(
                self.witness_profiles[0].clone(),
                self.witness_profiles[1].clone(),
            ),
            binding_generation=self.binding_generation,
            depth=self.depth,
            p_source_kinds=self.p_source_kinds,
            parent_refs=dict(self.parent_refs),
            profile_digest=self.profile_digest,
        )


@dataclass(frozen=True, slots=True)
class ResolveOwnerResult:
    """Result of ResolveOwner(anchor, new_branch, confirmed_rivals, frozen_W) (Core §7.7)."""

    status: StatusCode
    matched_owner_id: tuple[int, int] | None = None
    matched_z_cell_id: int | None = None
    diagnostic_detail: str = ""


def _check_branch_parent_references(
    branch: BranchSummary,
    w_state: WState,
) -> tuple[bool, StatusCode]:
    """Verify any DERIVED_EXTERNAL_CONTEXT P sources in branch have live COMPLETE parent bindings."""
    for ep in branch.episodes:
        for pid, kind in ep.p_source_kinds.items():
            if kind == WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT:
                ref = ep.p_parent_refs.get(pid)
                if ref is None:
                    return False, StatusCode.DERIVED_PROVENANCE_UNVERIFIED
                parent_bind = w_state.stable_bindings.get(pid)
                if parent_bind is None:
                    return False, StatusCode.PARENT_NOT_COMPLETE
                if (
                    parent_bind.status != BindingStatus.ACTIVE
                    or parent_bind.owner_id != (ref.parent_anchor_id, ref.parent_owner_seq)
                    or parent_bind.binding_generation != ref.parent_binding_generation
                ):
                    return False, StatusCode.PARENT_BINDING_STALE
                if ref.depth >= 8:
                    return False, StatusCode.CONTEXT_CHAIN_DEPTH_EXCEEDED
    return True, StatusCode.OK


def _matches_exact_profile(branch: BranchSummary, prof: OwnerProfile) -> tuple[bool, bool]:
    """Check if branch matches prof by exact physical witnessed P/C/Y digests + bounded top-8 supports.

    Returns:
        (is_exact_match, has_bundle_collision)
    """
    ep1, ep2 = branch.qualifying_two_episodes
    cand_w1 = CompactWitnessProfile.from_episode(ep1)
    cand_w2 = CompactWitnessProfile.from_episode(ep2)
    prof_w1, prof_w2 = prof.witness_profiles

    # Check collision: same neural role digest but different feature bundle digest
    for cw in (cand_w1, cand_w2):
        for pw in (prof_w1, prof_w2):
            if (
                cw.y_bundle_digest
                and pw.y_bundle_digest
                and cw.y_bundle_digest != pw.y_bundle_digest
                and cw.full_y_digest == pw.full_y_digest
            ):
                return False, True
            if (
                cw.p_bundle_digest
                and pw.p_bundle_digest
                and cw.p_bundle_digest != pw.p_bundle_digest
                and cw.full_p_digest == pw.full_p_digest
            ):
                return False, True

    # Full footprint digest equality + bounded top-8 support equality (root IDs excluded!)
    digests_match = (
        branch.p_digest == prof_w1.full_p_digest == prof_w2.full_p_digest
        and branch.c_digest == prof_w1.full_c_digest == prof_w2.full_c_digest
        and branch.y_digest == prof_w1.full_y_digest == prof_w2.full_y_digest
    )
    if not digests_match:
        return False, False

    supports_match = (
        cand_w1.top8_p_supports_u == prof_w1.top8_p_supports_u
        and cand_w1.top8_c_supports_u == prof_w1.top8_c_supports_u
        and cand_w1.top8_y_supports_u == prof_w1.top8_y_supports_u
        and cand_w1.p_source_kinds == prof_w1.p_source_kinds
        and cand_w1.p_parent_refs == prof_w1.p_parent_refs
    )
    return supports_match, False


def _overlaps_owner_roles(branch: BranchSummary, prof: OwnerProfile) -> bool:
    """Test physical role overlap (Core §7.7 step 3):
    Do both qualifying predecessor roots of branch support both of prof's selected P sources
    at or above prof.tau_ctx_q6 (or within the < 50,000 margin) AND >=1 of prof's selected C sources?
    """
    ep1, ep2 = branch.qualifying_two_episodes
    p0, p1 = prof.p_sources

    for ep in (ep1, ep2):
        # Verify source kind compatibility
        if ep.p_source_kinds.get(p0, WitnessSourceKind.DIRECT) != prof.p_source_kinds[0]:
            return False
        if ep.p_source_kinds.get(p1, WitnessSourceKind.DIRECT) != prof.p_source_kinds[1]:
            return False
        if prof.p_source_kinds[0] == WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT:
            if ep.p_parent_refs.get(p0) != prof.parent_refs.get(p0):
                return False
        if prof.p_source_kinds[1] == WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT:
            if ep.p_parent_refs.get(p1) != prof.parent_refs.get(p1):
                return False

        sup_p0 = ep.p_supports_u.get(p0, 0)
        sup_p1 = ep.p_supports_u.get(p1, 0)
        t_ep = min(sup_p0, sup_p1)
        if t_ep <= 0:
            return False
        # Overlap if t_ep meets tau_ctx_q6 or violates the 50,000 discrimination margin against prof.l_z_q6
        if t_ep < prof.tau_ctx_q6 and (prof.l_z_q6 - t_ep) >= M_P_Q6:
            return False

        if not any(ep.c_supports_u.get(cid, 0) > 0 for cid in prof.c_sources):
            return False

    return True


def _is_y_compatible(branch: BranchSummary, prof: OwnerProfile) -> bool:
    """Check whether branch's witnessed Y is compatible with prof's Y witness and selected Y targets."""
    ep1, ep2 = branch.qualifying_two_episodes
    for ep in (ep1, ep2):
        if not any(ep.y_supports_u.get(yid, 0) > 0 for yid in prof.y_targets):
            return False

    prof_y = prof.witness_profiles[0].top8_y_supports_u
    branch_y = _top_k_support_items(branch.representative_y_supports_u, 8)
    dist_y = compute_weighted_footprint_distance(branch_y, prof_y)
    return dist_y < D_Y_MIN


def _two_direction_p_discrimination_holds(
    branch: BranchSummary,
    confirmed_rivals: tuple[BranchSummary, ...],
    prof: OwnerProfile,
    w_state: WState,
) -> bool:
    """Check two-direction predecessor-pair discrimination between branch and retained owner prof (Core §7.7 step 4)."""
    ep1, ep2 = branch.qualifying_two_episodes
    p0, p1 = prof.p_sources

    # Direction 1: prof's selected (p0, p1) must discriminate prof's L_z against branch's 2 episodes by >= 50,000
    u_branch_on_prof_p = max(
        min(ep1.p_supports_u.get(p0, 0), ep1.p_supports_u.get(p1, 0)),
        min(ep2.p_supports_u.get(p0, 0), ep2.p_supports_u.get(p1, 0)),
    )
    if (prof.l_z_q6 - u_branch_on_prof_p) < M_P_Q6:
        return False

    # Direction 2: branch must have at least one feasible committed P-pair (np0, np1) that discriminates
    # branch's 2 episodes against prof's 2 witness profiles (and confirmed_rivals) by >= 50,000
    common_p = [
        cid
        for cid, sup in branch.representative_p_supports_u.items()
        if sup > 0
        and cid in w_state.committed_cells
        and w_state.available_outgoing_headroom(cid) > 0
    ]
    if len(common_p) < 2:
        return False

    pw1, pw2 = prof.witness_profiles
    for i in range(len(common_p)):
        for j in range(i + 1, len(common_p)):
            np0, np1 = common_p[i], common_p[j]
            l_new = min(
                min(ep1.p_supports_u.get(np0, 0), ep1.p_supports_u.get(np1, 0)),
                min(ep2.p_supports_u.get(np0, 0), ep2.p_supports_u.get(np1, 0)),
            )
            u_prof = max(
                min(pw1.top8_p_supports_u.get(np0, 0), pw1.top8_p_supports_u.get(np1, 0)),
                min(pw2.top8_p_supports_u.get(np0, 0), pw2.top8_p_supports_u.get(np1, 0)),
            )
            if (l_new - u_prof) < M_P_Q6:
                continue

            rival_ok = True
            for riv in confirmed_rivals:
                r1, r2 = riv.qualifying_two_episodes
                u_riv = max(
                    min(r1.p_supports_u.get(np0, 0), r1.p_supports_u.get(np1, 0)),
                    min(r2.p_supports_u.get(np0, 0), r2.p_supports_u.get(np1, 0)),
                )
                if (l_new - u_riv) < M_P_Q6:
                    rival_ok = False
                    break
            if rival_ok:
                return True

    return False


def resolve_owner(
    anchor_id: int,
    new_branch: BranchSummary,
    confirmed_rivals: tuple[BranchSummary, ...],
    w_state: WState,
    *,
    max_owners_per_anchor: int = DEFAULT_MAX_OWNERS_PER_ANCHOR,
) -> ResolveOwnerResult:
    """Execute persistent ResolveOwner(anchor, new_branch, confirmed_rivals, frozen_W) (Core §7.7, LLA §6.5).

    Statuses returned:
    - REUSE
    - NEW_ELIGIBLE
    - UNRESOLVED_BRANCH_MATCH
    - STALE_OWNER_BINDING
    - OWNER_REGISTRY_CONFLICT
    - OWNER_REGISTRY_CAPACITY
    - PARENT_NOT_COMPLETE / PARENT_BINDING_STALE / CONTEXT_CHAIN_DEPTH_EXCEEDED
    """
    # Step 1: Validate new_branch completeness and absence of collisions
    if (
        new_branch.anchor_id != anchor_id
        or new_branch.independent_root_count < 2
        or not new_branch.representative_p_supports_u
        or not new_branch.representative_c_supports_u
        or not new_branch.representative_y_supports_u
        or any(ep.has_collision for ep in new_branch.episodes)
    ):
        return ResolveOwnerResult(
            status=StatusCode.UNRESOLVED_BRANCH_MATCH,
            diagnostic_detail="Incomplete branch witnesses or collision flag",
        )

    ok_parents, parent_code = _check_branch_parent_references(new_branch, w_state)
    if not ok_parents:
        return ResolveOwnerResult(
            status=parent_code,
            diagnostic_detail="Invalid derived parent reference in new_branch",
        )

    profiles: list[OwnerProfile] = sorted(
        w_state.owner_profiles_by_anchor.get(anchor_id, []),  # type: ignore[arg-type]
        key=lambda p: p.owner_seq,
    )

    # Refresh any profile whose parent binding or own StableBinding became STALE
    for prof in profiles:
        if prof.state == OwnerState.COMPLETE:
            bind = w_state.stable_bindings.get(prof.z_cell_id)
            if bind is None or bind.status != BindingStatus.ACTIVE:
                prof.state = OwnerState.STALE
        if prof.depth > 1 and prof.state in (OwnerState.ACTIVE, OwnerState.COMPLETE):
            ok_h, _ = validate_parent_hierarchy(
                prof.depth,
                prof.p_sources,
                prof.p_source_kinds,
                prof.parent_refs,
                w_state,
                {prof.z_cell_id},
            )
            if not ok_h:
                prof.state = OwnerState.STALE

    # Step 2: Scan all owner profiles under anchor_id in canonical OwnerID order for exact matches
    exact_matches: list[OwnerProfile] = []
    for prof in profiles:
        is_exact, has_collision = _matches_exact_profile(new_branch, prof)
        if has_collision:
            return ResolveOwnerResult(
                status=StatusCode.UNRESOLVED_BRANCH_MATCH,
                diagnostic_detail="Feature bundle collision with existing OwnerProfile",
            )
        if is_exact:
            exact_matches.append(prof)

    if len(exact_matches) > 1:
        return ResolveOwnerResult(
            status=StatusCode.OWNER_REGISTRY_CONFLICT,
            diagnostic_detail="Multiple OwnerProfiles matched exact branch footprint",
        )
    if len(exact_matches) == 1:
        prof = exact_matches[0]
        if prof.state == OwnerState.STALE:
            return ResolveOwnerResult(
                status=StatusCode.STALE_OWNER_BINDING,
                matched_owner_id=prof.owner_id,
                matched_z_cell_id=prof.z_cell_id,
            )
        if prof.state in (OwnerState.ACTIVE, OwnerState.COMPLETE):
            return ResolveOwnerResult(
                status=StatusCode.REUSE,
                matched_owner_id=prof.owner_id,
                matched_z_cell_id=prof.z_cell_id,
            )
        # EXPIRED_VALIDATED or EXPIRED_EMPTY blocks automatic duplicate allocation (Core §7.7 step 5)
        return ResolveOwnerResult(
            status=StatusCode.UNRESOLVED_BRANCH_MATCH,
            matched_owner_id=prof.owner_id,
            matched_z_cell_id=prof.z_cell_id,
            diagnostic_detail=f"Owner {prof.owner_id} is {prof.state}; automatic duplicate blocked",
        )

    # Step 3: For non-exact profiles, test physical P/C role overlap
    overlapping_profiles: list[OwnerProfile] = [
        prof for prof in profiles if _overlaps_owner_roles(new_branch, prof)
    ]
    if len(overlapping_profiles) > 1:
        return ResolveOwnerResult(
            status=StatusCode.OWNER_REGISTRY_CONFLICT,
            diagnostic_detail="Multiple OwnerProfiles physically overlap new branch P/C roles",
        )
    if len(overlapping_profiles) == 1:
        prof = overlapping_profiles[0]
        if _is_y_compatible(new_branch, prof):
            if prof.state == OwnerState.STALE:
                return ResolveOwnerResult(
                    status=StatusCode.STALE_OWNER_BINDING,
                    matched_owner_id=prof.owner_id,
                    matched_z_cell_id=prof.z_cell_id,
                )
            if prof.state in (OwnerState.ACTIVE, OwnerState.COMPLETE):
                return ResolveOwnerResult(
                    status=StatusCode.REUSE,
                    matched_owner_id=prof.owner_id,
                    matched_z_cell_id=prof.z_cell_id,
                )
            return ResolveOwnerResult(
                status=StatusCode.UNRESOLVED_BRANCH_MATCH,
                matched_owner_id=prof.owner_id,
                matched_z_cell_id=prof.z_cell_id,
            )
        # Overlapping P/C but conflicting Y -> UNRESOLVED_BRANCH_MATCH, NOT new allocation (Core §7.7 step 3)
        return ResolveOwnerResult(
            status=StatusCode.UNRESOLVED_BRANCH_MATCH,
            matched_owner_id=prof.owner_id,
            matched_z_cell_id=prof.z_cell_id,
            diagnostic_detail="Physical P/C overlap with conflicting Y outcome",
        )

    # Step 4: Two-direction P-pair discrimination check against every relevant retained owner
    for prof in profiles:
        if prof.state in (OwnerState.ACTIVE, OwnerState.COMPLETE, OwnerState.EXPIRED_VALIDATED):
            if not _two_direction_p_discrimination_holds(
                new_branch, confirmed_rivals, prof, w_state
            ):
                return ResolveOwnerResult(
                    status=StatusCode.UNRESOLVED_BRANCH_MATCH,
                    matched_owner_id=prof.owner_id,
                    diagnostic_detail="Failed two-direction P-pair discrimination against retained owner",
                )

    # Step 5: Check owner registry capacity
    if len(profiles) >= max_owners_per_anchor:
        return ResolveOwnerResult(
            status=StatusCode.OWNER_REGISTRY_CAPACITY,
            diagnostic_detail=f"Anchor {anchor_id} reached max owners ({max_owners_per_anchor})",
        )

    return ResolveOwnerResult(status=StatusCode.NEW_ELIGIBLE)
