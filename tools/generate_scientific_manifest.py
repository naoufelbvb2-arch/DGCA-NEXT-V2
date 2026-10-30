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


def get_repo_root() -> Path:
    """Resolve the repository root directory relative to this script's location.

    This ensures repository-relative execution independent of current working directory,
    IDE workspace settings, or scratch environments.
    """
    # tools/generate_scientific_manifest.py -> repo_root is parent of tools
    return Path(__file__).resolve().parent.parent


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
) -> dict[str, Any]:
    """Generate the deterministic scientific manifest dictionary.

    Args:
        repo_root: Optional explicit repository root. Defaults to auto-resolved root.
        config_rel_paths: Optional sequence of repo-relative configuration paths.
                         Defaults to DEFAULT_CONFIG_FILES.

    Returns:
        Deterministic manifest dictionary containing source SHA, configuration hashes,
        repository-relative paths, and schema version.
    """
    if repo_root is None:
        resolved_repo_root = get_repo_root()
    else:
        resolved_repo_root = repo_root.resolve()

    if config_rel_paths is None:
        target_configs = DEFAULT_CONFIG_FILES
    else:
        target_configs = tuple(config_rel_paths)

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
) -> tuple[bool, list[str]]:
    """Verify that an existing manifest matches current repository state.

    Returns:
        (is_valid, list_of_discrepancies)
    """
    discrepancies: list[str] = []
    if repo_root is None:
        repo_root = get_repo_root()
    else:
        repo_root = repo_root.resolve()

    # Verify commit SHA
    try:
        current_sha = get_git_commit_sha(repo_root)
        manifest_sha = manifest_data.get("source_commit_sha") or manifest_data.get("source", {}).get("commit_sha")
        if manifest_sha != current_sha:
            discrepancies.append(
                f"Source commit SHA mismatch: recorded {manifest_sha!r} != actual {current_sha!r}"
            )
    except Exception as exc:
        discrepancies.append(f"Failed to inspect repository Git commit: {exc}")

    # Verify configurations
    configs = manifest_data.get("configurations", {})
    for rel_path, meta in configs.items():
        norm_rel = Path(rel_path).as_posix()
        abs_path = (repo_root / norm_rel).resolve()
        expected_hash = meta.get("sha256") if isinstance(meta, dict) else meta
        try:
            actual_hash = compute_file_sha256(abs_path)
            if actual_hash != expected_hash:
                discrepancies.append(
                    f"Configuration hash mismatch for {rel_path}: recorded {expected_hash} != actual {actual_hash}"
                )
        except Exception as exc:
            discrepancies.append(f"Failed to verify configuration {rel_path}: {exc}")

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

    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root()

    if args.check:
        check_path = Path(args.check).resolve()
        if not check_path.exists():
            sys.stderr.write(f"Error: Manifest file to check not found: {check_path}\n")
            return 1
        try:
            manifest_data = json.loads(check_path.read_text(encoding="utf-8"))
            valid, discrepancies = verify_manifest_against_repo(manifest_data, repo_root=repo_root)
            if not valid:
                sys.stderr.write("Manifest check FAILED:\n")
                for d in discrepancies:
                    sys.stderr.write(f"  - {d}\n")
                return 1
            sys.stdout.write("Manifest check PASSED: current repository state matches manifest.\n")
            return 0
        except Exception as exc:
            sys.stderr.write(f"Error during manifest verification: {exc}\n")
            return 1

    try:
        manifest = generate_manifest(repo_root=repo_root)
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
            out_path.write_text(canonical_str, encoding="utf-8")
        except OSError as exc:
            sys.stderr.write(f"Error writing manifest to '{out_path}': {exc}\n")
            return 1
    else:
        sys.stdout.write(canonical_str)

    return 0


if __name__ == "__main__":
    sys.exit(main())
