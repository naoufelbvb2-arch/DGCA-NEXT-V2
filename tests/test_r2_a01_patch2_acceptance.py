"""Acceptance test suite for R2-A01 Patch 2: Read-Only Immutability, Latent Virtual Lookups & Transactional STALE.

Covers:
- Field Coverage Audit: Complete, verifiable 100% attribute coverage across WState, LatentNeighborhoodTable, HSlowState, RState, and SurfaceReadoutLedgerV1
- Deterministic canonical serializer and cryptographically verified SHA-256 state hashes
- P1-01: Complete RETRIEVE Immutability Gate (Full WState, HSlowState, RState structural and SHA-256 equality)
- P1-02: Stale Binding Read-Only Isolation (Status stays ACTIVE in caller W, gate closes, diagnostic returned)
- P1-03: Homeostasis Scratch Isolation (H_slow cloned in scratch, float equality across repeated runs, SHA-256 equality)
- P1-04: Transactional STALE Transition (Abort leaves ACTIVE, Commit settles to STALE on w_shadow via Step 5.1)
- Focused latent tests: Virtual lookups on unmaterialized cells, forward/reverse neighbor and eligibility immutability
- Focused generation tests: GENERATE mode leaves caller permanent state and ledger completely untouched
- Mode discrimination: LEARN mode updates last_referenced_event, RETRIEVE mode does not
- Non-Empty Peripheral Ledger Verification (Correction V02): Integration test on genuinely trained 56-root cold-start curriculum with canonical EOS and multi-step rollouts for Cat (GEN_STOP_EOS) and Eagle (GEN_STOP_AMBIGUOUS)
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
from typing import Any
import pytest

from dgca.common.errors import DGCAError, StatusCode
from dgca.common.hashing import Region, WitnessSourceKind
from dgca.common.numeric import q6_from_binary64
from dgca.core.anatomy import (
    Synapse,
    SynapseKey,
    SynapseScope,
    SynapseState,
)
from dgca.core.context_gate import validate_and_refresh_stable_binding
from dgca.core.dynamics import execute_two_pass_event
from dgca.core.generator import generate_episode
from dgca.core.latent_index import (
    TOTAL_CELL_COUNT,
    LatentNeighborhoodTable,
    compute_fixed_local_neighbors,
    compute_fixed_topographic_neighbors,
)
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import (
    Assembly,
    AssemblyStatus,
    BindingStatus,
    CandidatePhase,
    ContextCandidateDescriptor,
    ExecutionMode,
    HSlowState,
    MachineState,
    OwnerState,
    ParentContextRef,
    RState,
    StableBinding,
    WState,
)
from dgca.lla.owner_registry import OwnerProfile, CompactWitnessProfile
from dgca.encoder.envelope import (
    CoreEventPayloadV1,
    EventOrigin,
    Marker,
    PeripheralSurfaceEnvelopeV1,
    encode_exposure,
    encode_lexical_token_event,
)
from dgca.lla.contrast_ledger import ContrastEpisodeRecord
from dgca.lifecycle.exposure_tx import (
    ExposureStatus,
    ExposureTransactionManager,
    compute_pred_score,
    run_read_only_episode,
)
from dgca.peripheral.readout_ledger import (
    LedgerCandidateRow,
    SurfaceReadoutLedgerV1,
)


# ---------------------------------------------------------------------------
# Deterministic Canonical Serializer & State Digest Computation
# ---------------------------------------------------------------------------

def canonical_state_digest(val: Any) -> bytes:
    """Recursively serialize arbitrary state structures into a deterministic canonical byte representation.

    Specification:
    - None: b'N;'
    - bool: b'B1;' or b'B0;'
    - int: b'I:<decimal>;'
    - float: b'F:<hex_float>;' (exact bitwise IEEE 754 precision, platform-independent)
    - str: b'S:<len>:<utf8_bytes>;'
    - bytes: b'X:<len>:<raw_bytes>;'
    - enum.Enum: b'E:<class_name>:<enum_value>;'
    - tuple / list: b'T:<len>[<element_digests>];'
    - set / frozenset: b'U:<len>{<sorted_element_digests>};' (elements sorted by their own canonical digest)
    - dict: b'D:<len>{<sorted_key_val_pairs>};' (pairs sorted by key's canonical digest)
    """
    if val is None:
        return b"N;"
    elif isinstance(val, bool):
        return b"B1;" if val else b"B0;"
    elif isinstance(val, int):
        return b"I:" + str(val).encode("ascii") + b";"
    elif isinstance(val, float):
        return b"F:" + val.hex().encode("ascii") + b";"
    elif isinstance(val, str):
        b = val.encode("utf-8")
        return b"S:" + str(len(b)).encode("ascii") + b":" + b + b";"
    elif isinstance(val, bytes):
        return b"X:" + str(len(val)).encode("ascii") + b":" + val + b";"
    elif isinstance(val, enum.Enum):
        return b"E:" + val.__class__.__name__.encode("ascii") + b":" + str(val.value).encode("utf-8") + b";"
    elif isinstance(val, (tuple, list)):
        return b"T:" + str(len(val)).encode("ascii") + b"[" + b"".join(canonical_state_digest(x) for x in val) + b"];"
    elif isinstance(val, (set, frozenset)):
        serialized = [canonical_state_digest(x) for x in val]
        serialized.sort()
        return b"U:" + str(len(val)).encode("ascii") + b"{" + b"".join(serialized) + b"};"
    elif isinstance(val, dict):
        pairs = [(canonical_state_digest(k), canonical_state_digest(v)) for k, v in val.items()]
        pairs.sort(key=lambda p: p[0])
        return b"D:" + str(len(val)).encode("ascii") + b"{" + b"".join(k + v for k, v in pairs) + b"};"
    raise TypeError(f"Unsupported type in canonical_state_digest: {type(val)}")


def hash_state_snapshot(snap: dict[str, Any]) -> str:
    """Compute the SHA-256 cryptographic digest of a canonical state snapshot."""
    return hashlib.sha256(canonical_state_digest(snap)).hexdigest()


# ---------------------------------------------------------------------------
# Deep Snapshot Helpers for Invariant Verification (Complete 100% Coverage)
# ---------------------------------------------------------------------------

def _snapshot_candidate(cand: ContextCandidateDescriptor) -> tuple[Any, ...]:
    return (
        cand.z_cell_id,
        cand.anchor_id,
        cand.owner_seq,
        cand.p_sources,
        cand.c_sources,
        cand.y_targets,
        cand.l_z_q6,
        cand.u_z_q6,
        cand.tau_ctx_q6,
        frozenset(cand.anchor_source_set),
        cand.phase,
        cand.probe_matches,
        cand.consolidation_matches,
        cand.age_events,
        cand.admitted_root_id,
        cand.depth,
        cand.p_source_kinds,
        tuple(
            sorted(
                (
                    cid,
                    (
                        ref.parent_z_cell_id,
                        ref.parent_anchor_id,
                        ref.parent_owner_seq,
                        ref.parent_binding_generation,
                        ref.depth,
                    ),
                )
                for cid, ref in cand.parent_refs.items()
            )
        ),
        cand.status,
    )


def _snapshot_binding(b: StableBinding) -> tuple[Any, ...]:
    return (
        b.schema_version,
        b.z_cell_id,
        b.anchor_id,
        b.owner_seq,
        b.binding_generation,
        b.p_keys,
        b.l_z_q6,
        b.u_z_q6,
        b.tau_ctx_q6,
        b.c_keys,
        b.y_keys,
        frozenset(b.anchor_source_set),
        b.status,
        b.depth,
        b.p_source_kinds,
        tuple(
            sorted(
                (
                    cid,
                    (
                        ref.parent_z_cell_id,
                        ref.parent_anchor_id,
                        ref.parent_owner_seq,
                        ref.parent_binding_generation,
                        ref.depth,
                    ),
                )
                for cid, ref in b.parent_refs.items()
            )
        ),
    )


def _snapshot_owner_profile(prof: OwnerProfile) -> tuple[Any, ...]:
    return (
        prof.schema_version,
        prof.anchor_id,
        prof.owner_seq,
        prof.z_cell_id,
        prof.state,
        prof.p_sources,
        prof.c_sources,
        prof.y_targets,
        prof.l_z_q6,
        prof.u_z_q6,
        prof.tau_ctx_q6,
        frozenset(prof.anchor_source_set),
        tuple(
            (
                tuple(sorted(wp.top8_p_supports_u.items())),
                tuple(sorted(wp.top8_c_supports_u.items())),
                tuple(sorted(wp.top8_y_supports_u.items())),
                bytes(wp.full_p_digest),
                bytes(wp.full_c_digest),
                bytes(wp.full_y_digest),
                tuple(sorted(wp.p_source_kinds.items())),
                tuple(
                    sorted(
                        (
                            cid,
                            (
                                ref.parent_z_cell_id,
                                ref.parent_anchor_id,
                                ref.parent_owner_seq,
                                ref.parent_binding_generation,
                                ref.depth,
                            ),
                        )
                        for cid, ref in wp.p_parent_refs.items()
                    )
                ),
                wp.audited_root_id,
                bytes(wp.p_bundle_digest),
                bytes(wp.c_bundle_digest),
                bytes(wp.y_bundle_digest),
            )
            for wp in prof.witness_profiles
        ),
        prof.binding_generation,
        prof.depth,
        prof.p_source_kinds,
        tuple(
            sorted(
                (
                    cid,
                    (
                        ref.parent_z_cell_id,
                        ref.parent_anchor_id,
                        ref.parent_owner_seq,
                        ref.parent_binding_generation,
                        ref.depth,
                    ),
                )
                for cid, ref in prof.parent_refs.items()
            )
        ),
        bytes(prof.profile_digest),
    )


def _snapshot_contrast_episode(ep: ContrastEpisodeRecord) -> tuple[Any, ...]:
    return (
        ep.anchor_id,
        ep.exposure_id,
        ep.event_order_b,
        ep.completed_event_clock,
        tuple(sorted(ep.p_supports_u.items())),
        tuple(sorted(ep.c_supports_u.items())),
        tuple(sorted(ep.y_supports_u.items())),
        tuple(sorted(ep.p_source_kinds.items())),
        tuple(
            sorted(
                (
                    cid,
                    (
                        ref.parent_z_cell_id,
                        ref.parent_anchor_id,
                        ref.parent_owner_seq,
                        ref.parent_binding_generation,
                        ref.depth,
                    ),
                )
                for cid, ref in ep.p_parent_refs.items()
            )
        ),
        bytes(ep.p_digest),
        bytes(ep.c_digest),
        bytes(ep.y_digest),
        bytes(ep.p_bundle_digest),
        bytes(ep.c_bundle_digest),
        bytes(ep.y_bundle_digest),
        tuple(sorted(ep.p_direct_x_u.items())),
        tuple(sorted(ep.c_direct_x_u.items())),
        ep.has_collision,
    )


def snapshot_w(w: WState) -> dict[str, Any]:
    """Capture a comprehensive deep snapshot of WState covering 100% of persistent fields."""
    latent_snap = {
        "_slots_by_cell": {cid: tuple(slots) for cid, slots in sorted(w.latent_table._slots_by_cell.items())},
        "_pinned_slots": {cid: frozenset(slots) for cid, slots in sorted(w.latent_table._pinned_slots.items())},
        "_coactive_reverse_index": {cid: frozenset(sources) for cid, sources in sorted(w.latent_table._coactive_reverse_index.items())},
        "_wiring_logs": {
            cid: tuple(
                (e.event_clock, e.owner_cell_id, e.slot_index, e.old_target_id, e.new_target_id, e.reason)
                for e in entries
            )
            for cid, entries in sorted(w.latent_table._wiring_logs.items())
        },
    }
    missing_latent = set(vars(w.latent_table).keys()) - set(latent_snap.keys())
    assert not missing_latent, f"snapshot_w latent_table missing fields: {missing_latent}"

    snap = {
        "outgoing_budget_b_i": w.outgoing_budget_b_i,
        "cross_outgoing_budget_b_i_x": w.cross_outgoing_budget_b_i_x,
        "committed_cells": dict(w.committed_cells),
        "last_referenced_event": dict(w.last_referenced_event),
        "latent_table": latent_snap,
        "synapses": {
            k: (
                s.key,
                s.state,
                s.S,
                s.E_ext,
                s.E_int,
                s.external_count,
                tuple(sorted(s.confirmed_roots)),
            )
            for k, s in sorted(w.synapses.items())
        },
        "outgoing_by_source": {src: frozenset(keys) for src, keys in sorted(w.outgoing_by_source.items())},
        "incoming_by_target": {tgt: frozenset(keys) for tgt, keys in sorted(w.incoming_by_target.items())},
        "reserved_keys_by_candidate": {cid: frozenset(keys) for cid, keys in sorted(w.reserved_keys_by_candidate.items())},
        "assemblies": {
            aid: (
                asm.assembly_id,
                asm.region,
                tuple(sorted(asm.member_cell_ids)),
                asm.structural_generation,
                asm.birth_close_serial,
                asm.last_mutation_close_serial,
                asm.last_merge_split_close_serial,
                asm.status,
            )
            for aid, asm in sorted(w.assemblies.items())
        },
        "next_assembly_id": w.next_assembly_id,
        "assemblies_by_member": {cid: frozenset(aids) for cid, aids in sorted(w.assemblies_by_member.items())},
        "context_candidates": {cid: _snapshot_candidate(cand) for cid, cand in sorted(w.context_candidates.items())},
        "stable_bindings": {zid: _snapshot_binding(b) for zid, b in sorted(w.stable_bindings.items())},
        "owner_profiles_by_anchor": {aid: tuple(_snapshot_owner_profile(prof) for prof in profs) for aid, profs in sorted(w.owner_profiles_by_anchor.items())},
        "next_owner_seq_by_anchor": dict(w.next_owner_seq_by_anchor),
        "contrast_episodes_by_anchor": {aid: tuple(_snapshot_contrast_episode(ep) for ep in eps) for aid, eps in sorted(w.contrast_episodes_by_anchor.items())},
        "completed_roots_high_watermark": w.completed_roots_high_watermark,
        "completed_external_events_count": w.completed_external_events_count,
        "global_event_clock": w.global_event_clock,
        "close_serial": w.close_serial,
    }
    missing_w = set(vars(w).keys()) - set(snap.keys())
    assert not missing_w, f"snapshot_w missing fields: {missing_w}"
    return snap


def snapshot_h_slow(h: HSlowState) -> dict[str, Any]:
    """Capture a comprehensive snapshot of HSlowState homeostatic variables."""
    snap = {
        "r_bar": dict(h.r_bar),
        "g": dict(h.g),
        "rho_bar_by_region": dict(h.rho_bar_by_region),
        "theta_active_by_region": dict(h.theta_active_by_region),
    }
    missing_h = set(vars(h).keys()) - set(snap.keys())
    assert not missing_h, f"snapshot_h_slow missing fields: {missing_h}"
    return snap


def snapshot_r(r: RState) -> dict[str, Any]:
    """Capture a complete snapshot of caller RState covering all 19 volatile fields."""
    snap = {
        "A": dict(r.A),
        "A_prev": dict(r.A_prev),
        "A_pass1": dict(r.A_pass1),
        "A_hist": {cid: tuple(hist) for cid, hist in sorted(r.A_hist.items())},
        "E1_frontier": frozenset(r.E1_frontier),
        "L_frontier": frozenset(r.L_frontier),
        "Lx_frontier": frozenset(r.Lx_frontier),
        "F_step": frozenset(r.F_step),
        "F_step_prev": frozenset(r.F_step_prev),
        "g_ctx_by_z": dict(r.g_ctx_by_z),
        "mu_source_mask": dict(r.mu_source_mask),
        "mu_prev_source_mask": dict(r.mu_prev_source_mask),
        "context_diagnostics": tuple(r.context_diagnostics),
        "active_attractors": {
            aid: (att.assembly_id, att.strength_c, att.age, att.err)
            for aid, att in sorted(r.active_attractors.items())
        },
        "contribution_lanes": tuple(
            (c.target_cell_id, c.source_cell_id, c.event_order, c.lane, c.nonnegative_support, tuple(c.witness_roots), c.step_id)
            for c in r.contribution_lanes
        ),
        "typed_supports_current": {
            cid: (rec.cell_id, rec.event_order, rec.origin_kind, rec.o_train, rec.o_runtime, rec.q6_train, rec.q6_runtime, rec.depth, rec.owner_id, rec.binding_generation, rec.parent_proof_verified)
            for cid, rec in sorted(r.typed_supports_current.items())
        },
        "typed_supports_prev": {
            cid: (rec.cell_id, rec.event_order, rec.origin_kind, rec.o_train, rec.o_runtime, rec.q6_train, rec.q6_runtime, rec.depth, rec.owner_id, rec.binding_generation, rec.parent_proof_verified)
            for cid, rec in sorted(r.typed_supports_prev.items())
        },
        "eligibility_traces": {
            cid: tuple(
                (e.cell_id, e.a_eligible, e.a_pass1, e.in_e1_frontier, e.in_f_step, e.in_l_frontier, e.in_lx_frontier, e.event_order, e.exposure_id, e.origin_kind, e.witness_id)
                for e in entries
            )
            for cid, entries in sorted(r.eligibility_traces.items())
        },
        "step_index": r.step_index,
    }
    missing_r = set(vars(r).keys()) - set(snap.keys())
    assert not missing_r, f"snapshot_r missing fields: {missing_r}"
    return snap


def snapshot_ledger(ledger: SurfaceReadoutLedgerV1) -> dict[str, Any]:
    """Capture a complete snapshot of SurfaceReadoutLedgerV1 without holding mutable aliases."""
    rows_snap: dict[tuple[int, int], dict[tuple[str, Marker, bytes], Any]] = {}
    for (aid, gen), candidate_map in sorted(ledger._rows_by_asm_gen.items()):
        rows_snap[(aid, gen)] = {
            t_key: (
                row.assembly_id,
                row.structural_generation,
                row.surface_utf8_nfc,
                row.marker,
                bytes(row.surface_sha256),
                bytes(row.feature_bundle_digest),
                (
                    row.envelope.raw_surface_nfc_utf8,
                    bytes(row.envelope.surface_sha256),
                    bytes(row.envelope.feature_bundle_digest),
                    tuple(row.envelope.canonical_features_copy),
                    row.envelope.marker,
                ),
                frozenset(row.confirmed_roots),
            )
            for t_key, row in sorted(candidate_map.items())
        }

    bundles_snap = {
        surf_key: frozenset(digests)
        for surf_key, digests in sorted(ledger._bundles_by_surface.items())
    }

    snap = {
        "available": ledger.available,
        "_rows_by_asm_gen": rows_snap,
        "_bundles_by_surface": bundles_snap,
        "_processed_outbox_keys": frozenset(ledger._processed_outbox_keys),
    }
    missing_ledger = set(vars(ledger).keys()) - set(snap.keys())
    assert not missing_ledger, f"snapshot_ledger missing fields: {missing_ledger}"
    return snap


# ---------------------------------------------------------------------------
# Trained Network Fixture Builders
# ---------------------------------------------------------------------------

def _build_rich_test_state() -> tuple[MachineState, CoreEventPayloadV1, CoreEventPayloadV1, int]:
    """Build a rich fixture network state with committed cells, consolidated synapses, and StableBinding."""
    state = MachineState()

    ev_a = encode_lexical_token_event("القط", exposure_id=1, event_order=0).core_event
    ev_b = encode_lexical_token_event("يشرب", exposure_id=1, event_order=1).core_event
    ev_c = encode_lexical_token_event("حليب", exposure_id=1, event_order=2).core_event

    proj_a = project_core_event_v1(ev_a)
    proj_b = project_core_event_v1(ev_b)
    proj_c = project_core_event_v1(ev_c)

    p_a = tuple(sorted(proj_a.x_fixed_by_global_id.keys()))[:2]
    c_b = tuple(sorted(proj_b.x_fixed_by_global_id.keys()))[:2]
    y_c = tuple(sorted(proj_c.x_fixed_by_global_id.keys()))[:3]

    for cid in p_a + c_b + y_c:
        state.W.commit_cell(cid, 0)

    # Pick candidate z from uncommitted cells in LANGUAGE region
    free_cells = [
        c for c in range(100, 200)
        if c not in state.W.committed_cells
    ]
    z_cell = free_cells[0]
    state.W.commit_cell(z_cell, 0)

    def _wire_syn(src: int, tgt: int, scope: SynapseScope, s_val: float = 0.85):
        if not state.W.latent_table.is_eligible(src, tgt):
            try:
                state.W.latent_table.admit_or_recycle_coactive_partner(
                    src, tgt,
                    protected_bidirectional_neighbors=state.W.get_protected_bidirectional_neighbors(src),
                    event_clock=state.W.global_event_clock,
                    reason="TEST_FIXTURE",
                )
            except Exception:
                state.W.latent_table.admit_or_recycle_coactive_partner(
                    tgt, src,
                    protected_bidirectional_neighbors=state.W.get_protected_bidirectional_neighbors(tgt),
                    event_clock=state.W.global_event_clock,
                    reason="TEST_FIXTURE",
                )
        syn = Synapse(
            key=(src, tgt, scope),
            state=SynapseState.CONSOLIDATED,
            S=s_val,
            E_ext=4.0,
            E_int=0.0,
            external_count=3,
            confirmed_roots=(1, 2, 3),
        )
        state.W.add_or_replace_synapse(syn)

    # Wire P -> z, C -> z, z -> Y
    for p in p_a:
        _wire_syn(p, z_cell, SynapseScope.ASSOCIATIVE, 0.90)
    for b in c_b:
        _wire_syn(b, z_cell, SynapseScope.LOCAL, 0.90)
    for y in y_c:
        _wire_syn(z_cell, y, SynapseScope.ASSOCIATIVE, 0.95)

    # Register calibrated StableBinding
    anchor_set_b = frozenset(proj_b.x_fixed_by_global_id.keys())
    state.W.stable_bindings[z_cell] = StableBinding(
        schema_version=2,
        z_cell_id=z_cell,
        anchor_id=c_b[0],
        owner_seq=1,
        binding_generation=1,
        p_keys=((p_a[0], z_cell, SynapseScope.ASSOCIATIVE), (p_a[1], z_cell, SynapseScope.ASSOCIATIVE)),
        l_z_q6=500_000,
        u_z_q6=100_000,
        tau_ctx_q6=150_000,
        c_keys=((c_b[0], z_cell, SynapseScope.LOCAL), (c_b[1], z_cell, SynapseScope.LOCAL)),
        y_keys=((z_cell, y_c[0], SynapseScope.ASSOCIATIVE), (z_cell, y_c[1], SynapseScope.ASSOCIATIVE)),
        anchor_source_set=anchor_set_b,
        status=BindingStatus.ACTIVE,
        depth=1,
    )

    # Wire reciprocal triangle for Assembly on y_c
    for u in y_c:
        for v in y_c:
            if u != v:
                _wire_syn(u, v, SynapseScope.LOCAL, 0.80)

    state.W.assemblies[1] = Assembly(
        assembly_id=1,
        region=Region.LANGUAGE,
        member_cell_ids=frozenset(y_c),
        structural_generation=1,
        status=AssemblyStatus.LIVE,
    )

    return state, ev_a, ev_b, z_cell


# ===========================================================================
# 0. Field Coverage Audit Test (Correction V01)
# ===========================================================================

def test_field_coverage_audit():
    """Verify that snapshot helpers cover 100% of declared persistent fields directly from production classes.

    Ensures that any future state attribute added to production classes without corresponding
    snapshot coverage will immediately cause this audit to fail.
    """
    state, _, _, _ = _build_rich_test_state()
    ledger = SurfaceReadoutLedgerV1()

    # 1. Audit WState and LatentNeighborhoodTable
    snap_w = snapshot_w(state.W)
    missing_w = set(vars(state.W).keys()) - set(snap_w.keys())
    assert not missing_w, f"Audit failed: WState has uncaptured fields: {missing_w}"

    missing_latent = set(vars(state.W.latent_table).keys()) - set(snap_w["latent_table"].keys())
    assert not missing_latent, f"Audit failed: LatentNeighborhoodTable has uncaptured fields: {missing_latent}"

    # 2. Audit HSlowState
    snap_h = snapshot_h_slow(state.H_slow)
    missing_h = set(vars(state.H_slow).keys()) - set(snap_h.keys())
    assert not missing_h, f"Audit failed: HSlowState has uncaptured fields: {missing_h}"

    # 3. Audit RState
    snap_r = snapshot_r(state.R)
    missing_r = set(vars(state.R).keys()) - set(snap_r.keys())
    assert not missing_r, f"Audit failed: RState has uncaptured fields: {missing_r}"

    # 4. Audit SurfaceReadoutLedgerV1
    snap_l = snapshot_ledger(ledger)
    missing_l = set(vars(ledger).keys()) - set(snap_l.keys())
    assert not missing_l, f"Audit failed: SurfaceReadoutLedgerV1 has uncaptured fields: {missing_l}"


# ===========================================================================
# 1. Mandatory Acceptance Tests (P1-01 through P1-04)
# ===========================================================================

def test_p1_01_complete_retrieve_immutability_gate():
    """Verify complete state immutability across read-only episode (W_after == W_before, H_slow, R).

    Specifically verifies:
    - 100% structural equality AND SHA-256 state hash equality before and after RETRIEVE
    - w.last_referenced_event is NOT updated in RETRIEVE mode
    - latent_table._slots_by_cell is NOT populated for unmaterialized cells
    - synaptic weights, assemblies, bindings, and counters remain bit-for-bit identical
    """
    state, ev_a, ev_b, z_cell = _build_rich_test_state()

    # Pre-snapshot entire state
    w_snap_before = snapshot_w(state.W)
    h_snap_before = snapshot_h_slow(state.H_slow)
    r_snap_before = snapshot_r(state.R)

    hash_w_before = hash_state_snapshot(w_snap_before)
    hash_h_before = hash_state_snapshot(h_snap_before)
    hash_r_before = hash_state_snapshot(r_snap_before)

    latent_keys_before = set(state.W.latent_table._slots_by_cell.keys())
    last_ref_before = dict(state.W.last_referenced_event)

    # Execute read-only episode
    summary = run_read_only_episode(state, [ev_a, ev_b])

    # Assert active cells fired during episode (computation actually occurred)
    assert len(summary.event_results) == 2
    assert len(summary.event_results[0].f_step) > 0
    assert len(summary.event_results[1].f_step) > 0

    # Post-snapshots
    w_snap_after = snapshot_w(state.W)
    h_snap_after = snapshot_h_slow(state.H_slow)
    r_snap_after = snapshot_r(state.R)

    hash_w_after = hash_state_snapshot(w_snap_after)
    hash_h_after = hash_state_snapshot(h_snap_after)
    hash_r_after = hash_state_snapshot(r_snap_after)

    # Exact equality checks
    assert w_snap_after == w_snap_before, "WState mutated during read-only episode!"
    assert h_snap_after == h_snap_before, "HSlowState mutated during read-only episode!"
    assert r_snap_after == r_snap_before, "Caller RState mutated during read-only episode!"

    # SHA-256 cryptographic equality checks
    assert hash_w_after == hash_w_before, f"WState SHA-256 digest changed! ({hash_w_before} != {hash_w_after})"
    assert hash_h_after == hash_h_before, f"HSlowState SHA-256 digest changed! ({hash_h_before} != {hash_h_after})"
    assert hash_r_after == hash_r_before, f"RState SHA-256 digest changed! ({hash_r_before} != {hash_r_after})"

    # Specific defect verifications
    assert state.W.last_referenced_event == last_ref_before, "last_referenced_event modified in RETRIEVE!"
    assert set(state.W.latent_table._slots_by_cell.keys()) == latent_keys_before, "Latent table keys expanded!"


def test_p1_02_stale_binding_read_only_isolation():
    """Verify that encountered invalid bindings in read-only mode close the gate without mutating status to STALE."""
    state, ev_a, ev_b, z_cell = _build_rich_test_state()

    # Corrupt binding calibration: l_z_q6 > u_z_q6 violates mandatory calibration invariant
    bad_binding = dataclasses.replace(
        state.W.stable_bindings[z_cell],
        l_z_q6=100_000,
        u_z_q6=500_000,  # Invalid: l_z_q6 must be >= u_z_q6
    )
    state.W.stable_bindings[z_cell] = bad_binding

    w_snap_before = snapshot_w(state.W)
    hash_w_before = hash_state_snapshot(w_snap_before)

    # Run read-only episode
    summary = run_read_only_episode(state, [ev_a, ev_b])

    # 1. Gate must close for z_cell
    ev1_res = summary.event_results[1]
    assert ev1_res.g_ctx_by_z.get(z_cell, 0) == 0, "Gate should be closed for invalid binding!"

    # 2. Diagnostic must record invalid context threshold
    assert StatusCode.INVALID_CONTEXT_THRESHOLD in ev1_res.diagnostics

    # 3. Permanent caller W must NOT mutate binding status to STALE
    assert state.W.stable_bindings[z_cell].status == BindingStatus.ACTIVE, "Binding status mutated to STALE in RETRIEVE!"

    # 4. Total WState immutability and SHA-256 match
    w_snap_after = snapshot_w(state.W)
    assert w_snap_after == w_snap_before, "WState snapshot changed despite read-only mode!"
    assert hash_state_snapshot(w_snap_after) == hash_w_before, "WState SHA-256 changed in RETRIEVE!"


def test_p1_03_homeostasis_scratch_isolation():
    """Verify homeostatic slow variables H_slow remain strictly isolated in scratch and deterministic across runs."""
    state, ev_a, ev_b, _ = _build_rich_test_state()

    h_snap_initial = snapshot_h_slow(state.H_slow)
    hash_h_initial = hash_state_snapshot(h_snap_initial)

    # Run multiple read-only episodes
    outputs = []
    for run_idx in range(5):
        summary = run_read_only_episode(state, [ev_a, ev_b])
        outputs.append(summary.next_step_pt_by_cell)
        h_snap_current = snapshot_h_slow(state.H_slow)
        assert h_snap_current == h_snap_initial, f"H_slow mutated on run {run_idx}!"
        assert hash_state_snapshot(h_snap_current) == hash_h_initial, f"H_slow SHA-256 changed on run {run_idx}!"

    # Output determinism check: every run produces identical floating-point temporal drive
    for out in outputs[1:]:
        assert out == outputs[0], "Non-deterministic output across read-only episodes!"


def test_p1_04_transactional_stale_transition_abort_vs_commit():
    """Verify transactional STALE mechanics: ABORT preserves ACTIVE, COMMIT settles invalid binding to STALE."""
    # --- Case A: Aborted Exposure preserves ACTIVE on permanent W ---
    state_a, _, _, z_cell = _build_rich_test_state()
    # Create events matching exposure_id 101
    ev_a101 = encode_lexical_token_event("القط", exposure_id=101, event_order=0).core_event
    ev_b101 = encode_lexical_token_event("يشرب", exposure_id=101, event_order=1).core_event

    # Corrupt binding on state_a
    state_a.W.stable_bindings[z_cell] = dataclasses.replace(
        state_a.W.stable_bindings[z_cell],
        l_z_q6=100_000,
        u_z_q6=500_000,
    )
    tx_a = ExposureTransactionManager(state_a, allow_headless_events=True)
    tx_a.begin_exposure(101)
    tx_a.process_event(ev_a101)
    tx_a.process_event(ev_b101)
    abort_status = tx_a.abort_exposure(101)

    assert abort_status == ExposureStatus.ABORTED
    assert state_a.W.stable_bindings[z_cell].status == BindingStatus.ACTIVE, "Aborted transaction marked binding STALE on permanent state!"

    # --- Case B: Committed Exposure settles invalid binding to STALE on shadow W (Step 5.1) ---
    state_b, _, _, z_cell = _build_rich_test_state()
    # Create events matching exposure_id 102
    ev_a102 = encode_lexical_token_event("القط", exposure_id=102, event_order=0).core_event
    ev_b102 = encode_lexical_token_event("يشرب", exposure_id=102, event_order=1).core_event

    state_b.W.stable_bindings[z_cell] = dataclasses.replace(
        state_b.W.stable_bindings[z_cell],
        l_z_q6=100_000,
        u_z_q6=500_000,
    )
    tx_b = ExposureTransactionManager(state_b, allow_headless_events=True)
    tx_b.begin_exposure(102)
    tx_b.process_event(ev_a102)
    tx_b.process_event(ev_b102)
    report_b = tx_b.end_exposure(102)

    assert report_b.status == ExposureStatus.COMPLETED
    assert StatusCode.INVALID_CONTEXT_THRESHOLD in report_b.diagnostics
    assert state_b.W.stable_bindings[z_cell].status == BindingStatus.STALE, "Committed exposure failed to settle invalid binding to STALE!"


# ===========================================================================
# 2. Focused Latent Neighborhood Virtual Lookup Tests
# ===========================================================================

def test_latent_lookup_on_unmaterialized_cell():
    """Verify get_slots_read_only returns deterministic 24 slots without inserting into _slots_by_cell."""
    table = LatentNeighborhoodTable()
    unmaterialized_id = 3500
    assert unmaterialized_id not in table._slots_by_cell

    # Call get_slots_read_only
    slots_ro = table.get_slots_read_only(unmaterialized_id)
    assert len(slots_ro) == 24
    assert unmaterialized_id not in table._slots_by_cell, "Read-only lookup mutated _slots_by_cell!"

    # Call get_slots (should delegate to get_slots_read_only)
    slots_delegated = table.get_slots(unmaterialized_id)
    assert slots_delegated == slots_ro
    assert unmaterialized_id not in table._slots_by_cell, "get_slots mutated _slots_by_cell!"

    # Verify fixed slots
    expected_local = compute_fixed_local_neighbors(unmaterialized_id)
    expected_topo = compute_fixed_topographic_neighbors(unmaterialized_id)
    assert slots_ro[6:12] == expected_local
    assert slots_ro[18:24] == expected_topo
    assert all(slots_ro[i] is None for i in range(0, 6))
    assert all(slots_ro[i] is None for i in range(12, 18))


def test_virtual_vs_materialized_neighbor_equality():
    """Verify virtual neighbor computation matches explicit materialize_cell output exactly."""
    table = LatentNeighborhoodTable()
    cell_id = 7777

    slots_virtual = table.get_slots_read_only(cell_id)
    assert cell_id not in table._slots_by_cell

    slots_materialized = tuple(table.materialize_cell(cell_id))
    assert cell_id in table._slots_by_cell
    assert slots_virtual == slots_materialized


def test_reverse_neighbors_and_eligibility_immutability():
    """Verify reverse_neighbors and is_eligible do not mutate _slots_by_cell for candidate sources."""
    table = LatentNeighborhoodTable()
    src = 500
    tgt = 501

    assert src not in table._slots_by_cell
    assert tgt not in table._slots_by_cell

    # Reverse neighbors check
    rev = table.reverse_neighbors(tgt)
    assert isinstance(rev, set)
    assert len(table._slots_by_cell) == 0, "reverse_neighbors mutated _slots_by_cell!"

    # Eligibility check
    eligible = table.is_eligible(src, tgt)
    assert isinstance(eligible, bool)
    assert len(table._slots_by_cell) == 0, "is_eligible mutated _slots_by_cell!"


# ===========================================================================
# 3. Focused GENERATE Immutability and Ledger Tests
# ===========================================================================

def test_generate_episode_caller_state_and_ledger_immutability():
    """Verify generate_episode leaves caller permanent state and readout ledger 100% untouched."""
    state, ev_a, ev_b, _ = _build_rich_test_state()
    ledger = SurfaceReadoutLedgerV1()

    # Pre-snapshots
    w_snap_before = snapshot_w(state.W)
    h_snap_before = snapshot_h_slow(state.H_slow)
    r_snap_before = snapshot_r(state.R)
    ledger_snap_before = snapshot_ledger(ledger)

    hash_w_before = hash_state_snapshot(w_snap_before)
    hash_h_before = hash_state_snapshot(h_snap_before)
    hash_r_before = hash_state_snapshot(r_snap_before)
    hash_l_before = hash_state_snapshot(ledger_snap_before)

    # Run generate_episode
    gen_summary = generate_episode(
        state,
        [ev_a, ev_b],
        ledger,
        max_steps=3,
    )

    # Post-snapshots
    w_snap_after = snapshot_w(state.W)
    h_snap_after = snapshot_h_slow(state.H_slow)
    r_snap_after = snapshot_r(state.R)
    ledger_snap_after = snapshot_ledger(ledger)

    assert w_snap_after == w_snap_before, "WState mutated during GENERATE_EPISODE!"
    assert h_snap_after == h_snap_before, "HSlowState mutated during GENERATE_EPISODE!"
    assert r_snap_after == r_snap_before, "RState mutated during GENERATE_EPISODE!"
    assert ledger_snap_after == ledger_snap_before, "Readout ledger mutated during GENERATE_EPISODE!"

    assert hash_state_snapshot(w_snap_after) == hash_w_before
    assert hash_state_snapshot(h_snap_after) == hash_h_before
    assert hash_state_snapshot(r_snap_after) == hash_r_before
    assert hash_state_snapshot(ledger_snap_after) == hash_l_before


# ===========================================================================
# 4. Mode Discrimination for last_referenced_event
# ===========================================================================

def test_learn_mode_updates_last_referenced_event_while_retrieve_does_not():
    """Verify LEARN mode updates last_referenced_event for active cells while RETRIEVE never updates it."""
    state, ev_a, ev_b, _ = _build_rich_test_state()
    p_a = project_core_event_v1(ev_a)
    active_cell = next(iter(p_a.x_fixed_by_global_id.keys()))

    # Set clock to 50
    state.W.global_event_clock = 50
    state.W.last_referenced_event[active_cell] = 10

    # 1. Execute in RETRIEVE mode
    proj = project_core_event_v1(ev_a)
    execute_two_pass_event(
        state,
        proj.x_fixed_by_global_id,
        proj.x_float_by_global_id,
        mode=ExecutionMode.RETRIEVE,
        origin=EventOrigin.READ_ONLY_OBSERVED,
        boundary=True,
    )
    assert state.W.last_referenced_event[active_cell] == 10, "last_referenced_event updated in RETRIEVE mode!"

    # 2. Execute in LEARN mode
    execute_two_pass_event(
        state,
        proj.x_fixed_by_global_id,
        proj.x_float_by_global_id,
        mode=ExecutionMode.LEARN,
        origin=EventOrigin.EXTERNAL_DIRECT,
        boundary=True,
    )
    assert state.W.last_referenced_event[active_cell] == 50, "last_referenced_event NOT updated in LEARN mode!"


# ===========================================================================
# 5. Non-Empty Ledger & Genuinely Trained Neural State Verification (Correction V02)
# ===========================================================================

def test_non_empty_ledger_genuine_56_root_curriculum_immutability():
    """Execute generation and retrieval on a genuinely trained 56-root curriculum state with a populated ledger.

    Normative verification requirements (Correction V02):
    - Preferred curriculum: 56 alternating cold-start roots with canonical EOS.
    - No hand-wired target assemblies, no manually inserted attestation rows.
    - Non-empty ledger confirmed: multiple assemblies, multiple words and canonical EOS rows attested.
    - Execute generation from Cat prompt ['القط'] -> ('يشرب', 'حليب') -> GEN_STOP_EOS.
    - Execute generation from Eagle prompt ['النسر'] -> ('يشرب', 'ماء') -> GEN_STOP_AMBIGUOUS.
    - Execute read-only retrieval episode.
    - Verify complete W equality before and after generation.
    - Verify complete H_slow equality before and after generation.
    - Verify complete caller R equality before and after generation.
    - Verify complete ledger equality before and after generation.
    - Verify bit-for-bit cryptographic equality of canonical SHA-256 digests across all state partitions.
    - Verify zero additional processed outbox keys and zero added/removed attestation roots.
    """
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
    )

    branch_ab = encode_exposure("القط يشرب حليب", append_eos=True)
    branch_db = encode_exposure("النسر يشرب ماء", append_eos=True)

    # Train across 56 alternating roots (cold-start from zero)
    for root_id in range(1, 57):
        is_ab = (root_id % 2 != 0)
        envs = branch_ab if is_ab else branch_db
        tx.begin_exposure(root_id)
        for env in envs:
            core_ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        tx.end_exposure(root_id)

    # 1. Assert non-empty, genuinely populated peripheral ledger
    assert len(ledger._rows_by_asm_gen) > 0, "Ledger must contain attested assembly rows!"
    assert len(ledger._processed_outbox_keys) == 398, "Ledger must have consumed genuine outbox notifications!"
    assert len(ledger._bundles_by_surface) > 0, "Ledger must contain attested bundle mappings!"

    # 2. Pre-snapshots of genuinely populated state before Cat generation
    w_snap_pre_cat = snapshot_w(state.W)
    h_snap_pre_cat = snapshot_h_slow(state.H_slow)
    r_snap_pre_cat = snapshot_r(state.R)
    ledger_snap_pre_cat = snapshot_ledger(ledger)

    hash_w_pre_cat = hash_state_snapshot(w_snap_pre_cat)
    hash_h_pre_cat = hash_state_snapshot(h_snap_pre_cat)
    hash_r_pre_cat = hash_state_snapshot(r_snap_pre_cat)
    hash_l_pre_cat = hash_state_snapshot(ledger_snap_pre_cat)

    # 3. Execute Cat prompt rollout
    prompt_cat = [branch_ab[0].core_event]
    gen_cat = generate_episode(state, prompt_cat, ledger, max_steps=5)

    assert gen_cat.emitted_surfaces == ("يشرب", "حليب"), f"Unexpected Cat rollout: {gen_cat.emitted_surfaces}"
    assert gen_cat.stop_status == StatusCode.GEN_STOP_EOS, f"Expected GEN_STOP_EOS, got: {gen_cat.stop_status}"
    assert gen_cat.steps[0].emitted_envelope is not None, "Missing readout envelope for step 0"
    assert gen_cat.steps[1].emitted_envelope is not None, "Missing readout envelope for step 1"
    assert gen_cat.steps[2].emitted_envelope.marker == Marker.EOS, "Step 2 envelope must have Marker.EOS"

    # Post-checks after Cat generation
    w_snap_post_cat = snapshot_w(state.W)
    h_snap_post_cat = snapshot_h_slow(state.H_slow)
    r_snap_post_cat = snapshot_r(state.R)
    ledger_snap_post_cat = snapshot_ledger(ledger)

    assert w_snap_post_cat == w_snap_pre_cat, "WState mutated during Cat generate_episode!"
    assert h_snap_post_cat == h_snap_pre_cat, "HSlowState mutated during Cat generate_episode!"
    assert r_snap_post_cat == r_snap_pre_cat, "Caller RState mutated during Cat generate_episode!"
    assert ledger_snap_post_cat == ledger_snap_pre_cat, "Populated ledger mutated during Cat generate_episode!"

    assert hash_state_snapshot(w_snap_post_cat) == hash_w_pre_cat, "WState SHA-256 digest drifted during Cat generation!"
    assert hash_state_snapshot(h_snap_post_cat) == hash_h_pre_cat, "HSlowState SHA-256 digest drifted during Cat generation!"
    assert hash_state_snapshot(r_snap_post_cat) == hash_r_pre_cat, "Caller RState SHA-256 digest drifted during Cat generation!"
    assert hash_state_snapshot(ledger_snap_post_cat) == hash_l_pre_cat, "Ledger SHA-256 digest drifted during Cat generation!"

    assert ledger._processed_outbox_keys == ledger_snap_pre_cat["_processed_outbox_keys"], "Outbox keys modified!"

    # 4. Pre-snapshots before Eagle prompt rollout
    w_snap_pre_eagle = snapshot_w(state.W)
    h_snap_pre_eagle = snapshot_h_slow(state.H_slow)
    r_snap_pre_eagle = snapshot_r(state.R)
    ledger_snap_pre_eagle = snapshot_ledger(ledger)

    hash_w_pre_eagle = hash_state_snapshot(w_snap_pre_eagle)
    hash_h_pre_eagle = hash_state_snapshot(h_snap_pre_eagle)
    hash_r_pre_eagle = hash_state_snapshot(r_snap_pre_eagle)
    hash_l_pre_eagle = hash_state_snapshot(ledger_snap_pre_eagle)

    prompt_eagle = [branch_db[0].core_event]
    gen_eagle = generate_episode(state, prompt_eagle, ledger, max_steps=5)

    assert gen_eagle.emitted_surfaces == ("يشرب", "ماء"), f"Unexpected Eagle rollout: {gen_eagle.emitted_surfaces}"
    assert gen_eagle.stop_status == StatusCode.GEN_STOP_AMBIGUOUS, f"Expected GEN_STOP_AMBIGUOUS, got: {gen_eagle.stop_status}"

    # Post-checks after Eagle generation
    assert snapshot_w(state.W) == w_snap_pre_eagle, "WState mutated during Eagle generate_episode!"
    assert snapshot_h_slow(state.H_slow) == h_snap_pre_eagle, "HSlowState mutated during Eagle generate_episode!"
    assert snapshot_r(state.R) == r_snap_pre_eagle, "Caller RState mutated during Eagle generate_episode!"
    assert snapshot_ledger(ledger) == ledger_snap_pre_eagle, "Populated ledger mutated during Eagle generate_episode!"

    assert hash_state_snapshot(snapshot_w(state.W)) == hash_w_pre_eagle, "WState SHA-256 digest drifted during Eagle generation!"
    assert hash_state_snapshot(snapshot_h_slow(state.H_slow)) == hash_h_pre_eagle, "HSlowState SHA-256 digest drifted during Eagle generation!"
    assert hash_state_snapshot(snapshot_r(state.R)) == hash_r_pre_eagle, "Caller RState SHA-256 digest drifted during Eagle generation!"
    assert hash_state_snapshot(snapshot_ledger(ledger)) == hash_l_pre_eagle, "Ledger SHA-256 digest drifted during Eagle generation!"

    # 5. RETRIEVE mode execution on genuinely trained 56-root state
    w_snap_pre_ro = snapshot_w(state.W)
    hash_w_pre_ro = hash_state_snapshot(w_snap_pre_ro)

    ro_summary = run_read_only_episode(state, [branch_ab[0].core_event, branch_ab[1].core_event])
    assert len(ro_summary.event_results) == 2

    assert snapshot_w(state.W) == w_snap_pre_ro, "WState mutated during RETRIEVE on trained state!"
    assert hash_state_snapshot(snapshot_w(state.W)) == hash_w_pre_ro, "WState SHA-256 drifted during RETRIEVE on trained state!"
