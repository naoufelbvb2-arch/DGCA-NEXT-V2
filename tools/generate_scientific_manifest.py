#!/usr/bin/env python3
"""Deterministic Scientific Manifest Generator for DGCA NEXT V2 (R2-A01 Patch 5).

Normative references:
- R2-A01-IMPLEMENTATION-PLAN.md §2 (Patch 5: Manifest Generator & Durable Persistence Boundary Isolation)
- R2-A01-REMEDIATION-DESIGN-CONTRACT.md §3.4 (Durable Persistence Boundaries)
- DGCA_CORE_RC4_1.md §11 (Reproducibility, Cold Reset & Scientific Provenance)
- DGCA_LLA_RC4_1.md §8.2 (Experiment Provenance and Metrics Manifest)

Artifact & Commit-SHA Policy:
-----------------------------
The scientific manifest is an execution-time reproducibility artifact generated
dynamically during verification runs, test suites, and scientific release packaging.
It is explicitly NOT tracked in Git as a static repository file.
Tracking the manifest containing its own commit's SHA would create a circular,
self-referential commit-SHA defect (committing the updated manifest changes the
Git HEAD SHA, invalidating the SHA recorded inside the manifest).

Instead, this generator script (`tools/generate_scientific_manifest.py`) is the
version-controlled canonical tool. It programmatically queries the authoritative
Git object database (`git rev-parse HEAD`) at execution time and records the
exact source SHA and direct SHA-256 digests of all scientific configuration files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence

SCHEMA_VERSION: str = "1.0.0"
REPOSITORY_IDENTIFIER: str = "naoufelbvb2-arch/DGCA-NEXT-V2"

DEFAULT_CONFIG_FILES: tuple[str, ...] = (
    "configs/lab_rc2_ablation.json",
    "configs/lab_rc4_1_default.json",
)

RELEVANT_SOURCE_PATHS: tuple[str, ...] = ("src", "configs", "tools")


def get_repo_root() -> Path:
    """Resolve the repository root directory relative to this script's location.

    This ensures repository-relative execution independent of current working directory,
    IDE workspace settings, or scratch environments.
    """
    # tools/generate_scientific_manifest.py -> repo_root is parent of tools
    return Path(__file__).resolve().parent.parent


def check_source_cleanliness(
    repo_root: Path,
    relevant_paths: Sequence[str] | None = None,
) -> tuple[bool, list[str]]:
    """Check whether relevant tracked source or configuration files have uncommitted modifications.

    Distinguishes:
    - Clean committed source.
    - Modified tracked source (staged or unstaged).
    - Relevant untracked source files in relevant scientific directories.
    - Irrelevant build caches and harmless artifacts (ignored via .gitignore).

    Returns:
        (is_clean, list_of_dirty_entries)
    """
    if relevant_paths is None:
        existing_targets = [p for p in RELEVANT_SOURCE_PATHS if (repo_root / p).exists()]
        if not existing_targets:
            target_args: list[str] = []
        else:
            target_args = ["--"] + existing_targets
    else:
        target_args = ["--"] + list(relevant_paths)

    cmd = ["git", "status", "--porcelain"] + target_args
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError) as exc:
        return False, [f"Failed to execute git status: {exc}"]

    if proc.returncode != 0:
        err = proc.stderr.strip() if proc.stderr else f"exit code {proc.returncode}"
        return False, [f"Git status returned error: {err}"]

    dirty: list[str] = []
    for line in proc.stdout.splitlines():
        trimmed = line.strip()
        if not trimmed:
            continue
        status_code = line[:2]
        path_part = line[3:].strip()
        # Filter out harmless temporary/cache patterns if any leaked through
        if any(ignored in path_part for ignored in ("__pycache__", ".pytest_cache", ".coverage")):
            continue
        dirty.append(f"{status_code} {path_part}")

    return len(dirty) == 0, dirty


def get_git_commit_sha(repo_root: Path) -> str:
    """Retrieve the authoritative Git HEAD commit SHA for the repository.

    Args:
        repo_root: Absolute path to repository root containing .git directory.

    Returns:
        Full 40-character hexadecimal lowercase Git commit SHA.

    Raises:
        RuntimeError: If git is unavailable, the directory is not a Git repo,
                      or git rev-parse HEAD returns an error or invalid SHA.
    """
    git_dir = repo_root / ".git"
    if not git_dir.exists():
        raise RuntimeError(
            f"Repository root '{repo_root}' does not contain an authoritative .git directory; "
            "cannot establish source commit identity."
        )

    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Git executable not found in PATH; cannot establish authoritative source identity."
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            f"OS error executing git rev-parse: {exc}"
        ) from exc

    if proc.returncode != 0:
        err_msg = proc.stderr.strip() if proc.stderr else f"exit code {proc.returncode}"
        raise RuntimeError(
            f"Failed to extract Git commit SHA via 'git rev-parse HEAD': {err_msg}"
        )

    sha = proc.stdout.strip()
    if len(sha) != 40 or not all(c in "0123456789abcdefABCDEF" for c in sha):
        raise RuntimeError(
            f"Invalid Git commit SHA format returned: {sha!r} (expected 40-character hex string)"
        )

    return sha.lower()


def compute_file_sha256(file_path: Path) -> str:
    """Compute the SHA-256 hex digest directly from the raw bytes of a file.

    Args:
        file_path: Path to the target file.

    Returns:
        64-character lowercase hexadecimal SHA-256 digest.

    Raises:
        FileNotFoundError: If the file does not exist.
        IsADirectoryError: If the path is a directory.
        OSError: If the file cannot be read.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Configuration file does not exist: {file_path}")
    if not file_path.is_file():
        raise IsADirectoryError(f"Configuration path is not a file: {file_path}")

    data = file_path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def generate_manifest(
    repo_root: Path | None = None,
    config_rel_paths: Sequence[str] | None = None,
    require_clean: bool = True,
) -> dict[str, Any]:
    """Generate the deterministic scientific manifest dictionary.

    Args:
        repo_root: Optional explicit repository root. Defaults to auto-resolved root.
        config_rel_paths: Optional sequence of repo-relative configuration paths.
                         Defaults to DEFAULT_CONFIG_FILES.
        require_clean: Whether to enforce that relevant scientific source files have
                       no uncommitted modifications. Defaults to True.

    Returns:
        Deterministic manifest dictionary containing source SHA, configuration hashes,
        repository-relative paths, and schema version.

    Raises:
        RuntimeError: If working tree contains uncommitted changes in relevant paths
                      and require_clean is True, or if Git identity cannot be resolved.
        FileNotFoundError: If a configuration file is missing.
        ValueError: If a path resolves outside the repository root.
    """
    if repo_root is None:
        resolved_repo_root = get_repo_root()
    else:
        resolved_repo_root = repo_root.resolve()

    if config_rel_paths is None:
        target_configs = DEFAULT_CONFIG_FILES
    else:
        target_configs = tuple(config_rel_paths)

    # Source integrity check
    if require_clean:
        is_clean, dirty_entries = check_source_cleanliness(resolved_repo_root)
        if not is_clean:
            raise RuntimeError(
                f"Working tree has uncommitted modifications in relevant scientific paths; "
                f"cannot generate authoritative manifest: {dirty_entries}"
            )

    commit_sha = get_git_commit_sha(resolved_repo_root)

    configurations: dict[str, dict[str, Any]] = {}
    configuration_hashes: dict[str, str] = {}

    for rel_path in sorted(target_configs):
        norm_rel = Path(rel_path).as_posix()
        abs_path = (resolved_repo_root / norm_rel).resolve()

        # Enforce that paths are within repository root
        try:
            abs_path.relative_to(resolved_repo_root)
        except ValueError as exc:
            raise ValueError(
                f"Configuration path '{rel_path}' resolves outside repository root '{resolved_repo_root}'"
            ) from exc

        digest = compute_file_sha256(abs_path)
        size_bytes = abs_path.stat().st_size

        configurations[norm_rel] = {
            "path": norm_rel,
            "sha256": digest,
            "size_bytes": size_bytes,
        }
        configuration_hashes[norm_rel] = digest

    manifest: dict[str, Any] = {
        "configuration_hashes": configuration_hashes,
        "configurations": configurations,
        "schema_version": SCHEMA_VERSION,
        "source": {
            "commit_sha": commit_sha,
            "repository": REPOSITORY_IDENTIFIER,
        },
        "source_commit_sha": commit_sha,
    }

    return manifest


