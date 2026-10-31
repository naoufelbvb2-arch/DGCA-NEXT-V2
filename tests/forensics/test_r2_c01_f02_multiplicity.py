"""Automated verification suite for R2-C01-F02 representational multiplicity.

Validates:
1. Sensory partition: Member cells of Assemblies 7, 9, 14, 17 belong 100% to the SIC-V1 sensory projection of 'ماء' and 'تفاح'.
2. Structural disjointness: Jaccard similarity is 0.0 between duplicates of the same word.
3. Predecessor connectivity: Incoming associative synapses originate strictly from the immediate predecessor word (verb), with zero direct connections from subjects.
4. Non-specialization: Readout scores for Assemblies 7 and 9 are invariant to subject context (P2 vs P4).
5. Self-competition: Readout margin between duplicates is below M_READ (0.04), inducing AMBIGUOUS halts.
"""

from __future__ import annotations

import pytest
from dgca.common.errors import StatusCode
from dgca.core.generator import generate_episode
from dgca.core.readout import M_READ
from dgca.core.sic_v1 import project_core_event_v1
from tools.forensics.run_r2_c01_cf01_experiment import CORPUS_GROUP_B, train_and_instrument


@pytest.fixture(scope="module")
def group_b_data():
    checkpoints, _, enc = train_and_instrument(CORPUS_GROUP_B, 112)
    return checkpoints, enc


def test_f02_sensory_partition_of_duplicate_assemblies(group_b_data):
    """Verify that Assemblies 7 & 9 partition 'ماء' sensory cells, and 14 & 17 partition 'تفاح' sensory cells."""
    checkpoints, enc = group_b_data
    state = checkpoints[56]["state"]
    asms = state.W.assemblies

    s2_water_ev = enc["S2"][2]
    s3_apple_ev = enc["S3"][2]

    water_sensory = set(project_core_event_v1(s2_water_ev.core_event).x_float_by_global_id.keys())
    apple_sensory = set(project_core_event_v1(s3_apple_ev.core_event).x_float_by_global_id.keys())

    assert len(water_sensory) == 16
    assert len(apple_sensory) == 16

    # Case 1: 'ماء'
    set7 = set(asms[7].member_cell_ids)
    set9 = set(asms[9].member_cell_ids)
    assert set7.issubset(water_sensory), f"Non-sensory cells in Asm 7: {set7 - water_sensory}"
    assert set9.issubset(water_sensory), f"Non-sensory cells in Asm 9: {set9 - water_sensory}"
    assert set7.isdisjoint(set9)
    assert len(set7 | set9) == 11  # 4 + 7 = 11 of 16 sensory cells

    # Case 2: 'تفاح'
    set14 = set(asms[14].member_cell_ids)
    set17 = set(asms[17].member_cell_ids)
    assert set14.issubset(apple_sensory), f"Non-sensory cells in Asm 14: {set14 - apple_sensory}"
    assert set17.issubset(apple_sensory), f"Non-sensory cells in Asm 17: {set17 - apple_sensory}"
    assert set14.isdisjoint(set17)
    assert len(set14 | set17) == 11  # 4 + 7 = 11 of 16 sensory cells


def test_f02_predecessor_connectivity_and_zero_subject_wiring(group_b_data):
    """Verify that incoming associative synapses originate from predecessor verb, not subjects."""
    checkpoints, _ = group_b_data
    state = checkpoints[56]["state"]
    w = state.W

    # Members of subject assemblies
    eagle_asm = w.assemblies[12]  # 'النسر'
    child_asm = w.assemblies[8]   # 'الطفل'
    subject_cells = set(eagle_asm.member_cell_ids) | set(child_asm.member_cell_ids)

    # Verb assemblies
    drink_cells = set(w.assemblies[5].member_cell_ids) | set(w.assemblies[6].member_cell_ids)

    # Check incoming synapses to Assemblies 7 and 9
    water_asm_cells = set(w.assemblies[7].member_cell_ids) | set(w.assemblies[9].member_cell_ids)
    incoming_water_syns = [
        s for s in w.synapses.values()
        if s.target_id in water_asm_cells and s.scope.name == "ASSOCIATIVE"
    ]

    # Verify zero incoming synapses from subject cells
    subject_to_water = [s for s in incoming_water_syns if s.source_id in subject_cells]
    assert len(subject_to_water) == 0, f"Found unexpected subject-to-water synapses: {subject_to_water}"

    # Verify all incoming synapses originate from 'يشرب' verb cells
    for s in incoming_water_syns:
        assert s.source_id in drink_cells, f"Synapse {s.source_id}->{s.target_id} does not originate from drink verb"


def test_f02_non_specialization_context_invariance(group_b_data):
    """Verify that Assembly 7 and 9 readout scores are context-invariant across P2 (eagle) and P4 (child)."""
    checkpoints, enc = group_b_data
    st56 = checkpoints[56]["state"]
    led56 = checkpoints[56]["ledger"]

    p2 = [enc["S2"][0].core_event, enc["S2"][1].core_event]
    p4 = [enc["S4"][0].core_event, enc["S4"][1].core_event]

    res_p2 = generate_episode(st56, p2, led56, max_steps=1)
    res_p4 = generate_episode(st56, p4, led56, max_steps=1)

    rr_p2 = res_p2.steps[0].readout_result
    rr_p4 = res_p4.steps[0].readout_result

    scores_p2 = {c.assembly_id: c.score_next for c in rr_p2.ranked_scores}
    scores_p4 = {c.assembly_id: c.score_next for c in rr_p4.ranked_scores}

    # Scores must be virtually identical across both contexts
    assert abs(scores_p2[7] - scores_p4[7]) < 0.0001
    assert abs(scores_p2[9] - scores_p4[9]) < 0.0001

    # Both must halt on AMBIGUOUS due to margin < 0.04
    assert res_p2.stop_status == StatusCode.GEN_STOP_AMBIGUOUS
    assert res_p4.stop_status == StatusCode.GEN_STOP_AMBIGUOUS
    assert rr_p2.margin < M_READ
    assert rr_p4.margin < M_READ
