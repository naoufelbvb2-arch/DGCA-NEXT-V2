"""Permanent Physical Conjunction Gate G_z^ctx, Candidate Probe, and RC4.1 Target-Scoped Routing μ_ij.

Normative references:
- DGCA_CORE_RC4_1.md §5.1 (RC3 — Permanent physical conjunction for contextual cells)
- DGCA_CORE_RC4_1.md §5.2 (RC3 / RC4.1 — Physically scoped contextual priority at the temporal source)
- DGCA_CORE_RC4_1.md §6.1 (RC4 typed physical support and derived contextual witness)
- DGCA_CORE_RC4_1.md §7.5 (LEARN-only Bootstrap inside the permanent gate)
- DGCA_CORE_RC4_1.md §7.6 & §11 (C04 binding integrity and STALE transitions)
"""

from __future__ import annotations

from dgca.common.errors import StatusCode
from dgca.common.hashing import WitnessSourceKind
from dgca.common.numeric import MILLION, noisy_or_float64, q6_from_binary64
from dgca.core.anatomy import (
    E_MAX,
    SynapseKey,
    SynapseScope,
    SynapseState,
    THETA_E,
    THETA_S,
)
from dgca.core.state import (
    BindingStatus,
    CandidatePhase,
    ContextCandidateDescriptor,
    ExecutionMode,
    StableBinding,
    TypedSupportRecord,
    WState,
)

M_P_Q6: int = 50_000
MAX_CHAIN_DEPTH: int = 8
ANCHOR_SOURCE_MAX: int = 64


def is_valid_calibration_triple(l_z_q6: int, u_z_q6: int, tau_ctx_q6: int) -> bool:
    """Validate immutable Q6 calibration triple (L_z, U_z, tau_ctx_q6) per Core §5.1 & LLA §6.2.

    Requires:
        0 <= U_z < L_z <= 1_000_000
        L_z - U_z >= 50_000
        tau_ctx_q6 == U_z + 50_000 <= L_z
    """
    for val in (l_z_q6, u_z_q6, tau_ctx_q6):
        if not isinstance(val, int) or isinstance(val, bool) or val < 0 or val > MILLION:
            return False
    if l_z_q6 - u_z_q6 < M_P_Q6:
        return False
    if tau_ctx_q6 != u_z_q6 + M_P_Q6:
        return False
    if tau_ctx_q6 > l_z_q6:
        return False
    return True


def is_legal_consolidated_synapse(
    key: SynapseKey,
    w: WState,
    *,
    mask_nonconsolidated: bool = False,
) -> bool:
    """Evaluate LEGAL_CONSOLIDATED(k, W) per Core §7.6 and LLA §6.4.

    Checks:
    - Live synapse exists in W with state == CONSOLIDATED
    - S >= theta_S (0.60), E / E_max >= theta_E (0.30), external_count >= 2
    - Both source and target are committed in W
    - Structural latent eligibility D_ij == 1 in W.latent_table
    """
    syn = w.synapses.get(key)
    if syn is None:
        return False
    if syn.state != SynapseState.CONSOLIDATED:
        return False
    if syn.S < THETA_S or (syn.E / E_MAX) < THETA_E or syn.external_count < 2:
        return False
    src, tgt, _ = key
    if src not in w.committed_cells or tgt not in w.committed_cells:
        return False
    if not w.latent_table.is_eligible(src, tgt):
        return False
    return True


