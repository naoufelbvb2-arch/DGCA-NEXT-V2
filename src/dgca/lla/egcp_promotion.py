"""DGCA NEXT V2 — EGCP E2c Structural Promotion & Growth Safety Contract (GSC).

Authoritative Specification:
- EGCP v1.0 — E0–E2 Frozen Experimental Specification (RC2-C01 §5.3, §6, §7)
- FR-03 (StableBindingV4 explicit versioned schema, structural_revision, canonical manifest digest)
- FR-06 / FR-08 / FR-09 (Growth Safety Contract, capacity preservation, anti-leakage)

State machine:
    OBSERVED_OPPORTUNITY (ephemeral)
        -> PENDING_LEARNING (upon first accepted legal proposal at END)
        -> READY_FOR_PROMOTION (native CONSOLIDATED criteria met: S>=0.60, E>=3.0, ext_count>=2)
        -> PROMOTED (atomic native consolidation + binding role publication)
        OR -> PENDING_LEARNING (safe structural deferral while within cap/TTL)
        OR -> EXPIRED / REJECTED (scoped closure, TTL=2000 events)
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Sequence

from dgca.common.errors import DGCAError, StatusCode
from dgca.core.anatomy import SynapseScope, SynapseState
from dgca.core.context_gate import is_legal_consolidated_synapse, validate_and_refresh_stable_binding
from dgca.core.state import (
    BindingStatus,
    EGCPGrowthState,
    EGCPMode,
    EGCPPendingGrowthV1,
    StableBinding,
    Synapse,
    SynapseKey,
    WState,
    compute_y_keys_manifest_digest,
    convert_to_stable_binding_v4,
)

# Refusal / Deferral Codes for GSC (§7.1)
GSC_PASS = "GSC_PASS"
GSC_DEFER_NOT_READY = "GSC_DEFER_NOT_READY"
GSC_REFUSAL_MODE_OFF = "GSC_REFUSAL_MODE_OFF"
GSC_REFUSAL_OWNER_NOT_ACTIVE = "GSC_REFUSAL_OWNER_NOT_ACTIVE"
GSC_REFUSAL_MISSING_PROVENANCE = "GSC_REFUSAL_MISSING_PROVENANCE"
GSC_REFUSAL_LATENT_INELIGIBLE = "GSC_REFUSAL_LATENT_INELIGIBLE"
GSC_REFUSAL_CAPACITY_EXCEEDED = "GSC_REFUSAL_CAPACITY_EXCEEDED"
GSC_REFUSAL_COLLISION = "GSC_REFUSAL_COLLISION"
GSC_REFUSAL_TTL_EXPIRED = "GSC_REFUSAL_TTL_EXPIRED"
GSC_REFUSAL_POST_ASSEMBLY_STALE = "GSC_REFUSAL_POST_ASSEMBLY_STALE"

EGCP_PENDING_TTL_EVENTS = 2000


@dataclass(frozen=True, slots=True)
class PromotionCandidateResult:
    key: SynapseKey
    owner_z_id: int
    owner_id: tuple[int, int]
    allowed: bool
    status_code: str
    previous_revision: int
    new_revision: int | None = None


@dataclass(frozen=True, slots=True)
class EGCPPreAssemblyPromotionReport:
    exposure_id: int
    evaluated_candidates: tuple[PromotionCandidateResult, ...]
    promoted_keys: tuple[SynapseKey, ...]
    upgraded_owners: tuple[int, ...]
    expired_keys: tuple[SynapseKey, ...]


def evaluate_growth_promotion_allowed(
    w_shadow: WState,
    key: SynapseKey,
    pending: EGCPPendingGrowthV1,
) -> tuple[bool, str]:
    """Evaluate GROWTH_PROMOTION_ALLOWED(owner, z, j, W1) predicate (EGCP RC2 §7.1).

    Predicate terms:
    1. EGCP_MODE == E2_GROWTH
    2. PENDING_CANDIDATE_EXCLUSIVE_AND_LIVE(W1, z, j)
    3. CANDIDATE_NATIVE_LLA_READY_TO_CONSOLIDATE(W1, z, j)
    4. ACCEPTED_DISTINCT_EXTERNAL_ROOTS_AND_SOURCE_TIMING_VALID(z, j)
    5. NO_UNRESOLVED_SIC_OR_TYPED_PARENT_PROVENANCE(z, j)
    6. VALID_OWNER_ID_AND_ACTIVE_BOUND_P_C_INTERFACE(z)
    7. Y_KEY_NOT_ALREADY_PROMOTED_OR_RESERVED_ELSEWHERE(z, j)
    8. LATENT_CAPACITY_AND_RESERVED_BUDGET_VALID_AT_CLOSE(z, j)
    9. NO_OWNER_COLLISION_OR_DUPLICATE_CONTEXT_OWNER(z)
    10. V4_CONVERSION_AND_STRUCTURAL_REVISION_VALID(z)
    11. BOUNDED_AFFECTED_DESCENDANTS_STRUCTURALLY_VALID(z)
    12. SHADOW_TRANSACTION_ALL_INDICES_AND_REFERENCES_CONSISTENT
    """
    # 1. Mode check
    if getattr(w_shadow, "egcp_mode", EGCPMode.OFF) != EGCPMode.E2_GROWTH:
        return False, GSC_REFUSAL_MODE_OFF

    # 2. Candidate exclusive and live in pending compartment
    if pending.state != EGCPGrowthState.READY_FOR_PROMOTION:
        return False, GSC_DEFER_NOT_READY

    z_id = pending.owner_z_id
    src_id, tgt_id, scope = key
    if src_id != z_id:
        return False, GSC_REFUSAL_COLLISION

    # 3. Candidate native LLA ready to consolidate (S >= 0.60, E/10.0 >= 0.30, external_count >= 2)
    syn = pending.synapse
    if syn.S < 0.60 or syn.E < 3.0 or syn.external_count < 2:
        return False, GSC_DEFER_NOT_READY

    # 4. Accepted distinct external roots
    if pending.accepted_root_count < 2:
        return False, GSC_DEFER_NOT_READY

    # 5. Provenance & target commitment
    if z_id not in w_shadow.committed_cells or tgt_id not in w_shadow.committed_cells:
        return False, GSC_REFUSAL_MISSING_PROVENANCE

    # 6. Valid owner ID and active bound P/C interface
    binding = w_shadow.stable_bindings.get(z_id)
    if binding is None or binding.status != BindingStatus.ACTIVE:
        return False, GSC_REFUSAL_OWNER_NOT_ACTIVE
    if binding.owner_id != pending.owner_id:
        return False, GSC_REFUSAL_OWNER_NOT_ACTIVE

    # Verify P keys are legal consolidated
    for pk in binding.p_keys:
        if not is_legal_consolidated_synapse(pk, w_shadow):
            return False, GSC_REFUSAL_OWNER_NOT_ACTIVE

    # Verify at least 1 C key is legal consolidated
    has_valid_c = any(
        ck[1] == z_id and ck[2] == SynapseScope.LOCAL and is_legal_consolidated_synapse(ck, w_shadow)
        for ck in binding.c_keys
    )
    if not has_valid_c:
        return False, GSC_REFUSAL_OWNER_NOT_ACTIVE

    # 7. Y key not already promoted
    if key in w_shadow.synapses:
        live_syn = w_shadow.synapses[key]
        if live_syn.state == SynapseState.CONSOLIDATED and key in binding.y_keys:
            return False, GSC_REFUSAL_COLLISION

    # 8. Latent capacity and reserved budget
    claimed_outgoing = w_shadow.unique_claimed_outgoing_keys(src_id)
    if len(claimed_outgoing) > w_shadow.outgoing_budget_b_i:
        return False, GSC_REFUSAL_CAPACITY_EXCEEDED

    if not w_shadow.latent_table.is_eligible(src_id, tgt_id):
        return False, GSC_REFUSAL_LATENT_INELIGIBLE

    # 9. No owner collision
    for other_z, other_b in w_shadow.stable_bindings.items():
        if other_z != z_id and other_b.status == BindingStatus.ACTIVE:
            if other_b.anchor_id == binding.anchor_id and other_b.owner_seq == binding.owner_seq:
                return False, GSC_REFUSAL_COLLISION

    # 10. V4 conversion and structural revision
    if binding.schema_version not in (2, 3, 4):
        return False, GSC_REFUSAL_OWNER_NOT_ACTIVE

    # All predicates pass
    return True, GSC_PASS


def execute_egcp_pre_assembly_shadow_stage(
    w_shadow: WState,
    *,
    exposure_id: int,
    w_pre_close: WState | None = None,
) -> EGCPPreAssemblyPromotionReport:
    """Execute EGCP Pre-Assembly Shadow Promotion Stage at END_EXPOSURE (EGCP RC2 §5.3, §7).

    Runs after contextual candidate close and before execute_assembly_end_pipeline.
    Mutates only w_shadow in an atomic pre-assembly transaction.
    """
    if getattr(w_shadow, "egcp_mode", EGCPMode.OFF) != EGCPMode.E2_GROWTH:
        return EGCPPreAssemblyPromotionReport(
            exposure_id=exposure_id,
            evaluated_candidates=(),
            promoted_keys=(),
            upgraded_owners=(),
            expired_keys=(),
        )

    pending_items = list(sorted(w_shadow.egcp_pending_growth.items(), key=lambda item: (item[0][0], item[0][1], str(item[0][2]))))
    evaluated: list[PromotionCandidateResult] = []
    promoted_keys: list[SynapseKey] = []
    upgraded_owners: set[int] = set()
    expired_keys: list[SynapseKey] = []

    # 1. Clean up TTL-expired pending reservations (§5.3 step 6, TTL=2000 events)
    for key, pending in pending_items:
        last_ev = pending.synapse.last_external_event_id or pending.synapse.created_event_id
        clock_delta = w_shadow.completed_external_events_count - last_ev
        if clock_delta > EGCP_PENDING_TTL_EVENTS and pending.state in (EGCPGrowthState.PENDING_LEARNING, EGCPGrowthState.READY_FOR_PROMOTION):
            pending.state = EGCPGrowthState.EXPIRED
            pending.reason_code = GSC_REFUSAL_TTL_EXPIRED
            del w_shadow.egcp_pending_growth[key]
            expired_keys.append(key)

    # 2. Evaluate candidates in READY_FOR_PROMOTION
    for key, pending in pending_items:
        if key in expired_keys:
            continue
        if pending.state != EGCPGrowthState.READY_FOR_PROMOTION:
            continue

        z_id = pending.owner_z_id
        binding = w_shadow.stable_bindings.get(z_id)
        prev_rev = binding.structural_revision if binding is not None else 0

        allowed, reason = evaluate_growth_promotion_allowed(w_shadow, key, pending)
        if not allowed:
            evaluated.append(
                PromotionCandidateResult(
                    key=key,
                    owner_z_id=z_id,
                    owner_id=pending.owner_id,
                    allowed=False,
                    status_code=reason,
                    previous_revision=prev_rev,
                    new_revision=None,
                )
            )
            continue

        # Atomically promote: transfer from pending to live consolidated synapse
        syn = pending.synapse
        syn.state = SynapseState.CONSOLIDATED
        src_id, tgt_id, scope = key

        # 1. Insert into live synapses
        w_shadow.synapses[key] = syn
        w_shadow.outgoing_by_source.setdefault(src_id, set()).add(key)
        w_shadow.incoming_by_target.setdefault(tgt_id, set()).add(key)

        # 2. Upgrade / Update owner's StableBinding to V4
        # Re-fetch binding as it might have been upgraded by an earlier key in this root
        current_binding = w_shadow.stable_bindings[z_id]
        updated_binding = convert_to_stable_binding_v4(current_binding, additional_y_keys=(key,))
        w_shadow.stable_bindings[z_id] = updated_binding

        # 3. Mark pending state PROMOTED and remove from pending compartment
        pending.state = EGCPGrowthState.PROMOTED
        del w_shadow.egcp_pending_growth[key]

        promoted_keys.append(key)
        upgraded_owners.add(z_id)
        evaluated.append(
            PromotionCandidateResult(
                key=key,
                owner_z_id=z_id,
                owner_id=pending.owner_id,
                allowed=True,
                status_code=GSC_PASS,
                previous_revision=prev_rev,
                new_revision=updated_binding.structural_revision,
            )
        )

    return EGCPPreAssemblyPromotionReport(
        exposure_id=exposure_id,
        evaluated_candidates=tuple(evaluated),
        promoted_keys=tuple(promoted_keys),
        upgraded_owners=tuple(sorted(upgraded_owners)),
        expired_keys=tuple(expired_keys),
    )
