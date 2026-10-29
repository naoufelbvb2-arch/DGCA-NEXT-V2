"""Acceptance test suite for R2-A01 Patch 2: Read-Only Immutability, Latent Virtual Lookups & Transactional STALE.

Covers:
- Field Coverage Audit: Complete, verifiable 100% attribute coverage across WState, LatentNeighborhoodTable, HSlowState, RState, and SurfaceReadoutLedgerV1
- Nested Dataclass Coverage Audit: Dynamic verification via dataclasses.fields() across Synapse, ContextCandidateDescriptor, StableBinding, OwnerProfile, CompactWitnessProfile, ContrastEpisodeRecord, Assembly, ParentContextRef, WiringLogEntry, LedgerCandidateRow
- Canonical Enum Serialization & Primitive Type Separation: Guarantees enum identity is serialized before generic int/str, preventing type collisions (IntEnum vs int, StrEnum vs str, bool vs int, int vs float)
- Adversarial Synapse Mutation Sensitivity Test: Modifies previously omitted Synapse fields (last_evidence_root, candidate_deadline, internally_supported, created_event_id, created_exposure_id, last_external_event_id) and proves structural inequality and SHA-256 digest divergence
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
    WiringLogEntry,
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
from dgca.encoder.envelope import (
    CoreEventPayloadV1,
    EventOrigin,
    Marker,
    PeripheralSurfaceEnvelopeV1,
    encode_exposure,
    encode_lexical_token_event,
)
from dgca.lifecycle.exposure_tx import (
    ExposureStatus,
    ExposureTransactionManager,
    compute_pred_score,
    run_read_only_episode,
)
from dgca.lla.contrast_ledger import ContrastEpisodeRecord
from dgca.lla.owner_registry import CompactWitnessProfile, OwnerProfile
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
    - bool: b'B1;' or b'B0;' (Checked before int, as bool is a subclass of int in Python)
    - enum.Enum: b'E:<class_name>:<enum_value>;' (Checked before int/str, so IntEnum/StrEnum retain enum identity)
    - int: b'I:<decimal>;'
    - float: b'F:<hex_float>;' (exact bitwise IEEE 754 precision, platform-independent)
    - str: b'S:<len>:<utf8_bytes>;'
    - bytes: b'X:<len>:<raw_bytes>;'
    - tuple / list: b'T:<len>[<element_digests>];'
    - set / frozenset: b'U:<len>{<sorted_element_digests>};' (elements sorted by their own canonical digest)
    - dict: b'D:<len>{<sorted_key_val_pairs>};' (pairs sorted by key's canonical digest)
    """
    if val is None:
        return b"N;"
    elif isinstance(val, bool):
        return b"B1;" if val else b"B0;"
    elif isinstance(val, enum.Enum):
        cls_name = val.__class__.__name__.encode("ascii")
        val_str = str(val.value).encode("utf-8")
        return b"E:" + cls_name + b":" + val_str + b";"
    elif isinstance(val, int):
        return b"I:" + str(val).encode("ascii") + b";"
    elif isinstance(val, float):
        return b"F:" + val.hex().encode("ascii") + b";"
    elif isinstance(val, str):
        b = val.encode("utf-8")
        return b"S:" + str(len(b)).encode("ascii") + b":" + b + b";"
    elif isinstance(val, bytes):
        return b"X:" + str(len(val)).encode("ascii") + b":" + val + b";"
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
# Deep Nested Snapshot Helpers for Invariant Verification (100% Dataclass Coverage)
# ---------------------------------------------------------------------------

