"""Scientific Acceptance and Legacy Regression Reconciliation Test Suite for R2-B03-C01/C02.

Covers:
- C01-S01: Automated Eagle Generation Proof (1-event & 2-event prompts, exact winner, generation, scores, margin, EOS).
- C01-S02: Real Post-Merge Attestation Proof (Ledger candidate rows for Asm 5 at Gen 8, confirmed roots [11..56], no leak from 6).
- C01-S03: Read-Only Generation & Retrieval Integrity (Full snapshot preservation of W, H_slow, R, Ledger, PublicationView).
- C01-S04: Post-Assembly Pre-Publication Fault (FP_02 shadow consolidation verified via hook, zero publication leak).
- C02-S02: Non-Empty FP_03 Outbox Test (Real deferred batch, idempotent reconciliation, non-mutating WState).
- C02-S05: Non-Identical MERGE Differential (Frozen baseline compiled directly from git faf361b vs patched code, full snapshot_w parity).
- C02-S03: Complete Transaction Publication Snapshot & Full State Determinism (Dual independent runs, 100% digest match across all partitions).
"""

from __future__ import annotations

import dataclasses
import hashlib
import subprocess
import types
from typing import Any
import pytest

from dgca.common.errors import StatusCode
from dgca.common.hashing import Region
from dgca.core.anatomy import Synapse, SynapseKey, SynapseScope, SynapseState
import dgca.core.assembly as asm_module
from dgca.core.assembly import (
    AssemblyEndReport,
    K_MAX,
    M_MAX,
    THETA_A,
    THETA_MERGE,
    THETA_OB,
    T_C_COOLDOWN,
    _try_merge_pair,
    _is_in_merge_split_cooldown,
    compute_mutual_support_r_b,
    _live_assembly_ids_for_cell,
    check_maintain_keep_guards,
    _rebuild_assemblies_by_member,
)
from dgca.core.generator import generate_episode
from dgca.core.readout import M_READ
from dgca.core.state import (
    Assembly,
    AssemblyStatus,
    HSlowState,
    MachineState,
    RState,
    WState,
)
from dgca.encoder.envelope import (
    CoreEventPayloadV1,
    Marker,
    PeripheralSurfaceEnvelopeV1,
    encode_exposure,
)
from dgca.lifecycle.exposure_tx import (
    EndExposureReport,
    ExposureStatus,
    ExposureTransactionManager,
    TransactionPublicationView,
    run_read_only_episode,
)
from dgca.peripheral.outbox import OutboxNotificationV1
from dgca.peripheral.readout_ledger import (
    LedgerCandidateRow,
    SurfaceReadoutLedgerV1,
)

# Reuse authoritative snapshot utilities from acceptance baseline
from tests.test_r2_a01_patch2_acceptance import (
    snapshot_w,
    snapshot_h_slow,
    snapshot_r,
    snapshot_ledger,
    hash_state_snapshot,
)


# ---------------------------------------------------------------------------
# Dynamic compilation of frozen baseline _try_merge_pair from git tree
# ---------------------------------------------------------------------------
_FROZEN_GIT_COMMIT = "faf361b6b95de6287b466eb1dc524ea49c732635"

def _load_frozen_baseline_try_merge() -> Any:
    """Retrieve and compile _try_merge_pair directly from the frozen production baseline commit."""
    frozen_src = subprocess.check_output(
        ["git", "show", f"{_FROZEN_GIT_COMMIT}:src/dgca/core/assembly.py"],
        text=True,
        encoding="utf-8",
    )
    frozen_mod = types.ModuleType("frozen_assembly_baseline")
    frozen_mod.__dict__.update(asm_module.__dict__)
    exec(compile(frozen_src, f"<git_show_{_FROZEN_GIT_COMMIT}>", "exec"), frozen_mod.__dict__)
    return frozen_mod._try_merge_pair

_baseline_try_merge_pair = _load_frozen_baseline_try_merge()


# ---------------------------------------------------------------------------
# Comprehensive TransactionPublicationView Snapshot Serializer (C02-S03)
# ---------------------------------------------------------------------------

def _snapshot_outbox_notification(n: OutboxNotificationV1) -> dict[str, Any]:
    """Capture authoritative stored fields of an OutboxNotificationV1."""
    return {
        "root_id": n.root_id,
        "event_order": n.event_order,
        "assembly_id": n.assembly_id,
        "structural_generation": n.structural_generation,
        "surface_sha256": n.surface_sha256,
        "feature_bundle_digest": n.feature_bundle_digest,
        "marker": n.marker,
        "raw_surface": n.envelope.raw_surface_nfc_utf8 if n.envelope else None,
    }


def _snapshot_assembly_report(r: AssemblyEndReport | None) -> dict[str, Any] | None:
    """Capture authoritative stored fields of an AssemblyEndReport."""
    if r is None:
        return None
    return {
        "maintained_ids": tuple(r.maintained_ids),
        "archived_by_maintain_ids": tuple(r.archived_by_maintain_ids),
        "grown_ids": tuple(r.grown_ids),
        "formed_ids": tuple(r.formed_ids),
        "merged_pairs": tuple(r.merged_pairs),
        "split_pairs": tuple(r.split_pairs),
        "diagnostics": tuple(r.diagnostics),
    }