def validate_parent_hierarchy(
    depth: int,
    p_sources: tuple[int, int],
    p_source_kinds: tuple[WitnessSourceKind, WitnessSourceKind],
    parent_refs: dict[int, object],
    w: WState,
    visited_z: set[int] | None = None,
) -> tuple[bool, StatusCode]:
    """Validate depth <= 8, no cycles, and live parent StableBindings for depth > 1 (Core §6.1, LLA §6.6)."""
    if depth < 1 or depth > MAX_CHAIN_DEPTH:
        return False, StatusCode.CONTEXT_CHAIN_DEPTH_EXCEEDED

    for idx, p_id in enumerate(p_sources):
        kind = p_source_kinds[idx]
        if kind == WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT:
            ref = parent_refs.get(p_id)
            if ref is None:
                return False, StatusCode.DERIVED_PROVENANCE_UNVERIFIED
            parent_bind = w.stable_bindings.get(p_id)
            if parent_bind is None:
                return False, StatusCode.PARENT_NOT_COMPLETE
            if (
                parent_bind.status != BindingStatus.ACTIVE
                or parent_bind.owner_id != (ref.parent_anchor_id, ref.parent_owner_seq)
                or parent_bind.binding_generation != ref.parent_binding_generation
            ):
                return False, StatusCode.PARENT_BINDING_STALE
            seen = set(visited_z) if visited_z is not None else set()
            if p_id in seen:
                return False, StatusCode.CONTEXT_CHAIN_CYCLE
            seen.add(p_id)
            if parent_bind.depth >= depth:
                return False, StatusCode.DERIVED_PROVENANCE_UNVERIFIED
            ok, code = validate_parent_hierarchy(
                parent_bind.depth,
                parent_bind.p_sources,
                parent_bind.p_source_kinds,
                parent_bind.parent_refs,
                w,
                seen,
            )
            if not ok:
                return False, code

    return True, StatusCode.OK


def validate_and_refresh_stable_binding(
    binding: StableBinding,
    w: WState,
    *,
    mutate: bool = False,
) -> tuple[bool, StatusCode]:
    """Verify all mandatory physical keys and thresholds of a StableBinding (Core §5.1, §7.6, §11).

    If mutate=True and any mandatory key is non-live/illegal, marks binding.status = STALE (R2-A01 Patch 2).
    """
    if binding.status != BindingStatus.ACTIVE:
        return False, StatusCode.STALE_CONTEXT_BINDING

    def _fail(code: StatusCode) -> tuple[bool, StatusCode]:
        if mutate:
            binding.status = BindingStatus.STALE
        return False, code

    if not is_valid_calibration_triple(binding.l_z_q6, binding.u_z_q6, binding.tau_ctx_q6):
        return _fail(StatusCode.INVALID_CONTEXT_THRESHOLD)
    if binding.z_cell_id not in w.committed_cells:
        return _fail(StatusCode.STALE_CONTEXT_BINDING)
    if len(binding.anchor_source_set) > ANCHOR_SOURCE_MAX:
        return _fail(StatusCode.ANCHOR_CONTEXT_TOO_WIDE)

    # Both P keys must be legal consolidated ASSOCIATIVE links
    if len(binding.p_keys) != 2:
        return _fail(StatusCode.STALE_CONTEXT_BINDING)
    for pk in binding.p_keys:
        if pk[1] != binding.z_cell_id or pk[2] != SynapseScope.ASSOCIATIVE:
            return _fail(StatusCode.STALE_CONTEXT_BINDING)
        if not is_legal_consolidated_synapse(pk, w):
            return _fail(StatusCode.STALE_CONTEXT_BINDING)

    # At least 1 retained C key must be a legal consolidated LOCAL link
    valid_c = [
        ck
        for ck in binding.c_keys
        if ck[1] == binding.z_cell_id
        and ck[2] == SynapseScope.LOCAL
        and is_legal_consolidated_synapse(ck, w)
    ]
    if not valid_c:
        return _fail(StatusCode.STALE_CONTEXT_BINDING)

    # At least 1 retained Y key must be a legal consolidated ASSOCIATIVE link
    valid_y = [
        yk
        for yk in binding.y_keys
        if yk[0] == binding.z_cell_id
        and yk[2] != SynapseScope.LOCAL
        and is_legal_consolidated_synapse(yk, w)
    ]
    if not valid_y:
        return _fail(StatusCode.STALE_CONTEXT_BINDING)

    # Validate parent hierarchy if depth > 1
    if binding.depth > 1:
        ok, code = validate_parent_hierarchy(
            binding.depth,
            binding.p_sources,
            binding.p_source_kinds,
            binding.parent_refs,
            w,
            {binding.z_cell_id},
        )
        if not ok:
            return _fail(code)

    return True, StatusCode.OK


