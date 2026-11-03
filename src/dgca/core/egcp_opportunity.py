"""DGCA NEXT V2 — EGCP E2a Prediction Opportunity Measurement Layer.

FROZEN SPECIFICATION AUTHORITY: RC2-C01 §3.1, §3.2, §3.2A, §3.3.
SCOPE: Observation and measurement only.
INVARIANTS:
- No new growth synapses created in W.
- No pending quarantine learning or V4 migration.
- No alteration to LLA evidence, Q, S, E, activations, Readout, or StableBindings.
- Exact OFF-mode compatibility.
- Pre-observation snapshots are strictly pre-outcome (zero future event leakage).
- Bounded candidate enumeration and explicit refusal reasons.
"""

from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass
from typing import Any, Sequence

from dgca.core.anatomy import SynapseScope
from dgca.core.dynamics import EventExecutionResult
from dgca.core.state import (
    BindingStatus,
    ContributionLane,
    EGCPMode,
    MachineState,
    WState,
)
from dgca.encoder.envelope import EventOrigin

# Refusal reason codes (RC2 §3.3, §4.4)
REFUSAL_NONE = "NONE_ADMISSIBLE"
REFUSAL_NO_LEGAL_LOCAL_PATH = "NO_LEGAL_LOCAL_PATH"
REFUSAL_CAPACITY_BLOCKED = "CAPACITY_BLOCKED"
REFUSAL_EXISTING_LIVE_KEY = "EXISTING_LIVE_KEY"
REFUSAL_UNRESOLVED_PROVENANCE = "UNRESOLVED_PROVENANCE"
REFUSAL_ILLEGAL_TEMPORAL_BOUNDARY = "ILLEGAL_TEMPORAL_BOUNDARY"
REFUSAL_INCOMPLETE_OBSERVATION = "INCOMPLETE_OBSERVATION"
REFUSAL_STALE_OWNER = "STALE_OWNER"
REFUSAL_EGCP_FRONTIER_LIMIT = "EGCP_FRONTIER_LIMIT"

MAX_PENDING_KEYS_PER_OWNER = 8
MAX_OUTGOING_SYNAPSE_BUDGET = 64


@dataclass(frozen=True, slots=True)
class PreObsContextSnapshot:
    """T0 Pre-observation contextual owner snapshot (RC2-C01 §3.1).

    Captured strictly BEFORE the next external event is processed.
    Contains ZERO information about future event t.
    """

    snapshot_id: str
    root_id: int | None
    event_order_prev: int
    event_order_target: int
    owner_id: int
    z_cell_id: int
    binding_generation: int
    owner_status: str  # "ACTIVE"
    owner_gate_at_prev: int  # 1
    owner_pre_activity: float  # A_z^+(t-1)
    owner_in_f_step_prev: bool  # True
    owner_theta_emit: float
    certified_external_context_provenance: bool
    selected_p_c_interface_fingerprint: str
    eligible_source_role: str  # "DERIVED_EXTERNAL_CONTEXT"
    source_contributions_for_existing_legal_z_outgoing_edges: tuple[tuple[int, int, int, float], ...]
    legacy_mu_diagnostics: tuple[Any, ...]
    config_digest: str


@dataclass(frozen=True, slots=True)
class E2OpportunityCandidate:
    """T3 Candidate contextual prediction opportunity (RC2-C01 §3.2, §3.3)."""

    owner_id: int
    z_cell_id: int
    target_cell_id: int
    scope: SynapseScope
    e_z: float
    x_j: float
    p_zj: float
    u_val: float
    u_q6: int
    is_legal: bool
    refusal_reason: str


@dataclass(frozen=True, slots=True)
class E2OpportunityMeasurementResult:
    """Complete diagnostic measurement for an event step under E2a."""

    exposure_id: int | None
    event_order: int
    mode: EGCPMode
    pre_obs_snapshots: tuple[PreObsContextSnapshot, ...]
    all_candidates: tuple[E2OpportunityCandidate, ...]
    admissible_candidates: tuple[E2OpportunityCandidate, ...]
    refused_candidates: tuple[E2OpportunityCandidate, ...]