def _snapshot_end_exposure_report(rep: EndExposureReport) -> dict[str, Any]:
    """Capture 100% of declared fields of an EndExposureReport."""
    return {
        "exposure_id": rep.exposure_id,
        "status": rep.status,
        "events_processed": rep.events_processed,
        "proposal_outcomes_count": len(rep.proposal_outcomes),
        "pruned_synapses": tuple(sorted(rep.pruned_synapses)),
        "last_event_remaining_k_r": rep.last_event_remaining_k_r,
        "diagnostics": tuple(rep.diagnostics),
        "candidate_settlements_count": len(rep.candidate_settlements),
        "recruitments_count": len(rep.recruitments),
        "assembly_report": _snapshot_assembly_report(rep.assembly_report),
        "outbox_notifications": tuple(_snapshot_outbox_notification(n) for n in rep.outbox_notifications),
    }


def snapshot_publication_view(pv: TransactionPublicationView) -> dict[str, Any]:
    """Capture comprehensive snapshot of TransactionPublicationView."""
    return {
        "w_snapshot": snapshot_w(pv.W),
        "completed_roots": {
            rid: _snapshot_end_exposure_report(rep)
            for rid, rep in sorted(pv.completed_roots.items())
        },
        "pending_outbox_by_root": {
            rid: tuple(_snapshot_outbox_notification(n) for n in notifs)
            for rid, notifs in sorted(pv.pending_outbox_by_root.items())
        },
        "completed_roots_high_watermark": pv.completed_roots_high_watermark,
        "active_exposure_id": pv.active_exposure_id,
    }


# ---------------------------------------------------------------------------
# Training and Test Helpers
# ---------------------------------------------------------------------------

def _train_56_root_curriculum(
    tx: ExposureTransactionManager,
) -> tuple[list[Any], list[Any]]:
    """Train complete 56-root curriculum alternating between Cat and Eagle."""
    branch_cat = encode_exposure("القط يشرب حليب", append_eos=True)
    branch_eagle = encode_exposure("النسر يشرب ماء", append_eos=True)

    for root_id in range(1, 57):
        branch = branch_cat if (root_id % 2 == 1) else branch_eagle
        tx.begin_exposure(root_id)
        for env in branch:
            core_ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        tx.end_exposure(root_id)

    return branch_cat, branch_eagle


def _wire_reciprocal_pair(
    state: MachineState,
    u: int,
    v: int,
    *,
    s_val: float = 0.85,
    e_ext: float = 6.0,
) -> None:
    """Wire bidirectional CONSOLIDATED LOCAL links between u and v in LANGUAGE region."""
    state.W.commit_cell(u, 0)
    state.W.commit_cell(v, 0)
    if not state.W.latent_table.is_eligible(u, v):
        try:
            state.W.latent_table.admit_or_recycle_coactive_partner(
                u,
                v,
                event_clock=0,
                protected_bidirectional_neighbors=state.W.get_protected_bidirectional_neighbors(u),
            )
        except Exception:
            state.W.latent_table.admit_or_recycle_coactive_partner(
                v,
                u,
                event_clock=0,
                protected_bidirectional_neighbors=state.W.get_protected_bidirectional_neighbors(v),
            )

    for src, tgt in ((u, v), (v, u)):
        syn = Synapse(
            key=(src, tgt, SynapseScope.LOCAL),
            state=SynapseState.CONSOLIDATED,
            S=s_val,
            E_ext=e_ext,
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


# ==============================================================================
# C01-S01: Automated Eagle Generation Proof
# ==============================================================================

def test_c01_s01_eagle_generation_proof() -> None:
    """C01-S01: Automated Eagle Generation Proof on genuine 56-root trained state."""
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
    )

    branch_cat, branch_eagle = _train_56_root_curriculum(tx)

    # 1. Cat 1-event prompt rollout: ['القط'] -> ('يشرب', 'حليب') -> GEN_STOP_EOS
    prompt_cat1 = [branch_cat[0].core_event]
    gen_cat1 = generate_episode(state, prompt_cat1, ledger, max_steps=5)
    assert gen_cat1.emitted_surfaces == ("يشرب", "حليب")
    assert gen_cat1.stop_status == StatusCode.GEN_STOP_EOS

    # 2. Cat 2-event prompt rollout: ['القط', 'يشرب'] -> ('حليب',) -> GEN_STOP_EOS
    prompt_cat2 = [branch_cat[0].core_event, branch_cat[1].core_event]
    gen_cat2 = generate_episode(state, prompt_cat2, ledger, max_steps=5)
    assert gen_cat2.emitted_surfaces == ("حليب",)
    assert gen_cat2.stop_status == StatusCode.GEN_STOP_EOS

    # 3. Eagle 1-event prompt rollout: ['النسر'] -> ('يشرب', 'ماء') -> GEN_STOP_EOS
    prompt_eagle1 = [branch_eagle[0].core_event]
    gen_eagle1 = generate_episode(state, prompt_eagle1, ledger, max_steps=5)
    assert gen_eagle1.emitted_surfaces == ("يشرب", "ماء")
    assert gen_eagle1.stop_status == StatusCode.GEN_STOP_EOS

    # 4. Eagle 2-event prompt rollout: ['النسر', 'يشرب'] -> ('ماء',) -> GEN_STOP_EOS
    prompt_eagle2 = [branch_eagle[0].core_event, branch_eagle[1].core_event]
    gen_eagle2 = generate_episode(state, prompt_eagle2, ledger, max_steps=5)
    assert gen_eagle2.emitted_surfaces == ("ماء",)
    assert gen_eagle2.stop_status == StatusCode.GEN_STOP_EOS

    # 5. Precise runtime assertions on Eagle Step 2 (EOS step)
    step2 = gen_eagle1.steps[2]
    assert step2.winner_assembly_id == 5, f"Expected winner Asm 5, got {step2.winner_assembly_id}"
    assert step2.winner_generation == 8, f"Expected winner Gen 8, got {step2.winner_generation}"

    res = step2.readout_result
    assert res.winner_assembly_id == 5
    assert res.winner_generation == 8
    assert abs(res.top_score - 0.20694424313392146) < 1e-9
    assert abs(res.second_score - 0.09358942151495935) < 1e-9
    assert abs(res.margin - 0.11335482161896211) < 1e-9
    assert res.margin >= M_READ, f"Margin {res.margin} < M_READ {M_READ}"

    assert step2.ledger_resolution.status == StatusCode.OK
    assert step2.emitted_envelope is not None
    assert step2.emitted_envelope.marker == Marker.EOS
    assert step2.emitted_envelope.raw_surface_nfc_utf8 == "<EOS>"


