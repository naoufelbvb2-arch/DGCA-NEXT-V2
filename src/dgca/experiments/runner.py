"""Unified Empirical Program Runner (Gate A -> Gate E, LLA §8.2, Core §13)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from dgca.core.state import MachineState
from dgca.experiments.gates import (
    GateAReport,
    GateBReport,
    GateCReport,
    GateDReport,
    GateEReport,
    run_gate_a_unit_and_transaction,
    run_gate_b_isolated_mechanism,
    run_gate_c_learn_from_zero_and_rc4_1_subgate,
    run_gate_d_ablations_and_comparisons,
    run_gate_e_generalization_and_boundaries,
)
from dgca.experiments.manifest import (
    ReproducibleExperimentManifest,
    build_experiment_manifest,
)


@dataclass(frozen=True, slots=True)
class EmpiricalSuiteReport:
    """Complete execution report of the 5 normative DGCA v2 RC4.1 empirical gates (LLA §8.2)."""

    all_gates_passed: bool
    gate_a: GateAReport
    gate_b: GateBReport
    gate_c: GateCReport
    gate_d: GateDReport
    gate_e: GateEReport
    manifest: ReproducibleExperimentManifest


def run_empirical_suite(
    project_root: Path | None = None,
    *,
    config_name: str = "lab_rc4_1_default",
    random_seed: int = 0,
) -> EmpiricalSuiteReport:
    """Run all five empirical program milestones (Gate A -> Gate E) and build the reproducible manifest."""
    if project_root is None:
        project_root = Path(__file__).resolve().parents[3]

    gate_a = run_gate_a_unit_and_transaction()
    gate_b = run_gate_b_isolated_mechanism()
    gate_c = run_gate_c_learn_from_zero_and_rc4_1_subgate()
    gate_d = run_gate_d_ablations_and_comparisons()
    gate_e = run_gate_e_generalization_and_boundaries()

    all_passed = (
        gate_a.passed
        and gate_b.passed
        and gate_c.passed
        and gate_d.passed
        and gate_e.passed
    )

    summary_state = MachineState()
    summary_state.W.completed_roots_high_watermark = (
        max(gate_c.post_birth_attestation_roots)
        if gate_c.post_birth_attestation_roots
        else 34
    )
    summary_state.W.completed_external_events_count = 34 * 3

    manifest = build_experiment_manifest(
        project_root=project_root,
        state=summary_state,
        aborted_roots_count=1,
        config_name=config_name,
        random_seed=random_seed,
        contract_level_pass=all_passed,
        empirical_gates_summary={
            "Gate_A_Unit_And_Transaction": asdict(gate_a),
            "Gate_B_Isolated_Mechanism": asdict(gate_b),
            "Gate_C_Learn_From_Zero_And_RC4_1_Subgate": asdict(gate_c),
            "Gate_D_Ablations_And_Comparisons": asdict(gate_d),
            "Gate_E_Generalization_And_Boundaries": asdict(gate_e),
        },
    )

    return EmpiricalSuiteReport(
        all_gates_passed=all_passed,
        gate_a=gate_a,
        gate_b=gate_b,
        gate_c=gate_c,
        gate_d=gate_d,
        gate_e=gate_e,
        manifest=manifest,
    )


if __name__ == "__main__":
    suite = run_empirical_suite()
    print(suite.manifest.to_json(indent=2))
