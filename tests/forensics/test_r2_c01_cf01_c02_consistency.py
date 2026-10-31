"""Automated evidence consistency verification suite for R2-C01-CF01-C02.

Validates:
1. Assembly membership sets, non-overlap, and Jaccard calculations for Group B (7 vs 9, 14 vs 17).
2. Canonical experimental prompts (P1-P4) and absence of unauthorized substitutions ('الرجل').
3. Strict stop-code categorization (distinguishing READOUT_UNKNOWN from NO_MATCH).
4. Ledger row and attestation counts across checkpoints.
"""

from __future__ import annotations

import pytest
from dgca.common.errors import StatusCode
from dgca.core.generator import generate_episode
from tools.forensics.run_r2_c01_cf01_experiment import (
    CORPUS_GROUP_A,
    CORPUS_GROUP_B,
    train_and_instrument,
)
from tools.forensics.run_r2_c01_trial import capture_telemetry, train_trial


@pytest.fixture(scope="module")
def group_b_checkpoints():
    checkpoints, _, enc = train_and_instrument(CORPUS_GROUP_B, 112)
    return checkpoints, enc


@pytest.fixture(scope="module")
def group_a_checkpoints():
    checkpoints, _, enc = train_and_instrument(CORPUS_GROUP_A, 112)
    return checkpoints, enc


def test_task_a_assembly_membership_and_disjointness(group_b_checkpoints):
    """Verify exact membership, disjoint intersection, and 0.0 Jaccard for Group B duplicate assemblies."""
    checkpoints, _ = group_b_checkpoints
    
    for root in (56, 112):
        state = checkpoints[root]["state"]
        asms = state.W.assemblies
        
        # Pair 1: Assemblies 7 and 9 ('ماء')
        asm7 = asms[7]
        asm9 = asms[9]
        assert asm7.structural_generation == 2
        assert asm9.structural_generation == 5
        set7 = set(asm7.member_cell_ids)
        set9 = set(asm9.member_cell_ids)
        assert len(set7) == 4
        assert len(set9) == 7
        assert set7 == {8242, 9854, 11638, 11984}
        assert set9 == {8809, 9734, 9740, 10044, 10308, 10634, 11193}
        assert set7.isdisjoint(set9), f"Intersection non-empty: {set7 & set9}"
        assert len(set7 | set9) == 11
        
        # Pair 2: Assemblies 14 and 17 ('تفاح')
        asm14 = asms[14]
        asm17 = asms[17]
        assert asm14.structural_generation == 2
        assert asm17.structural_generation == 5
        set14 = set(asm14.member_cell_ids)
        set17 = set(asm17.member_cell_ids)
        assert len(set14) == 4
        assert len(set17) == 7
        assert set14 == {9334, 9468, 10457, 11289}
        assert set17 == {8513, 8961, 10181, 10363, 10616, 10737, 11830}
        
        # Specific regression check: cell 10457 must be in 14, NOT in 17
        assert 10457 in set14
        assert 10457 not in set17
        assert set14.isdisjoint(set17), f"Intersection non-empty: {set14 & set17}"
        assert len(set14 | set17) == 11


def test_task_b_canonical_prompts_and_absence_of_man_substitution():
    """Verify canonical prompt sentences and ensure 'الرجل' is never present in the corpus."""
    expected_a = {
        "S1": "القط يشرب الحليب",
        "S2": "النسر يشرب الماء",
        "S3": "الطفل يأكل التفاح",
        "S4": "الطفل يشرب الماء",
    }
    expected_b = {
        "S1": "القط يشرب حليب",
        "S2": "النسر يشرب ماء",
        "S3": "الطفل يأكل تفاح",
        "S4": "الطفل يشرب ماء",
    }
    assert CORPUS_GROUP_A == expected_a
    assert CORPUS_GROUP_B == expected_b
    
    # Verify unauthorized substitutions do not appear anywhere in corpora
    for corpus in (CORPUS_GROUP_A, CORPUS_GROUP_B):
        for text in corpus.values():
            assert "الرجل" not in text, f"Unauthorized prompt word 'الرجل' in {text}"