# ==============================================================================
# C01-S02: Real Post-Merge Attestation Proof
# ==============================================================================

def test_c01_s02_real_post_merge_attestation_proof() -> None:
    """C01-S02: Inspect real Ledger produced by 56-root training run for Assembly 5 at Gen 8."""
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
    )

    _train_56_root_curriculum(tx)

    # 1. Assembly 5 at final structural generation 8 has exactly 1 candidate row
    candidate_rows = ledger.get_candidate_rows(5, 8)
    assert len(candidate_rows) == 1, f"Expected 1 candidate row, got {len(candidate_rows)}"
    row = candidate_rows[0]

    # 2. Verified confirmed_roots
    confirmed_roots = sorted(row.confirmed_roots)
    assert len(confirmed_roots) == 46, f"Expected 46 confirmed roots, got {len(confirmed_roots)}"
    first_root = confirmed_roots[0]
    second_root = confirmed_roots[1]
    assert first_root == 11, f"Expected first qualifying root 11, got {first_root}"
    assert second_root == 12, f"Expected second qualifying root 12, got {second_root}"
    assert confirmed_roots == list(range(11, 57))

    # 3. Surface, marker, and feature bundle match
    assert row.surface_utf8_nfc == "<EOS>"
    assert row.marker == Marker.EOS
    assert row.envelope.raw_surface_nfc_utf8 == "<EOS>"
    assert row.envelope.marker == Marker.EOS
    assert len(row.feature_bundle_digest) == 32

    # 4. No conflicting unresolved candidate rows
    resolution = ledger.resolve_readout(5, 8, current_live_generation=8)
    assert resolution.status == StatusCode.OK
    assert resolution.external_count == 46

    # 5. Old generation evidence is NOT transferred to Gen 8
    assert len(ledger.get_candidate_rows(5, 1)) == 0
    assert len(ledger.get_candidate_rows(5, 7)) == 0
    res_old = ledger.resolve_readout(5, 1, current_live_generation=8)
    assert res_old.status == StatusCode.GEN_STOP_STALE_ASSEMBLY

    # 6. Archived Assembly 6 provided zero evidence after archival (no candidate rows)
    for gen in range(1, 15):
        assert len(ledger.get_candidate_rows(6, gen)) == 0


# ==============================================================================
# C01-S03 & C02-S04: Read-Only Generation & Retrieval Integrity
# ==============================================================================

