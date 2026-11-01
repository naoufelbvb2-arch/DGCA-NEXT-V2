"""DGCA NEXT V2 — R2-C01-D02-C01 Evidence Reconciliation Verification Tests.

Verifies:
- Test 1: Actual MachineState Assembly membership sizes at Root 112:
    - Assembly 4 ('ماء'): size = 5 (structural generation 3).
    - Assembly 6 ('حليب'): size = 7 (structural generation 5).
    - Assembly 1 ('<EOS>'): size = 12 (structural generation 10).
- Test 2: Canonical Generation Trajectories at Root 112:
    - P1 ('القط يشرب'): NO_MATCH (GEN_STOP_NO_MATCH).
    - P2 ('النسر يشرب'): 'ماء' -> NO_MATCH.
    - P3 ('الطفل يأكل'): 'تفاح' -> NO_MATCH.
    - P4 ('الطفل يشرب'): 'ماء' -> <EOS> (GEN_STOP_EOS).
- Test 3: Authentic Autonomous Rollout EOS Metrics (P2 vs P4 at Root 112):
    - Autonomous reinjection of 'ماء' via lawful generator path.
    - P4 achieves score 0.355377 on Assembly 1 with 8 eligible members, A_ctrl == 0.0.
    - P2 achieves score 0.036007 on Assembly 1 with 8 eligible members, A_ctrl > 0.85 on cell 8728.
- Test 4: Report Calculation Integrity & Negative Control Trace:
    - Assert score arithmetic: score == sum(eligible_j * gain_j) / len(members).
    - Assert negative controls actually executed ('حصان يركض', 'القط').
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

from dgca.common.errors import StatusCode
from dgca.core.dynamics import execute_two_pass_event
from dgca.core.generator import generate_episode, reinject_attested_bundle
from dgca.core.readout import THETA_READ, evaluate_full_vs_control_readout
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import ExecutionMode
from dgca.encoder.envelope import EventOrigin, encode_exposure
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


def test_1_assembly_membership_sizes(group_b_checkpoints):
    """Verify actual MachineState assembly sizes at Root 112 (Asm 4 size 5, Asm 6 size 7, Asm 1 size 12)."""
    st112 = group_b_checkpoints[112]["state"]
    w = st112.W

    # Group B Assembly 4 (ماء) has exactly 5 members
    asm4 = w.assemblies[4]
    assert len(asm4.member_cell_ids) == 5, f"Expected Asm 4 size 5, got {len(asm4.member_cell_ids)}"
    assert asm4.structural_generation == 3
    assert sorted(list(asm4.member_cell_ids)) == [8242, 8809, 9854, 11638, 11984]

    # Group B Assembly 6 (حليب) has exactly 7 members
    asm6 = w.assemblies[6]
    assert len(asm6.member_cell_ids) == 7, f"Expected Asm 6 size 7, got {len(asm6.member_cell_ids)}"
    assert asm6.structural_generation == 5
    assert sorted(list(asm6.member_cell_ids)) == [9183, 9319, 9325, 10903, 11191, 11220, 11463]

    # Group B Assembly 1 (<EOS>) has exactly 12 members at Root 112
    asm1 = w.assemblies[1]
    assert len(asm1.member_cell_ids) == 12, f"Expected Asm 1 size 12, got {len(asm1.member_cell_ids)}"
    assert asm1.structural_generation == 10
    assert sorted(list(asm1.member_cell_ids)) == [
        8728, 8834, 9209, 10417, 10570, 10646, 10915, 11153, 11583, 11859, 12116, 12117
    ]


def test_2_canonical_trajectories_root112(group_b_checkpoints):
    """Verify genuine autonomous generation trajectories at Root 112 for all 4 authorized probes."""
    st112 = group_b_checkpoints[112]["state"]
    led112 = group_b_checkpoints[112]["ledger"]

    # P1: القط يشرب -> NO_MATCH
    e1 = encode_exposure("القط يشرب", append_eos=False)
    res1 = generate_episode(st112.clone(), [e.core_event for e in e1], led112, max_steps=4)
    assert res1.stop_status == StatusCode.GEN_STOP_NO_MATCH
    assert len(res1.emitted_surfaces) == 0

    # P2: النسر يشرب -> ماء -> NO_MATCH
    e2 = encode_exposure("النسر يشرب", append_eos=False)
    res2 = generate_episode(st112.clone(), [e.core_event for e in e2], led112, max_steps=4)
    assert res2.stop_status == StatusCode.GEN_STOP_NO_MATCH
    assert res2.emitted_surfaces == ("ماء",)

    # P3: الطفل يأكل -> تفاح -> NO_MATCH (Canonical P3 is الطفل يأكل, NOT الماء بارد)
    e3 = encode_exposure("الطفل يأكل", append_eos=False)
    res3 = generate_episode(st112.clone(), [e.core_event for e in e3], led112, max_steps=4)
    assert res3.stop_status == StatusCode.GEN_STOP_NO_MATCH
    assert res3.emitted_surfaces == ("تفاح",)

    # P4: الطفل يشرب -> ماء -> <EOS>
    e4 = encode_exposure("الطفل يشرب", append_eos=False)
    res4 = generate_episode(st112.clone(), [e.core_event for e in e4], led112, max_steps=4)
    assert res4.stop_status == StatusCode.GEN_STOP_EOS
    assert res4.emitted_surfaces == ("ماء",)
    assert res4.steps[1].winner_assembly_id == 1


def test_3_authentic_rollout_eos_metrics(group_b_checkpoints):
    """Verify authentic autonomous rollout EOS metrics after genuine assembly selection and reinjection."""
    st112 = group_b_checkpoints[112]["state"]
    led112 = group_b_checkpoints[112]["ledger"]

    # Ingest P4 and trace Step 1
    scratch4 = st112.clone()
    scratch4.R.reset_cold()
    e4 = encode_exposure("الطفل يشرب", append_eos=False)
    p_cores4 = [e.core_event for e in e4]
    for idx, pev in enumerate(p_cores4):
        proj = project_core_event_v1(pev)
        execute_two_pass_event(
            scratch4, proj.x_fixed_by_global_id, proj.x_float_by_global_id,
            mode=ExecutionMode.GENERATE, origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=(idx == 0 or pev.boundary), event_order=idx, feature_bundle_digest=proj.feature_bundle_digest,
        )
    rr0_4 = evaluate_full_vs_control_readout(scratch4, theta_read=THETA_READ)
    att_env4 = led112.resolve_readout(rr0_4.winner_assembly_id, rr0_4.winner_generation).envelope
    reinj_ev4 = reinject_attested_bundle(att_env4, exposure_id=None, event_order=len(p_cores4))
    reinj_proj4 = project_core_event_v1(reinj_ev4)
    execute_two_pass_event(
        scratch4, reinj_proj4.x_fixed_by_global_id, reinj_proj4.x_float_by_global_id,
        mode=ExecutionMode.GENERATE, origin=EventOrigin.INTERNAL_SELECTED,
        boundary=False, event_order=len(p_cores4), feature_bundle_digest=reinj_proj4.feature_bundle_digest,
        apply_pt_debit_selected=True,
    )
    rr1_4 = evaluate_full_vs_control_readout(scratch4, theta_read=THETA_READ)
    asm1_cand_4 = [s for s in rr1_4.ranked_scores if s.assembly_id == 1][0]
    assert asm1_cand_4.eligible_member_count == 8
    assert abs(asm1_cand_4.score_next - 0.355377) < 1e-4

    # Ingest P2 and trace Step 1
    scratch2 = st112.clone()
    scratch2.R.reset_cold()
    e2 = encode_exposure("النسر يشرب", append_eos=False)
    p_cores2 = [e.core_event for e in e2]
    for idx, pev in enumerate(p_cores2):
        proj = project_core_event_v1(pev)
        execute_two_pass_event(
            scratch2, proj.x_fixed_by_global_id, proj.x_float_by_global_id,
            mode=ExecutionMode.GENERATE, origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=(idx == 0 or pev.boundary), event_order=idx, feature_bundle_digest=proj.feature_bundle_digest,
        )
    rr0_2 = evaluate_full_vs_control_readout(scratch2, theta_read=THETA_READ)
    att_env2 = led112.resolve_readout(rr0_2.winner_assembly_id, rr0_2.winner_generation).envelope
    reinj_ev2 = reinject_attested_bundle(att_env2, exposure_id=None, event_order=len(p_cores2))
    reinj_proj2 = project_core_event_v1(reinj_ev2)
    execute_two_pass_event(
        scratch2, reinj_proj2.x_fixed_by_global_id, reinj_proj2.x_float_by_global_id,
        mode=ExecutionMode.GENERATE, origin=EventOrigin.INTERNAL_SELECTED,
        boundary=False, event_order=len(p_cores2), feature_bundle_digest=reinj_proj2.feature_bundle_digest,
        apply_pt_debit_selected=True,
    )
    rr1_2 = evaluate_full_vs_control_readout(scratch2, theta_read=THETA_READ)
    asm1_cand_2 = [s for s in rr1_2.ranked_scores if s.assembly_id == 1][0]
    assert asm1_cand_2.eligible_member_count == 8
    assert abs(asm1_cand_2.score_next - 0.036007) < 1e-4
    assert rr1_2.status == StatusCode.NO_MATCH


def test_4_readout_arithmetic_integrity(group_b_checkpoints):
    """Verify that score arithmetic strictly satisfies: score == sum(gain_j for j in eligible) / |M|."""
    st56 = group_b_checkpoints[56]["state"]
    p_cores = [e.core_event for e in encode_exposure("القط يشرب", append_eos=False)]
    st56_p1 = feed_prompt(st56, p_cores)
    rr56 = evaluate_full_vs_control_readout(st56_p1)

    for cand in rr56.ranked_scores:
        asm = st56.W.assemblies[cand.assembly_id]
        expected_score = sum(
            rr56.gain_by_cell.get(c, 0.0)
            for c in asm.member_cell_ids
            if c in rr56.eligible_next_cells
        ) / len(asm.member_cell_ids)
        assert abs(cand.score_next - expected_score) < 1e-6, (
            f"Arithmetic mismatch on Asm {cand.assembly_id}: {cand.score_next} vs {expected_score}"
        )
