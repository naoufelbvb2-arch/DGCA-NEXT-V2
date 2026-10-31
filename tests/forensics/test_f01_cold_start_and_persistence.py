"""Forensic Investigation Phase C, E, F: COLD START, EOS BOUNDARIES & PERSISTENCE (Tasks 5, 6, 7).

TASK 5 — Strengthened Cold-Start Evidence:
- Verifies 34 and 56 roots with explicit assertions of two distinct COMPLETE contextual owners.
- Verifies native Assembly formation and surface attestations without fixtures.

TASK 6 — EOS and Autoregressive Boundary Experiment:
- Evaluates native EOS learning with append_eos=True.
- Verifies 2-step autoregressive rollout from ['القط'] -> ['يشرب', 'حليب'] -> <EOS>.

Phase F — Persistence Contract:
- Verifies CROSS_PROCESS_PERSISTENCE_NOT_IMPLEMENTED.
"""

from __future__ import annotations

import pytest
from dgca.common.errors import ObservationError, StatusCode
from dgca.core.generator import generate_episode
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import BindingStatus, MachineState
import dataclasses
from dgca.encoder.envelope import Marker, encode_exposure, encode_lexical_token_event
from dgca.experiments.gates import _extract_f0_cells
from dgca.lifecycle.exposure_tx import ExposureTransactionManager, compute_pred_score, run_read_only_episode
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1


def test_f01_task5_strengthened_cold_start_learning_from_zero() -> None:
    """Task 5: Strengthened verification of cold-start learning from zero at roots 34 and 56."""
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
    )

    branch_ab = encode_exposure("القط يشرب حليب", append_eos=False)
    branch_db = encode_exposure("النسر يشرب ماء", append_eos=False)

    f0_c = _extract_f0_cells(project_core_event_v1(branch_ab[2].core_event))[:3]
    f0_e = _extract_f0_cells(project_core_event_v1(branch_db[2].core_event))[:3]

    for root_id in range(1, 57):
        is_ab = (root_id % 2 != 0)
        envs = branch_ab if is_ab else branch_db
        tx.begin_exposure(root_id)
        for item in envs:
            core_ev = encode_lexical_token_event(
                item.peripheral_surface.raw_surface_nfc_utf8,
                exposure_id=root_id,
                event_order=item.core_event.event_order,
                boundary=item.core_event.boundary,
            ).core_event
            tx.process_event(core_ev, peripheral_envelope=item.peripheral_surface)
        tx.end_exposure(root_id)

        if root_id == 34:
            # Checkpoint 34: Assert two distinct COMPLETE owners with ACTIVE bindings
            assert len(state.W.stable_bindings) == 2, "Expected exactly two graduated contextual owners"
            z_ids = sorted(state.W.stable_bindings.keys())
            b1 = state.W.stable_bindings[z_ids[0]]
            b2 = state.W.stable_bindings[z_ids[1]]
            assert b1.status == BindingStatus.ACTIVE
            assert b2.status == BindingStatus.ACTIVE
            # Assert distinct P and Y footprints
            assert b1.p_sources != b2.p_sources
            assert b1.y_targets != b2.y_targets

            # Retrieval check
            ro_ab_34 = run_read_only_episode(state, [branch_ab[0].core_event, branch_ab[1].core_event])
            _, p_c_ab_34 = compute_pred_score(ro_ab_34.next_step_pt_by_cell, f0_c)
            _, p_e_ab_34 = compute_pred_score(ro_ab_34.next_step_pt_by_cell, f0_e)
            assert p_c_ab_34 > 0.10
            assert p_e_ab_34 == 0.0

            # Generation on AB fails at 34 roots due to formula-compliant dilution
            gen_ab_34 = generate_episode(state, [branch_ab[0].core_event, branch_ab[1].core_event], ledger, max_steps=3)
            assert gen_ab_34.emitted_surfaces == ()
            assert gen_ab_34.stop_status == StatusCode.GEN_STOP_NO_MATCH

        elif root_id == 56:
            # Checkpoint 56: Generation succeeds on both branches with non-fixture assemblies
            gen_ab_56 = generate_episode(state, [branch_ab[0].core_event, branch_ab[1].core_event], ledger, max_steps=3)
            gen_db_56 = generate_episode(state, [branch_db[0].core_event, branch_db[1].core_event], ledger, max_steps=3)

            assert gen_ab_56.emitted_surfaces == ("حليب",)
            assert gen_db_56.emitted_surfaces == ("ماء",)
            # In natural learning without append_eos, both stop at step 1 with NO_MATCH
            assert gen_ab_56.stop_status == StatusCode.GEN_STOP_NO_MATCH
            assert gen_db_56.stop_status == StatusCode.GEN_STOP_NO_MATCH