def test_c01_s03_read_only_generation_integrity() -> None:
    """C01-S03 & C02-S04: Snapshot verification of complete state immutability during generation & retrieval."""
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
    )

    branch_cat, branch_eagle = _train_56_root_curriculum(tx)

    # Capture complete pre-rollout snapshots
    w_snap_pre_cat = snapshot_w(state.W)
    h_snap_pre_cat = snapshot_h_slow(state.H_slow)
    r_snap_pre_cat = snapshot_r(state.R)
    ledger_snap_pre_cat = snapshot_ledger(ledger)
    pv_snap_pre = snapshot_publication_view(tx._publication_view)

    hash_w_pre_cat = hash_state_snapshot(w_snap_pre_cat)
    hash_h_pre_cat = hash_state_snapshot(h_snap_pre_cat)
    hash_r_pre_cat = hash_state_snapshot(r_snap_pre_cat)
    hash_l_pre_cat = hash_state_snapshot(ledger_snap_pre_cat)
    hash_pv_pre = hash_state_snapshot(pv_snap_pre)

    # 1. Cat rollout
    prompt_cat = [branch_cat[0].core_event]
    gen_cat = generate_episode(state, prompt_cat, ledger, max_steps=5)
    assert gen_cat.stop_status == StatusCode.GEN_STOP_EOS

    assert snapshot_w(state.W) == w_snap_pre_cat, "WState mutated during Cat generate_episode!"
    assert snapshot_h_slow(state.H_slow) == h_snap_pre_cat, "HSlowState mutated during Cat generate_episode!"
    assert snapshot_r(state.R) == r_snap_pre_cat, "Caller RState mutated during Cat generate_episode!"
    assert snapshot_ledger(ledger) == ledger_snap_pre_cat, "Ledger mutated during Cat generate_episode!"

    assert hash_state_snapshot(snapshot_w(state.W)) == hash_w_pre_cat
    assert hash_state_snapshot(snapshot_h_slow(state.H_slow)) == hash_h_pre_cat
    assert hash_state_snapshot(snapshot_r(state.R)) == hash_r_pre_cat
    assert hash_state_snapshot(snapshot_ledger(ledger)) == hash_l_pre_cat
    assert ledger._processed_outbox_keys == ledger_snap_pre_cat["_processed_outbox_keys"]

    # 2. Eagle rollout
    w_snap_pre_eagle = snapshot_w(state.W)
    h_snap_pre_eagle = snapshot_h_slow(state.H_slow)
    r_snap_pre_eagle = snapshot_r(state.R)
    ledger_snap_pre_eagle = snapshot_ledger(ledger)

    hash_w_pre_eagle = hash_state_snapshot(w_snap_pre_eagle)
    hash_h_pre_eagle = hash_state_snapshot(h_snap_pre_eagle)
    hash_r_pre_eagle = hash_state_snapshot(r_snap_pre_eagle)
    hash_l_pre_eagle = hash_state_snapshot(ledger_snap_pre_eagle)

    prompt_eagle = [branch_eagle[0].core_event]
    gen_eagle = generate_episode(state, prompt_eagle, ledger, max_steps=5)
    assert gen_eagle.stop_status == StatusCode.GEN_STOP_EOS

    assert snapshot_w(state.W) == w_snap_pre_eagle, "WState mutated during Eagle generate_episode!"
    assert snapshot_h_slow(state.H_slow) == h_snap_pre_eagle, "HSlowState mutated during Eagle generate_episode!"
    assert snapshot_r(state.R) == r_snap_pre_eagle, "Caller RState mutated during Eagle generate_episode!"
    assert snapshot_ledger(ledger) == ledger_snap_pre_eagle, "Ledger mutated during Eagle generate_episode!"

    assert hash_state_snapshot(snapshot_w(state.W)) == hash_w_pre_eagle
    assert hash_state_snapshot(snapshot_h_slow(state.H_slow)) == hash_h_pre_eagle
    assert hash_state_snapshot(snapshot_r(state.R)) == hash_r_pre_eagle
    assert hash_state_snapshot(snapshot_ledger(ledger)) == hash_l_pre_eagle

    # 3. Read-only retrieval (C02-S04)
    w_snap_pre_ro = snapshot_w(state.W)
    h_snap_pre_ro = snapshot_h_slow(state.H_slow)
    r_snap_pre_ro = snapshot_r(state.R)
    l_snap_pre_ro = snapshot_ledger(ledger)
    pv_snap_pre_ro = snapshot_publication_view(tx._publication_view)

    hash_w_pre_ro = hash_state_snapshot(w_snap_pre_ro)
    hash_h_pre_ro = hash_state_snapshot(h_snap_pre_ro)
    hash_r_pre_ro = hash_state_snapshot(r_snap_pre_ro)
    hash_l_pre_ro = hash_state_snapshot(l_snap_pre_ro)
    hash_pv_pre_ro = hash_state_snapshot(pv_snap_pre_ro)

    ro_summary = run_read_only_episode(state, [branch_cat[0].core_event, branch_cat[1].core_event])
    assert len(ro_summary.event_results) == 2

    assert snapshot_w(state.W) == w_snap_pre_ro, "WState mutated during RETRIEVE!"
    assert snapshot_h_slow(state.H_slow) == h_snap_pre_ro, "HSlowState mutated during RETRIEVE!"
    assert snapshot_r(state.R) == r_snap_pre_ro, "Caller RState mutated during RETRIEVE!"
    assert snapshot_ledger(ledger) == l_snap_pre_ro, "Ledger mutated during RETRIEVE!"
    assert snapshot_publication_view(tx._publication_view) == pv_snap_pre_ro, "PublicationView mutated during RETRIEVE!"

    assert hash_state_snapshot(snapshot_w(state.W)) == hash_w_pre_ro
    assert hash_state_snapshot(snapshot_h_slow(state.H_slow)) == hash_h_pre_ro
    assert hash_state_snapshot(snapshot_r(state.R)) == hash_r_pre_ro
    assert hash_state_snapshot(snapshot_ledger(ledger)) == hash_l_pre_ro
    assert hash_state_snapshot(snapshot_publication_view(tx._publication_view)) == hash_pv_pre_ro


# ==============================================================================
# C01-S04 & C02-S02: Post-Assembly Pre-Publication Fault & Non-Empty FP_03
# ==============================================================================

