"""RC4 Hierarchical Derived Context Provenance and Depth <= 8 Governance.

Normative references:
- DGCA_CORE_RC4_1.md §6.1 (RC4 typed physical support and derived contextual witness, MAX_CHAIN_DEPTH=8)
- DGCA_LLA_RC4_1.md §6.6 (RC4 derived-external provenance and higher-level context learning, FP-ROLE-V2)
- DGCA_LLA_RC4_1.md §8.3 (LG-T04, LG-T05, LG-T06, LG-T13)
"""

from __future__ import annotations

from dgca.common.errors import StatusCode
from dgca.common.hashing import (
    Role,
    RoleV2Record,
    WitnessSourceKind,
    compute_fp_role_v1,
    compute_fp_role_v2,
)
from dgca.core.context_gate import (
    MAX_CHAIN_DEPTH,
    validate_and_refresh_stable_binding,
    validate_parent_hierarchy,
)
from dgca.core.state import (
    BindingStatus,
    ContributionLane,
    ExecutionMode,
    ParentContextRef,
    TypedSupportRecord,
    WState,
)
from dgca.encoder.envelope import EventOrigin


def has_ancestor_cycle(
    candidate_z_id: int,
    p_sources: tuple[int, int],
    p_source_kinds: tuple[WitnessSourceKind, WitnessSourceKind],
    w: WState,
) -> bool:
    """Return True if candidate_z_id appears anywhere in the ancestor chain of p_sources (Core §6.1, LG-T06)."""
    stack: list[tuple[int, set[int]]] = []
    for idx, pid in enumerate(p_sources):
        if p_source_kinds[idx] == WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT:
            if pid == candidate_z_id:
                return True
            stack.append((pid, {candidate_z_id, pid}))

    while stack:
        curr_id, seen = stack.pop()
        bind = w.stable_bindings.get(curr_id)
        if bind is None:
            continue
        for idx, parent_id in enumerate(bind.p_sources):
            if bind.p_source_kinds[idx] == WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT:
                if parent_id in seen:
                    return True
                stack.append((parent_id, seen | {parent_id}))
    return False


def validate_child_context_admission_hierarchy(
    p_sources: tuple[int, int],
    p_source_kinds: tuple[WitnessSourceKind, WitnessSourceKind],
    parent_refs: dict[int, ParentContextRef],
    w: WState,
    *,
    candidate_z_id: int | None = None,
    newly_graduated_z_ids: set[int] | None = None,
) -> tuple[bool, StatusCode, int]:
    """Validate parent completion, binding freshness, cycle-freeness, and depth <= 8 at admission (Core §6.1, LLA §6.6, LG-T06).

    Never falls back to DIRECT when a contextual parent fails validation.
    Returns:
        (ok, status_code, computed_depth)
    """
    graduated_now = newly_graduated_z_ids or set()
    max_parent_depth = 0

    for idx, pid in enumerate(p_sources):
        kind = p_source_kinds[idx]
        if kind == WitnessSourceKind.DIRECT:
            # A contextual cell can never be treated as a DIRECT_OBSERVED sensory source (Core §6.1, LG-T06, LG-T13)
            if w.is_contextual_cell(pid):
                return False, StatusCode.DERIVED_PROVENANCE_UNVERIFIED, 0
        elif kind == WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT:
            # Parent must have graduated BEFORE this close (not incomplete, and not newly graduated in this same END)
            if pid in graduated_now or pid in w.context_candidates or pid not in w.stable_bindings:
                return False, StatusCode.PARENT_NOT_COMPLETE, 0

            parent_bind = w.stable_bindings[pid]
            ref = parent_refs.get(pid)
            if ref is None:
                return False, StatusCode.DERIVED_PROVENANCE_UNVERIFIED, 0

            if (
                parent_bind.status != BindingStatus.ACTIVE
                or parent_bind.owner_id != (ref.parent_anchor_id, ref.parent_owner_seq)
                or parent_bind.binding_generation != ref.parent_binding_generation
                or parent_bind.depth != ref.depth
            ):
                return False, StatusCode.PARENT_BINDING_STALE, 0

            ok_parent, parent_code = validate_and_refresh_stable_binding(parent_bind, w)
            if not ok_parent:
                if parent_code == StatusCode.STALE_CONTEXT_BINDING:
                    return False, StatusCode.PARENT_BINDING_STALE, 0
                return False, parent_code, 0

            max_parent_depth = max(max_parent_depth, parent_bind.depth)
        else:
            return False, StatusCode.DERIVED_PROVENANCE_UNVERIFIED, 0

    if candidate_z_id is not None and has_ancestor_cycle(
        candidate_z_id, p_sources, p_source_kinds, w
    ):
        return False, StatusCode.CONTEXT_CHAIN_CYCLE, 0

    computed_depth = 1 + max_parent_depth
    if computed_depth > MAX_CHAIN_DEPTH:
        return False, StatusCode.CONTEXT_CHAIN_DEPTH_EXCEEDED, computed_depth

    initial_visited = {candidate_z_id} if candidate_z_id is not None else set()
    ok_hier, hier_code = validate_parent_hierarchy(
        computed_depth,
        p_sources,
        p_source_kinds,
        parent_refs,
        w,
        initial_visited,
    )
    if not ok_hier:
        return False, hier_code, computed_depth

    return True, StatusCode.OK, computed_depth