def _snapshot_synapse(s: Synapse) -> dict[str, Any]:
    """Capture all 13 declared fields of Synapse with dynamic dataclass audit (Correction V04)."""
    snap = {
        "key": s.key,
        "S": s.S,
        "E_ext": s.E_ext,
        "E_int": s.E_int,
        "external_count": s.external_count,
        "state": s.state,
        "created_event_id": s.created_event_id,
        "created_exposure_id": s.created_exposure_id,
        "last_external_event_id": s.last_external_event_id,
        "last_evidence_root": s.last_evidence_root,
        "candidate_deadline": s.candidate_deadline,
        "internally_supported": s.internally_supported,
        "confirmed_roots": tuple(sorted(s.confirmed_roots)),
    }
    missing = {f.name for f in dataclasses.fields(Synapse)} - set(snap.keys())
    assert not missing, f"_snapshot_synapse missing dataclass fields: {missing}"
    return snap


def _snapshot_assembly(asm: Assembly) -> dict[str, Any]:
    """Capture all declared fields of Assembly."""
    snap = {
        "assembly_id": asm.assembly_id,
        "region": asm.region,
        "member_cell_ids": tuple(sorted(asm.member_cell_ids)),
        "structural_generation": asm.structural_generation,
        "birth_close_serial": asm.birth_close_serial,
        "last_mutation_close_serial": asm.last_mutation_close_serial,
        "last_merge_split_close_serial": asm.last_merge_split_close_serial,
        "status": asm.status,
    }
    missing = {f.name for f in dataclasses.fields(Assembly)} - set(snap.keys())
    assert not missing, f"_snapshot_assembly missing dataclass fields: {missing}"
    return snap


def _snapshot_parent_context_ref(ref: ParentContextRef) -> dict[str, Any]:
    """Capture all declared fields of ParentContextRef."""
    snap = {
        "parent_z_cell_id": ref.parent_z_cell_id,
        "parent_anchor_id": ref.parent_anchor_id,
        "parent_owner_seq": ref.parent_owner_seq,
        "parent_binding_generation": ref.parent_binding_generation,
        "depth": ref.depth,
    }
    missing = {f.name for f in dataclasses.fields(ParentContextRef)} - set(snap.keys())
    assert not missing, f"_snapshot_parent_context_ref missing dataclass fields: {missing}"
    return snap


def _snapshot_candidate(cand: ContextCandidateDescriptor) -> dict[str, Any]:
    """Capture all declared fields of ContextCandidateDescriptor."""
    snap = {
        "z_cell_id": cand.z_cell_id,
        "anchor_id": cand.anchor_id,
        "owner_seq": cand.owner_seq,
        "p_sources": cand.p_sources,
        "c_sources": cand.c_sources,
        "y_targets": cand.y_targets,
        "l_z_q6": cand.l_z_q6,
        "u_z_q6": cand.u_z_q6,
        "tau_ctx_q6": cand.tau_ctx_q6,
        "anchor_source_set": frozenset(cand.anchor_source_set),
        "phase": cand.phase,
        "probe_matches": cand.probe_matches,
        "consolidation_matches": cand.consolidation_matches,
        "age_events": cand.age_events,
        "admitted_root_id": cand.admitted_root_id,
        "depth": cand.depth,
        "p_source_kinds": cand.p_source_kinds,
        "parent_refs": {cid: _snapshot_parent_context_ref(ref) for cid, ref in sorted(cand.parent_refs.items())},
        "status": cand.status,
    }
    missing = {f.name for f in dataclasses.fields(ContextCandidateDescriptor)} - set(snap.keys())
    assert not missing, f"_snapshot_candidate missing dataclass fields: {missing}"
    return snap