def test_c01_s04_post_assembly_pre_publication_fault_fp02() -> None:
    """C01-S04: Verify FP_02 post-assembly pre-publication failure containment."""
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
    )

    branch_cat = encode_exposure("القط يشرب حليب", append_eos=True)
    branch_eagle = encode_exposure("النسر يشرب ماء", append_eos=True)

    # Train roots 1-8
    for r in range(1, 9):
        b = branch_cat if (r % 2 == 1) else branch_eagle
        tx.begin_exposure(r)
        for env in b:
            core_ev = dataclasses.replace(env.core_event, exposure_id=r)
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        tx.end_exposure(r)

    pre_asms = {
        aid: (a.status, a.structural_generation, a.member_cell_ids)
        for aid, a in state.W.assemblies.items()
    }
    assert pre_asms[5] == (AssemblyStatus.LIVE, 1, (8834, 9209, 10570))
    assert pre_asms[6] == (AssemblyStatus.LIVE, 1, (10646, 10915, 11153))

    # Register an end_exposure hook to verify that shadow consolidation occurred
    shadow_consolidation_verified = False

    def _verify_shadow_consolidation(w_pre, w_shadow, h_slow, journal, diags):
        nonlocal shadow_consolidation_verified
        # In w_shadow, Asm 5 and 6 have grown and merged
        assert w_shadow.assemblies[5].status == AssemblyStatus.LIVE
        assert w_shadow.assemblies[5].structural_generation == 7
        assert w_shadow.assemblies[6].status == AssemblyStatus.ARCHIVED
        assert w_shadow.assemblies[6].structural_generation == 7
        shadow_consolidation_verified = True

    tx.register_end_exposure_hook(_verify_shadow_consolidation)

    # Begin Root 9
    tx.begin_exposure(9)
    for env in branch_cat:
        core_ev = dataclasses.replace(env.core_event, exposure_id=9)
        tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)

    # Injected fault at FP_02
    tx._fault_injection_point = "FP_02"

    with pytest.raises(RuntimeError, match="Injected fault at FP-02"):
        tx.end_exposure(9)

    # Verify shadow consolidation did indeed run before failure
    assert shadow_consolidation_verified is True, "Shadow consolidation hook never fired!"

    # Active W retains pre-publication Assembly identities and generations
    post_asms = {
        aid: (a.status, a.structural_generation, a.member_cell_ids)
        for aid, a in state.W.assemblies.items()
    }
    assert pre_asms == post_asms, "Active WState assemblies mutated despite FP_02 failure!"
    assert state.W.assemblies[5].structural_generation == 1
    assert state.W.assemblies[6].status == AssemblyStatus.LIVE
    assert state.W.assemblies[6].structural_generation == 1

    # No outbox evidence published from aborted consolidation
    assert 9 not in tx._publication_view.pending_outbox_by_root
    assert 9 not in tx._publication_view.completed_roots
    assert state.W.completed_roots_high_watermark == 8


def test_c02_s02_non_empty_fp03_outbox_delivery() -> None:
    """C02-S02: Non-empty FP_03 outbox delivery, deferred batch staging, and idempotent reconciliation."""
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
    )

    branch_cat = encode_exposure("القط يشرب حليب", append_eos=True)
    branch_eagle = encode_exposure("النسر يشرب ماء", append_eos=True)

    # Train roots 1-10 normally so pre-existing LIVE assemblies exist with stable generations
    for r in range(1, 11):
        b = branch_cat if (r % 2 == 1) else branch_eagle
        tx.begin_exposure(r)
        for env in b:
            core_ev = dataclasses.replace(env.core_event, exposure_id=r)
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        tx.end_exposure(r)

    # Pre-checks before Root 11: Assembly 5 is LIVE at Gen 8, has 0 ledger candidate rows
    assert state.W.assemblies[5].status == AssemblyStatus.LIVE
    assert state.W.assemblies[5].structural_generation == 8
    assert len(ledger.get_candidate_rows(5, 8)) == 0

    # Begin Root 11 (Cat: exposes <EOS>)
    tx.begin_exposure(11)
    for env in branch_cat:
        core_ev = dataclasses.replace(env.core_event, exposure_id=11)
        tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)

    # Inject FP_03: post-commit peripheral dispatch deferred
    tx._fault_injection_point = "FP_03"
    report = tx.end_exposure(11)

    # 1. Atomic END_EXPOSURE commit succeeds
    assert report.status == ExposureStatus.COMPLETED

    # 2. Completed root is durable
    assert 11 in tx.completed_roots
    assert 11 in tx._publication_view.completed_roots

    # 3. Publication watermark advances
    assert tx._publication_view.completed_roots_high_watermark == 11
    assert tx.state.W.completed_roots_high_watermark == 11

    # 4. Pending Outbox contains a NON-EMPTY batch (must fail if empty)
    pending_batch = tx._publication_view.pending_outbox_by_root.get(11)
    assert pending_batch is not None, "Pending outbox missing root 11!"
    assert len(pending_batch) > 0, "Pending outbox batch for root 11 is empty!"
    assert len(pending_batch) == 5, f"Expected 5 notifications, got {len(pending_batch)}"

    # 5. Deferred batch is NOT consumed prematurely by ledger
    assert len(ledger.get_candidate_rows(5, 8)) == 0, "Ledger consumed deferred batch prematurely!"

    # Snapshot WState before reconcile to verify immutability
    w_snap_pre_reconcile = snapshot_w(state.W)

    # 6. reconcile_outbox() delivers the genuine batch
    reconciled_count = tx.reconcile_outbox()
    assert reconciled_count == 5, f"Expected 5 reconciled notifications, got {reconciled_count}"

    # 7. Pending entries are cleared only after acknowledgement
    assert 11 not in tx._publication_view.pending_outbox_by_root

    # 8. Repeated reconciliation is idempotent
    reconciled_again = tx.reconcile_outbox()
    assert reconciled_again == 0, f"Expected 0 on idempotent retry, got {reconciled_again}"

    # 9. No duplicate Ledger confirmations appear
    rows_after = ledger.get_candidate_rows(5, 8)
    assert len(rows_after) == 1, f"Expected 1 candidate row, got {len(rows_after)}"
    assert rows_after[0].confirmed_roots == {11}

    # 10. WState remains unchanged during peripheral reconciliation
    w_snap_post_reconcile = snapshot_w(state.W)
    assert w_snap_post_reconcile == w_snap_pre_reconcile, "WState mutated during outbox reconciliation!"