def verify_derived_context_chain(
    z_cell_id: int,
    event_order: int,
    prev_supports: dict[int, TypedSupportRecord],
    curr_supports: dict[int, TypedSupportRecord],
    w: WState,
    *,
    mode: ExecutionMode,
    origin: EventOrigin,
    g_ctx: int,
    in_f_step: bool,
    is_bootstrapped: bool,
) -> tuple[bool, StatusCode]:
    """Verify that COMPLETE contextual cell z_cell_id has a valid causal chain at event_order (Core §6.1, LLA §6.6, LG-T04/T05/T13).

    Checks:
    - z_cell_id is COMPLETE (in w.stable_bindings and not in w.context_candidates)
    - StableBinding is ACTIVE and structurally valid (depth <= 8, no cycles, parents active)
    - g_ctx == 1 and in_f_step == True
    - In LEARN: origin == EXTERNAL_DIRECT and not is_bootstrapped (no probe contribution)
    - event_order >= binding.depth (causal ordering inside the open exposure/episode)
    - Both P sources in prev_supports have exact prior event_order (event_order - 1),
      parent_proof_verified == True, and matching source kind & parent binding reference
    - At least one retained C source has direct SIC support at event_order
    """
    if z_cell_id in w.context_candidates or z_cell_id not in w.stable_bindings:
        return False, StatusCode.PARENT_NOT_COMPLETE

    binding = w.stable_bindings[z_cell_id]
    ok_bind, bind_code = validate_and_refresh_stable_binding(binding, w)
    if not ok_bind:
        return False, bind_code

    if g_ctx != 1 or not in_f_step:
        return False, StatusCode.DERIVED_PROVENANCE_UNVERIFIED

    if is_bootstrapped:
        return False, StatusCode.DERIVED_PROVENANCE_UNVERIFIED

    if mode == ExecutionMode.LEARN and origin != EventOrigin.EXTERNAL_DIRECT:
        return False, StatusCode.DERIVED_PROVENANCE_UNVERIFIED

    if event_order < binding.depth:
        return False, StatusCode.DERIVED_PROVENANCE_UNVERIFIED

    # Check both predecessor supports at event_order - 1
    for idx, pid in enumerate(binding.p_sources):
        expected_kind = binding.p_source_kinds[idx]
        rec_p = prev_supports.get(pid)
        if rec_p is None:
            return False, StatusCode.DERIVED_PROVENANCE_UNVERIFIED
        if rec_p.event_order != event_order - 1 or not rec_p.parent_proof_verified:
            return False, StatusCode.DERIVED_PROVENANCE_UNVERIFIED

        if expected_kind == WitnessSourceKind.DIRECT:
            if w.is_contextual_cell(pid):
                return False, StatusCode.DERIVED_PROVENANCE_UNVERIFIED
            if mode == ExecutionMode.LEARN:
                if rec_p.origin_kind != EventOrigin.EXTERNAL_DIRECT.value or rec_p.o_train <= 0.0:
                    return False, StatusCode.DERIVED_PROVENANCE_UNVERIFIED
            else:
                if (
                    rec_p.origin_kind
                    not in (
                        EventOrigin.EXTERNAL_DIRECT.value,
                        EventOrigin.READ_ONLY_OBSERVED.value,
                        EventOrigin.INTERNAL_SELECTED.value,
                    )
                    or rec_p.o_runtime <= 0.0
                ):
                    return False, StatusCode.DERIVED_PROVENANCE_UNVERIFIED
        elif expected_kind == WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT:
            ref = binding.parent_refs.get(pid)
            if ref is None:
                return False, StatusCode.DERIVED_PROVENANCE_UNVERIFIED
            if (
                rec_p.owner_id != (ref.parent_anchor_id, ref.parent_owner_seq)
                or rec_p.binding_generation != ref.parent_binding_generation
                or rec_p.depth != ref.depth
            ):
                return False, StatusCode.PARENT_BINDING_STALE
            if mode == ExecutionMode.LEARN:
                if (
                    rec_p.origin_kind != ContributionLane.DERIVED_EXTERNAL_CONTEXT.value
                    or rec_p.o_train <= 0.0
                ):
                    return False, StatusCode.DERIVED_PROVENANCE_UNVERIFIED
            else:
                if (
                    rec_p.origin_kind
                    not in (
                        ContributionLane.DERIVED_EXTERNAL_CONTEXT.value,
                        ContributionLane.DERIVED_RUNTIME_CONTEXT.value,
                    )
                    or rec_p.o_runtime <= 0.0
                ):
                    return False, StatusCode.DERIVED_PROVENANCE_UNVERIFIED
        else:
            return False, StatusCode.DERIVED_PROVENANCE_UNVERIFIED

    # Check at least 1 retained C source has direct SIC support at event_order
    has_valid_c = False
    for cid in binding.c_sources:
        if w.is_contextual_cell(cid):
            continue
        rec_c = curr_supports.get(cid)
        if rec_c is None or rec_c.event_order != event_order:
            continue
        if mode == ExecutionMode.LEARN:
            if rec_c.origin_kind == EventOrigin.EXTERNAL_DIRECT.value and rec_c.o_train > 0.0:
                has_valid_c = True
                break
        else:
            if (
                rec_c.origin_kind
                in (
                    EventOrigin.EXTERNAL_DIRECT.value,
                    EventOrigin.READ_ONLY_OBSERVED.value,
                    EventOrigin.INTERNAL_SELECTED.value,
                )
                and rec_c.o_runtime > 0.0
            ):
                has_valid_c = True
                break

    if not has_valid_c:
        return False, StatusCode.DERIVED_PROVENANCE_UNVERIFIED

    return True, StatusCode.OK


