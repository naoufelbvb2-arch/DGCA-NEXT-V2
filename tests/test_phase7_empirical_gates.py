"""Phase 7 Tests: Empirical Program Milestones (Gate A -> Gate E) and Reproducible Manifest (LLA §8.2, Core §13)."""

from __future__ import annotations

import json
from pathlib import Path

from dgca.common.errors import StatusCode
from dgca.experiments import (
    run_empirical_suite,
    run_gate_a_unit_and_transaction,
    run_gate_b_isolated_mechanism,
    run_gate_c_learn_from_zero_and_rc4_1_subgate,
    run_gate_d_ablations_and_comparisons,
    run_gate_e_generalization_and_boundaries,
)


def test_gate_a_unit_and_transaction_milestone() -> None:
    """Verify Gate A: canonical SIC, same-root (q,y) aggregation, exact scopes, budgets, ABORT rollback, read-only immutability."""
    rep = run_gate_a_unit_and_transaction()
    assert rep.passed is True
    assert rep.sic_deterministic is True
    assert rep.same_root_max_q_or_y_verified is True
    assert rep.k_neural_and_k_evidence_verified is True
    assert rep.outgoing_budget_b_i == 64
    assert rep.abort_restores_h_slow_begin is True
    assert rep.read_only_immutability_verified is True


def test_gate_b_isolated_mechanism_milestone() -> None:
    """Verify Gate B: known-legal fixture network for AB->C vs DB->E separation and FULL vs CONTROL readout."""
    rep = run_gate_b_isolated_mechanism()
    assert rep.passed is True
    assert rep.pred_c_given_ab > rep.pred_e_given_ab
    assert rep.pred_e_given_db > rep.pred_c_given_db
    assert rep.readout_winner_on_ab == 1
    assert rep.readout_winner_on_db == 2
    assert rep.readout_margin_on_ab >= 0.04
    assert rep.readout_margin_on_db >= 0.04


def test_gate_c_learn_from_zero_and_rc4_1_subgate_milestone() -> None:
    """Verify Gate C + RC4.1 Subgate: cold-start learning of AB->C vs DB->E and native triangle birth-to-attestation telemetry."""
    rep = run_gate_c_learn_from_zero_and_rc4_1_subgate()
    assert rep.passed is True
    assert 1 in rep.sensory_commit_roots and 2 in rep.sensory_commit_roots
    assert len(rep.recruited_context_cells) >= 2
    assert rep.first_pz_root is not None
    assert rep.first_cz_root is not None
    assert rep.first_zy_root is not None
    assert rep.pred_c_given_ab > rep.pred_e_given_ab
    assert rep.pred_e_given_db > rep.pred_c_given_db

    # RC4.1 Subgate checks
    assert rep.triangle_receiver_commit_root == 1
    assert rep.triangle_all_six_edges_consolidated is True
    assert rep.assembly_birth_root is not None
    assert rep.birth_root_attestations == 0
    assert len(rep.post_birth_attestation_roots) >= 2
    assert rep.surface_readout_attested is True
    assert rep.idealized_reference_table["0.45"] == (15, 18)
    assert rep.idealized_reference_table["0.60"] == (9, 12)
    assert rep.idealized_reference_table["0.70"] == (7, 10)
    assert rep.idealized_reference_table["0.80"] == (5, 8)


def test_gate_d_ablations_and_comparisons_milestone() -> None:
    """Verify Gate D: DCR z-path vs baseline, probe on vs off, B_i=64 vs 32, and Replay on vs off."""
    rep = run_gate_d_ablations_and_comparisons()
    assert rep.passed is True
    assert rep.dcr_z_enabled_margin_ab > 0.10
    assert abs(rep.baseline_z_disabled_margin_ab) < 1e-9
    assert rep.probe_enabled_z_active_in_discovery is True
    assert rep.probe_disabled_z_active_in_discovery is False
    assert rep.rc4_budget_64_feasible_headroom_at_32_links == 32
    assert rep.rc2_budget_32_feasible_headroom_at_32_links == 0
    assert rep.replay_preserves_e_ext_and_ext_count is True


def test_gate_e_generalization_and_boundaries_milestone() -> None:
    """Verify Gate E: separated G1, G2, and held-out compositional G3 reporting and explicit scope limitations."""
    rep = run_gate_e_generalization_and_boundaries()
    assert rep.passed is True
    assert rep.g1_memorized_rollout_surfaces == ("تشرق",)
    assert rep.g1_stop_status == StatusCode.GEN_STOP_EOS
    assert rep.g2_branch_ab_surfaces == ("حليب",)
    assert rep.g2_branch_db_surfaces == ("ماء",)
    assert rep.g3_unseen_compositional_stop_status == StatusCode.GEN_STOP_NO_MATCH
    assert rep.g3_unseen_compositional_surfaces == ()
    assert rep.separated_evaluation.g1_passed is True
    assert rep.separated_evaluation.g2_passed is True
    assert rep.separated_evaluation.g3_passed is False
    assert rep.separated_evaluation.overall_gate_d_passed is False
    assert len(rep.explicit_limitations) >= 4


def test_full_empirical_suite_and_reproducible_manifest() -> None:
    """Verify the unified empirical suite runner and JSON manifest provenance fields (LLA §8.2)."""
    project_root = Path(__file__).resolve().parents[1]
    suite = run_empirical_suite(project_root=project_root)
    assert suite.all_gates_passed is True
    manifest_json = suite.manifest.to_json()
    parsed = json.loads(manifest_json)
    assert parsed["schema_version"] == "DGCA-EMPIRICAL-MANIFEST-V1"
    assert parsed["config_name"] == "lab_rc4_1_default"
    assert parsed["contract_level_pass"] is True
    assert parsed["spec_sha256"]["DGCA_CORE_RC4_1.md"] != "MISSING"
    assert parsed["spec_sha256"]["DGCA_LLA_RC4_1.md"] != "MISSING"
    assert (
        parsed["spec_sha256"]["dgca_v2_dynamic_core_reconstruction_encoder_specification.md"]
        != "MISSING"
    )
    assert "Gate_A_Unit_And_Transaction" in parsed["empirical_gates_summary"]
    assert "Gate_C_Learn_From_Zero_And_RC4_1_Subgate" in parsed["empirical_gates_summary"]