def _snapshot_binding(b: StableBinding) -> dict[str, Any]:
    """Capture all declared fields of StableBinding."""
    snap = {
        "schema_version": b.schema_version,
        "z_cell_id": b.z_cell_id,
        "anchor_id": b.anchor_id,
        "owner_seq": b.owner_seq,
        "binding_generation": b.binding_generation,
        "p_keys": b.p_keys,
        "l_z_q6": b.l_z_q6,
        "u_z_q6": b.u_z_q6,
        "tau_ctx_q6": b.tau_ctx_q6,
        "c_keys": b.c_keys,
        "y_keys": b.y_keys,
        "anchor_source_set": frozenset(b.anchor_source_set),
        "status": b.status,
        "depth": b.depth,
        "p_source_kinds": b.p_source_kinds,
        "parent_refs": {cid: _snapshot_parent_context_ref(ref) for cid, ref in sorted(b.parent_refs.items())},
    }
    missing = {f.name for f in dataclasses.fields(StableBinding)} - set(snap.keys())
    assert not missing, f"_snapshot_binding missing dataclass fields: {missing}"
    return snap


def _snapshot_compact_witness_profile(wp: CompactWitnessProfile) -> dict[str, Any]:
    """Capture all declared fields of CompactWitnessProfile."""
    snap = {
        "top8_p_supports_u": dict(wp.top8_p_supports_u),
        "top8_c_supports_u": dict(wp.top8_c_supports_u),
        "top8_y_supports_u": dict(wp.top8_y_supports_u),
        "full_p_digest": bytes(wp.full_p_digest),
        "full_c_digest": bytes(wp.full_c_digest),
        "full_y_digest": bytes(wp.full_y_digest),
        "p_source_kinds": dict(wp.p_source_kinds),
        "p_parent_refs": {cid: _snapshot_parent_context_ref(ref) for cid, ref in sorted(wp.p_parent_refs.items())},
        "audited_root_id": wp.audited_root_id,
        "p_bundle_digest": bytes(wp.p_bundle_digest),
        "c_bundle_digest": bytes(wp.c_bundle_digest),
        "y_bundle_digest": bytes(wp.y_bundle_digest),
    }
    missing = {f.name for f in dataclasses.fields(CompactWitnessProfile)} - set(snap.keys())
    assert not missing, f"_snapshot_compact_witness_profile missing dataclass fields: {missing}"
    return snap


def _snapshot_owner_profile(prof: OwnerProfile) -> dict[str, Any]:
    """Capture all declared fields of OwnerProfile."""
    snap = {
        "schema_version": prof.schema_version,
        "anchor_id": prof.anchor_id,
        "owner_seq": prof.owner_seq,
        "z_cell_id": prof.z_cell_id,
        "state": prof.state,
        "p_sources": prof.p_sources,
        "c_sources": prof.c_sources,
        "y_targets": prof.y_targets,
        "l_z_q6": prof.l_z_q6,
        "u_z_q6": prof.u_z_q6,
        "tau_ctx_q6": prof.tau_ctx_q6,
        "anchor_source_set": frozenset(prof.anchor_source_set),
        "witness_profiles": tuple(_snapshot_compact_witness_profile(wp) for wp in prof.witness_profiles),
        "binding_generation": prof.binding_generation,
        "depth": prof.depth,
        "p_source_kinds": prof.p_source_kinds,
        "parent_refs": {cid: _snapshot_parent_context_ref(ref) for cid, ref in sorted(prof.parent_refs.items())},
        "profile_digest": bytes(prof.profile_digest),
    }
    missing = {f.name for f in dataclasses.fields(OwnerProfile)} - set(snap.keys())
    assert not missing, f"_snapshot_owner_profile missing dataclass fields: {missing}"
    return snap


