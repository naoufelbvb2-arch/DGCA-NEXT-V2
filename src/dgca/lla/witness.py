"""Observation Witnesses, Distinguishability, Context Witnesses, and V_ext Validation.

Normative references:
- DGCA_LLA_RC4_1.md §2.1 (Witness record and direct-support distinction, DISTINGUISHABLE)
- DGCA_LLA_RC4_1.md §2.3 (Context witness, runtime versus learning)
- DGCA_LLA_RC4_1.md §2.4 (Exact positive external link validation V_ext)
- DGCA_LLA_RC4_1.md §6.6 (EligibleExternalP and derived-external provenance)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from dgca.common.errors import StatusCode
from dgca.common.hashing import SIC_SALTS, WitnessSourceKind, sha256_bytes
from dgca.common.numeric import q6_from_binary64
from dgca.core.anatomy import SynapseKey, SynapseScope
from dgca.core.context_gate import validate_and_refresh_stable_binding, validate_candidate_descriptor
from dgca.core.dynamics import EventExecutionResult
from dgca.core.sic_v1 import (
    CellAddress,
    SICProjectionResult,
    compute_weighted_footprint_distance,
)
from dgca.core.state import (
    BindingStatus,
    ContributionLane,
    ExecutionMode,
    WState,
)
from dgca.encoder.envelope import EventOrigin

SIC_CONFIG_DIGEST: bytes = sha256_bytes(b"DGCA-SIC-V1-CONFIG:" + b"".join(SIC_SALTS))


class ObservationScope(StrEnum):
    """Observation completeness scope (LLA §2.1)."""

    COMPLETE_NEXT_EVENT = "COMPLETE_NEXT_EVENT"
    PARTIAL = "PARTIAL"
    UNSPECIFIED = "UNSPECIFIED"


@dataclass(frozen=True, slots=True)
class ObservationWitness:
    """Immutable local observation witness stored before neural propagation (LLA §2.1)."""

    witness_id: tuple[int | None, int, bytes]
    exposure_id: int | None
    event_order: int
    direct_sources: tuple[tuple[int, int], ...]
    direct_float_sources: dict[int, float]
    feature_digest: bytes
    sic_config_digest: bytes
    origin: EventOrigin
    scope: ObservationScope
    status: StatusCode
    aliased_cells: tuple[int, ...]

    @classmethod
    def from_projection(
        cls,
        projection: SICProjectionResult,
        *,
        exposure_id: int | None,
        event_order: int,
        origin: EventOrigin = EventOrigin.EXTERNAL_DIRECT,
        scope: ObservationScope = ObservationScope.COMPLETE_NEXT_EVENT,
    ) -> ObservationWitness:
        """Construct an immutable ObservationWitness from a SIC-V1 projection result."""
        return cls(
            witness_id=(exposure_id, event_order, projection.feature_bundle_digest),
            exposure_id=exposure_id,
            event_order=event_order,
            direct_sources=projection.sorted_direct_items,
            direct_float_sources=dict(projection.x_float_by_global_id),
            feature_digest=projection.feature_bundle_digest,
            sic_config_digest=SIC_CONFIG_DIGEST,
            origin=origin,
            scope=scope,
            status=StatusCode.OK,
            aliased_cells=projection.aliased_global_cell_ids,
        )


def evaluate_distinguishable(
    y1: ObservationWitness | None,
    y2: ObservationWitness | None,
) -> tuple[StatusCode, float]:
    """Evaluate DISTINGUISHABLE(Y1, Y2) per LLA §2.1.

    Rules:
    - If no comparator (y1 is None or y2 is None) -> NOT_EVALUATED_NO_COMPARATOR
    - If inadequate coverage (not COMPLETE_NEXT_EVENT or empty footprint) -> UNRESOLVED_COVERAGE
    - If same neural direct footprints and different canonical observed features -> UNRESOLVED_COLLISION
    - If same neural footprints and same observed features -> NO_CONTRAST
    - Otherwise compute weighted d_Y and return (StatusCode.OK, d_Y)
    """
    if y1 is None or y2 is None:
        return StatusCode.NOT_EVALUATED_NO_COMPARATOR, 0.0

    if (
        y1.status != StatusCode.OK
        or y2.status != StatusCode.OK
        or y1.origin != EventOrigin.EXTERNAL_DIRECT
        or y2.origin != EventOrigin.EXTERNAL_DIRECT
        or y1.scope != ObservationScope.COMPLETE_NEXT_EVENT
        or y2.scope != ObservationScope.COMPLETE_NEXT_EVENT
        or not y1.direct_sources
        or not y2.direct_sources
    ):
        return StatusCode.UNRESOLVED_COVERAGE, 0.0

    if y1.direct_sources == y2.direct_sources:
        if y1.feature_digest != y2.feature_digest:
            return StatusCode.UNRESOLVED_COLLISION, 0.0
        return StatusCode.NO_CONTRAST, 0.0

    d_y = compute_weighted_footprint_distance(
        dict(y1.direct_sources), dict(y2.direct_sources)
    )
    return StatusCode.OK, d_y


def eligible_external_p(
    p_cell_id: int,
    prev_event: EventExecutionResult | None,
    w: WState,
) -> tuple[WitnessSourceKind | None, float]:
    """Evaluate EligibleExternalP(p, root, t_prev) per LLA §6.6.

    - If OBS_ELIGIBLE(p, t_prev): return (DIRECT, X_ext)
    - If p is COMPLETE contextual source and live StableBinding V2/V3:
      require parent context gate true at t_prev, no probe contribution,
      p emitted in frozen F_step(t_prev) above theta_emit, and recursive parents
      completed valid ordered events inside this very OPEN external root (max depth 8).
      Return (DERIVED_EXTERNAL_CONTEXT, Q6(A_p^+)/1e6).
    - Else: return (None, 0.0)
    """
    if prev_event is None:
        return None, 0.0
    if (
        prev_event.mode != ExecutionMode.LEARN
        or prev_event.origin != EventOrigin.EXTERNAL_DIRECT
    ):
        return None, 0.0

    # 1. Direct external sensory observation (contextual cells can never be DIRECT_OBSERVED per Core §6.1)
    if p_cell_id in prev_event.obs_eligible_cells and not w.is_contextual_cell(p_cell_id):
        rec = prev_event.typed_supports.get(p_cell_id)
        if (
            rec is not None
            and rec.origin_kind == EventOrigin.EXTERNAL_DIRECT.value
            and rec.o_train > 0.0
            and rec.event_order == prev_event.event_order
        ):
            return WitnessSourceKind.DIRECT, rec.o_train

    # 2. COMPLETE contextual source emitting with DERIVED_EXTERNAL_CONTEXT provenance (no probe, valid depth <= 8)
    if p_cell_id in w.context_candidates:
        return None, 0.0
    binding = w.stable_bindings.get(p_cell_id)
    if binding is not None and binding.status == BindingStatus.ACTIVE:
        ok, _ = validate_and_refresh_stable_binding(binding, w)
        if not ok:
            return None, 0.0
        if prev_event.g_ctx_by_z.get(p_cell_id, 0) != 1:
            return None, 0.0
        if p_cell_id not in prev_event.f_step:
            return None, 0.0
        if prev_event.event_order < binding.depth:
            return None, 0.0
        if any(
            c.target_cell_id == p_cell_id and c.lane == ContributionLane.BOOTSTRAPPED
            for c in prev_event.contributions
        ):
            return None, 0.0
        rec = prev_event.typed_supports.get(p_cell_id)
        if (
            rec is not None
            and rec.origin_kind == ContributionLane.DERIVED_EXTERNAL_CONTEXT.value
            and rec.o_train > 0.0
            and rec.parent_proof_verified
            and rec.event_order == prev_event.event_order
            and rec.depth == binding.depth
            and rec.depth <= 8
            and rec.owner_id == binding.owner_id
            and rec.binding_generation == binding.binding_generation
        ):
            return WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT, rec.o_train

    return None, 0.0


def is_valid_context_witness(
    z_cell_id: int,
    curr_event: EventExecutionResult,
    prev_event: EventExecutionResult | None,
    w: WState,
) -> bool:
    """Evaluate ContextWitness(z, t) for a contextual cell z in LEARN (LLA §2.3).

    Valid only when:
    - mode == LEARN, origin == EXTERNAL_DIRECT, not boundary
    - prev_event is from the same OPEN exposure with event_order == curr_event.event_order - 1
    - z was committed before curr_event
    - Both selected P sources satisfy EligibleExternalP at prev_event with Q6(min(P)) >= tau_ctx_q6(z)
    - >= 1 selected C source has OBS_ELIGIBLE direct current support at curr_event
    - z participates in L_frontier at curr_event (A_z^+(t) >= theta_active) and G_z^ctx(t) == 1
    """
    if (
        curr_event.mode != ExecutionMode.LEARN
        or curr_event.origin != EventOrigin.EXTERNAL_DIRECT
        or curr_event.boundary
        or prev_event is None
    ):
        return False
    if (
        prev_event.exposure_id != curr_event.exposure_id
        or prev_event.event_order != curr_event.event_order - 1
        or prev_event.origin != EventOrigin.EXTERNAL_DIRECT
    ):
        return False
    if z_cell_id not in curr_event.committed_before_event:
        return False
    if curr_event.g_ctx_by_z.get(z_cell_id, 0) != 1:
        return False
    if z_cell_id not in curr_event.l_frontier:
        return False

    cand = w.context_candidates.get(z_cell_id)
    if cand is not None:
        ok, _ = validate_candidate_descriptor(cand, w)
        if not ok:
            return False
        p0, p1 = cand.p_sources
        kind0, sup0 = eligible_external_p(p0, prev_event, w)
        kind1, sup1 = eligible_external_p(p1, prev_event, w)
        if kind0 != cand.p_source_kinds[0] or kind1 != cand.p_source_kinds[1]:
            return False
        if q6_from_binary64(min(sup0, sup1)) < cand.tau_ctx_q6:
            return False
        if not any(cid in curr_event.obs_eligible_cells for cid in cand.c_sources):
            return False
        return True

    binding = w.stable_bindings.get(z_cell_id)
    if binding is not None:
        ok, _ = validate_and_refresh_stable_binding(binding, w)
        if not ok:
            return False
        p0, p1 = binding.p_sources
        kind0, sup0 = eligible_external_p(p0, prev_event, w)
        kind1, sup1 = eligible_external_p(p1, prev_event, w)
        if kind0 != binding.p_source_kinds[0] or kind1 != binding.p_source_kinds[1]:
            return False
        if q6_from_binary64(min(sup0, sup1)) < binding.tau_ctx_q6:
            return False
        if not any(cid in curr_event.obs_eligible_cells for cid in binding.c_sources):
            return False
        return True

    return False


def is_verified_cell_at_event(
    cell_id: int,
    curr_event: EventExecutionResult,
    prev_event: EventExecutionResult | None,
    w: WState,
) -> bool:
    """Evaluate Verified(j, t) per LLA §2.4.

    Verified(j, t) holds iff OBS_ELIGIBLE(j, t) OR a valid ContextWitness(j, t).
    Never generalized from SPATIALLY_COMPLETED, PREDICTED, RESIDUAL, or ATTRACTOR.
    """
    if cell_id in curr_event.obs_eligible_cells:
        return True
    if w.is_contextual_cell(cell_id):
        return is_valid_context_witness(cell_id, curr_event, prev_event, w)
    return False


def is_verified_associative_source_at_prev(
    source_id: int,
    prev_event: EventExecutionResult | None,
    prev_prev_event: EventExecutionResult | None,
    w: WState,
) -> bool:
    """Evaluate Verified(i, t-1) for an ASSOCIATIVE source i in F_step(t-1) (LLA §2.4, §6.6)."""
    if prev_event is None or source_id not in prev_event.f_step:
        return False
    if source_id in prev_event.obs_eligible_cells:
        return True
    # Check if source_id is a COMPLETE derived external context source at t-1
    kind, sup = eligible_external_p(source_id, prev_event, w)
    if kind == WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT and sup > 0.0:
        return True
    # Or an incomplete candidate with valid ContextWitness(i, t-1)
    if source_id in w.context_candidates:
        return is_valid_context_witness(source_id, prev_event, prev_prev_event, w)
    return False


def validate_v_ext(
    key: SynapseKey,
    curr_event: EventExecutionResult,
    prev_event: EventExecutionResult | None,
    prev_prev_event: EventExecutionResult | None,
    w: WState,
) -> bool:
    """Evaluate exact positive external link validation V_ext(k, t) in {0, 1} (LLA §2.4).

    Necessary and sufficient conditions:
    1. mode == LEARN, open external exposure (origin == EXTERNAL_DIRECT), source != target.
    2. Both endpoints committed before their respective source and target learning events.
    3. Structural latent eligibility D_event == 1 at event time.
    4. Scope-specific frontier and witness conditions:
       - LOCAL (delta=0): region(i) == region(j), i in E_t^(1), Verified(i, t) && Verified(j, t) && j in L_t
       - CROSS_TERRITORY (delta=0): region(i) != region(j), i in E_t^(1), i in L_t^x, j in L_t^x,
         Verified(i, t) && Verified(j, t) && j in L_t
       - ASSOCIATIVE (delta=1): not boundary, prev_event in same OPEN root, i in F_step(t-1),
         Verified_prev_source(i, t-1) && Verified(j, t) && j in L_t
    """
    src_id, tgt_id, scope = key
    if src_id == tgt_id:
        return False
    if (
        curr_event.mode != ExecutionMode.LEARN
        or curr_event.origin != EventOrigin.EXTERNAL_DIRECT
        or curr_event.exposure_id is None
    ):
        return False
    if tgt_id not in curr_event.committed_before_event:
        return False
    if tgt_id not in curr_event.l_frontier:
        return False
    if not w.latent_table.is_eligible(src_id, tgt_id):
        return False
    if not is_verified_cell_at_event(tgt_id, curr_event, prev_event, w):
        return False

    reg_src = CellAddress.from_global_id(src_id).region
    reg_tgt = CellAddress.from_global_id(tgt_id).region

    if scope == SynapseScope.LOCAL:
        if reg_src != reg_tgt:
            return False
        if src_id not in curr_event.committed_before_event:
            return False
        if src_id not in curr_event.e1_frontier:
            return False
        return is_verified_cell_at_event(src_id, curr_event, prev_event, w)

    if scope == SynapseScope.CROSS_TERRITORY:
        if reg_src == reg_tgt:
            return False
        if src_id not in curr_event.committed_before_event:
            return False
        if src_id not in curr_event.e1_frontier:
            return False
        if src_id not in curr_event.lx_frontier or tgt_id not in curr_event.lx_frontier:
            return False
        return is_verified_cell_at_event(src_id, curr_event, prev_event, w)

    if scope == SynapseScope.ASSOCIATIVE:
        if curr_event.boundary or prev_event is None:
            return False
        if (
            prev_event.exposure_id != curr_event.exposure_id
            or prev_event.event_order != curr_event.event_order - 1
            or prev_event.origin != EventOrigin.EXTERNAL_DIRECT
        ):
            return False
        if src_id not in prev_event.committed_before_event:
            return False
        if src_id not in prev_event.f_step:
            return False
        return is_verified_associative_source_at_prev(src_id, prev_event, prev_prev_event, w)

    return False
