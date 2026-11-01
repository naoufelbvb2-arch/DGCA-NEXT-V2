"""DGCA NEXT V2 — R2-C01-D02 Diagnostic Verification Tests.

Verifies:
- Test 1: Milk representation retention dynamics and contextual gating transition at Root 57 (Assembly 6 member count 7, mu gating of un-targeted members).
- Test 2: P1 Root 56 wrong-branch causation (generic verb drive from 'يشرب' to 'ماء' with Q ~ 0.76 vs weaker milk drive).
- Test 3: EOS continuation asymmetry between P2 and P4 at Root 112 (differential causal gain vs control pass saturation).
- Test 4: Negative controls (clean rejection of unseen lexical inputs, lawful subject-only continuation).
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

from dgca.common.errors import StatusCode
from dgca.core.anatomy import SynapseScope
from dgca.core.generator import generate_episode
from dgca.core.readout import THETA_READ, evaluate_full_vs_control_readout
from dgca.encoder.envelope import encode_exposure
from tools.forensics.run_r2_c01_d02_investigation import feed_prompt, run_training_stream


@pytest.fixture(scope="module")
def group_b_checkpoints():
    """Run training stream once for module tests up to Root 112."""
    gb = run_training_stream(
        enable_cross_clique_diversification=True,
        max_roots=112,
        checkpoint_roots=[56, 57, 60, 64, 112],
    )
    return gb["checkpoints"]


def test_1_milk_retention_and_context_gating(group_b_checkpoints):
    """Verify Assembly 6 retention history and the exact Root 57 contextual gating transition."""
    # 1. Size invariant: Assembly 6 has exactly 7 members across all checkpoints
    for r in [56, 57, 60, 64, 112]:
        st = group_b_checkpoints[r]["state"]
        asm6 = st.W.assemblies[6]
        assert len(asm6.member_cell_ids) == 7, f"Assembly 6 size changed at root {r}: {len(asm6.member_cell_ids)}"
        assert sorted(list(asm6.member_cell_ids)) == [9183, 9319, 9325, 10903, 11191, 11220, 11463]

    # 2. Before Root 57 (at Root 56): No stable bindings; all sensory sources unmuted (mu=0)
    st56 = group_b_checkpoints[56]["state"]
    assert len(st56.W.stable_bindings) == 0, "Expected zero stable bindings at Root 56"
    p_envs = encode_exposure("القط يشرب", append_eos=False)
    p_cores = [e.core_event for e in p_envs]
    st56_p1 = feed_prompt(st56, p_cores)
    assert all(m == 0 for m in st56_p1.R.mu_source_mask.values())
    rr56 = evaluate_full_vs_control_readout(st56_p1)
    asm6_score_56 = [s for s in rr56.ranked_scores if s.assembly_id == 6][0]
    assert asm6_score_56.score_next > 0.25, f"Expected score > 0.25 at Root 56, got {asm6_score_56.score_next}"
    assert asm6_score_56.eligible_member_count == 7

    # 3. At Root 57: Contextual cell 8320 graduates to an active StableBinding targeting only [9319, 9325]
    st57 = group_b_checkpoints[57]["state"]
    assert 8320 in st57.W.stable_bindings
    b8320 = st57.W.stable_bindings[8320]
    target_ids = sorted([k[1] for k in b8320.y_keys])
    assert target_ids == [9319, 9325], f"Expected targets [9319, 9325], got {target_ids}"

    # 4. At Root 64: Contextual gate sets mu=1 for sensory cells, muting 5 of 7 milk cells
    st64 = group_b_checkpoints[64]["state"]
    st64_p1 = feed_prompt(st64, p_cores)
    # Check that sensory cells of 'يشرب' are masked
    assert st64_p1.R.mu_source_mask.get(10167, 0) == 1
    assert st64_p1.R.mu_source_mask.get(10696, 0) == 1
    rr64 = evaluate_full_vs_control_readout(st64_p1)
    asm6_score_64 = [s for s in rr64.ranked_scores if s.assembly_id == 6][0]
    assert asm6_score_64.eligible_member_count == 2
    assert asm6_score_64.score_next < THETA_READ, f"Expected score < {THETA_READ}, got {asm6_score_64.score_next}"


def test_2_wrong_branch_p1_root56(group_b_checkpoints):
    """Verify wrong-branch causation at Root 56: generic verb drive dominates without subject binding."""
    st56 = group_b_checkpoints[56]["state"]
    p_envs = encode_exposure("القط يشرب", append_eos=False)
    p_cores = [e.core_event for e in p_envs]
    st56_p1 = feed_prompt(st56, p_cores)

    # Check incoming ASSOC synapses from 'يشرب' (10167) into Assembly 4 (water) vs Assembly 6 (milk)
    w = st56.W
    syn_water = w.synapses.get((10167, 8242, SynapseScope.ASSOCIATIVE))
    syn_milk = w.synapses.get((10167, 11191, SynapseScope.ASSOCIATIVE))
    assert syn_water is not None and syn_water.Q > 0.70
    assert syn_milk is not None and syn_milk.Q < 0.45

    # Assembly 4 wins over Assembly 6 by a wide margin
    rr = evaluate_full_vs_control_readout(st56_p1)
    sc4 = [s for s in rr.ranked_scores if s.assembly_id == 4][0].score_next
    sc6 = [s for s in rr.ranked_scores if s.assembly_id == 6][0].score_next
    assert sc4 > 0.60
    assert sc6 < 0.35
    assert sc4 - sc6 > 0.30


def test_3_eos_continuation_asymmetry_root112(group_b_checkpoints):
    """Verify EOS continuation asymmetry at Root 112 (P2 NO_MATCH vs P4 EOS)."""
    st112 = group_b_checkpoints[112]["state"]
    led112 = group_b_checkpoints[112]["ledger"]

    # P4: autonomous generation achieves EOS
    envs4 = encode_exposure("الطفل يشرب", append_eos=False)
    res4 = generate_episode(st112.clone(), [e.core_event for e in envs4], led112, max_steps=4)
    assert res4.stop_status == StatusCode.GEN_STOP_EOS
    assert res4.emitted_surfaces == ("ماء",)
    assert res4.steps[1].winner_assembly_id == 1  # EOS assembly won

    # P2: autonomous generation emits 'ماء' then halts with NO_MATCH
    envs2 = encode_exposure("النسر يشرب", append_eos=False)
    res2 = generate_episode(st112.clone(), [e.core_event for e in envs2], led112, max_steps=4)
    assert res2.stop_status == StatusCode.GEN_STOP_NO_MATCH
    assert res2.emitted_surfaces == ("ماء",)
    assert res2.steps[1].winner_assembly_id is None

    # Step 1 causal gain inspection:
    # P4 step 1 control pass has a_ctrl == 0.0 on EOS cells
    # P2 step 1 control pass has a_ctrl > 0.85 on EOS cells due to lingering pre-activation
    rr1_p4 = res4.steps[1].readout_result
    rr1_p2 = res2.steps[1].readout_result

    # Cell 8728 is an EOS member
    assert rr1_p4.a_control_by_cell.get(8728, 0.0) == 0.0
    assert rr1_p2.a_control_by_cell.get(8728, 0.0) > 0.85
    assert rr1_p4.gain_by_cell.get(8728, 0.0) > 0.50
    assert rr1_p2.gain_by_cell.get(8728, 0.0) < 0.05


def test_4_negative_controls_and_zero_leakage(group_b_checkpoints):
    """Verify negative controls: zero false positives on unseen input and lawful subject-only prediction."""
    st112 = group_b_checkpoints[112]["state"]
    led112 = group_b_checkpoints[112]["ledger"]

    # Negative Control 1: Unseen lexical input produces clean NO_MATCH
    envs_unseen = encode_exposure("حصان يركض", append_eos=False)
    st_u = feed_prompt(st112, [e.core_event for e in envs_unseen])
    rr_u = evaluate_full_vs_control_readout(st_u)
    assert rr_u.status == StatusCode.NO_MATCH
    assert rr_u.top_score == 0.0
    assert rr_u.winner_assembly_id is None

    # Negative Control 2: Subject-only "القط" correctly predicts "يشرب"
    envs_cat = encode_exposure("القط", append_eos=False)
    st_cat = feed_prompt(st112, [e.core_event for e in envs_cat])
    rr_cat = evaluate_full_vs_control_readout(st_cat)
    assert rr_cat.status == StatusCode.OK
    assert rr_cat.winner_assembly_id == 3  # Assembly 3 is "يشرب"
    res_led = led112.resolve_readout(rr_cat.winner_assembly_id, rr_cat.winner_generation)
    assert res_led.envelope.surface_utf8_nfc == "يشرب"