def test_task_b_group_a_root_56_stop_codes(group_a_checkpoints):
    """Verify Group A Root 56 generation stop codes, explicitly asserting READOUT_UNKNOWN on P2."""
    checkpoints, enc = group_a_checkpoints
    state = checkpoints[56]["state"]
    ledger = checkpoints[56]["ledger"]
    
    p1 = [enc["S1"][0].core_event, enc["S1"][1].core_event]
    p2 = [enc["S2"][0].core_event, enc["S2"][1].core_event]
    p3 = [enc["S3"][0].core_event, enc["S3"][1].core_event]
    p4 = [enc["S4"][0].core_event, enc["S4"][1].core_event]
    
    res1 = generate_episode(state, p1, ledger, max_steps=4)
    res2 = generate_episode(state, p2, ledger, max_steps=4)
    res3 = generate_episode(state, p3, ledger, max_steps=4)
    res4 = generate_episode(state, p4, ledger, max_steps=4)
    
    assert res1.stop_status == StatusCode.GEN_STOP_NO_MATCH
    assert res1.emitted_surfaces == ()
    
    assert res2.stop_status == StatusCode.GEN_STOP_READOUT_UNKNOWN
    assert res2.emitted_surfaces == ("الماء",)
    
    assert res3.stop_status == StatusCode.GEN_STOP_NO_MATCH
    assert res3.emitted_surfaces == ("التفاح",)
    
    assert res4.stop_status == StatusCode.GEN_STOP_NO_MATCH
    assert res4.emitted_surfaces == ("الماء",)
    
    # Stop-code distribution check
    statuses = [res1.stop_status, res2.stop_status, res3.stop_status, res4.stop_status]
    assert statuses.count(StatusCode.GEN_STOP_NO_MATCH) == 3
    assert statuses.count(StatusCode.GEN_STOP_READOUT_UNKNOWN) == 1
    assert statuses.count(StatusCode.GEN_STOP_AMBIGUOUS) == 0


def test_task_b_group_b_root_56_and_112_outcomes(group_b_checkpoints):
    """Verify Group B stop codes and emitted tokens at Root 56 and 112."""
    checkpoints, enc = group_b_checkpoints
    
    # Root 56: P1 is NO_MATCH; P2, P3, P4 are AMBIGUOUS
    st56 = checkpoints[56]["state"]
    led56 = checkpoints[56]["ledger"]
    probes_56 = {
        "P1": [enc["S1"][0].core_event, enc["S1"][1].core_event],
        "P2": [enc["S2"][0].core_event, enc["S2"][1].core_event],
        "P3": [enc["S3"][0].core_event, enc["S3"][1].core_event],
        "P4": [enc["S4"][0].core_event, enc["S4"][1].core_event],
    }
    r56_p1 = generate_episode(st56, probes_56["P1"], led56, max_steps=4)
    r56_p2 = generate_episode(st56, probes_56["P2"], led56, max_steps=4)
    r56_p3 = generate_episode(st56, probes_56["P3"], led56, max_steps=4)
    r56_p4 = generate_episode(st56, probes_56["P4"], led56, max_steps=4)
    
    assert r56_p1.stop_status == StatusCode.GEN_STOP_NO_MATCH
    assert r56_p2.stop_status == StatusCode.GEN_STOP_AMBIGUOUS
    assert r56_p3.stop_status == StatusCode.GEN_STOP_AMBIGUOUS
    assert r56_p4.stop_status == StatusCode.GEN_STOP_AMBIGUOUS
    assert r56_p1.emitted_surfaces == ()
    assert r56_p2.emitted_surfaces == ()
    assert r56_p3.emitted_surfaces == ()
    assert r56_p4.emitted_surfaces == ()
    
    # Root 112: P1 emits 'حليب', P3 emits 'تفاح'; P2 and P4 remain AMBIGUOUS
    st112 = checkpoints[112]["state"]
    led112 = checkpoints[112]["ledger"]
    r112_p1 = generate_episode(st112, probes_56["P1"], led112, max_steps=4)
    r112_p2 = generate_episode(st112, probes_56["P2"], led112, max_steps=4)
    r112_p3 = generate_episode(st112, probes_56["P3"], led112, max_steps=4)
    r112_p4 = generate_episode(st112, probes_56["P4"], led112, max_steps=4)
    
    assert r112_p1.stop_status == StatusCode.GEN_STOP_NO_MATCH
    assert r112_p1.emitted_surfaces == ("حليب",)
    assert r112_p2.stop_status == StatusCode.GEN_STOP_AMBIGUOUS
    assert r112_p2.emitted_surfaces == ()
    assert r112_p3.stop_status == StatusCode.GEN_STOP_NO_MATCH
    assert r112_p3.emitted_surfaces == ("تفاح",)
    assert r112_p4.stop_status == StatusCode.GEN_STOP_AMBIGUOUS
    assert r112_p4.emitted_surfaces == ()


def test_task_c_ledger_counts_canonical_reconciliation(group_a_checkpoints):
    """Verify that ledger candidate rows and attestations match runtime state across both scripts."""
    checkpoints_a, _ = group_a_checkpoints
    
    # Query CF-1 Group A
    t_cf_56 = capture_telemetry(checkpoints_a[56]["state"], checkpoints_a[56]["ledger"], 56)
    t_cf_112 = capture_telemetry(checkpoints_a[112]["state"], checkpoints_a[112]["ledger"], 112)
    
    rows_56 = t_cf_56["ledger_rows"]
    att_56 = [r for r in rows_56.values() if r["is_attested"]]
    assert len(rows_56) == 31
    assert len(att_56) == 25
    
    rows_112 = t_cf_112["ledger_rows"]
    att_112 = [r for r in rows_112.values() if r["is_attested"]]
    assert len(rows_112) == 31
    assert len(att_112) == 27
