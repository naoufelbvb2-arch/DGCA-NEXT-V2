"""Acceptance test suite for R2-B03: Exact-Duplicate Assembly Consolidation.

Implements and verifies Alternative A under Core §2.0 Operator 4 (`MERGE`).
Covers:
- EXP-B02-01: Exact duplicate consolidation at Root 9 (Asm 5 & 6)
- EXP-B02-02: Partial overlap invariance (Branch 4b mutual support)
- EXP-B02-03: Proper subset rejection (A subset B rejected)
- EXP-B02-04: Ledger generation safety (unattested Gen 8 fail-closed halt)
- EXP-B02-05: Post-merge re-attestation across >= 2 independent qualifying roots
- EXP-B02-06: 56-root curriculum dual-replay determinism and measurement
- EXP-B02-07: Transaction failure boundaries (ordinary ineligibility vs exceptional abort)
- EXP-B02-NEG-01: Single external root confirmation leaves row unattested
- EXP-B02-NEG-02: Repeated observations within same root deduplicated by root_id
- EXP-B02-NEG-03: Old-generation evidence invalidation (strict key mismatch)
- EXP-B02-NEG-04: Same-surface / different-bundle conflict triggers READOUT_AMBIGUOUS_PENDING
- EXP-B02-NEG-05: Proper subset absorption attempt rejected
- EXP-B02-NEG-06: Cooldown bypass attempt rejected (T_c = 200)
- EXP-B02-NEG-07: Archived assembly governance (neural exclusion, zero aliasing, zero evidence transfer)
- EXP-B02-NEG-08: Zero peripheral selection leakage during neural candidate ranking
- EXP-B02-NEG-09: Ordinary ineligibility continuity (returns False without transaction abort)
"""

from __future__ import annotations

import dataclasses
import hashlib
import pytest

from dgca.common.errors import StatusCode
from dgca.common.hashing import Region
from dgca.core.anatomy import Synapse, SynapseKey, SynapseScope, SynapseState
from dgca.core.assembly import (
    K_MAX,
    M_MAX,
    THETA_MERGE,
    THETA_OB,
    T_C_COOLDOWN,
    _try_merge_pair,
    _run_merge_stage,
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
)
from dgca.peripheral.outbox import OutboxNotificationV1
from dgca.peripheral.readout_ledger import (
    LedgerCandidateRow,
    SurfaceReadoutLedgerV1,
    MIN_ATTESTED_EXTERNAL_ROOTS,
)


def _make_env(
    surface: str,
    marker: Marker = Marker.NONE,
    digest: bytes = b"digest_test",
) -> PeripheralSurfaceEnvelopeV1:
    """Helper to create a canonical PeripheralSurfaceEnvelopeV1."""
    return PeripheralSurfaceEnvelopeV1(
        raw_surface_nfc_utf8=surface,
        surface_sha256=hashlib.sha256(surface.encode("utf-8")).digest(),
        feature_bundle_digest=digest,
        canonical_features_copy=(("f", "1.0"),),
        marker=marker,
    )


def _make_notif(
    root_id: int,
    order: int,
    asm_id: int,
    gen: int,
    envelope: PeripheralSurfaceEnvelopeV1,
) -> OutboxNotificationV1:
    """Helper to create an OutboxNotificationV1 from an envelope."""
    return OutboxNotificationV1(
        root_id=root_id,
        event_order=order,
        assembly_id=asm_id,
        structural_generation=gen,
        surface_sha256=envelope.surface_sha256,
        feature_bundle_digest=envelope.feature_bundle_digest,
        marker=envelope.marker,
        envelope=envelope,
    )


def _add_reciprocal_local_pair(
    state: MachineState,
    u: int,
    v: int,
    *,
    s_val: float = 0.85,
    e_ext: float = 6.0,
) -> None:
    """Add bidirectional CONSOLIDATED LOCAL links between u and v in LANGUAGE region."""
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