def serialize_manifest(manifest: dict[str, Any]) -> str:
    """Serialize the manifest dictionary into a canonical, deterministic JSON string.

    Uses sorted keys, 2-space indentation, and UTF-8 encoding.
    """
    return json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def compute_manifest_digest(manifest_str: str) -> str:
    """Compute the SHA-256 digest of the canonical manifest JSON string."""
    return hashlib.sha256(manifest_str.encode("utf-8")).hexdigest()


def verify_manifest_against_repo(
    manifest_data: dict[str, Any],
    repo_root: Path | None = None,
    require_clean: bool = True,
) -> tuple[bool, list[str]]:
    """Verify that a manifest satisfies the complete canonical schema and matches repo state.

    Enforces:
    1. Working tree cleanliness in relevant scientific paths (if require_clean is True).
    2. Exact top-level required fields (no missing, no unexpected).
    3. Exact schema version.
    4. Exact repository identifier.
    5. Authoritative source commit SHA matching repository HEAD.
    6. Exact consistency between source.commit_sha and source_commit_sha.
    7. Complete authoritative configuration inventory (no missing, no unexpected entries).
    8. SHA-256 digest match for every configuration file directly against disk.
    9. Byte size match for every configuration file directly against disk.
    10. Exact correspondence between configuration_hashes and configurations.
    11. Rejection of malformed field types.
    12. Rejection of repository-escaping or absolute configuration paths.
    13. Rejection of contradictory metadata.

    Returns:
        (is_valid, list_of_discrepancies)
    """
    discrepancies: list[str] = []
    if repo_root is None:
        repo_root = get_repo_root()
    else:
        repo_root = repo_root.resolve()

    # 1. Working tree cleanliness
    if require_clean:
        is_clean, dirty_entries = check_source_cleanliness(repo_root)
        if not is_clean:
            discrepancies.append(
                f"Working tree has uncommitted modifications in relevant scientific paths: {dirty_entries}"
            )

    # 2. Type check
    if not isinstance(manifest_data, dict):
        return False, ["Manifest root must be a JSON object (dict)"]

    # 3. Required top-level keys
    expected_top_keys = {
        "configuration_hashes",
        "configurations",
        "schema_version",
        "source",
        "source_commit_sha",
    }
    actual_top_keys = set(manifest_data.keys())
    missing_top_keys = expected_top_keys - actual_top_keys
    if missing_top_keys:
        discrepancies.append(f"Missing required top-level field(s): {sorted(missing_top_keys)}")
    unexpected_top_keys = actual_top_keys - expected_top_keys
    if unexpected_top_keys:
        discrepancies.append(f"Unexpected top-level field(s) under canonical schema: {sorted(unexpected_top_keys)}")

    # 4. Schema version
    if manifest_data.get("schema_version") != SCHEMA_VERSION:
        discrepancies.append(
            f"Schema version mismatch: recorded {manifest_data.get('schema_version')!r} != expected {SCHEMA_VERSION!r}"
        )

    # 5. Source object and Commit SHA
    source_obj = manifest_data.get("source")
    source_commit_sha = manifest_data.get("source_commit_sha")

    if not isinstance(source_obj, dict):
        discrepancies.append("Field 'source' must be a JSON object (dict)")
    else:
        expected_source_keys = {"commit_sha", "repository"}
        if set(source_obj.keys()) != expected_source_keys:
            discrepancies.append(
                f"Field 'source' must contain exactly {sorted(expected_source_keys)}, got {sorted(source_obj.keys())}"
            )
        if source_obj.get("repository") != REPOSITORY_IDENTIFIER:
            discrepancies.append(
                f"Repository identifier mismatch: recorded {source_obj.get('repository')!r} != expected {REPOSITORY_IDENTIFIER!r}"
            )

        nested_sha = source_obj.get("commit_sha")
        if nested_sha != source_commit_sha:
            discrepancies.append(
                f"Contradictory source commit SHAs: source.commit_sha={nested_sha!r} != source_commit_sha={source_commit_sha!r}"
            )

        if not isinstance(nested_sha, str) or len(nested_sha) != 40 or not all(c in "0123456789abcdef" for c in nested_sha.lower()):
            discrepancies.append(f"Malformed source commit SHA format in source.commit_sha: {nested_sha!r}")
        elif not isinstance(source_commit_sha, str) or len(source_commit_sha) != 40 or not all(c in "0123456789abcdef" for c in source_commit_sha.lower()):
            discrepancies.append(f"Malformed source commit SHA format in source_commit_sha: {source_commit_sha!r}")
        else:
            try:
                actual_sha = get_git_commit_sha(repo_root)
                if nested_sha != actual_sha:
                    discrepancies.append(
                        f"Source commit SHA mismatch: recorded {nested_sha!r} != actual repository HEAD {actual_sha!r}"
                    )
            except Exception as exc:
                discrepancies.append(f"Failed to inspect repository Git commit: {exc}")

    # 6. Configurations inventory and validation
    configs_obj = manifest_data.get("configurations")
    if not isinstance(configs_obj, dict):
        discrepancies.append("Field 'configurations' must be a JSON object (dict)")
    else:
        expected_configs = set(DEFAULT_CONFIG_FILES)
        actual_configs = set(configs_obj.keys())

        missing_configs = expected_configs - actual_configs
        if missing_configs:
            discrepancies.append(f"Missing required configuration entries: {sorted(missing_configs)}")

        unexpected_configs = actual_configs - expected_configs
        if unexpected_configs:
            discrepancies.append(f"Unexpected configuration entries under canonical schema: {sorted(unexpected_configs)}")

        for rel_path, meta in configs_obj.items():
            if not isinstance(rel_path, str):
                discrepancies.append(f"Configuration key must be a string, got {type(rel_path).__name__}")
                continue

            # Path formatting and safety
            if "\\" in rel_path:
                discrepancies.append(f"Configuration path {rel_path!r} must use POSIX forward slashes")
            if Path(rel_path).is_absolute() or rel_path.startswith("/"):
                discrepancies.append(f"Configuration path {rel_path!r} must be relative, not absolute")
            if ".." in Path(rel_path).parts:
                discrepancies.append(f"Configuration path {rel_path!r} must not traverse outside repository")

            if not isinstance(meta, dict):
                discrepancies.append(f"Configuration entry for {rel_path!r} must be a dict")
                continue

            expected_meta_keys = {"path", "sha256", "size_bytes"}
            if set(meta.keys()) != expected_meta_keys:
                discrepancies.append(f"Configuration entry {rel_path!r} must contain {sorted(expected_meta_keys)}, got {sorted(meta.keys())}")

            if meta.get("path") != rel_path:
                discrepancies.append(f"Contradictory path in entry {rel_path!r}: meta.path={meta.get('path')!r}")

            recorded_hash = meta.get("sha256")
            if not isinstance(recorded_hash, str) or len(recorded_hash) != 64 or not all(c in "0123456789abcdef" for c in recorded_hash.lower()):
                discrepancies.append(f"Malformed sha256 digest in entry {rel_path!r}: {recorded_hash!r}")

            recorded_size = meta.get("size_bytes")
            if not isinstance(recorded_size, int) or recorded_size < 0:
                discrepancies.append(f"Malformed size_bytes in entry {rel_path!r}: {recorded_size!r}")

            # Direct verification against actual filesystem
            norm_rel = Path(rel_path).as_posix()
            abs_target = (repo_root / norm_rel).resolve()
            try:
                abs_target.relative_to(repo_root)
            except ValueError:
                discrepancies.append(f"Configuration path {rel_path!r} resolves outside repository root")
                continue

            if not abs_target.is_file():
                discrepancies.append(f"Configuration file does not exist on disk: {rel_path}")
            else:
                try:
                    actual_hash = compute_file_sha256(abs_target)
                    actual_size = abs_target.stat().st_size
                    if recorded_hash != actual_hash:
                        discrepancies.append(
                            f"Configuration hash mismatch for {rel_path}: recorded {recorded_hash} != actual {actual_hash}"
                        )
                    if recorded_size != actual_size:
                        discrepancies.append(
                            f"Configuration size mismatch for {rel_path}: recorded {recorded_size} != actual {actual_size}"
                        )
                except Exception as exc:
                    discrepancies.append(f"Failed to read configuration file {rel_path}: {exc}")

    # 7. Configuration hashes mapping correspondence
    hashes_obj = manifest_data.get("configuration_hashes")
    if not isinstance(hashes_obj, dict):
        discrepancies.append("Field 'configuration_hashes' must be a JSON object (dict)")
    else:
        if isinstance(configs_obj, dict):
            if set(hashes_obj.keys()) != set(configs_obj.keys()):
                discrepancies.append(
                    f"Keys in configuration_hashes {sorted(hashes_obj.keys())} do not match configurations {sorted(configs_obj.keys())}"
                )
            for k, recorded_h in hashes_obj.items():
                if not isinstance(recorded_h, str) or len(recorded_h) != 64:
                    discrepancies.append(f"Malformed sha256 in configuration_hashes[{k!r}]: {recorded_h!r}")
                cfg_h = configs_obj.get(k, {}).get("sha256") if isinstance(configs_obj.get(k), dict) else None
                if recorded_h != cfg_h:
                    discrepancies.append(
                        f"Contradictory hash for {k!r}: configuration_hashes has {recorded_h!r} but configurations has {cfg_h!r}"
                    )

    return len(discrepancies) == 0, discrepancies


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for deterministic scientific manifest generation."""
    parser = argparse.ArgumentParser(
        description="Deterministic Scientific Manifest Generator for DGCA NEXT V2 (R2-A01 Patch 5)."
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Optional path to write the canonical manifest JSON.",
    )
    parser.add_argument(
        "--repo-root",
        type=str,
        default=None,
        help="Explicit repository root directory (defaults to parent directory of tools/).",
    )
    parser.add_argument(
        "--canonical-digest",
        action="store_true",
        help="Print only the SHA-256 digest of the canonical manifest JSON.",
    )
    parser.add_argument(
        "--check",
        type=str,
        default=None,
        help="Verify an existing manifest file against current repository state.",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow generation or checking against a dirty working tree (non-authoritative).",
    )

    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root()
    require_clean = not args.allow_dirty

    if args.check:
        check_path = Path(args.check).resolve()
        if not check_path.exists():
            sys.stderr.write(f"Error: Manifest file to check not found: {check_path}\n")
            return 1
        try:
            candidate_bytes = check_path.read_bytes()
            try:
                candidate_text = candidate_bytes.decode("utf-8")
                manifest_data = json.loads(candidate_text)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                sys.stderr.write(f"Manifest check FAILED: candidate is not valid UTF-8 JSON: {exc}\n")
                return 1

            valid, discrepancies = verify_manifest_against_repo(
                manifest_data,
                repo_root=repo_root,
                require_clean=require_clean,
            )
            if not valid:
                sys.stderr.write("Manifest check FAILED:\n")
                for d in discrepancies:
                    sys.stderr.write(f"  - {d}\n")
                return 1

            # Exact canonical byte equality check (normalizing CRLF to LF for cross-platform portability)
            expected_manifest = generate_manifest(
                repo_root=repo_root,
                require_clean=require_clean,
            )
            canonical_bytes = serialize_manifest(expected_manifest).encode("utf-8")
            normalized_candidate = candidate_bytes.replace(b"\r\n", b"\n")
            if normalized_candidate != canonical_bytes:
                sys.stderr.write("Manifest check FAILED:\n")
                sys.stderr.write("  - Candidate file bytes do not match canonical serialization byte-for-byte.\n")
                return 1

            sys.stdout.write("Manifest check PASSED: canonical manifest matches repository state byte-for-byte.\n")
            return 0
        except Exception as exc:
            sys.stderr.write(f"Error during manifest verification: {exc}\n")
            return 1

    try:
        manifest = generate_manifest(repo_root=repo_root, require_clean=require_clean)
        canonical_str = serialize_manifest(manifest)
    except Exception as exc:
        sys.stderr.write(f"Error generating scientific manifest: {exc}\n")
        return 1

    if args.canonical_digest:
        digest = compute_manifest_digest(canonical_str)
        sys.stdout.write(f"{digest}\n")
        return 0

    if args.output:
        out_path = Path(args.output).resolve()
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(canonical_str.encode("utf-8"))
        except OSError as exc:
            sys.stderr.write(f"Error writing manifest to '{out_path}': {exc}\n")
            return 1
    else:
        sys.stdout.write(canonical_str)

    return 0


if __name__ == "__main__":
    sys.exit(main())
