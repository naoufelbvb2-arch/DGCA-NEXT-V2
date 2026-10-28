"""Reproducible Experiment Manifest and Provenance Digest Generator (LLA §8.2, Core §11).

Normative references:
- DGCA_LLA_RC4_1.md §8.2: "Every run stores configuration and numeric precision, SIC salt digest,
  random seed, baseline source SHA, implementation commit SHA, full accepted/aborted exposure
  journal high-watermark and a reproducible metrics manifest. Contract-level PASS is NOT empirical Core PASS."
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dgca.common.hashing import SIC_SALTS, sha256_bytes
from dgca.core.state import MachineState


def compute_sic_salt_digest() -> str:
    """Compute the canonical SHA-256 hex digest of the 4 fixed SIC-V1 salt bytes."""
    joined = b"".join(SIC_SALTS)
    return sha256_bytes(joined).hex()


def compute_file_sha256(path: Path) -> str:
    """Compute SHA-256 hex digest of a file if it exists, else 'MISSING'."""
    if not path.is_file():
        return "MISSING"
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


@dataclass(frozen=True, slots=True)
class ReproducibleExperimentManifest:
    """Normative experiment provenance and metrics manifest (LLA §8.2)."""

    schema_version: str
    config_name: str
    numeric_precision_policy: str
    sic_salt_sha256: str
    random_seed: int
    spec_sha256: dict[str, str]
    completed_roots_high_watermark: int
    aborted_roots_count: int
    completed_external_events_count: int
    contract_level_pass: bool
    empirical_gates_summary: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, sort_keys=True)


def build_experiment_manifest(
    *,
    project_root: Path,
    state: MachineState,
    aborted_roots_count: int,
    config_name: str = "lab_rc4_1_default",
    random_seed: int = 0,
    contract_level_pass: bool = True,
    empirical_gates_summary: dict[str, dict[str, Any]] | None = None,
) -> ReproducibleExperimentManifest:
    """Construct a complete ReproducibleExperimentManifest for an empirical run (LLA §8.2)."""
    spec_files = {
        "DGCA_CORE_RC4_1.md": compute_file_sha256(project_root / "DGCA_CORE_RC4_1.md"),
        "DGCA_LLA_RC4_1.md": compute_file_sha256(project_root / "DGCA_LLA_RC4_1.md"),
        "dgca_v2_dynamic_core_reconstruction_encoder_specification.md": compute_file_sha256(
            project_root / "dgca_v2_dynamic_core_reconstruction_encoder_specification.md"
        ),
    }
    return ReproducibleExperimentManifest(
        schema_version="DGCA-EMPIRICAL-MANIFEST-V1",
        config_name=config_name,
        numeric_precision_policy="IEEE754-binary64 + exact-decimal-millionths-Q6 (FIFR-B04)",
        sic_salt_sha256=compute_sic_salt_digest(),
        random_seed=random_seed,
        spec_sha256=spec_files,
        completed_roots_high_watermark=state.W.completed_roots_high_watermark,
        aborted_roots_count=aborted_roots_count,
        completed_external_events_count=state.W.completed_external_events_count,
        contract_level_pass=contract_level_pass,
        empirical_gates_summary=dict(empirical_gates_summary or {}),
    )