def build_typed_p_role_digest(
    p_supports_u: dict[int, int],
    p_source_kinds: dict[int, WitnessSourceKind],
    p_parent_refs: dict[int, ParentContextRef],
) -> bytes:
    """Compute canonical FP-ROLE-V1 (all DIRECT) or FP-ROLE-V2 (any DERIVED_EXTERNAL_CONTEXT) digest for Role.P (LLA §6.6)."""
    nonzero_items = sorted((cid, sup) for cid, sup in p_supports_u.items() if sup > 0)
    has_derived = any(
        p_source_kinds.get(cid, WitnessSourceKind.DIRECT)
        == WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT
        for cid, _ in nonzero_items
    )
    if not has_derived:
        return compute_fp_role_v1(Role.P, nonzero_items)

    records: list[RoleV2Record] = []
    for cid, sup in nonzero_items:
        kind = p_source_kinds.get(cid, WitnessSourceKind.DIRECT)
        if kind == WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT:
            ref = p_parent_refs.get(cid)
            if ref is None:
                raise ValueError(f"Missing ParentContextRef for derived predecessor {cid}")
            records.append(
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
            records.append(
                RoleV2Record(
                    global_cell_id=cid,
                    support_millionths=sup,
                    kind=WitnessSourceKind.DIRECT,
                )
            )
    return compute_fp_role_v2(Role.P, records)