def validate_candidate_descriptor(cand: ContextCandidateDescriptor, w: WState) -> tuple[bool, StatusCode]:
    """Verify physical legality of an incomplete ContextCandidateDescriptor (Core §5.1, §7.4)."""
    if cand.status != BindingStatus.ACTIVE or cand.phase == CandidatePhase.FAILED_OR_EXPIRED:
        return False, StatusCode.STALE_CONTEXT_BINDING
    if not is_valid_calibration_triple(cand.l_z_q6, cand.u_z_q6, cand.tau_ctx_q6):
        return False, StatusCode.INVALID_CONTEXT_THRESHOLD
    if cand.z_cell_id not in w.committed_cells:
        return False, StatusCode.MISSING_CONTEXT_SOURCE
    if len(cand.anchor_source_set) > ANCHOR_SOURCE_MAX:
        return False, StatusCode.ANCHOR_CONTEXT_TOO_WIDE
    if len(cand.p_sources) != 2 or len(cand.c_sources) != 2 or len(cand.y_targets) != 2:
        return False, StatusCode.MISSING_CONTEXT_SOURCE

    for pid in cand.p_sources:
        if pid not in w.committed_cells or not w.latent_table.is_eligible(pid, cand.z_cell_id):
            return False, StatusCode.MISSING_CONTEXT_SOURCE
    for cid in cand.c_sources:
        if cid not in w.committed_cells or not w.latent_table.is_eligible(cid, cand.z_cell_id):
            return False, StatusCode.MISSING_CONTEXT_SOURCE
    for yid in cand.y_targets:
        if yid not in w.committed_cells or not w.latent_table.is_eligible(cand.z_cell_id, yid):
            return False, StatusCode.MISSING_CONTEXT_SOURCE

    if cand.depth > 1:
        ok, code = validate_parent_hierarchy(
            cand.depth,
            cand.p_sources,
            cand.p_source_kinds,
            cand.parent_refs,
            w,
            {cand.z_cell_id},
        )
        if not ok:
            return False, code

    return True, StatusCode.OK


def _extract_predecessor_support(
    p_id: int,
    expected_kind: WitnessSourceKind,
    prev_supports: dict[int, TypedSupportRecord],
    mode: ExecutionMode,
) -> float:
    """Extract typed physical predecessor support o_p(t-1) per Core §5.1 & §6.1."""
    rec = prev_supports.get(p_id)
    if rec is None:
        return 0.0
    if not rec.parent_proof_verified:
        return 0.0

    if expected_kind == WitnessSourceKind.DIRECT:
        if rec.origin_kind not in ("EXTERNAL_DIRECT", "READ_ONLY_OBSERVED", "INTERNAL_SELECTED"):
            return 0.0
    elif expected_kind == WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT:
        if rec.origin_kind not in ("DERIVED_EXTERNAL_CONTEXT", "DERIVED_RUNTIME_CONTEXT"):
            return 0.0
    else:
        return 0.0

    if mode == ExecutionMode.LEARN and rec.origin_kind in ("EXTERNAL_DIRECT", "DERIVED_EXTERNAL_CONTEXT"):
        return rec.o_train
    return rec.o_runtime


def _extract_current_c_support(
    c_id: int,
    curr_supports: dict[int, TypedSupportRecord],
    mode: ExecutionMode,
) -> float:
    """Extract typed physical current C support o_c(t) (direct SIC only) per Core §5.1 & §6.1."""
    rec = curr_supports.get(c_id)
    if rec is None:
        return 0.0
    if rec.origin_kind not in ("EXTERNAL_DIRECT", "READ_ONLY_OBSERVED", "INTERNAL_SELECTED"):
        return 0.0
    if mode == ExecutionMode.LEARN and rec.origin_kind == "EXTERNAL_DIRECT":
        return rec.o_train
    return rec.o_runtime


