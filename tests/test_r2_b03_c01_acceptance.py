"""Scientific Acceptance and Legacy Regression Reconciliation Test Suite for R2-B03-C01.

Covers:
- C01-S01: Automated Eagle Generation Proof (1-event & 2-event prompts, exact winner, generation, scores, margin, EOS).
- C01-S02: Real Post-Merge Attestation Proof (Ledger candidate rows for Asm 5 at Gen 8, confirmed roots [11..56], no leak from 6).
- C01-S03: Read-Only Generation Integrity (Snapshot preservation of W, H_slow, R, Ledger across Cat, Eagle, and RETRIEVE).
- C01-S04: Post-Assembly Pre-Publication Fault (FP_02 shadow consolidation verified via hook, zero publication leak; FP_03 coverage).
- C01-S05: Non-Identical MERGE Differential (Frozen baseline vs patched implementation across 8 non-identical cases + exact duplicate).
- C01-S07: Full State Determinism (Dual independent cold-start curriculum replays, 100% cryptographic digest match).
"""

from __future__ import annotations

import dataclasses
import hashlib
from typing import Any
import pytest

from dgca.common.errors import StatusCode
from dgca.common.hashing import Region
from dgca.core.anatomy import Synapse, SynapseKey, SynapseScope, SynapseState
from dgca.core.assembly import (
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
    ExposureStatus,
    ExposureTransactionManager,
    run_read_only_episode,
)
from dgca.core.readout import M_READ
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


def _baseline_try_merge_pair(
    a_id: int,
    b_id: int,
    w: WState,
    n_rec_cache: dict[int, dict[int, float]],
) -> bool:
    """Exact frozen baseline implementation of _try_merge_pair from origin/main:faf361b6b95de6287b466eb1dc524ea49c732635."""
    if a_id not in w.assemblies or b_id not in w.assemblies:
        return False
    asm_a = w.assemblies[a_id]
    asm_b = w.assemblies[b_id]
    if asm_a.status != AssemblyStatus.LIVE or asm_b.status != AssemblyStatus.LIVE:
        return False
    if _is_in_merge_split_cooldown(asm_a, w) or _is_in_merge_split_cooldown(asm_b, w):
        return False

    set_a = set(asm_a.member_cell_ids)
    set_b = set(asm_b.member_cell_ids)
    union_set = set_a | set_b
    if len(union_set) > K_MAX or not union_set:
        return False

    inter_set = set_a & set_b
    jaccard = float(len(inter_set)) / float(len(union_set))
    if jaccard < THETA_MERGE:
        return False

    excl_a = sorted(set_a - set_b)
    excl_b = sorted(set_b - set_a)
    if not excl_a or not excl_b:
        between_strength = 0.0
    else:
        cross_vals = [
            compute_mutual_support_r_b(i, j, w)
            for i in excl_a
            for j in excl_b
        ]
        between_strength = sum(cross_vals) / float(len(cross_vals))

    if between_strength < THETA_OB:
        return False

    union_tuple = tuple(sorted(union_set))
    for x in union_tuple:
        live_after = (_live_assembly_ids_for_cell(x, w) - {b_id}) | {a_id}
        if len(live_after) > M_MAX:
            return False
        if not check_maintain_keep_guards(x, union_tuple, w, n_rec_cache):
            return False

    asm_a.member_cell_ids = union_tuple
    asm_a.structural_generation += 1
    asm_a.last_mutation_close_serial = w.close_serial
    asm_a.last_merge_split_close_serial = w.completed_external_events_count

    asm_b.status = AssemblyStatus.ARCHIVED
    asm_b.structural_generation += 1
    asm_b.last_mutation_close_serial = w.close_serial
    asm_b.last_merge_split_close_serial = w.completed_external_events_count

    _rebuild_assemblies_by_member(w)
    return True


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
# C01-S03: Read-Only Generation Integrity
# ==============================================================================

def test_c01_s03_read_only_generation_integrity() -> None:
    """C01-S03: Snapshot verification of complete state immutability during generation & retrieval."""
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

    hash_w_pre_cat = hash_state_snapshot(w_snap_pre_cat)
    hash_h_pre_cat = hash_state_snapshot(h_snap_pre_cat)
    hash_r_pre_cat = hash_state_snapshot(r_snap_pre_cat)
    hash_l_pre_cat = hash_state_snapshot(ledger_snap_pre_cat)

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

    # 3. Read-only retrieval
    w_snap_pre_ro = snapshot_w(state.W)
    hash_w_pre_ro = hash_state_snapshot(w_snap_pre_ro)

    ro_summary = run_read_only_episode(state, [branch_cat[0].core_event, branch_cat[1].core_event])
    assert len(ro_summary.event_results) == 2

    assert snapshot_w(state.W) == w_snap_pre_ro, "WState mutated during RETRIEVE!"
    assert hash_state_snapshot(snapshot_w(state.W)) == hash_w_pre_ro


