"""Forensic Investigation Phase C, E, and F: COLD_START, GATE CLASSIFICATION, AND PERSISTENCE.

Investigates:
- Phase C: Cold-start learning from zero (34 and 56 roots)
- Phase E: Gate A-E evidence classifications and scientific gap analysis (R1-H01, R1-H02, R1-H03)
- Phase F: Persistence contract verification (R1-B03)
"""

from __future__ import annotations

import pytest
from dgca.common.errors import StatusCode
from dgca.core.generator import generate_episode
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import MachineState
from dgca.encoder.envelope import encode_exposure, encode_lexical_token_event
from dgca.experiments.gates import _extract_f0_cells, run_gate_c_learn_from_zero_and_rc4_1_subgate
from dgca.lifecycle.exposure_tx import ExposureTransactionManager, compute_pred_score, run_read_only_episode
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1


def test_f01_cold_start_learning_checkpoints_34_and_56() -> None:
    """Phase C: Cold start learning verification of AB->C vs DB->E at roots 34 and 56."""
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
            # Checkpoint 34
            ro_ab_34 = run_read_only_episode(state, [branch_ab[0].core_event, branch_ab[1].core_event])
            _, p_c_ab_34 = compute_pred_score(ro_ab_34.next_step_pt_by_cell, f0_c)
            _, p_e_ab_34 = compute_pred_score(ro_ab_34.next_step_pt_by_cell, f0_e)
            assert p_c_ab_34 > p_e_ab_34

            # Generation on prompt AB at root 34 fails due to dilution (score < 0.08)
            gen_ab_34 = generate_episode(state, [branch_ab[0].core_event, branch_ab[1].core_event], ledger, max_steps=3)
            assert gen_ab_34.emitted_surfaces == (), "Root 34 Gen AB failed to emit surfaces due to dilution"

        elif root_id == 56:
            # Checkpoint 56
            ro_ab_56 = run_read_only_episode(state, [branch_ab[0].core_event, branch_ab[1].core_event])
            _, p_c_ab_56 = compute_pred_score(ro_ab_56.next_step_pt_by_cell, f0_c)
            _, p_e_ab_56 = compute_pred_score(ro_ab_56.next_step_pt_by_cell, f0_e)
            assert p_c_ab_56 > p_e_ab_56

            # Generation on prompt AB at root 56 emits single word 'حليب'
            gen_ab_56 = generate_episode(state, [branch_ab[0].core_event, branch_ab[1].core_event], ledger, max_steps=3)
            gen_db_56 = generate_episode(state, [branch_db[0].core_event, branch_db[1].core_event], ledger, max_steps=3)
            assert gen_ab_56.emitted_surfaces == ("حليب",)
            assert gen_db_56.emitted_surfaces == ("ماء",)
            # Both stop with NO_MATCH at step 1 because no EOS assembly exists
            assert gen_ab_56.stop_status == StatusCode.GEN_STOP_NO_MATCH
            assert gen_db_56.stop_status == StatusCode.GEN_STOP_NO_MATCH


def test_f01_persistence_not_implemented() -> None:
    """Phase F (R1-B03): Verify that complete cross-process disk persistence is not implemented."""
    import dgca.common.serialization as s_mod

    # Inspect functions available in serialization.py
    fns = [attr for attr in dir(s_mod) if not attr.startswith("__")]
    
    # Must only contain binary64 and record envelope packers
    assert "pack_binary64_be" in fns
    assert "pack_record_envelope" in fns

    # High-level state serializers do NOT exist
    assert "serialize_machine_state" not in fns
    assert "deserialize_machine_state" not in fns
    assert "serialize_w_state" not in fns
    assert "deserialize_w_state" not in fns
    assert "save_checkpoint" not in fns
    assert "load_checkpoint" not in fns

    # Verdict: CROSS_PROCESS_PERSISTENCE_NOT_IMPLEMENTED
    persistence_implemented = hasattr(s_mod, "serialize_machine_state")
    assert persistence_implemented is False, "Expected cross-process persistence to be absent"