def evaluate_context_gate_for_cell(
    z_cell_id: int,
    w: WState,
    *,
    boundary: bool,
    prev_supports: dict[int, TypedSupportRecord],
    curr_supports: dict[int, TypedSupportRecord],
    mode: ExecutionMode,
    committed_before_event: set[int],
    mask_nonconsolidated_candidate_links: bool = False,
) -> tuple[int, float, list[StatusCode]]:
    """Compute permanent gate G_z^ctx(t) in {0, 1} and optional candidate probe G_z^probe(t) (Core §5.1, §7.5).

    Returns:
        (g_ctx: 0 | 1, g_probe: float, diagnostics: list[StatusCode])
    """
    diagnostics: list[StatusCode] = []

    if z_cell_id not in committed_before_event:
        return 0, 0.0, diagnostics

    # Case 1: Incomplete contextual candidate with ContextCandidateDescriptor
    # (Checked before stable_bindings so PRE scratch preflight evaluates cand descriptor
    # while hypothetical StableBinding in stable_bindings is used by compute_temporal_source_mask_mu)
    cand = w.context_candidates.get(z_cell_id)
    if cand is not None:
        ok, code = validate_candidate_descriptor(cand, w)
        if not ok:
            diagnostics.append(code)
            return 0, 0.0, diagnostics
        if boundary:
            return 0, 0.0, diagnostics

        # Under CONSOLIDATED_W scratch tests (mask_nonconsolidated_candidate_links=True),
        # require both P keys and >=1 C key to already be consolidated
        if mask_nonconsolidated_candidate_links:
            p0, p1 = cand.p_sources
            if not (
                is_legal_consolidated_synapse((p0, z_cell_id, SynapseScope.ASSOCIATIVE), w)
                and is_legal_consolidated_synapse((p1, z_cell_id, SynapseScope.ASSOCIATIVE), w)
            ):
                return 0, 0.0, diagnostics
            valid_c_sources = [
                cid
                for cid in cand.c_sources
                if is_legal_consolidated_synapse((cid, z_cell_id, SynapseScope.LOCAL), w)
            ]
            if not valid_c_sources:
                return 0, 0.0, diagnostics
        else:
            valid_c_sources = list(cand.c_sources)

        p0, p1 = cand.p_sources
        o_p0 = _extract_predecessor_support(p0, cand.p_source_kinds[0], prev_supports, mode)
        o_p1 = _extract_predecessor_support(p1, cand.p_source_kinds[1], prev_supports, mode)
        t_z = min(o_p0, o_p1)
        if q6_from_binary64(t_z) < cand.tau_ctx_q6:
            return 0, 0.0, diagnostics

        c_supports = [_extract_current_c_support(cid, curr_supports, mode) for cid in valid_c_sources]
        if not any(s > 0.0 for s in c_supports):
            return 0, 0.0, diagnostics

        # Compute G_z^probe = T_z^probe * C_z^probe (Core §7.5)
        c_probe = noisy_or_float64(c_supports)
        g_probe = t_z * c_probe
        return 1, g_probe, diagnostics

    # Case 2: Completed contextual owner with StableBinding
    binding = w.stable_bindings.get(z_cell_id)
    if binding is not None:
        ok, code = validate_and_refresh_stable_binding(binding, w)
        if not ok:
            diagnostics.append(code)
            return 0, 0.0, diagnostics
        if boundary:
            return 0, 0.0, diagnostics

        p0, p1 = binding.p_sources
        o_p0 = _extract_predecessor_support(p0, binding.p_source_kinds[0], prev_supports, mode)
        o_p1 = _extract_predecessor_support(p1, binding.p_source_kinds[1], prev_supports, mode)
        t_z = min(o_p0, o_p1)
        if q6_from_binary64(t_z) < binding.tau_ctx_q6:
            return 0, 0.0, diagnostics

        # Retained consolidated C sources
        valid_c_sources = [
            ck[0]
            for ck in binding.c_keys
            if is_legal_consolidated_synapse(ck, w)
        ]
        if not any(_extract_current_c_support(cid, curr_supports, mode) > 0.0 for cid in valid_c_sources):
            return 0, 0.0, diagnostics

        # Completed owners never receive a candidate probe
        return 1, 0.0, diagnostics

    return 0, 0.0, diagnostics