def capture_pre_obs_context_snapshots(
    w: WState,
    prev_event: EventExecutionResult | None,
    target_event_order: int,
    exposure_id: int | None,
) -> tuple[PreObsContextSnapshot, ...]:
    """Capture immutable T0 pre-observation snapshots of eligible contextual owners.

    Executed strictly before target event executes. Uses only prev_event (t-1) records and WState.
    """
    if prev_event is None:
        return ()

    snapshots: list[PreObsContextSnapshot] = []

    for z_id in sorted(w.stable_bindings.keys()):
        binding = w.stable_bindings[z_id]
        if binding.status != BindingStatus.ACTIVE:
            continue

        # Must be in prev_event F_step and ctx_event_match_cells
        in_f_step = z_id in prev_event.f_step
        in_ctx_match = z_id in prev_event.ctx_event_match_cells
        if not (in_f_step and in_ctx_match):
            continue

        # Must have verified DERIVED_EXTERNAL_CONTEXT typed support record
        rec = prev_event.typed_supports.get(z_id)
        has_typed_provenance = (
            rec is not None
            and rec.origin_kind == ContributionLane.DERIVED_EXTERNAL_CONTEXT.value
            and rec.parent_proof_verified
            and rec.o_train > 0.0
        )
        if not has_typed_provenance:
            continue

        a_z_prev = prev_event.a_plus_by_cell.get(z_id, 0.0)
        if a_z_prev <= 0.0:
            continue

        # Compute interface fingerprint from p_keys, c_keys, y_keys
        p_c_repr = f"p={binding.p_keys}|c={binding.c_keys}|y={binding.y_keys}"
        p_c_hash = hashlib.sha256(p_c_repr.encode("utf-8")).hexdigest()[:16]

        # Existing outgoing edges from z
        outgoing_contribs: list[tuple[int, int, int, float]] = []
        for syn_key, syn in sorted(w.synapses.items()):
            if syn_key[0] == z_id:
                outgoing_contribs.append((syn_key[0], syn_key[1], int(syn_key[2]), syn.Q))

        snap_id = f"snap_r{exposure_id}_e{prev_event.event_order}_z{z_id}"
        snap = PreObsContextSnapshot(
            snapshot_id=snap_id,
            root_id=exposure_id,
            event_order_prev=prev_event.event_order,
            event_order_target=target_event_order,
            owner_id=binding.owner_seq,
            z_cell_id=z_id,
            binding_generation=binding.binding_generation,
            owner_status=binding.status.value,
            owner_gate_at_prev=1,
            owner_pre_activity=a_z_prev,
            owner_in_f_step_prev=True,
            owner_theta_emit=0.5,
            certified_external_context_provenance=True,
            selected_p_c_interface_fingerprint=p_c_hash,
            eligible_source_role=ContributionLane.DERIVED_EXTERNAL_CONTEXT.value,
            source_contributions_for_existing_legal_z_outgoing_edges=tuple(outgoing_contribs),
            legacy_mu_diagnostics=tuple(),
            config_digest=f"gen_{binding.binding_generation}",
        )
        snapshots.append(snap)

    return tuple(snapshots)