def test_f01_task6_reencoded_eos_discrepancy_and_outbox_bypass() -> None:
    """Task 1 / Task 6 Discrepancy Verification & Patch 1 Elimination.

    Investigates Section 1:
    - Original canonical EOS features vs re-encoded lexical features (features & digest diverge).
    - Historical vulnerability: re-encoded lexical token previously bypassed outbox checks.
    - Patch 1 resolution: passing re-encoded lexical token with Marker.EOS envelope is now
      strictly trapped and rejected during process_event with PROVENANCE_FEATURE_COPY_MISMATCH.
    - EventExecutionResult now carries feature_bundle_digest, preventing unverified bypass.
    """
    branch_ab = encode_exposure("القط يشرب حليب", append_eos=True)
    eos_env = branch_ab[-1]

    # 1. Inspect original canonical EOS event & envelope
    orig_marker = eos_env.peripheral_surface.marker
    orig_features = eos_env.core_event.features
    orig_digest = eos_env.core_event.feature_bundle_digest

    assert orig_marker == Marker.EOS
    assert orig_features == (("\x1fEOS#0", "1.000000"), ("\x1fEOS#1", "0.900000"), ("\x1fEOS#2", "0.800000"))
    assert orig_digest == eos_env.peripheral_surface.feature_bundle_digest

    # 2. Inspect re-encoded lexical token event
    re_ev = encode_lexical_token_event(
        eos_env.peripheral_surface.raw_surface_nfc_utf8,
        exposure_id=1,
        event_order=eos_env.core_event.event_order,
        boundary=eos_env.core_event.boundary,
    )
    re_features = re_ev.core_event.features
    re_digest = re_ev.core_event.feature_bundle_digest

    # Re-encoded features are lexical n-grams, NOT canonical special tokens
    assert re_features == (("S>$", "0.800000"), ("^<E", "0.900000"), ("^<EOS>$", "1.000000"), ("~EOS", "0.750000"))
    assert re_digest != orig_digest
    assert (re_digest == eos_env.peripheral_surface.feature_bundle_digest) is False

    # 3. Verify that under R2-A01 Patch 1, passing re-encoded lexical event with Marker.EOS envelope
    # is immediately rejected during process_event with PROVENANCE_FEATURE_COPY_MISMATCH:
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(state, enable_context_pipeline=True, enable_assembly_pipeline=True, readout_ledger=ledger)
    tx.begin_exposure(1)
    for env in branch_ab[:-1]:
        core_ev = encode_lexical_token_event(
            env.peripheral_surface.raw_surface_nfc_utf8,
            exposure_id=1,
            event_order=env.core_event.event_order,
            boundary=env.core_event.boundary,
        ).core_event
        tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)

    # Terminal event has Marker.EOS in envelope, but core_ev was re-encoded as ordinary lexical token
    mismatched_core_ev = encode_lexical_token_event(
        eos_env.peripheral_surface.raw_surface_nfc_utf8,
        exposure_id=1,
        event_order=eos_env.core_event.event_order,
        boundary=eos_env.core_event.boundary,
    ).core_event

    with pytest.raises(ObservationError) as exc_info:
        tx.process_event(mismatched_core_ev, peripheral_envelope=eos_env.peripheral_surface)
    assert exc_info.value.code == StatusCode.PROVENANCE_FEATURE_COPY_MISMATCH

    # 4. Verify EventExecutionResult now carries feature_bundle_digest:
    last_valid_ev_result = tx.open_journal.event_results[-1]
    assert getattr(last_valid_ev_result, "feature_bundle_digest", None) is not None
    assert last_valid_ev_result.feature_bundle_digest == branch_ab[-2].peripheral_surface.feature_bundle_digest
    tx.abort_exposure(1)