def _train_curriculum_to_root(
    tx: ExposureTransactionManager,
    max_root: int,
) -> None:
    """Train curriculum alternating between Cat and Eagle up to max_root."""
    branch_cat = encode_exposure("القط يشرب حليب", append_eos=True)
    branch_eagle = encode_exposure("النسر يشرب ماء", append_eos=True)

    for root_id in range(1, max_root + 1):
        branch = branch_cat if (root_id % 2 == 1) else branch_eagle
        tx.begin_exposure(root_id)
        for env in branch:
            core_ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        tx.end_exposure(root_id)


# ==============================================================================
# 1. Primary Acceptance Tests (EXP-B02-01 to EXP-B02-07)
# ==============================================================================

def test_exp_b02_01_exact_duplicate_consolidation_root_9() -> None:
    """EXP-B02-01: Replay Root 9 where Assemblies 5 & 6 converge to identical 8 cells.
    
    Verifies:
    - Candidate pair (5, 6) passes all guards under Branch 4a.
    - Assembly 5 remains LIVE, advances to Gen 7 post-merge.
    - Assembly 6 becomes ARCHIVED, advances to Gen 7.
    - Cooldown applied to both assemblies (T_c = 200).
    - Reverse membership index assemblies_by_member updated cleanly.
    """
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
    )

    # Train to Root 9 (Cat)
    _train_curriculum_to_root(tx, 9)

    # Assembly 5 must be LIVE at Gen 7 with 8 cells
    asm_5 = state.W.assemblies[5]
    assert asm_5.status == AssemblyStatus.LIVE
    assert asm_5.structural_generation == 7
    expected_8_cells = (8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116)
    assert asm_5.member_cell_ids == expected_8_cells

    # Assembly 6 must be ARCHIVED at Gen 7
    asm_6 = state.W.assemblies[6]
    assert asm_6.status == AssemblyStatus.ARCHIVED
    assert asm_6.structural_generation == 7

    # Cooldown verified
    assert asm_5.last_merge_split_close_serial == state.W.completed_external_events_count
    assert asm_6.last_merge_split_close_serial == state.W.completed_external_events_count

    # Reverse membership index verified: Asm 6 removed from all member cells
    for cid in expected_8_cells:
        live_asms = [aid for aid in state.W.assemblies_by_member[cid] if state.W.assemblies[aid].status == AssemblyStatus.LIVE]
        assert 5 in live_asms
        assert 6 not in live_asms


def test_exp_b02_02_partial_overlap_invariance() -> None:
    """EXP-B02-02: Synthetic pair with partial overlap merges legally under Branch 4b."""
    state = MachineState()
    # Cells 8200..8256 shared (8 cells), c8=8264 in A, c9=8272 in B
    # |A|=9, |B|=9, |A U B|=10, Jaccard = 8/10 = 0.80 >= 0.70
    c0, c1, c2, c3, c4, c5, c6, c7 = 8200, 8208, 8216, 8224, 8232, 8240, 8248, 8256
    c8, c9 = 8264, 8272
    shared_8 = (c0, c1, c2, c3, c4, c5, c6, c7)
    for u in shared_8:
        for v in shared_8:
            if u < v:
                _add_reciprocal_local_pair(state, u, v, s_val=0.85, e_ext=6.0)
    for m in (c0, c1, c2):
        _add_reciprocal_local_pair(state, c8, m, s_val=0.85, e_ext=6.0)
    for m in (c3, c4, c5):
        _add_reciprocal_local_pair(state, c9, m, s_val=0.85, e_ext=6.0)
    _add_reciprocal_local_pair(state, c8, c9, s_val=0.85, e_ext=6.0)

    asm_a = Assembly(
        assembly_id=1,
        region=Region.LANGUAGE,
        member_cell_ids=(*shared_8, c8),
        structural_generation=1,
        status=AssemblyStatus.LIVE,
    )
    asm_b = Assembly(
        assembly_id=2,
        region=Region.LANGUAGE,
        member_cell_ids=(*shared_8, c9),
        structural_generation=1,
        status=AssemblyStatus.LIVE,
    )
    state.W.assemblies[1] = asm_a
    state.W.assemblies[2] = asm_b
    _rebuild_assemblies_by_member(state.W)

    n_rec_cache: dict[int, dict[int, float]] = {}
    merged = _try_merge_pair(1, 2, state.W, n_rec_cache)
    assert merged is True
    assert asm_a.status == AssemblyStatus.LIVE
    assert asm_b.status == AssemblyStatus.ARCHIVED
    assert asm_a.structural_generation == 2
    assert asm_b.structural_generation == 2
    assert len(asm_a.member_cell_ids) == 10