def _snapshot_contrast_episode(ep: ContrastEpisodeRecord) -> dict[str, Any]:
    """Capture all declared fields of ContrastEpisodeRecord."""
    snap = {
        "anchor_id": ep.anchor_id,
        "exposure_id": ep.exposure_id,
        "event_order_b": ep.event_order_b,
        "completed_event_clock": ep.completed_event_clock,
        "p_supports_u": dict(ep.p_supports_u),
        "c_supports_u": dict(ep.c_supports_u),
        "y_supports_u": dict(ep.y_supports_u),
        "p_source_kinds": dict(ep.p_source_kinds),
        "p_parent_refs": {cid: _snapshot_parent_context_ref(ref) for cid, ref in sorted(ep.p_parent_refs.items())},
        "p_digest": bytes(ep.p_digest),
        "c_digest": bytes(ep.c_digest),
        "y_digest": bytes(ep.y_digest),
        "p_bundle_digest": bytes(ep.p_bundle_digest),
        "c_bundle_digest": bytes(ep.c_bundle_digest),
        "y_bundle_digest": bytes(ep.y_bundle_digest),
        "p_direct_x_u": dict(ep.p_direct_x_u),
        "c_direct_x_u": dict(ep.c_direct_x_u),
        "has_collision": ep.has_collision,
    }
    missing = {f.name for f in dataclasses.fields(ContrastEpisodeRecord)} - set(snap.keys())
    assert not missing, f"_snapshot_contrast_episode missing dataclass fields: {missing}"
    return snap


def _snapshot_wiring_log_entry(entry: WiringLogEntry) -> dict[str, Any]:
    """Capture all declared fields of WiringLogEntry."""
    snap = {
        "event_clock": entry.event_clock,
        "owner_cell_id": entry.owner_cell_id,
        "slot_index": entry.slot_index,
        "old_target_id": entry.old_target_id,
        "new_target_id": entry.new_target_id,
        "reason": entry.reason,
    }
    missing = {f.name for f in dataclasses.fields(WiringLogEntry)} - set(snap.keys())
    assert not missing, f"_snapshot_wiring_log_entry missing dataclass fields: {missing}"
    return snap


def _snapshot_ledger_candidate_row(row: LedgerCandidateRow) -> dict[str, Any]:
    """Capture all declared fields of LedgerCandidateRow."""
    snap = {
        "assembly_id": row.assembly_id,
        "structural_generation": row.structural_generation,
        "surface_utf8_nfc": row.surface_utf8_nfc,
        "marker": row.marker,
        "surface_sha256": bytes(row.surface_sha256),
        "feature_bundle_digest": bytes(row.feature_bundle_digest),
        "envelope": (
            row.envelope.raw_surface_nfc_utf8,
            bytes(row.envelope.surface_sha256),
            bytes(row.envelope.feature_bundle_digest),
            tuple(row.envelope.canonical_features_copy),
            row.envelope.marker,
        ),
        "confirmed_roots": frozenset(row.confirmed_roots),
    }
    missing = {f.name for f in dataclasses.fields(LedgerCandidateRow)} - set(snap.keys())
    assert not missing, f"_snapshot_ledger_candidate_row missing dataclass fields: {missing}"
    return snap


