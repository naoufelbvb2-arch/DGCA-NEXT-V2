"""R2-A01 Patch 5 Acceptance & Scientific Manifest Verification Suite.

Normative references:
- R2-A01-IMPLEMENTATION-PLAN.md §2 (Patch 5: Manifest Generator & Durable Persistence Boundary Isolation)
- R2-A01-REMEDIATION-DESIGN-CONTRACT.md §3.4 (Durable Persistence Boundaries)
- DGCA_CORE_RC4_1.md §11 (Reproducibility, Cold Reset & Scientific Provenance)
- DGCA_LLA_RC4_1.md §8.2 (Experiment Provenance and Metrics Manifest)

Acceptance Test Scenarios:
- M01: Source SHA Accuracy (manifest source matches git rev-parse HEAD)
- M02: Configuration Hash Accuracy (SHA-256 computed from raw file bytes)
- M03: Deterministic Replay (two runs produce byte-for-byte identical output)
- M04: Path Portability (operates from repo root or external directory)
- M05: No Hardcoded Paths (zero local absolute paths, drive letters, usernames)
- M06: Invalid Environment Handling (explicit failure on missing/unreadable files)
- M07: Persistence Boundary Isolation (no durability engine, WAL, or persistent DB)
- M08: Frozen Regression Integrity (Patches 1-4 invariants preserved)
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

import pytest

from dgca.common.serialization import DurablePersistenceService
from tools.generate_scientific_manifest import (
    DEFAULT_CONFIG_FILES,
    SCHEMA_VERSION,
    compute_file_sha256,
    compute_manifest_digest,
    generate_manifest,
    get_git_commit_sha,
    get_repo_root,
    main as manifest_main,
    serialize_manifest,
    verify_manifest_against_repo,
)


@pytest.fixture
def repo_root() -> Path:
    """Fixture providing authoritative repository root."""
    return get_repo_root()


def test_m01_source_sha_accuracy(repo_root: Path) -> None:
    """M01: Verify that manifest source SHA matches actual Git commit SHA."""
    # Obtain actual HEAD SHA via Git
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    expected_sha = proc.stdout.strip().lower()

    manifest = generate_manifest(repo_root=repo_root)

    assert manifest["source_commit_sha"] == expected_sha
    assert manifest["source"]["commit_sha"] == expected_sha
    assert len(manifest["source_commit_sha"]) == 40
    assert all(c in "0123456789abcdef" for c in manifest["source_commit_sha"])


def test_m02_configuration_hash_accuracy(repo_root: Path) -> None:
    """M02: Verify that each recorded config hash matches SHA-256 computed directly from raw bytes."""
    manifest = generate_manifest(repo_root=repo_root)

    for rel_path in DEFAULT_CONFIG_FILES:
        abs_path = repo_root / rel_path
        assert abs_path.is_file(), f"Config file missing: {abs_path}"

        raw_bytes = abs_path.read_bytes()
        expected_sha256 = hashlib.sha256(raw_bytes).hexdigest()

        # Check recorded entry in manifest
        norm_path = Path(rel_path).as_posix()
        assert norm_path in manifest["configurations"]
        assert manifest["configurations"][norm_path]["sha256"] == expected_sha256
        assert manifest["configurations"][norm_path]["size_bytes"] == len(raw_bytes)
        assert manifest["configuration_hashes"][norm_path] == expected_sha256


def test_m03_deterministic_replay(repo_root: Path) -> None:
    """M03: Verify that two manifest generations under identical conditions produce identical canonical bytes."""
    manifest_1 = generate_manifest(repo_root=repo_root)
    serialized_1 = serialize_manifest(manifest_1)

    manifest_2 = generate_manifest(repo_root=repo_root)
    serialized_2 = serialize_manifest(manifest_2)

    # Byte-for-byte equality
    assert serialized_1.encode("utf-8") == serialized_2.encode("utf-8")
    assert compute_manifest_digest(serialized_1) == compute_manifest_digest(serialized_2)

    # Verify keys are sorted
    data_1 = json.loads(serialized_1)
    keys = list(data_1.keys())
    assert keys == sorted(keys), f"Top-level keys not sorted: {keys}"
    config_keys = list(data_1["configurations"].keys())
    assert config_keys == sorted(config_keys), f"Configuration keys not sorted: {config_keys}"


def test_m04_path_portability(repo_root: Path) -> None:
    """M04: Verify that the script operates identically from repo root and an unrelated working directory."""
    script_path = repo_root / "tools" / "generate_scientific_manifest.py"
    assert script_path.is_file()

    # 1. Run from repo root
    proc_root = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    output_root = proc_root.stdout

    # 2. Run from an external temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        proc_temp = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        output_temp = proc_temp.stdout

    assert output_root == output_temp, "Manifest output differs when run from different working directories"


def test_m05_no_hardcoded_paths(repo_root: Path) -> None:
    """M05: Verify that output contains no local machine paths, usernames, or IDE dependencies."""
    manifest = generate_manifest(repo_root=repo_root)
    serialized = serialize_manifest(manifest)

    # Check for drive letters, backslashes, user names, or full repo directory strings
    assert str(repo_root) not in serialized
    assert ":\\" not in serialized  # Windows drive letter pattern
    assert ":/" not in serialized

    # Check that paths inside manifest are strictly repository-relative POSIX format
    for rel_path, config_meta in manifest["configurations"].items():
        assert not Path(rel_path).is_absolute()
        assert "\\" not in rel_path
        assert config_meta["path"] == rel_path


def test_m06_invalid_environment_handling(repo_root: Path) -> None:
    """M06: Verify explicit failure on missing files, unreadable files, or non-git environment."""
    # 1. Missing configuration file
    with pytest.raises(FileNotFoundError, match="Configuration file does not exist"):
        generate_manifest(
            repo_root=repo_root,
            config_rel_paths=["configs/nonexistent_file_definitely_missing.json"],
        )

    # 2. Path traversing outside repository root
    with pytest.raises(ValueError, match="outside repository root"):
        generate_manifest(
            repo_root=repo_root,
            config_rel_paths=["../../outside_repo.json"],
        )

    # 3. Non-git directory
    with tempfile.TemporaryDirectory() as empty_dir:
        with pytest.raises(RuntimeError, match="cannot establish source commit identity"):
            get_git_commit_sha(Path(empty_dir))


def test_m07_persistence_boundary_isolation() -> None:
    """M07: Verify persistence boundary isolation: Protocol defined, zero durability engine implemented."""
    import dgca.common.serialization as s_mod

    # 1. DurablePersistenceService exists and is a Protocol
    assert hasattr(s_mod, "DurablePersistenceService")
    proto = getattr(s_mod, "DurablePersistenceService")
    assert isinstance(proto, type)

    # 2. Verify that no disk durability engine, WAL, or persistent checkpoint functions exist
    exported_names = [name for name in dir(s_mod) if not name.startswith("__")]
    assert "serialize_machine_state" not in exported_names
    assert "save_checkpoint" not in exported_names
    assert "load_checkpoint" not in exported_names
    assert "replay_wal" not in exported_names
    assert "DurablePersistenceEngine" not in exported_names

    # 3. Protocol cannot be instantiated directly without implementation
    with pytest.raises(TypeError):
        proto()  # type: ignore[misc]


def test_m08_frozen_regression_curriculum_integrity() -> None:
    """M08: Verify that cold-start curriculum and dual-owner invariants remain intact."""
    from dgca.common.hashing import Region
    from dgca.core.readout import M_READ, THETA_READ
    from dgca.core.assembly import RHO_CORE, THETA_OB
    from dgca.core.dynamics import K_R_PER_EVENT

    # Authoritative constants check
    assert THETA_READ == 0.08
    assert M_READ == 0.04
    assert THETA_OB == 0.40
    assert RHO_CORE == 0.70
    assert K_R_PER_EVENT == 12


def test_cli_flags_and_check(repo_root: Path) -> None:
    """Verify CLI options: --canonical-digest, --output, --check."""
    # 1. Canonical digest CLI
    manifest = generate_manifest(repo_root=repo_root)
    serialized = serialize_manifest(manifest)
    expected_digest = compute_manifest_digest(serialized)

    script_path = repo_root / "tools" / "generate_scientific_manifest.py"
    proc_digest = subprocess.run(
        [sys.executable, str(script_path), "--canonical-digest"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    assert proc_digest.stdout.strip() == expected_digest

    # 2. Output flag CLI
    with tempfile.TemporaryDirectory() as temp_dir:
        out_file = Path(temp_dir) / "manifest.json"
        subprocess.run(
            [sys.executable, str(script_path), "-o", str(out_file)],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
        )
        assert out_file.is_file()
        assert out_file.read_text(encoding="utf-8") == serialized

        # 3. Check flag CLI: valid manifest passes
        proc_check_ok = subprocess.run(
            [sys.executable, str(script_path), "--check", str(out_file)],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        assert proc_check_ok.returncode == 0
        assert "Manifest check PASSED" in proc_check_ok.stdout

        # 4. Check flag CLI: tampered manifest fails
        tampered_data = json.loads(serialized)
        tampered_data["source_commit_sha"] = "0" * 40
        tampered_file = Path(temp_dir) / "tampered_manifest.json"
        tampered_file.write_text(json.dumps(tampered_data), encoding="utf-8")

        proc_check_fail = subprocess.run(
            [sys.executable, str(script_path), "--check", str(tampered_file)],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        assert proc_check_fail.returncode == 1
        assert "Manifest check FAILED" in proc_check_fail.stderr