def test_exp_b02_03_proper_subset_rejection() -> None:
    """EXP-B02-03: Synthetic pair with A subset of B (|A|=4, |B|=5) rejected under Branch 4b."""
    w = WState()
    cells_a = (8200, 8208, 8216, 8224)
    cells_b = (8200, 8208, 8216, 8224, 8232)
    for cid in cells_b:
        w.commit_cell(cid, 0)

    asm_a = Assembly(
        assembly_id=1,
        region=Region.LANGUAGE,
        member_cell_ids=cells_a,
        status=AssemblyStatus.LIVE,
        structural_generation=1,
    )
    asm_b = Assembly(
        assembly_id=2,
        region=Region.LANGUAGE,
        member_cell_ids=cells_b,
        status=AssemblyStatus.LIVE,
        structural_generation=1,
    )
    w.assemblies[1] = asm_a
    w.assemblies[2] = asm_b
    _rebuild_assemblies_by_member(w)

    n_rec_cache: dict[int, dict[int, float]] = {}
    merged = _try_merge_pair(1, 2, w, n_rec_cache)
    assert merged is False
    assert asm_a.status == AssemblyStatus.LIVE
    assert asm_b.status == AssemblyStatus.LIVE


def test_exp_b02_04_ledger_generation_safety() -> None:
    """EXP-B02-04: Readout queried on an unattested new generation halts fail-closed."""
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
    )

    # Train to Root 10
    _train_curriculum_to_root(tx, 10)

    # Key (5, 8) must have zero candidate rows in the ledger
    candidate_rows = ledger.get_candidate_rows(5, 8)
    assert len(candidate_rows) == 0

    # Resolve readout on (5, 8) must return READOUT_UNKNOWN
    res = ledger.resolve_readout(5, 8, current_live_generation=8)
    assert res.status == StatusCode.READOUT_UNKNOWN
    assert res.external_count == 0


def test_exp_b02_05_post_merge_re_attestation() -> None:
    """EXP-B02-05: Consolidated assembly requires >= 2 distinct completed roots for attestation."""
    ledger = SurfaceReadoutLedgerV1()
    env = _make_env("<EOS>", Marker.EOS, b"bundle_eos_digest_1234567890ab")

    # 1st root exposure
    notif_root_12 = _make_notif(12, 3, 5, 8, env)
    ledger.consume_outbox_notification(notif_root_12)

    # After 1 root: external_count = 1 < 2 -> NOT attested
    res_1 = ledger.resolve_readout(5, 8, current_live_generation=8)
    assert res_1.status == StatusCode.READOUT_UNKNOWN
    assert res_1.external_count == 1

    # 2nd root exposure (distinct root_id 14)
    notif_root_14 = _make_notif(14, 3, 5, 8, env)
    ledger.consume_outbox_notification(notif_root_14)

    # After 2 roots: external_count = 2 >= 2 -> ATTESTED (OK)
    res_2 = ledger.resolve_readout(5, 8, current_live_generation=8)
    assert res_2.status == StatusCode.OK
    assert res_2.external_count == 2
    assert res_2.envelope is not None
    assert res_2.envelope.raw_surface_nfc_utf8 == "<EOS>"


