"""DGCA Empirical Program Milestones Package (Gate A -> Gate E, LLA §8.2, Core §13)."""

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
    compute_file_sha256,
    compute_sic_salt_digest,
)
from dgca.experiments.runner import (
    EmpiricalSuiteReport,
    run_empirical_suite,
)

__all__ = [
    "EmpiricalSuiteReport",
    "GateAReport",
    "GateBReport",
    "GateCReport",
    "GateDReport",
    "GateEReport",
    "ReproducibleExperimentManifest",
    "build_experiment_manifest",
    "compute_file_sha256",
    "compute_sic_salt_digest",
    "run_empirical_suite",
    "run_gate_a_unit_and_transaction",
    "run_gate_b_isolated_mechanism",
    "run_gate_c_learn_from_zero_and_rc4_1_subgate",
    "run_gate_d_ablations_and_comparisons",
    "run_gate_e_generalization_and_boundaries",
]