# ==============================================================================
# C01-S04: Post-Assembly Pre-Publication Fault (FP_02 & FP_03)
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


def test_c01_s04_post_commit_dispatch_fault_fp03() -> None:
    """C01-S04: Verify FP_03 post-commit dispatch failure leaves outbox pending safely."""
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
    )

    branch_cat = encode_exposure("القط يشرب حليب", append_eos=True)
    tx.begin_exposure(1)
    for env in branch_cat:
        core_ev = dataclasses.replace(env.core_event, exposure_id=1)
        tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)

    tx._fault_injection_point = "FP_03"
    # Commit succeeds despite post-commit dispatch deferred
    report = tx.end_exposure(1)
    assert report.status == ExposureStatus.COMPLETED
    assert 1 in tx.completed_roots
    assert tx.state.W.completed_roots_high_watermark == 1


# ==============================================================================
# C01-S05: Non-Identical MERGE Differential
# ==============================================================================

def test_c01_s05_non_identical_merge_differential() -> None:
    """C01-S05: Differential execution of baseline vs patched MERGE on 8 non-identical scenarios."""

    def _run_differential_case(
        setup_fn,
        case_name: str,
        expected_decision: bool,
    ) -> None:
        # Build identical baseline state and patched state
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
        assert asm_b_base.status == asm_b_patch.status
        assert asm_b_base.structural_generation == asm_b_patch.structural_generation
        assert asm_b_base.member_cell_ids == asm_b_patch.member_cell_ids
        assert state_base.W.assemblies_by_member == state_patch.W.assemblies_by_member

    # 1. Eligible partial-overlap merge (J = 8/10 = 0.80 >= 0.70, mutual link between c8 and c9)
    def _case_1_eligible_partial(state: MachineState) -> None:
        c = tuple(range(8200, 8280, 8))[:10]  # c0..c9
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
        # Weak link: S=0.20 < 0.60 (fails is_legal_consolidated_synapse)
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

        # Wire dummy assemblies 10..23 covering cell c0 so len(live_after) > 12
        for aid in range(10, 24):
            state.W.assemblies[aid] = Assembly(
                assembly_id=aid,
                region=Region.LANGUAGE,
                member_cell_ids=(c[0], 8300, 8400),
                status=AssemblyStatus.LIVE,
                structural_generation=1,
            )

        state.W.assemblies[1] = Assembly(assembly_id=1, region=Region.LANGUAGE, member_cell_ids=(*shared, c8), status=AssemblyStatus.LIVE, structural_generation=1)
        state.W.assemblies[2] = Assembly(assembly_id=2, region=Region.LANGUAGE, member_cell_ids=(*shared, c9), status=AssemblyStatus.LIVE, structural_generation=1)
        state.W.assemblies_by_member[c[0]] = set(range(10, 24)) | {1, 2}

    _run_differential_case(_case_7_capacity, "Case 7: Capacity Exceeded", expected_decision=False)

    # 8. Keep-guard rejection (union cell has degree < 2)
    def _case_8_keep_guard(state: MachineState) -> None:
        c = tuple(range(8200, 8280, 8))[:10]
        shared = c[:8]
        c8, c9 = c[8], c[9]
        for cid in c:
            state.W.commit_cell(cid, 0)
        # c8 and c9 have 0 synapses to the other members
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
# C01-S07: Full State Determinism
# ==============================================================================

def test_c01_s07_full_state_determinism() -> None:
    """C01-S07: Dual independent cold-start curriculum executions yield identical canonical digests."""

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

    # 5. Publication View state
    pv1 = tx1._publication_view
    pv2 = tx2._publication_view
    assert pv1.completed_roots_high_watermark == pv2.completed_roots_high_watermark == 56
    assert set(pv1.completed_roots.keys()) == set(pv2.completed_roots.keys()) == set(range(1, 57))
    assert len(pv1.pending_outbox_by_root) == len(pv2.pending_outbox_by_root) == 0
    assert l1._processed_outbox_keys == l2._processed_outbox_keys
    assert len(l1._processed_outbox_keys) == 352