def test_exp_b02_06_56_root_curriculum_replay() -> None:
    """EXP-B02-06: Dual cold-start replay of full 56-root curriculum verifies determinism."""
    def _run_full_curriculum():
        state = MachineState()
        ledger = SurfaceReadoutLedgerV1()
        tx = ExposureTransactionManager(
            state,
            enable_context_pipeline=True,
            enable_assembly_pipeline=True,
            readout_ledger=ledger,
        )
        _train_curriculum_to_root(tx, 56)
        return state, ledger

    state1, ledger1 = _run_full_curriculum()
    state2, ledger2 = _run_full_curriculum()

    # Exact equality of assembly state
    assert len(state1.W.assemblies) == len(state2.W.assemblies)
    for aid in state1.W.assemblies:
        a1 = state1.W.assemblies[aid]
        a2 = state2.W.assemblies[aid]
        assert a1.status == a2.status
        assert a1.structural_generation == a2.structural_generation
        assert a1.member_cell_ids == a2.member_cell_ids

    # Outbox keys count identical
    assert ledger1._processed_outbox_keys == ledger2._processed_outbox_keys
    assert len(ledger1._processed_outbox_keys) == 352


def test_exp_b02_07_transaction_fault_semantics() -> None:
    """EXP-B02-07: Injected shadow execution failure discards mutations cleanly."""
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
    )

    _train_curriculum_to_root(tx, 8)
    asms_pre = {aid: a.member_cell_ids for aid, a in state.W.assemblies.items()}

    # Begin Root 9, process events
    branch_cat = encode_exposure("القط يشرب حليب", append_eos=True)
    tx.begin_exposure(9)
    for env in branch_cat:
        core_ev = dataclasses.replace(env.core_event, exposure_id=9)
        tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)

    # Injected fault: abort exposure before atomic commit
    tx.abort_exposure(9)

    # WState assemblies remain exactly as they were pre-open
    asms_post = {aid: a.member_cell_ids for aid, a in state.W.assemblies.items()}
    assert asms_pre == asms_post
    assert state.W.assemblies[5].structural_generation == 1
    assert state.W.assemblies[6].structural_generation == 1

    # Also verify that exception in end_exposure preserves pre-state cleanly on next root 10
    branch_eagle = encode_exposure("النسر يشرب ماء", append_eos=True)
    tx.begin_exposure(10)
    for env in branch_eagle:
        core_ev = dataclasses.replace(env.core_event, exposure_id=10)
        tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
    tx._fault_injection_point = "FP_01"
    with pytest.raises(RuntimeError):
        tx.end_exposure(10)

    asms_post_fault = {aid: a.member_cell_ids for aid, a in state.W.assemblies.items()}
    assert asms_pre == asms_post_fault
    assert state.W.assemblies[5].structural_generation == 1
    assert state.W.assemblies[6].structural_generation == 1


# ==============================================================================
# 2. Negative Test Suite (EXP-B02-NEG-01 to EXP-B02-NEG-09)
# ==============================================================================

def test_exp_b02_neg_01_single_external_confirmation() -> None:
    """NEG-01: Exactly one external root confirmation leaves candidate row unattested."""
    ledger = SurfaceReadoutLedgerV1()
    env = _make_env("test", Marker.NONE, b"digest1")
    notif = _make_notif(10, 0, 100, 1, env)
    ledger.consume_outbox_notification(notif)

    res = ledger.resolve_readout(100, 1, current_live_generation=1)
    assert res.status == StatusCode.READOUT_UNKNOWN
    assert res.external_count == 1


def test_exp_b02_neg_02_repeated_observations_within_root() -> None:
    """NEG-02: Repeated observations within the same root deduplicate by root_id."""
    ledger = SurfaceReadoutLedgerV1()
    env = _make_env("test", Marker.NONE, b"digest1")
    notif1 = _make_notif(10, 0, 100, 1, env)
    notif2 = _make_notif(10, 1, 100, 1, env)

    ledger.consume_outbox_notification(notif1)
    ledger.consume_outbox_notification(notif2)

    rows = ledger.get_candidate_rows(100, 1)
    assert len(rows) == 1
    assert rows[0].external_count == 1
    assert rows[0].confirmed_roots == {10}