def compute_temporal_source_mask_mu(
    w: WState,
    *,
    g_ctx_by_z: dict[int, int],
    a_plus_by_id: dict[int, float],
    f_step: frozenset[int],
    curr_supports: dict[int, TypedSupportRecord],
    theta_emit_by_cell: dict[int, float],
) -> tuple[dict[int, int], list[StatusCode]]:
    """Compute frozen temporal source mask mu_i(t) at the end of event t (Core §5.2).

    S_t = {z : StableBinding ACTIVE, owner COMPLETE, G_z^ctx(t)=1, A_z^+(t)>=theta_emit,
               z in F_step(t), at least one legal consolidated z->Y link}
    """
    diagnostics: list[StatusCode] = []

    # Direct SIC receivers emitting in F_step(t) with EXTERNAL_DIRECT, READ_ONLY_OBSERVED, or INTERNAL_SELECTED
    direct_emitting_receivers: set[int] = {
        cid
        for cid, rec in curr_supports.items()
        if cid in f_step
        and rec.origin_kind in ("EXTERNAL_DIRECT", "READ_ONLY_OBSERVED", "INTERNAL_SELECTED")
        and (rec.o_train > 0.0 or rec.o_runtime > 0.0)
    }

    # Find all qualified COMPLETE owners z in S_t
    qualified_by_anchor: dict[int, list[StableBinding]] = {}
    for z_id, binding in sorted(w.stable_bindings.items()):
        if binding.status != BindingStatus.ACTIVE:
            continue
        if g_ctx_by_z.get(z_id, 0) != 1:
            continue
        if z_id not in f_step:
            continue
        if a_plus_by_id.get(z_id, 0.0) < theta_emit_by_cell.get(z_id, 0.23):
            continue
        ok, _ = validate_and_refresh_stable_binding(binding, w)
        if not ok:
            continue
        qualified_by_anchor.setdefault(binding.anchor_id, []).append(binding)

    # Map each candidate source cell i -> list of qualified z owners claiming i in M_z(t)
    owners_claiming_source: dict[int, list[int]] = {}
    for anchor_id, bindings in sorted(qualified_by_anchor.items()):
        if len(bindings) > 1:
            # Two or more independent completed contextual owners qualify for the same physical anchor
            diagnostics.append(StatusCode.AMBIGUOUS_CONTEXT_OWNER)
            continue
        winner_bind = bindings[0]
        m_z = winner_bind.anchor_source_set & direct_emitting_receivers
        for src_id in m_z:
            if src_id != winner_bind.z_cell_id:
                owners_claiming_source.setdefault(src_id, []).append(winner_bind.z_cell_id)

    mu_source: dict[int, int] = {}
    for src_id in sorted(f_step):
        claimants = owners_claiming_source.get(src_id, [])
        if len(claimants) == 1:
            # Verify src_id has ordinary ASSOCIATIVE source role
            has_assoc = any(
                k[2] == SynapseScope.ASSOCIATIVE
                for k in w.outgoing_by_source.get(src_id, ())
            )
            if has_assoc:
                mu_source[src_id] = 1
            else:
                mu_source[src_id] = 0
        elif len(claimants) > 1:
            # Source appearing in more than one anchor is ambiguous and receives no suppression
            if StatusCode.AMBIGUOUS_CONTEXT_OWNER not in diagnostics:
                diagnostics.append(StatusCode.AMBIGUOUS_CONTEXT_OWNER)
            mu_source[src_id] = 0
        else:
            mu_source[src_id] = 0

    return mu_source, diagnostics


def compute_directed_mu_ij(
    source_id: int,
    target_id: int,
    mu_prev_source_mask: dict[int, int],
    w: WState,
) -> int:
    """Compute RC4.1 target-scoped temporal mask mu_ij(t-1) = mu_i(t-1) * 1[not ContextTarget(j, t)] (Core §5.2).

    Temporarily masks generic outgoing ASSOCIATIVE contribution to ordinary/non-contextual targets,
    while preserving mu_ij = 0 for every legitimate gated contextual target (including incomplete
    candidates and COMPLETE depth > 1 descendants).
    """
    mu_i = mu_prev_source_mask.get(source_id, 0)
    if mu_i == 0:
        return 0
    if w.is_context_target(target_id):
        return 0
    return 1
