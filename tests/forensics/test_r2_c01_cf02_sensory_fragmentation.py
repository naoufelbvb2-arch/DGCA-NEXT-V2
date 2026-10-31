"""Test suite for DGCA NEXT V2 — R2-C01-CF02 Controlled Sensory Fragmentation Experiment.

Verifies:
1. Single context is sufficient for duplicate assembly formation (Contradicts H1, Supports H2).
2. Sensory footprint under-recruitment permits independent duplicate sprouting (Supports H3).
3. Contextual frequency shifts modulate growth and competitive margins (Supports H4).
4. Structural multiplicity does not necessarily cause readout ambiguity (Contradicts H5).
"""

from __future__ import annotations

import dataclasses
import pytest

from dgca.core.assembly import compute_mutual_support_r_b
from dgca.core.generator import generate_episode
from dgca.core.readout import M_READ
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import MachineState
from dgca.encoder.envelope import encode_exposure
from dgca.lifecycle.exposure_tx import ExposureTransactionManager
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1
from tools.forensics.run_r2_c01_cf02_experiment import (
    CORPUS_GROUP_A,
    CORPUS_GROUP_B,
    train_and_instrument_group,
)


@pytest.fixture(scope="module")
def cf02_experiment_runs():
    group_a = train_and_instrument_group("Group A (Two Contexts)", CORPUS_GROUP_A, 112)
    group_b = train_and_instrument_group("Group B (Repeated Single Context)", CORPUS_GROUP_B, 112)
    return group_a, group_b


def test_cf02_single_context_multiplicity_contradicts_h1_and_supports_h2(cf02_experiment_runs):
    """Proves that multiple contexts are NOT necessary (H1 contradicted) and repeated

    single context is sufficient (H2 supported) for duplicate assembly formation.
    """
    group_a, group_b = cf02_experiment_runs

    # Inspect Group B (single context for 'ماء': S2 and S4 both 'النسر يشرب ماء')
    st_b = group_b["checkpoints"][112]["state"]
    led_b = group_b["checkpoints"][112]["ledger"]

    # Identify all assemblies resolving to 'ماء' in Group B
    water_asms_b = []
    for aid, asm in st_b.W.assemblies.items():
        res = led_b.resolve_readout(aid, asm.structural_generation)
        if res and res.envelope and res.envelope.surface_utf8_nfc == "ماء":
            water_asms_b.append((aid, asm))

    # Must find exactly 2 distinct assemblies for 'ماء' in Group B
    assert len(water_asms_b) == 2, f"Expected 2 assemblies for 'ماء' in Group B, found {len(water_asms_b)}"

    aid1, asm1 = water_asms_b[0]
    aid2, asm2 = water_asms_b[1]

    # Verify they have 0 mutual overlap (Jaccard = 0.0)
    inter = set(asm1.member_cell_ids) & set(asm2.member_cell_ids)
    assert len(inter) == 0, f"Assemblies {aid1} and {aid2} unexpectedly share cells: {inter}"

    # Verify both assemblies are 100% sensory cells of 'ماء'
    s2_water_ev = group_b["encoded_corpus"]["S2"][2]
    proj = project_core_event_v1(s2_water_ev.core_event)
    sensory_cells = set(proj.x_float_by_global_id.keys())
    assert len(sensory_cells) == 16

    assert set(asm1.member_cell_ids).issubset(sensory_cells)
    assert set(asm2.member_cell_ids).issubset(sensory_cells)


def test_cf02_sensory_coverage_and_triangle_sprouting_supports_h3(cf02_experiment_runs):
    """Proves that the initial assembly captures only part of the sensory footprint (18.75% -> 25%),

    leaving uncovered sensory cells (75%) that sprout a secondary assembly (H3 supported).
    """
    group_a, group_b = cf02_experiment_runs

    for g in (group_a, group_b):
        log = g["water_exposure_log"]
        # Exposure #7 (Root 14): Assembly 1 forms
        # Exposure #8 (Root 16): Assembly 2 forms
        exp7 = log[6]
        exp8 = log[7]

        assert exp7["root_id"] == 14
        assert exp8["root_id"] == 16

        # Before Root 16, covered cells are exactly 4 (out of 16), uncovered are 12
        assert len(exp8["covered_before"]) == 4
        assert len(exp8["uncovered_before"]) == 12

        # After Root 16, the second assembly recruited from the 12 uncovered cells
        # and grew by Root 18 to cover 11 total cells, leaving 5 uncovered
        exp9 = log[8]
        assert exp9["root_id"] == 18
        assert len(exp9["covered_before"]) == 11
        assert len(exp9["uncovered_before"]) == 5


def test_cf02_readout_competition_and_internal_control_evaluates_h4_and_h5(cf02_experiment_runs):
    """Proves that structural multiplicity does NOT necessarily cause readout ambiguity (H5 contradicted)

    as evidenced by 'تفاح' breaking symmetry at Root 112 in both groups.
    Also proves that contextual frequency changes alter assembly growth and margin (H4 supported).
    """
    group_a, group_b = cf02_experiment_runs

    # At Root 112, probe 'الطفل يأكل' (internal control 'تفاح')
    st_a_112 = group_a["checkpoints"][112]["state"]
    led_a_112 = group_a["checkpoints"][112]["ledger"]
    probe_apple_a = [group_a["encoded_corpus"]["S3"][0].core_event, group_a["encoded_corpus"]["S3"][1].core_event]
    res_a = generate_episode(st_a_112, probe_apple_a, led_a_112, max_steps=1)
    rr_a = res_a.steps[0].readout_result

    # Margin must exceed M_READ = 0.04, resolving cleanly (not AMBIGUOUS)
    assert rr_a.margin > M_READ, f"Group A 'تفاح' margin {rr_a.margin} did not exceed {M_READ}"
    assert rr_a.status.name == "OK"

    st_b_112 = group_b["checkpoints"][112]["state"]
    led_b_112 = group_b["checkpoints"][112]["ledger"]
    probe_apple_b = [group_b["encoded_corpus"]["S3"][0].core_event, group_b["encoded_corpus"]["S3"][1].core_event]
    res_b = generate_episode(st_b_112, probe_apple_b, led_b_112, max_steps=1)
    rr_b = res_b.steps[0].readout_result

    assert rr_b.margin > M_READ, f"Group B 'تفاح' margin {rr_b.margin} did not exceed {M_READ}"
    assert rr_b.status.name == "OK"

    # In Group B, changed contextual frequency widened the margin (0.0592 vs 0.0487)
    assert rr_b.margin > rr_a.margin