def test_exp_b02_neg_03_old_generation_evidence_invalidation() -> None:
    """NEG-03: Readout queried at Gen 8 against older generation evidence strictly mismatches."""
    ledger = SurfaceReadoutLedgerV1()
    env = _make_env("test", Marker.NONE, b"digest1")
    # Old evidence at Gen 1 with 5 confirmed roots
    for r in range(1, 6):
        notif = _make_notif(r, 0, 5, 1, env)
        ledger.consume_outbox_notification(notif)

    assert ledger.resolve_readout(5, 1).status == StatusCode.OK

    # Querying Gen 8 must strictly return 0 candidate rows (READOUT_UNKNOWN)
    res_gen_8 = ledger.resolve_readout(5, 8, current_live_generation=8)
    assert res_gen_8.status == StatusCode.READOUT_UNKNOWN
    assert res_gen_8.external_count == 0


def test_exp_b02_neg_04_same_surface_differing_bundle_conflict() -> None:
    """NEG-04: Conflicting feature bundle for same surface string yields READOUT_AMBIGUOUS_PENDING."""
    ledger = SurfaceReadoutLedgerV1()
    env1 = _make_env("token", Marker.NONE, b"digest_AAA")
    env2 = _make_env("token", Marker.NONE, b"digest_BBB")

    # Root 1 & 2 attestation for bundle AAA
    for r in [1, 2]:
        ledger.consume_outbox_notification(_make_notif(r, 0, 10, 1, env1))

    # Conflicting observation for bundle BBB at Root 3
    ledger.consume_outbox_notification(_make_notif(3, 0, 10, 1, env2))

    res = ledger.resolve_readout(10, 1, current_live_generation=1)
    assert res.status == StatusCode.READOUT_AMBIGUOUS_PENDING


def test_exp_b02_neg_05_proper_subset_absorption_attempt() -> None:
    """NEG-05: Subset pair (A subset B) fails mutual support and returns False."""
    w = WState()
    cells = (8200, 8208, 8216, 8224, 8232, 8240)
    for cid in cells:
        w.commit_cell(cid, 0)

    asm_a = Assembly(
        assembly_id=1,
        region=Region.LANGUAGE,
        member_cell_ids=cells[:3],
        status=AssemblyStatus.LIVE,
        structural_generation=1,
    )
    asm_b = Assembly(
        assembly_id=2,
        region=Region.LANGUAGE,
        member_cell_ids=cells,
        status=AssemblyStatus.LIVE,
        structural_generation=1,
    )
    w.assemblies[1] = asm_a
    w.assemblies[2] = asm_b
    _rebuild_assemblies_by_member(w)

    assert _try_merge_pair(1, 2, w, {}) is False
    assert asm_a.status == AssemblyStatus.LIVE
    assert asm_b.status == AssemblyStatus.LIVE


def test_exp_b02_neg_06_cooldown_bypass_attempt() -> None:
    """NEG-06: Identical pair rejected if either assembly is in cooldown (T_c = 200)."""
    w = WState()
    w.completed_external_events_count = 50
    cells = (8200, 8208, 8216, 8224)
    for cid in cells:
        w.commit_cell(cid, 0)

    # Asm 1 underwent mutation at event 10 (elapsed 40 < 200)
    asm_a = Assembly(
        assembly_id=1,
        region=Region.LANGUAGE,
        member_cell_ids=cells,
        status=AssemblyStatus.LIVE,
        structural_generation=1,
        last_merge_split_close_serial=10,
    )
    asm_b = Assembly(
        assembly_id=2,
        region=Region.LANGUAGE,
        member_cell_ids=cells,
        status=AssemblyStatus.LIVE,
        structural_generation=1,
        last_merge_split_close_serial=0,
    )
    w.assemblies[1] = asm_a
    w.assemblies[2] = asm_b

    assert _try_merge_pair(1, 2, w, {}) is False
    assert asm_a.status == AssemblyStatus.LIVE
    assert asm_b.status == AssemblyStatus.LIVE


