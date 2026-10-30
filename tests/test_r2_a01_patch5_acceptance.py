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
- C01-S01: Complete Manifest Verification (rejection of incomplete/corrupted schemas)
- C01-S02: Working Tree Source Cleanliness Detection (fail closed on uncommitted source)
- C01-S03: Comprehensive Negative Scenario Suite
- C02-S01: Distinguishable Non-Authoritative Dirty Artifact & Rejection Gate
- C02-S02: Exact Canonical-Byte Enforcement (strict byte-for-byte matching without CRLF normalization)
"""

from __future__ import annotations

import copy
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
    REPOSITORY_IDENTIFIER,
    SCHEMA_VERSION,
    check_source_cleanliness,
    compute_file_sha256,
    compute_manifest_digest,
    generate_manifest,
    get_git_commit_sha,
    get_repo_root,
    main as manifest_main,
    serialize_manifest,
    verify_manifest_against_repo,
    verify_manifest_bytes,
)


@pytest.fixture
def repo_root() -> Path:
    """Fixture providing authoritative repository root."""
    return get_repo_root()


@pytest.fixture
def clean_git_repo(tmp_path: Path) -> Path:
    """Fixture providing an isolated, clean Git repository with standard configs."""
    repo_dir = tmp_path / "authoritative_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Runner"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_dir), check=True, capture_output=True)

    configs_dir = repo_dir / "configs"
    configs_dir.mkdir()
    cfg1 = configs_dir / "lab_rc2_ablation.json"
    cfg1.write_text('{"schema_version": "test-ablation"}', encoding="utf-8")
    cfg2 = configs_dir / "lab_rc4_1_default.json"
    cfg2.write_text('{"schema_version": "test-default"}', encoding="utf-8")

    src_dir = repo_dir / "src"
    src_dir.mkdir()
    (src_dir / "model.py").write_text("# Authoritative source\ndef run(): pass\n", encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial clean commit"], cwd=str(repo_dir), check=True, capture_output=True)
    return repo_dir


def test_m01_source_sha_accuracy(repo_root: Path) -> None:
    """M01: Verify that manifest source SHA matches actual Git commit SHA."""
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    expected_sha = proc.stdout.strip().lower()

    is_clean, _ = check_source_cleanliness(repo_root)
    if is_clean:
        manifest = generate_manifest(repo_root=repo_root, require_clean=True)
        assert manifest["source_commit_sha"] == expected_sha
        assert manifest["source"]["commit_sha"] == expected_sha
        assert len(manifest["source_commit_sha"]) == 40
        assert all(c in "0123456789abcdef" for c in manifest["source_commit_sha"])
    else:
        manifest = generate_manifest(repo_root=repo_root, require_clean=False)
        assert manifest["source_commit_sha"] == f"{expected_sha}-DIRTY"
        assert manifest["source"]["commit_sha"] == f"{expected_sha}-DIRTY"


def test_m02_configuration_hash_accuracy(repo_root: Path) -> None:
    """M02: Verify that each recorded config hash matches SHA-256 computed directly from raw bytes."""
    manifest = generate_manifest(repo_root=repo_root, require_clean=False)

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
    manifest_1 = generate_manifest(repo_root=repo_root, require_clean=False)
    serialized_1 = serialize_manifest(manifest_1)

    manifest_2 = generate_manifest(repo_root=repo_root, require_clean=False)
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
        [sys.executable, str(script_path), "--allow-dirty"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    output_root = proc_root.stdout

    # 2. Run from an external temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        proc_temp = subprocess.run(
            [sys.executable, str(script_path), "--allow-dirty"],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        output_temp = proc_temp.stdout

    assert output_root == output_temp, "Manifest output differs when run from different working directories"


def test_m05_no_hardcoded_paths(repo_root: Path) -> None:
    """M05: Verify that output contains no local machine paths, usernames, or IDE dependencies."""
    manifest = generate_manifest(repo_root=repo_root, require_clean=False)
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
            require_clean=False,
        )

    # 2. Path traversing outside repository root
    with pytest.raises(ValueError, match="outside repository root"):
        generate_manifest(
            repo_root=repo_root,
            config_rel_paths=["../../outside_repo.json"],
            require_clean=False,
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
    from dgca.core.readout import M_READ, THETA_READ
    from dgca.core.assembly import RHO_CORE, THETA_OB
    from dgca.core.dynamics import K_R_PER_EVENT

    # Authoritative constants check
    assert THETA_READ == 0.08
    assert M_READ == 0.04
    assert THETA_OB == 0.40
    assert RHO_CORE == 0.70
    assert K_R_PER_EVENT == 12


def test_cli_flags_and_check(clean_git_repo: Path, repo_root: Path) -> None:
    """Verify CLI options: --canonical-digest, --output, --check against clean repo."""
    manifest = generate_manifest(repo_root=clean_git_repo, require_clean=True)
    serialized = serialize_manifest(manifest)
    expected_digest = compute_manifest_digest(serialized)

    script_path = repo_root / "tools" / "generate_scientific_manifest.py"
    proc_digest = subprocess.run(
        [sys.executable, str(script_path), "--canonical-digest", "--repo-root", str(clean_git_repo)],
        cwd=str(clean_git_repo),
        capture_output=True,
        text=True,
        check=True,
    )
    assert proc_digest.stdout.strip() == expected_digest

    with tempfile.TemporaryDirectory() as temp_dir:
        out_file = Path(temp_dir) / "manifest.json"
        subprocess.run(
            [sys.executable, str(script_path), "-o", str(out_file), "--repo-root", str(clean_git_repo)],
            cwd=str(clean_git_repo),
            capture_output=True,
            text=True,
            check=True,
        )
        assert out_file.is_file()
        assert out_file.read_bytes() == serialized.encode("utf-8")

        # Check flag CLI: valid manifest passes
        proc_check_ok = subprocess.run(
            [sys.executable, str(script_path), "--check", str(out_file), "--repo-root", str(clean_git_repo)],
            cwd=str(clean_git_repo),
            capture_output=True,
            text=True,
        )
        assert proc_check_ok.returncode == 0
        assert "Manifest check PASSED" in proc_check_ok.stdout

        # Check flag CLI: tampered manifest fails
        tampered_data = json.loads(serialized)
        tampered_data["source_commit_sha"] = "0" * 40
        tampered_file = Path(temp_dir) / "tampered_manifest.json"
        tampered_file.write_bytes(serialize_manifest(tampered_data).encode("utf-8"))

        proc_check_fail = subprocess.run(
            [sys.executable, str(script_path), "--check", str(tampered_file), "--repo-root", str(clean_git_repo)],
            cwd=str(clean_git_repo),
            capture_output=True,
            text=True,
        )
        assert proc_check_fail.returncode == 1
        assert "Manifest check FAILED" in proc_check_fail.stderr


# ==============================================================================
# CORRECTION C01-S01 & C01-S03 TESTS: COMPLETE MANIFEST VERIFICATION & NEGATIVES
# ==============================================================================

def test_c01_s01_incomplete_manifest_reproduction_and_rejection(repo_root: Path) -> None:
    """C01-S01: Demonstrate that incomplete manifest with empty configurations is rejected."""
    incomplete = {
        "source_commit_sha": get_git_commit_sha(repo_root),
        "configurations": {},
    }
    valid, discrepancies = verify_manifest_against_repo(
        incomplete,
        repo_root=repo_root,
        require_clean=False,
    )
    assert valid is False
    assert len(discrepancies) > 0
    # Must report missing configuration entries and missing required fields
    assert any("Missing required configuration entries" in d for d in discrepancies)
    assert any("Missing required top-level field" in d for d in discrepancies)


def test_c01_s01_missing_configuration_inventory_entry(repo_root: Path) -> None:
    """C01-S01: Reject manifest missing one required configuration file."""
    manifest = generate_manifest(repo_root=repo_root, require_clean=False)
    # Remove one required config
    del manifest["configurations"]["configs/lab_rc2_ablation.json"]
    del manifest["configuration_hashes"]["configs/lab_rc2_ablation.json"]

    valid, discrepancies = verify_manifest_against_repo(manifest, repo_root=repo_root, require_clean=False)
    assert valid is False
    assert any("Missing required configuration entries: ['configs/lab_rc2_ablation.json']" in d for d in discrepancies)


def test_c01_s01_unexpected_configuration_entry(repo_root: Path) -> None:
    """C01-S01: Reject manifest with extra unexpected configuration file."""
    manifest = generate_manifest(repo_root=repo_root, require_clean=False)
    manifest["configurations"]["configs/unexpected_extra.json"] = {
        "path": "configs/unexpected_extra.json",
        "sha256": "0" * 64,
        "size_bytes": 100,
    }
    manifest["configuration_hashes"]["configs/unexpected_extra.json"] = "0" * 64

    valid, discrepancies = verify_manifest_against_repo(manifest, repo_root=repo_root, require_clean=False)
    assert valid is False
    assert any("Unexpected configuration entries" in d for d in discrepancies)


def test_c01_s01_invalid_schema_version(repo_root: Path) -> None:
    """C01-S01: Reject manifest with wrong schema version."""
    manifest = generate_manifest(repo_root=repo_root, require_clean=False)
    manifest["schema_version"] = "2.0.0"

    valid, discrepancies = verify_manifest_against_repo(manifest, repo_root=repo_root, require_clean=False)
    assert valid is False
    assert any("Schema version mismatch" in d for d in discrepancies)


def test_c01_s01_conflicting_source_shas(repo_root: Path) -> None:
    """C01-S01: Reject manifest where source.commit_sha != source_commit_sha."""
    manifest = generate_manifest(repo_root=repo_root, require_clean=False)
    manifest["source"]["commit_sha"] = "a" * 40
    manifest["source_commit_sha"] = "b" * 40

    valid, discrepancies = verify_manifest_against_repo(manifest, repo_root=repo_root, require_clean=False)
    assert valid is False
    assert any("Contradictory source commit SHAs" in d for d in discrepancies)


def test_c01_s01_incorrect_repository_identifier(repo_root: Path) -> None:
    """C01-S01: Reject manifest with incorrect repository identifier."""
    manifest = generate_manifest(repo_root=repo_root, require_clean=False)
    manifest["source"]["repository"] = "other-org/other-repo"

    valid, discrepancies = verify_manifest_against_repo(manifest, repo_root=repo_root, require_clean=False)
    assert valid is False
    assert any("Repository identifier mismatch" in d for d in discrepancies)


def test_c01_s01_incorrect_configuration_hash(repo_root: Path) -> None:
    """C01-S01: Reject manifest with tampered configuration SHA-256."""
    manifest = generate_manifest(repo_root=repo_root, require_clean=False)
    target = "configs/lab_rc2_ablation.json"
    manifest["configurations"][target]["sha256"] = "f" * 64
    manifest["configuration_hashes"][target] = "f" * 64

    valid, discrepancies = verify_manifest_against_repo(manifest, repo_root=repo_root, require_clean=False)
    assert valid is False
    assert any("Configuration hash mismatch" in d for d in discrepancies)


def test_c01_s01_incorrect_configuration_size(repo_root: Path) -> None:
    """C01-S01: Reject manifest with tampered configuration file size."""
    manifest = generate_manifest(repo_root=repo_root, require_clean=False)
    target = "configs/lab_rc2_ablation.json"
    manifest["configurations"][target]["size_bytes"] = 999999

    valid, discrepancies = verify_manifest_against_repo(manifest, repo_root=repo_root, require_clean=False)
    assert valid is False
    assert any("Configuration size mismatch" in d for d in discrepancies)


def test_c01_s01_inconsistent_duplicate_hash_fields(repo_root: Path) -> None:
    """C01-S01: Reject manifest where configuration_hashes diverges from configurations."""
    manifest = generate_manifest(repo_root=repo_root, require_clean=False)
    target = "configs/lab_rc2_ablation.json"
    manifest["configuration_hashes"][target] = "e" * 64

    valid, discrepancies = verify_manifest_against_repo(manifest, repo_root=repo_root, require_clean=False)
    assert valid is False
    assert any("Contradictory hash" in d for d in discrepancies)


def test_c01_s01_invalid_configuration_path_format(repo_root: Path) -> None:
    """C01-S01: Reject manifest with non-POSIX, absolute, or traversal path."""
    manifest = generate_manifest(repo_root=repo_root, require_clean=False)
    # 1. Absolute path
    manifest_abs = copy.deepcopy(manifest)
    manifest_abs["configurations"]["/configs/lab_rc2_ablation.json"] = manifest_abs["configurations"].pop("configs/lab_rc2_ablation.json")
    manifest_abs["configuration_hashes"]["/configs/lab_rc2_ablation.json"] = manifest_abs["configuration_hashes"].pop("configs/lab_rc2_ablation.json")

    valid_abs, disc_abs = verify_manifest_against_repo(manifest_abs, repo_root=repo_root, require_clean=False)
    assert valid_abs is False
    assert any("must be relative" in d or "Unexpected configuration entries" in d for d in disc_abs)

    # 2. Traversal path
    manifest_trav = copy.deepcopy(manifest)
    manifest_trav["configurations"]["configs/../configs/lab_rc2_ablation.json"] = manifest_trav["configurations"].pop("configs/lab_rc2_ablation.json")
    manifest_trav["configuration_hashes"]["configs/../configs/lab_rc2_ablation.json"] = manifest_trav["configuration_hashes"].pop("configs/lab_rc2_ablation.json")

    valid_trav, disc_trav = verify_manifest_against_repo(manifest_trav, repo_root=repo_root, require_clean=False)
    assert valid_trav is False
    assert any("must not traverse outside" in d or "Unexpected configuration entries" in d for d in disc_trav)


# ==============================================================================
# CORRECTION C01-S02 TEST: WORKING TREE SOURCE CLEANLINESS IN CONTROLLED GIT REPO
# ==============================================================================

def test_c01_s02_working_tree_dirty_source_detection(tmp_path: Path) -> None:
    """C01-S02: Mandatory controlled test verifying detection of uncommitted source changes."""
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()

    # Initialize controlled git repo
    subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Runner"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_dir), check=True, capture_output=True)

    # 1. Create valid configs
    configs_dir = repo_dir / "configs"
    configs_dir.mkdir()
    cfg1 = configs_dir / "lab_rc2_ablation.json"
    cfg1.write_text('{"schema_version": "test-ablation"}', encoding="utf-8")
    cfg2 = configs_dir / "lab_rc4_1_default.json"
    cfg2.write_text('{"schema_version": "test-default"}', encoding="utf-8")

    # Create tracked scientific source file
    src_dir = repo_dir / "src"
    src_dir.mkdir()
    src_file = src_dir / "model.py"
    src_file.write_text('# Authoritative source code\ndef run(): pass\n', encoding="utf-8")

    # Initial commit
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_dir), check=True, capture_output=True)

    # 2. Authoritative generation succeeds on clean tree
    manifest = generate_manifest(repo_root=repo_dir, require_clean=True)
    assert manifest["source_commit_sha"] is not None
    valid, discrepancies = verify_manifest_against_repo(manifest, repo_root=repo_dir, require_clean=True)
    assert valid is True
    assert discrepancies == []

    # 3. Modify a relevant tracked source file without committing
    src_file.write_text('# Tampered uncommitted source code\ndef run(): raise Exception()\n', encoding="utf-8")

    # 4. Verify that generator detects dirty source condition and fails closed
    with pytest.raises(RuntimeError, match="uncommitted modifications"):
        generate_manifest(repo_root=repo_dir, require_clean=True)

    valid_dirty, disc_dirty = verify_manifest_against_repo(manifest, repo_root=repo_dir, require_clean=True)
    assert valid_dirty is False
    assert any("uncommitted modifications" in d for d in disc_dirty)

    # 5. Restore the file to original committed state
    src_file.write_text('# Authoritative source code\ndef run(): pass\n', encoding="utf-8")

    # 6. Verify that authoritative manifest generation succeeds again
    manifest_restored = generate_manifest(repo_root=repo_dir, require_clean=True)
    assert manifest_restored["source_commit_sha"] == manifest["source_commit_sha"]
    valid_restored, disc_restored = verify_manifest_against_repo(manifest_restored, repo_root=repo_dir, require_clean=True)
    assert valid_restored is True
    assert disc_restored == []


# ==============================================================================
# CORRECTION C01-S03 TESTS: ADDITIONAL NEGATIVE FAILURE INJECTION SCENARIOS
# ==============================================================================

def test_c01_s03_failed_file_read_controlled_simulation(repo_root: Path, tmp_path: Path) -> None:
    """C01-S03: Verify controlled failure on unreadable or invalid file targets without fragile OS bits."""
    dir_target = tmp_path / "dummy_dir"
    dir_target.mkdir()

    with pytest.raises(IsADirectoryError, match="not a file"):
        compute_file_sha256(dir_target)

    missing_target = tmp_path / "does_not_exist.json"
    with pytest.raises(FileNotFoundError, match="does not exist"):
        compute_file_sha256(missing_target)


def test_c01_s03_non_git_source_failure(tmp_path: Path) -> None:
    """C01-S03: Verify fail-fast on directories without Git object database."""
    empty_dir = tmp_path / "not_a_git_repo"
    empty_dir.mkdir()

    with pytest.raises(RuntimeError, match="cannot establish source commit identity"):
        get_git_commit_sha(empty_dir)

    is_clean, dirty = check_source_cleanliness(empty_dir)
    assert is_clean is False
    assert any("Git status" in d for d in dirty)


def test_c01_s03_cli_check_exact_canonical_byte_enforcement(clean_git_repo: Path, repo_root: Path) -> None:
    """C01-S03: Verify that --check rejects valid JSON that is not canonical bytes."""
    manifest = generate_manifest(repo_root=clean_git_repo, require_clean=True)
    script_path = repo_root / "tools" / "generate_scientific_manifest.py"

    with tempfile.TemporaryDirectory() as temp_dir:
        # Non-canonical formatting: 4-space indentation and extra newline
        non_canonical_json = json.dumps(manifest, indent=4) + "\n\n"
        test_file = Path(temp_dir) / "non_canonical.json"
        test_file.write_text(non_canonical_json, encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, str(script_path), "--check", str(test_file), "--repo-root", str(clean_git_repo)],
            cwd=str(clean_git_repo),
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        assert "Candidate file bytes do not match canonical serialization byte-for-byte" in proc.stderr


# ==============================================================================
# CORRECTION C02-S01 & C02-S02 TESTS: DIRTY OVERRIDE BOUNDARY & EXACT BYTES
# ==============================================================================

def test_c02_s01_dirty_manifest_distinguishable_and_rejected(tmp_path: Path) -> None:
    """C02-S01: Mandatory reproduction verifying that dirty override produces an unambiguously
    distinguishable non-authoritative artifact that is rejected by authoritative verification.
    """
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()

    # Initialize controlled git repo
    subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Runner"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_dir), check=True, capture_output=True)

    # 1. Create and commit valid source and configuration files
    configs_dir = repo_dir / "configs"
    configs_dir.mkdir()
    cfg1 = configs_dir / "lab_rc2_ablation.json"
    cfg1.write_text('{"schema_version": "test-ablation"}', encoding="utf-8")
    cfg2 = configs_dir / "lab_rc4_1_default.json"
    cfg2.write_text('{"schema_version": "test-default"}', encoding="utf-8")

    src_dir = repo_dir / "src"
    src_dir.mkdir()
    src_file = src_dir / "model.py"
    src_file.write_text('# Authoritative source code\ndef run(): pass\n', encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_dir), check=True, capture_output=True)

    # 2. Generate clean authoritative manifest
    clean_manifest = generate_manifest(repo_root=repo_dir, require_clean=True)
    assert clean_manifest.get("authoritative", True) is True
    assert "dirty" not in clean_manifest
    assert "-DIRTY" not in clean_manifest["source_commit_sha"]

    # 3. Modify a tracked source file without committing
    src_file.write_text('# Tampered uncommitted source\ndef run(): raise Exception()\n', encoding="utf-8")

    # Authoritative generation must fail closed
    with pytest.raises(RuntimeError, match="uncommitted modifications"):
        generate_manifest(repo_root=repo_dir, require_clean=True)

    # 4. Invoke dirty override
    dirty_manifest = generate_manifest(repo_root=repo_dir, require_clean=False)

    # 5. Demonstrate that dirty artifact is unambiguously distinguishable from clean manifest
    assert dirty_manifest != clean_manifest
    assert dirty_manifest["authoritative"] is False
    assert dirty_manifest["dirty"] is True
    assert dirty_manifest["source_commit_sha"].endswith("-DIRTY")
    assert dirty_manifest["source"]["authoritative"] is False
    assert dirty_manifest["source"]["clean"] is False
    assert dirty_manifest["dirty_files"] == [" M src/model.py"]

    # 6. Verify that dirty-source output cannot pass authoritative verification
    valid, discrepancies = verify_manifest_against_repo(dirty_manifest, repo_root=repo_dir, require_clean=True)
    assert valid is False
    assert any("non-authoritative" in d or "dirty" in d for d in discrepancies)

    dirty_bytes = serialize_manifest(dirty_manifest).encode("utf-8")
    valid_bytes, disc_bytes = verify_manifest_bytes(dirty_bytes, repo_root=repo_dir)
    assert valid_bytes is False
    assert any("non-authoritative" in d or "dirty" in d for d in disc_bytes)

    # 7. Restore the source file
    src_file.write_text('# Authoritative source code\ndef run(): pass\n', encoding="utf-8")

    # 8. Verify normal authoritative generation and checking succeed again
    clean_restored = generate_manifest(repo_root=repo_dir, require_clean=True)
    assert clean_restored == clean_manifest
    valid_restored, disc_restored = verify_manifest_against_repo(clean_restored, repo_root=repo_dir, require_clean=True)
    assert valid_restored is True
    assert disc_restored == []

    clean_bytes_restored = serialize_manifest(clean_restored).encode("utf-8")
    valid_bytes_restored, disc_bytes_restored = verify_manifest_bytes(clean_bytes_restored, repo_root=repo_dir)
    assert valid_bytes_restored is True
    assert disc_bytes_restored == []


def test_c02_s02_exact_canonical_bytes_contract(clean_git_repo: Path) -> None:
    """C02-S02: Mandatory exact canonical-byte verification tests."""
    manifest = generate_manifest(repo_root=clean_git_repo, require_clean=True)
    canonical_str = serialize_manifest(manifest)
    canonical_bytes = canonical_str.encode("utf-8")

    # 1. Canonical LF JSON passes
    valid_lf, disc_lf = verify_manifest_bytes(canonical_bytes, repo_root=clean_git_repo)
    assert valid_lf is True
    assert disc_lf == []

    # 2. Identical JSON with CRLF fails exact-byte verification
    crlf_bytes = canonical_bytes.replace(b"\n", b"\r\n")
    valid_crlf, disc_crlf = verify_manifest_bytes(crlf_bytes, repo_root=clean_git_repo)
    assert valid_crlf is False
    assert any("do not match canonical serialization byte-for-byte" in d for d in disc_crlf)

    # 3. Whitespace changes fail (e.g. 4-space indentation)
    ws_bytes = json.dumps(manifest, indent=4, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
    valid_ws, disc_ws = verify_manifest_bytes(ws_bytes, repo_root=clean_git_repo)
    assert valid_ws is False
    assert any("do not match canonical serialization byte-for-byte" in d for d in disc_ws)

    # 4. Additional trailing newlines fail
    extra_nl_bytes = canonical_bytes + b"\n"
    valid_extra_nl, disc_extra_nl = verify_manifest_bytes(extra_nl_bytes, repo_root=clean_git_repo)
    assert valid_extra_nl is False
    assert any("do not match canonical serialization byte-for-byte" in d for d in disc_extra_nl)

    # 5. UTF-8 BOM fails
    bom_bytes = b"\xef\xbb\xbf" + canonical_bytes
    valid_bom, disc_bom = verify_manifest_bytes(bom_bytes, repo_root=clean_git_repo)
    assert valid_bom is False
    assert any("BOM" in d or "byte-for-byte" in d for d in disc_bom)

    # 6. Repeated clean generation remains byte-for-byte deterministic
    manifest_repeat = generate_manifest(repo_root=clean_git_repo, require_clean=True)
    canonical_bytes_repeat = serialize_manifest(manifest_repeat).encode("utf-8")
    assert canonical_bytes == canonical_bytes_repeat

    # 7. Existing schema validation continues to reject incomplete manifests
    incomplete = {"source_commit_sha": get_git_commit_sha(clean_git_repo), "configurations": {}}
    valid_inc, disc_inc = verify_manifest_against_repo(incomplete, repo_root=clean_git_repo, require_clean=True)
    assert valid_inc is False
    assert len(disc_inc) > 0
