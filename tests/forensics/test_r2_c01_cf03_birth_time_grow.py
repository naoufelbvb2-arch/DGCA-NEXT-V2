"""Test suite for DGCA NEXT V2 — R2-C01-CF03 Bounded Birth-Time Structural Reuse Counterfactual.

Verifies:
1. Birth-time grow accelerates membership commit to the birth root close (Roots 14 and 16).
2. Duplicate assembly formation persists (Null effect on representational fragmentation).
3. Readout competition and ambiguity margins remain structurally invariant.
4. Transactional atomicity and shadow rollback are strictly preserved under failure injection.
"""

from __future__ import annotations

import dataclasses
import pytest

from dgca.common.errors import StatusCode, DGCAError
from dgca.core.readout import M_READ
from dgca.core.state import MachineState
from dgca.encoder.envelope import encode_exposure
from dgca.lifecycle.exposure_tx import ExposureTransactionManager
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1
from tools.forensics.run_r2_c01_cf03_experiment import (
    CORPUS,
    train_and_instrument_cf03,
    evaluate_probes,
)


@pytest.fixture(scope="module")
def cf03_runs():
    group_a = train_and_instrument_cf03("Group A (Frozen Baseline)", enable_birth_time_grow=False, total_roots=112)
    group_b = train_and_instrument_cf03("Group B (Experimental Birth-Time Growth)", enable_birth_time_grow=True, total_roots=112)
    return group_a, group_b


def test_cf03_birth_time_grow_accelerates_membership_commit(cf03_runs):
    """Verify that Group B commits pre-consolidated structural growth at birth-root close."""
    group_a, group_b = cf03_runs

    # At Root 14 close:
    # Group A: Assembly 7 is Gen 1, size 3
    asms_a_14 = group_a["checkpoints"][14]["assembly_snapshot"]
    assert asms_a_14[7]["gen"] == 1
    assert len(asms_a_14[7]["members"]) == 3

    # Group B: Assembly 7 is Gen 2, size 4 (recruited 11984 at birth close)
    asms_b_14 = group_b["checkpoints"][14]["assembly_snapshot"]
    assert asms_b_14[7]["gen"] == 2
    assert len(asms_b_14[7]["members"]) == 4
    assert 11984 in asms_b_14[7]["members"]

    # At Root 16 close:
    # Group A: Assembly 9 is Gen 1, size 3
    asms_a_16 = group_a["checkpoints"][16]["assembly_snapshot"]
    assert asms_a_16[9]["gen"] == 1
    assert len(asms_a_16[9]["members"]) == 3

    # Group B: Assembly 9 is Gen 5, size 7 (recruited 4 candidate cells at birth close)
    asms_b_16 = group_b["checkpoints"][16]["assembly_snapshot"]
    assert asms_b_16[9]["gen"] == 5
    assert len(asms_b_16[9]["members"]) == 7


def test_cf03_duplicate_assembly_formation_persists_confirming_null_effect(cf03_runs):
    """Verify that accelerating growth to birth time does NOT prevent secondary duplicate assembly formation."""
    group_a, group_b = cf03_runs

    for g in (group_a, group_b):
        water_asms = [a for a in g["known_asms"].values() if a["surface"] == "ماء"]
        apple_asms = [a for a in g["known_asms"].values() if a["surface"] == "تفاح"]

        # Exactly 2 assemblies for 'ماء' in BOTH groups
        assert len(water_asms) == 2, f"Expected 2 assemblies for 'ماء' in {g['group_name']}, found {len(water_asms)}"
        # Exactly 2 assemblies for 'تفاح' in BOTH groups
        assert len(apple_asms) == 2, f"Expected 2 assemblies for 'تفاح' in {g['group_name']}, found {len(apple_asms)}"

        # Verify Jaccard overlap between Assembly 7 and 9 remains 0.0000
        mem7 = set(g["checkpoints"][112]["state"].W.assemblies[7].member_cell_ids)
        mem9 = set(g["checkpoints"][112]["state"].W.assemblies[9].member_cell_ids)
        assert len(mem7 & mem9) == 0


def test_cf03_readout_competition_and_ambiguity_invariance(cf03_runs):
    """Verify readout competition and margin outcomes are identical across Group A and Group B."""
    group_a, group_b = cf03_runs

    for r in [56, 112]:
        probes_a = evaluate_probes(group_a, r)
        probes_b = evaluate_probes(group_b, r)

        for p_name in ["P2 (النسر يشرب)", "P3 (الطفل يأكل)", "P4 (الطفل يشرب)"]:
            res_a = probes_a[p_name]
            res_b = probes_b[p_name]

            assert res_a["first_step_stop_status"] == res_b["first_step_stop_status"]
            assert res_a["first_step_readout_status"] == res_b["first_step_readout_status"]
            assert pytest.approx(res_a["margin"], abs=1e-5) == res_b["margin"]
            assert pytest.approx(res_a["top_score"], abs=1e-5) == res_b["top_score"]


def test_cf03_transactional_atomicity_and_rollback():
    """Verify that failure injection during exposure transaction with enable_birth_time_grow=True preserves atomic rollback."""
    state = MachineState()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        enable_birth_time_grow=True,
    )
    tx._fault_injection_point = "FP_01"

    tx.begin_exposure(1)
    ev_list = encode_exposure("النسر يشرب ماء", append_eos=True)
    for env in ev_list:
        tx.process_event(env.core_event, peripheral_envelope=env.peripheral_surface)

    # Injected fault at FP-01 must abort cleanly
    with pytest.raises(RuntimeError, match="FP-01"):
        tx.end_exposure(1)

    # State.W must not contain partial commitments from Root 1
    assert state.W.completed_roots_high_watermark == 0
    assert len(state.W.assemblies) == 0