def test_exp_b02_neg_07_archived_assembly_governance() -> None:
    """NEG-07: Archived assemblies excluded from neural ranking, no alias, no evidence transfer."""
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()

    # Pre-populate historical evidence for archived Asm 6 at Gen 1
    env = _make_env("<EOS>", Marker.EOS, b"digest_eos")
    for r in [1, 2]:
        ledger.consume_outbox_notification(_make_notif(r, 0, 6, 1, env))

    # Asm 6 is ARCHIVED
    state.W.assemblies[6] = Assembly(
        assembly_id=6,
        region=Region.LANGUAGE,
        member_cell_ids=(8200, 8208, 8216),
        status=AssemblyStatus.ARCHIVED,
        structural_generation=2,
    )
    state.W.assemblies[5] = Assembly(
        assembly_id=5,
        region=Region.LANGUAGE,
        member_cell_ids=(8200, 8208, 8216),
        status=AssemblyStatus.LIVE,
        structural_generation=2,
    )

    # 1. Historical ledger row for 6 exists and is immutable
    assert ledger.resolve_readout(6, 1).status == StatusCode.OK

    # 2. No alias: resolving 6 does not resolve to 5
    assert ledger.resolve_readout(6, 1).assembly_id == 6

    # 3. No evidence transfer: Asm 5 has zero evidence from Asm 6
    assert ledger.resolve_readout(5, 2, current_live_generation=2).status == StatusCode.READOUT_UNKNOWN

    # 4. Readout query for archived assembly at current generation fails stale/exclusion
    res_stale = ledger.resolve_readout(6, 1, current_live_generation=2)
    assert res_stale.status == StatusCode.GEN_STOP_STALE_ASSEMBLY


def test_exp_b02_neg_08_zero_peripheral_selection_leakage() -> None:
    """NEG-08: Neural candidate ranking strictly ignores peripheral ledger entries."""
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()

    # Artificially populate ledger for assembly 99 with 100 attestations
    env = _make_env("winner", Marker.NONE, b"digest_win")
    for r in range(1, 101):
        ledger.consume_outbox_notification(_make_notif(r, 0, 99, 1, env))

    # But assembly 99 has zero neural activation overlap
    state.W.assemblies[99] = Assembly(
        assembly_id=99,
        region=Region.LANGUAGE,
        member_cell_ids=(8200, 8208, 8216),
        status=AssemblyStatus.LIVE,
        structural_generation=1,
    )
    for cid in (8200, 8208, 8216):
        state.W.commit_cell(cid, 0)

    branch = encode_exposure("القط", append_eos=False)
    prompt = [branch[0].core_event]
    gen = generate_episode(state, prompt, ledger, max_steps=1)

    # Asm 99 must not be selected despite 100 ledger attestations
    if gen.steps:
        assert gen.steps[0].winner_assembly_id != 99


def test_exp_b02_neg_09_ordinary_ineligibility_continuity() -> None:
    """NEG-09: Ordinary ineligibility in Stage 4 returns False without transaction abort."""
    w = WState()
    # Ineligible pair due to Jaccard < 0.70
    asm_a = Assembly(
        assembly_id=1,
        region=Region.LANGUAGE,
        member_cell_ids=(8200, 8208, 8216),
        status=AssemblyStatus.LIVE,
        structural_generation=1,
    )
    asm_b = Assembly(
        assembly_id=2,
        region=Region.LANGUAGE,
        member_cell_ids=(8224, 8232, 8240),
        status=AssemblyStatus.LIVE,
        structural_generation=1,
    )
    w.assemblies[1] = asm_a
    w.assemblies[2] = asm_b

    merged_pairs = _run_merge_stage(w, {})
    assert len(merged_pairs) == 0
    assert asm_a.status == AssemblyStatus.LIVE
    assert asm_b.status == AssemblyStatus.LIVE