# ==============================================================================
# C01-S05 & C02-S05: Non-Identical MERGE Differential
# ==============================================================================

def test_c01_s05_non_identical_merge_differential() -> None:
    """C01-S05 & C02-S05: Differential execution of frozen baseline vs patched MERGE across all 8 non-identical cases."""

    def _run_differential_case(
        setup_fn,
        case_name: str,
        expected_decision: bool,
    ) -> None:
        state_base = MachineState()
        setup_fn(state_base)
        state_patch = MachineState()
        setup_fn(state_patch)

        n_cache_base: dict[int, dict[int, float]] = {}
        n_cache_patch: dict[int, dict[int, float]] = {}

        res_base = _baseline_try_merge_pair(1, 2, state_base.W, n_cache_base)
        res_patch = _try_merge_pair(1, 2, state_patch.W, n_cache_patch)

        assert res_base == expected_decision, f"[{case_name}] Baseline unexpected decision: {res_base}"
        assert res_patch == expected_decision, f"[{case_name}] Patched unexpected decision: {res_patch}"
        assert res_base == res_patch, f"[{case_name}] Differential decision mismatch: base={res_base}, patch={res_patch}"

        # Compare resulting assembly states
        asm_a_base = state_base.W.assemblies[1]
        asm_a_patch = state_patch.W.assemblies[1]
        asm_b_base = state_base.W.assemblies[2]
        asm_b_patch = state_patch.W.assemblies[2]

        assert asm_a_base.status == asm_a_patch.status
        assert asm_a_base.structural_generation == asm_a_patch.structural_generation
        assert asm_a_base.member_cell_ids == asm_a_patch.member_cell_ids
        assert asm_a_base.last_mutation_close_serial == asm_a_patch.last_mutation_close_serial
        assert asm_a_base.last_merge_split_close_serial == asm_a_patch.last_merge_split_close_serial

        assert asm_b_base.status == asm_b_patch.status
        assert asm_b_base.structural_generation == asm_b_patch.structural_generation
        assert asm_b_base.member_cell_ids == asm_b_patch.member_cell_ids
        assert asm_b_base.last_mutation_close_serial == asm_b_patch.last_mutation_close_serial
        assert asm_b_base.last_merge_split_close_serial == asm_b_patch.last_merge_split_close_serial

        assert state_base.W.assemblies_by_member == state_patch.W.assemblies_by_member

        # Complete WState snapshot and cryptographic digest equality
        snap_base = snapshot_w(state_base.W)
        snap_patch = snapshot_w(state_patch.W)
        assert snap_base == snap_patch, f"[{case_name}] WState deep snapshot mismatch!"
        assert hash_state_snapshot(snap_base) == hash_state_snapshot(snap_patch)

    # 1. Eligible partial-overlap merge (J = 8/10 = 0.80 >= 0.70, mutual link between c8 and c9)
    def _case_1_eligible_partial(state: MachineState) -> None:
        c = tuple(range(8200, 8280, 8))[:10]
        shared = c[:8]
        c8, c9 = c[8], c[9]
        for u in shared:
            for v in shared:
                if u < v:
                    _wire_reciprocal_pair(state, u, v, s_val=0.85, e_ext=6.0)
        for m in c[:3]:
            _wire_reciprocal_pair(state, c8, m, s_val=0.85, e_ext=6.0)
        for m in c[3:6]:
            _wire_reciprocal_pair(state, c9, m, s_val=0.85, e_ext=6.0)
        _wire_reciprocal_pair(state, c8, c9, s_val=0.85, e_ext=6.0)

        state.W.assemblies[1] = Assembly(assembly_id=1, region=Region.LANGUAGE, member_cell_ids=(*shared, c8), status=AssemblyStatus.LIVE, structural_generation=1)
        state.W.assemblies[2] = Assembly(assembly_id=2, region=Region.LANGUAGE, member_cell_ids=(*shared, c9), status=AssemblyStatus.LIVE, structural_generation=1)
        _rebuild_assemblies_by_member(state.W)

    _run_differential_case(_case_1_eligible_partial, "Case 1: Eligible Partial-Overlap", expected_decision=True)

    # 2. Weak exclusive support (J = 8/10 = 0.80, but mutual link between c8 and c9 has S=0.20 < 0.60)
    def _case_2_weak_support(state: MachineState) -> None:
        c = tuple(range(8200, 8280, 8))[:10]
        shared = c[:8]
        c8, c9 = c[8], c[9]
        for u in shared:
            for v in shared:
                if u < v:
                    _wire_reciprocal_pair(state, u, v, s_val=0.85, e_ext=6.0)
        for m in c[:3]:
            _wire_reciprocal_pair(state, c8, m, s_val=0.85, e_ext=6.0)
        for m in c[3:6]:
            _wire_reciprocal_pair(state, c9, m, s_val=0.85, e_ext=6.0)
        _wire_reciprocal_pair(state, c8, c9, s_val=0.20, e_ext=1.0)

        state.W.assemblies[1] = Assembly(assembly_id=1, region=Region.LANGUAGE, member_cell_ids=(*shared, c8), status=AssemblyStatus.LIVE, structural_generation=1)
        state.W.assemblies[2] = Assembly(assembly_id=2, region=Region.LANGUAGE, member_cell_ids=(*shared, c9), status=AssemblyStatus.LIVE, structural_generation=1)
        _rebuild_assemblies_by_member(state.W)

    _run_differential_case(_case_2_weak_support, "Case 2: Weak Exclusive Support", expected_decision=False)

    # 3. Proper subset (A subset B, |A|=4, |B|=5)
    def _case_3_proper_subset(state: MachineState) -> None:
        c = tuple(range(8200, 8240, 8))[:5]
        for cid in c:
            state.W.commit_cell(cid, 0)
        state.W.assemblies[1] = Assembly(assembly_id=1, region=Region.LANGUAGE, member_cell_ids=c[:4], status=AssemblyStatus.LIVE, structural_generation=1)
        state.W.assemblies[2] = Assembly(assembly_id=2, region=Region.LANGUAGE, member_cell_ids=c, status=AssemblyStatus.LIVE, structural_generation=1)
        _rebuild_assemblies_by_member(state.W)

    _run_differential_case(_case_3_proper_subset, "Case 3: Proper Subset", expected_decision=False)

    # 4. Proper superset (B subset A, |A|=5, |B|=4)
    def _case_4_proper_superset(state: MachineState) -> None:
        c = tuple(range(8200, 8240, 8))[:5]
        for cid in c:
            state.W.commit_cell(cid, 0)
        state.W.assemblies[1] = Assembly(assembly_id=1, region=Region.LANGUAGE, member_cell_ids=c, status=AssemblyStatus.LIVE, structural_generation=1)
        state.W.assemblies[2] = Assembly(assembly_id=2, region=Region.LANGUAGE, member_cell_ids=c[:4], status=AssemblyStatus.LIVE, structural_generation=1)
        _rebuild_assemblies_by_member(state.W)

    _run_differential_case(_case_4_proper_superset, "Case 4: Proper Superset", expected_decision=False)

    # 5. Below-threshold Jaccard (J = 1/7 < 0.70)
    def _case_5_low_jaccard(state: MachineState) -> None:
        for cid in range(8200, 8260, 8):
            state.W.commit_cell(cid, 0)
        state.W.assemblies[1] = Assembly(assembly_id=1, region=Region.LANGUAGE, member_cell_ids=(8200, 8208, 8216, 8224), status=AssemblyStatus.LIVE, structural_generation=1)
        state.W.assemblies[2] = Assembly(assembly_id=2, region=Region.LANGUAGE, member_cell_ids=(8224, 8232, 8240, 8248), status=AssemblyStatus.LIVE, structural_generation=1)
        _rebuild_assemblies_by_member(state.W)

    _run_differential_case(_case_5_low_jaccard, "Case 5: Below-Threshold Jaccard", expected_decision=False)

    # 6. Cooldown active (elapsed 50 < 200)
    def _case_6_cooldown(state: MachineState) -> None:
        state.W.completed_external_events_count = 100
        c = tuple(range(8200, 8280, 8))[:10]
        for cid in c:
            state.W.commit_cell(cid, 0)
        state.W.assemblies[1] = Assembly(assembly_id=1, region=Region.LANGUAGE, member_cell_ids=c[:9], status=AssemblyStatus.LIVE, structural_generation=1, last_merge_split_close_serial=80)
        state.W.assemblies[2] = Assembly(assembly_id=2, region=Region.LANGUAGE, member_cell_ids=c[1:], status=AssemblyStatus.LIVE, structural_generation=1, last_merge_split_close_serial=0)
        _rebuild_assemblies_by_member(state.W)

    _run_differential_case(_case_6_cooldown, "Case 6: Cooldown Active", expected_decision=False)

    # 7. Capacity exceeded (shared cell has 12 live assemblies already)
    def _case_7_capacity(state: MachineState) -> None:
        c = tuple(range(8200, 8280, 8))[:10]
        shared = c[:8]
        c8, c9 = c[8], c[9]
        for u in shared:
            for v in shared:
                if u < v:
                    _wire_reciprocal_pair(state, u, v, s_val=0.85, e_ext=6.0)
        for m in c[:3]:
            _wire_reciprocal_pair(state, c8, m, s_val=0.85, e_ext=6.0)
        for m in c[3:6]:
            _wire_reciprocal_pair(state, c9, m, s_val=0.85, e_ext=6.0)
        _wire_reciprocal_pair(state, c8, c9, s_val=0.85, e_ext=6.0)

        for aid in range(10, 24):
            state.W.assemblies[aid] = Assembly(assembly_id=aid, region=Region.LANGUAGE, member_cell_ids=(c[0], 8300, 8400), status=AssemblyStatus.LIVE)

        state.W.assemblies[1] = Assembly(assembly_id=1, region=Region.LANGUAGE, member_cell_ids=(*shared, c8), status=AssemblyStatus.LIVE, structural_generation=1)
        state.W.assemblies[2] = Assembly(assembly_id=2, region=Region.LANGUAGE, member_cell_ids=(*shared, c9), status=AssemblyStatus.LIVE, structural_generation=1)
        state.W.assemblies_by_member[c[0]] = set(range(10, 24)) | {1, 2}

    _run_differential_case(_case_7_capacity, "Case 7: Capacity Exceeded", expected_decision=False)

    # 8. Keep-guard rejection (exclusive cells have 0 reciprocal connections to other members)
    def _case_8_keep_guard(state: MachineState) -> None:
        c = tuple(range(8200, 8280, 8))[:10]
        shared = c[:8]
        c8, c9 = c[8], c[9]
        for cid in c:
            state.W.commit_cell(cid, 0)
        state.W.assemblies[1] = Assembly(assembly_id=1, region=Region.LANGUAGE, member_cell_ids=(*shared, c8), status=AssemblyStatus.LIVE, structural_generation=1)
        state.W.assemblies[2] = Assembly(assembly_id=2, region=Region.LANGUAGE, member_cell_ids=(*shared, c9), status=AssemblyStatus.LIVE, structural_generation=1)
        _rebuild_assemblies_by_member(state.W)

    _run_differential_case(_case_8_keep_guard, "Case 8: Keep-Guard Rejection", expected_decision=False)

    # 9. Case 9: EXACT DUPLICATE (the single intentional divergence)
    state_base = MachineState()
    state_patch = MachineState()
    for s in (state_base, state_patch):
        c = tuple(range(8200, 8240, 8))[:4]
        for u in c:
            for v in c:
                if u < v:
                    _wire_reciprocal_pair(s, u, v, s_val=0.85, e_ext=6.0)
        s.W.assemblies[1] = Assembly(assembly_id=1, region=Region.LANGUAGE, member_cell_ids=c, status=AssemblyStatus.LIVE, structural_generation=1)
        s.W.assemblies[2] = Assembly(assembly_id=2, region=Region.LANGUAGE, member_cell_ids=c, status=AssemblyStatus.LIVE, structural_generation=1)
        _rebuild_assemblies_by_member(s.W)

    res_base = _baseline_try_merge_pair(1, 2, state_base.W, {})
    res_patch = _try_merge_pair(1, 2, state_patch.W, {})

    assert res_base is False, "Baseline incorrectly allowed exact-duplicate merge"
    assert res_patch is True, "Patched failed exact-duplicate merge"