def snapshot_w(w: WState) -> dict[str, Any]:
    """Capture a comprehensive deep snapshot of WState covering 100% of persistent fields."""
    latent_snap = {
        "_slots_by_cell": {cid: tuple(slots) for cid, slots in sorted(w.latent_table._slots_by_cell.items())},
        "_pinned_slots": {cid: frozenset(slots) for cid, slots in sorted(w.latent_table._pinned_slots.items())},
        "_coactive_reverse_index": {cid: frozenset(sources) for cid, sources in sorted(w.latent_table._coactive_reverse_index.items())},
        "_wiring_logs": {
            cid: tuple(_snapshot_wiring_log_entry(e) for e in entries)
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
            k: _snapshot_synapse(s)
            for k, s in sorted(w.synapses.items())
        },
        "outgoing_by_source": {src: frozenset(keys) for src, keys in sorted(w.outgoing_by_source.items())},
        "incoming_by_target": {tgt: frozenset(keys) for tgt, keys in sorted(w.incoming_by_target.items())},
        "reserved_keys_by_candidate": {cid: frozenset(keys) for cid, keys in sorted(w.reserved_keys_by_candidate.items())},
        "assemblies": {
            aid: _snapshot_assembly(asm)
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
    rows_snap = {
        (aid, gen): {
            t_key: _snapshot_ledger_candidate_row(row)
            for t_key, row in sorted(candidate_map.items())
        }
        for (aid, gen), candidate_map in sorted(ledger._rows_by_asm_gen.items())
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
            created_event_id=1,
            created_exposure_id=1,
            last_external_event_id=2,
            last_evidence_root=1,
            candidate_deadline=100,
            internally_supported=False,
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
# 0. Field Coverage Audit Tests (Correction V01 & Section 3)
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


def test_nested_dataclass_coverage_audit():
    """Verify that nested snapshot helpers cover 100% of declared fields in all mutable dataclasses (Section 3).

    Specifically audits:
    - Synapse (all 13 fields)
    - ContextCandidateDescriptor (all 19 fields)
    - StableBinding (all 16 fields)
    - OwnerProfile (all 18 fields)
    - CompactWitnessProfile (all 12 fields)
    - ContrastEpisodeRecord (all 18 fields)
    - Assembly (all 8 fields)
    - ParentContextRef (all 5 fields)
    - WiringLogEntry (all 6 fields)
    - LedgerCandidateRow (all 8 fields)
    """
    state, _, _, z_cell = _build_rich_test_state()
    syn = next(iter(state.W.synapses.values()))
    binding = state.W.stable_bindings[z_cell]
    asm = state.W.assemblies[1]

    # 1. Synapse
    syn_snap = _snapshot_synapse(syn)
    assert set(syn_snap.keys()) == {f.name for f in dataclasses.fields(Synapse)}

    # 2. Assembly
    asm_snap = _snapshot_assembly(asm)
    assert set(asm_snap.keys()) == {f.name for f in dataclasses.fields(Assembly)}

    # 3. StableBinding
    bind_snap = _snapshot_binding(binding)
    assert set(bind_snap.keys()) == {f.name for f in dataclasses.fields(StableBinding)}

    # 4. ParentContextRef
    pref = ParentContextRef(
        parent_z_cell_id=5, parent_anchor_id=10, parent_owner_seq=1, parent_binding_generation=1, depth=2
    )
    pref_snap = _snapshot_parent_context_ref(pref)
    assert set(pref_snap.keys()) == {f.name for f in dataclasses.fields(ParentContextRef)}

    # 5. ContextCandidateDescriptor
    cand = ContextCandidateDescriptor(
        z_cell_id=10, anchor_id=20, owner_seq=1, p_sources=(1, 2), c_sources=(3, 4), y_targets=(5, 6),
        l_z_q6=500_000, u_z_q6=100_000, tau_ctx_q6=150_000, anchor_source_set=frozenset([1, 2]),
    )
    cand_snap = _snapshot_candidate(cand)
    assert set(cand_snap.keys()) == {f.name for f in dataclasses.fields(ContextCandidateDescriptor)}

    # 6. CompactWitnessProfile
    wp = CompactWitnessProfile(
        top8_p_supports_u={1: 100}, top8_c_supports_u={2: 200}, top8_y_supports_u={3: 300},
        full_p_digest=b"p", full_c_digest=b"c", full_y_digest=b"y",
    )
    wp_snap = _snapshot_compact_witness_profile(wp)
    assert set(wp_snap.keys()) == {f.name for f in dataclasses.fields(CompactWitnessProfile)}

    # 7. OwnerProfile
    prof = OwnerProfile(
        schema_version=1, anchor_id=20, owner_seq=1, z_cell_id=10, state=OwnerState.ACTIVE,
        p_sources=(1, 2), c_sources=(3, 4), y_targets=(5, 6), l_z_q6=500_000, u_z_q6=100_000,
        tau_ctx_q6=150_000, anchor_source_set=frozenset([1, 2]), witness_profiles=(wp, wp),
    )
    prof_snap = _snapshot_owner_profile(prof)
    assert set(prof_snap.keys()) == {f.name for f in dataclasses.fields(OwnerProfile)}

    # 8. ContrastEpisodeRecord
    ep = ContrastEpisodeRecord(
        anchor_id=20, exposure_id=1, event_order_b=1, completed_event_clock=100,
        p_supports_u={1: 100}, c_supports_u={2: 200}, y_supports_u={3: 300},
    )
    ep_snap = _snapshot_contrast_episode(ep)
    assert set(ep_snap.keys()) == {f.name for f in dataclasses.fields(ContrastEpisodeRecord)}

    # 9. WiringLogEntry
    wlog = WiringLogEntry(
        event_clock=10, owner_cell_id=1, slot_index=2, old_target_id=None, new_target_id=3, reason="TEST"
    )
    wlog_snap = _snapshot_wiring_log_entry(wlog)
    assert set(wlog_snap.keys()) == {f.name for f in dataclasses.fields(WiringLogEntry)}

    # 10. LedgerCandidateRow
    env = PeripheralSurfaceEnvelopeV1(
        raw_surface_nfc_utf8="test", surface_sha256=b"s", feature_bundle_digest=b"d",
        canonical_features_copy=(("f", "1.0"),), marker=Marker.NONE,
    )
    row = LedgerCandidateRow(
        assembly_id=1, structural_generation=1, surface_utf8_nfc="test", marker=Marker.NONE,
        surface_sha256=b"s", feature_bundle_digest=b"d", envelope=env,
    )
    row_snap = _snapshot_ledger_candidate_row(row)
    assert set(row_snap.keys()) == {f.name for f in dataclasses.fields(LedgerCandidateRow)}


def test_canonical_enum_and_primitive_type_separation():
    """Verify that canonical_state_digest differentiates enum types from generic int and str (Section 4).

    Asserts that:
    - IntEnum (SynapseScope.LOCAL) does NOT collapse into generic int (0)
    - StrEnum (ExecutionMode.LEARN) does NOT collapse into generic str ("LEARN")
    - bool (True/False) does NOT collapse into int (1/0)
    - int (1) does NOT collapse into float (1.0)
    - str ("0") does NOT collapse into bytes (b"0")
    """
    cases = [
        (False, b"B0;"),
        (True, b"B1;"),
        (0, b"I:0;"),
        (1, b"I:1;"),
        (0.0, b"F:0x0.0p+0;"),
        (1.0, b"F:0x1.0000000000000p+0;"),
        (SynapseScope.LOCAL, b"E:SynapseScope:0;"),
        (SynapseScope.ASSOCIATIVE, b"E:SynapseScope:2;"),
        ("0", b"S:1:0;"),
        (b"0", b"X:1:0;"),
        (ExecutionMode.LEARN, b"E:ExecutionMode:LEARN;"),
        ("LEARN", b"S:5:LEARN;"),
    ]

    digests = []
    for val, expected in cases:
        d = canonical_state_digest(val)
        assert d == expected, f"Mismatch for {val}: expected {expected}, got {d}"
        digests.append(d)

    # Assert all 12 cases produce strictly distinct byte strings
    assert len(digests) == len(set(digests)), "Collision detected between distinct Python types in canonical digest!"


def test_synapse_mutation_sensitivity_adversarial():
    """Adversarial verification proving that snapshot and SHA-256 state hashing detect mutations (Correction V04).

    Mutates previously omitted Synapse fields:
    - last_evidence_root
    - candidate_deadline
    - internally_supported
    - created_event_id
    - created_exposure_id
    - last_external_event_id
    Asserts that in every case:
    1. Structural snapshot comparison detects the mutation (snapshot_mut != snapshot_base)
    2. SHA-256 state digest changes (hash_mut != hash_base)
    3. Restoring the original state restores exact snapshot and SHA-256 equality
    """
    state, _, _, _ = _build_rich_test_state()
    syn_key = next(iter(state.W.synapses.keys()))
    syn = state.W.synapses[syn_key]

    snap_base = snapshot_w(state.W)
    hash_base = hash_state_snapshot(snap_base)

    # 1. Mutate last_evidence_root
    orig_root = syn.last_evidence_root
    syn.last_evidence_root = orig_root + 99
    snap_mut1 = snapshot_w(state.W)
    hash_mut1 = hash_state_snapshot(snap_mut1)
    assert snap_mut1 != snap_base, "Snapshot failed to detect last_evidence_root mutation!"
    assert hash_mut1 != hash_base, "SHA-256 failed to detect last_evidence_root mutation!"
    syn.last_evidence_root = orig_root
    assert snapshot_w(state.W) == snap_base
    assert hash_state_snapshot(snapshot_w(state.W)) == hash_base

    # 2. Mutate candidate_deadline
    orig_deadline = syn.candidate_deadline
    syn.candidate_deadline = orig_deadline + 500
    snap_mut2 = snapshot_w(state.W)
    hash_mut2 = hash_state_snapshot(snap_mut2)
    assert snap_mut2 != snap_base, "Snapshot failed to detect candidate_deadline mutation!"
    assert hash_mut2 != hash_base, "SHA-256 failed to detect candidate_deadline mutation!"
    syn.candidate_deadline = orig_deadline
    assert snapshot_w(state.W) == snap_base
    assert hash_state_snapshot(snapshot_w(state.W)) == hash_base

    # 3. Mutate internally_supported
    orig_supp = syn.internally_supported
    syn.internally_supported = not orig_supp
    snap_mut3 = snapshot_w(state.W)
    hash_mut3 = hash_state_snapshot(snap_mut3)
    assert snap_mut3 != snap_base, "Snapshot failed to detect internally_supported mutation!"
    assert hash_mut3 != hash_base, "SHA-256 failed to detect internally_supported mutation!"
    syn.internally_supported = orig_supp
    assert snapshot_w(state.W) == snap_base
    assert hash_state_snapshot(snapshot_w(state.W)) == hash_base

    # 4. Mutate created_event_id
    orig_ev = syn.created_event_id
    syn.created_event_id = orig_ev + 17
    snap_mut4 = snapshot_w(state.W)
    hash_mut4 = hash_state_snapshot(snap_mut4)
    assert snap_mut4 != snap_base, "Snapshot failed to detect created_event_id mutation!"
    assert hash_mut4 != hash_base, "SHA-256 failed to detect created_event_id mutation!"
    syn.created_event_id = orig_ev
    assert snapshot_w(state.W) == snap_base
    assert hash_state_snapshot(snapshot_w(state.W)) == hash_base

    # 5. Mutate created_exposure_id
    orig_exp = syn.created_exposure_id
    syn.created_exposure_id = orig_exp + 33
    snap_mut5 = snapshot_w(state.W)
    hash_mut5 = hash_state_snapshot(snap_mut5)
    assert snap_mut5 != snap_base, "Snapshot failed to detect created_exposure_id mutation!"
    assert hash_mut5 != hash_base, "SHA-256 failed to detect created_exposure_id mutation!"
    syn.created_exposure_id = orig_exp
    assert snapshot_w(state.W) == snap_base
    assert hash_state_snapshot(snapshot_w(state.W)) == hash_base

    # 6. Mutate last_external_event_id
    orig_last_ev = syn.last_external_event_id
    syn.last_external_event_id = orig_last_ev + 11
    snap_mut6 = snapshot_w(state.W)
    hash_mut6 = hash_state_snapshot(snap_mut6)
    assert snap_mut6 != snap_base, "Snapshot failed to detect last_external_event_id mutation!"
    assert hash_mut6 != hash_base, "SHA-256 failed to detect last_external_event_id mutation!"
    syn.last_external_event_id = orig_last_ev
    assert snapshot_w(state.W) == snap_base
    assert hash_state_snapshot(snapshot_w(state.W)) == hash_base


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