def measure_e2_prediction_opportunities(
    snapshots: tuple[PreObsContextSnapshot, ...],
    curr_event: EventExecutionResult,
    w: WState,
    *,
    egcp_mode: EGCPMode | str = EGCPMode.OFF,
    cap_per_owner: int = MAX_PENDING_KEYS_PER_OWNER,
) -> E2OpportunityMeasurementResult:
    """Evaluate E2a prediction opportunities and explicit refusal codes (RC2-C01 §3.2, §3.3).

    Measurement-only: does not modify W, synapses, activations, or LLA state.
    Under OFF: returns empty candidate lists (exact compatibility).
    """
    mode = EGCPMode(egcp_mode)
    if mode != EGCPMode.E2_GROWTH:
        return E2OpportunityMeasurementResult(
            exposure_id=curr_event.exposure_id,
            event_order=curr_event.event_order,
            mode=mode,
            pre_obs_snapshots=(),
            all_candidates=(),
            admissible_candidates=(),
            refused_candidates=(),
        )

    if not snapshots:
        return E2OpportunityMeasurementResult(
            exposure_id=curr_event.exposure_id,
            event_order=curr_event.event_order,
            mode=mode,
            pre_obs_snapshots=(),
            all_candidates=(),
            admissible_candidates=(),
            refused_candidates=(),
        )

    # Validate observation prerequisites
    is_external_direct = (curr_event.origin == EventOrigin.EXTERNAL_DIRECT)
    is_non_boundary = not curr_event.boundary

    # Bounded candidate target set: only directly observed receiver cells committed before event
    observed_receiver_cells = sorted(curr_event.obs_eligible_cells & curr_event.committed_before_event)

    all_candidates: list[E2OpportunityCandidate] = []
    admissible_candidates: list[E2OpportunityCandidate] = []
    refused_candidates: list[E2OpportunityCandidate] = []

    for snap in snapshots:
        z_id = snap.z_cell_id
        outgoing_count = sum(1 for k in w.synapses if k[0] == z_id)
        owner_candidates: list[E2OpportunityCandidate] = []

        for target_id in observed_receiver_cells:
            # 1. Temporal boundary and origin checks
            if not is_non_boundary:
                cand = _make_refused_candidate(snap, target_id, REFUSAL_ILLEGAL_TEMPORAL_BOUNDARY)
                owner_candidates.append(cand)
                continue

            if not is_external_direct:
                cand = _make_refused_candidate(snap, target_id, REFUSAL_INCOMPLETE_OBSERVATION)
                owner_candidates.append(cand)
                continue

            # 2. Latent physical eligibility
            is_latent_eligible = w.latent_table.is_eligible(z_id, target_id)

            # 3. Existing live key check
            syn_key = (z_id, target_id, SynapseScope.ASSOCIATIVE)
            is_existing_key = syn_key in w.synapses
            syn_obj = w.synapses.get(syn_key)

            # 4. Outgoing capacity check (B_i = 64)
            is_capacity_blocked = (outgoing_count >= MAX_OUTGOING_SYNAPSE_BUDGET)

            # 5. Compute opportunity components (Core RC2 §3.2)
            e_z = min(1.0, max(0.0, snap.owner_pre_activity))
            x_j = min(1.0, max(0.0, curr_event.a_plus_by_cell.get(target_id, 1.0)))

            if is_existing_key and syn_obj is not None:
                p_zj = min(1.0, max(0.0, snap.owner_pre_activity * syn_obj.Q * 1.0))
            else:
                p_zj = 0.0

            u_val = (e_z * x_j) * (1.0 - p_zj)
            u_q6 = int(round(u_val * 64.0))

            # 6. Refusal reason classification
            if is_existing_key:
                refusal = REFUSAL_EXISTING_LIVE_KEY
                is_legal = False
            elif not is_latent_eligible:
                refusal = REFUSAL_NO_LEGAL_LOCAL_PATH
                is_legal = False
            elif is_capacity_blocked:
                refusal = REFUSAL_CAPACITY_BLOCKED
                is_legal = False
            else:
                refusal = REFUSAL_NONE
                is_legal = True

            cand = E2OpportunityCandidate(
                owner_id=snap.owner_id,
                z_cell_id=z_id,
                target_cell_id=target_id,
                scope=SynapseScope.ASSOCIATIVE,
                e_z=e_z,
                x_j=x_j,
                p_zj=p_zj,
                u_val=u_val,
                u_q6=u_q6,
                is_legal=is_legal,
                refusal_reason=refusal,
            )
            owner_candidates.append(cand)

        # Deterministic ranking: descending integer U_q6, owner ID, z ID, target cell ID, scope
        owner_candidates.sort(
            key=lambda c: (-c.u_q6, c.owner_id, c.z_cell_id, c.target_cell_id, int(c.scope))
        )

        # Apply per-owner capacity cap
        admitted_for_owner = 0
        for cand in owner_candidates:
            if cand.is_legal:
                if admitted_for_owner < cap_per_owner:
                    admissible_candidates.append(cand)
                    all_candidates.append(cand)
                    admitted_for_owner += 1
                else:
                    # Bounded frontier limit exceeded
                    limited_cand = dataclasses.replace(
                        cand,
                        is_legal=False,
                        refusal_reason=REFUSAL_EGCP_FRONTIER_LIMIT,
                    )
                    refused_candidates.append(limited_cand)
                    all_candidates.append(limited_cand)
            else:
                refused_candidates.append(cand)
                all_candidates.append(cand)

    return E2OpportunityMeasurementResult(
        exposure_id=curr_event.exposure_id,
        event_order=curr_event.event_order,
        mode=mode,
        pre_obs_snapshots=snapshots,
        all_candidates=tuple(all_candidates),
        admissible_candidates=tuple(admissible_candidates),
        refused_candidates=tuple(refused_candidates),
    )


def _make_refused_candidate(
    snap: PreObsContextSnapshot,
    target_id: int,
    refusal_reason: str,
) -> E2OpportunityCandidate:
    return E2OpportunityCandidate(
        owner_id=snap.owner_id,
        z_cell_id=snap.z_cell_id,
        target_cell_id=target_id,
        scope=SynapseScope.ASSOCIATIVE,
        e_z=snap.owner_pre_activity,
        x_j=0.0,
        p_zj=0.0,
        u_val=0.0,
        u_q6=0,
        is_legal=False,
        refusal_reason=refusal_reason,
    )