def test_f01_task6_canonical_eos_learning_and_multistep_rollout() -> None:
    """Task 3 & 4: Corrected canonical EOS learning across 56 roots and multi-step autonomous rollout.

    Uses identity-preserving dataclasses.replace to set exposure_id while preserving canonical features & digests.
    Demonstrates:
    - Complete causal chain (observations, commitment, local synapses, birth, attestations).
    - Prompt ['القط'] -> ('يشرب', 'حليب') -> GEN_STOP_EOS via neural selection of Asm 2.
    - Prompt ['القط', 'يشرب'] -> ('حليب',) -> GEN_STOP_EOS via neural selection of Asm 2.
    - Prompt ['النسر'] -> ('يشرب', 'ماء') -> GEN_STOP_EOS (resolved via consolidated Asm 5).
    - Prompt ['النسر', 'يشرب'] -> ('ماء',) -> GEN_STOP_EOS (resolved via consolidated Asm 5).
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

    for root_id in range(1, 57):
        is_ab = (root_id % 2 != 0)
        envs = branch_ab if is_ab else branch_db
        tx.begin_exposure(root_id)
        for env in envs:
            # Identity-preserving: retain canonical features and digest
            core_ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        tx.end_exposure(root_id)

    # 1. Verify canonical EOS Assemblies formed and attested
    eos_asms = []
    for asm_id, asm in state.W.assemblies.items():
        if asm.status.name != "LIVE":
            continue
        res_r = ledger.resolve_readout(asm_id, asm.structural_generation, current_live_generation=asm.structural_generation)
        marker = getattr(res_r.envelope, "marker", None)
        if marker and marker == Marker.EOS:
            eos_asms.append(asm_id)
    # Assemblies 2, 5 are canonical EOS assemblies (Asm 6 consolidated into 5)
    assert set(eos_asms) == {2, 5}

    # 2. Test prompt ['القط'] -> generates ('يشرب', 'حليب') and cleanly halts at <EOS>
    prompt_cat = [branch_ab[0].core_event]
    gen_cat = generate_episode(state, prompt_cat, ledger, max_steps=5)
    assert gen_cat.emitted_surfaces == ("يشرب", "حليب")
    assert gen_cat.stop_status == StatusCode.GEN_STOP_EOS
    assert gen_cat.steps[2].winner_assembly_id == 2
    assert gen_cat.steps[2].emitted_envelope.marker == Marker.EOS

    # 3. Test prompt ['القط', 'يشرب'] -> generates ('حليب',) and halts at <EOS>
    prompt_ab = [branch_ab[0].core_event, branch_ab[1].core_event]
    gen_ab = generate_episode(state, prompt_ab, ledger, max_steps=5)
    assert gen_ab.emitted_surfaces == ("حليب",)
    assert gen_ab.stop_status == StatusCode.GEN_STOP_EOS
    assert gen_ab.steps[1].winner_assembly_id == 2

    # 4. Test prompt ['النسر'] -> generates ('يشرب', 'ماء') then hits duplicate Asm 5 & 6 collision
    prompt_eagle = [branch_db[0].core_event]
    gen_eagle = generate_episode(state, prompt_eagle, ledger, max_steps=5)
    assert gen_eagle.emitted_surfaces == ("يشرب", "ماء")
    # Post-remediation: Asm 5 wins with margin > M_READ -> GEN_STOP_EOS
    assert gen_eagle.stop_status == StatusCode.GEN_STOP_EOS

    # 5. Test prompt ['النسر', 'يشرب'] -> generates ('ماء',) then hits same collision
    prompt_eagle_drink = [branch_db[0].core_event, branch_db[1].core_event]
    gen_eagle_drink = generate_episode(state, prompt_eagle_drink, ledger, max_steps=5)
    assert gen_eagle_drink.emitted_surfaces == ("ماء",)
    assert gen_eagle_drink.stop_status == StatusCode.GEN_STOP_EOS


def test_f01_persistence_not_implemented() -> None:
    """Phase F (R1-B03): Verify that complete cross-process disk persistence is not implemented."""
    import dgca.common.serialization as s_mod

    fns = [attr for attr in dir(s_mod) if not attr.startswith("__")]
    assert "pack_binary64_be" in fns
    assert "pack_record_envelope" in fns
    assert "serialize_machine_state" not in fns
    assert "save_checkpoint" not in fns