# ==============================================================================
# C01-S07 & C02-S03: Full State Determinism
# ==============================================================================

def test_c01_s07_full_state_determinism() -> None:
    """C01-S07 & C02-S03: Dual independent cold-start curriculum executions yield identical canonical digests."""

    def _execute_curriculum():
        state = MachineState()
        ledger = SurfaceReadoutLedgerV1()
        tx = ExposureTransactionManager(
            state,
            enable_context_pipeline=True,
            enable_assembly_pipeline=True,
            readout_ledger=ledger,
        )
        _train_56_root_curriculum(tx)
        return state, ledger, tx

    s1, l1, tx1 = _execute_curriculum()
    s2, l2, tx2 = _execute_curriculum()

    # 1. WState cryptographic digest
    hash_w1 = hash_state_snapshot(snapshot_w(s1.W))
    hash_w2 = hash_state_snapshot(snapshot_w(s2.W))
    assert hash_w1 == hash_w2, f"WState digest mismatch:\n  Run 1: {hash_w1}\n  Run 2: {hash_w2}"

    # 2. HSlowState cryptographic digest
    hash_h1 = hash_state_snapshot(snapshot_h_slow(s1.H_slow))
    hash_h2 = hash_state_snapshot(snapshot_h_slow(s2.H_slow))
    assert hash_h1 == hash_h2, f"HSlowState digest mismatch:\n  Run 1: {hash_h1}\n  Run 2: {hash_h2}"

    # 3. RState cryptographic digest
    hash_r1 = hash_state_snapshot(snapshot_r(s1.R))
    hash_r2 = hash_state_snapshot(snapshot_r(s2.R))
    assert hash_r1 == hash_r2, f"RState digest mismatch:\n  Run 1: {hash_r1}\n  Run 2: {hash_r2}"

    # 4. Peripheral Ledger cryptographic digest
    hash_l1 = hash_state_snapshot(snapshot_ledger(l1))
    hash_l2 = hash_state_snapshot(snapshot_ledger(l2))
    assert hash_l1 == hash_l2, f"Ledger digest mismatch:\n  Run 1: {hash_l1}\n  Run 2: {hash_l2}"

    # 5. TransactionPublicationView comprehensive cryptographic digest (C02-S03)
    snap_pv1 = snapshot_publication_view(tx1._publication_view)
    snap_pv2 = snapshot_publication_view(tx2._publication_view)
    assert snap_pv1 == snap_pv2, "PublicationView deep snapshot mismatch!"
    hash_pv1 = hash_state_snapshot(snap_pv1)
    hash_pv2 = hash_state_snapshot(snap_pv2)
    assert hash_pv1 == hash_pv2, f"PublicationView digest mismatch:\n  Run 1: {hash_pv1}\n  Run 2: {hash_pv2}"

    # 6. Specific publication metadata checks
    pv1 = tx1._publication_view
    pv2 = tx2._publication_view
    assert pv1.completed_roots_high_watermark == pv2.completed_roots_high_watermark == 56
    assert set(pv1.completed_roots.keys()) == set(pv2.completed_roots.keys()) == set(range(1, 57))
    assert len(pv1.pending_outbox_by_root) == len(pv2.pending_outbox_by_root) == 0
    assert l1._processed_outbox_keys == l2._processed_outbox_keys
    assert len(l1._processed_outbox_keys) == 352
