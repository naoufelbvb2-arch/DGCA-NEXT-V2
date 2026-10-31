"""Portable, immutable, source-pinned verification fixture for frozen production baseline.

Authoritative Source Provenance:
- Commit SHA: faf361b6b95de6287b466eb1dc524ea49c732635
- Blob SHA:   ed0a0e4b12191d119ea687b4c7d8b6970cfc9be9
- Source Path: src/dgca/core/assembly.py
- Symbol:     _try_merge_pair
- AST Digest: e9cb637e0e1675059f1ae682cdc9be455d1f754bb0e8e1f83f72c6f3406ee8d7
"""

from __future__ import annotations

import ast
import enum
import hashlib
import inspect
import subprocess
from typing import Any

from dgca.core.assembly import (
    K_MAX,
    M_MAX,
    THETA_MERGE,
    THETA_OB,
    _is_in_merge_split_cooldown,
    compute_mutual_support_r_b,
    _live_assembly_ids_for_cell,
    check_maintain_keep_guards,
    _rebuild_assemblies_by_member,
)
from dgca.core.state import (
    AssemblyStatus,
    WState,
)

FROZEN_BASELINE_COMMIT_SHA: str = "faf361b6b95de6287b466eb1dc524ea49c732635"
FROZEN_BASELINE_BLOB_SHA: str = "ed0a0e4b12191d119ea687b4c7d8b6970cfc9be9"
FROZEN_BASELINE_PATH: str = "src/dgca/core/assembly.py"
FROZEN_BASELINE_SYMBOL: str = "_try_merge_pair"
FROZEN_BASELINE_AST_SHA256: str = "e9cb637e0e1675059f1ae682cdc9be455d1f754bb0e8e1f83f72c6f3406ee8d7"


class ProvenanceStatus(str, enum.Enum):
    """Authoritative fixture provenance verification outcome (R2-B05-S04)."""
    PROVENANCE_VERIFIED = "PROVENANCE_VERIFIED"
    PROVENANCE_UNAVAILABLE = "PROVENANCE_UNAVAILABLE"
    PROVENANCE_MISMATCH = "PROVENANCE_MISMATCH"


def _baseline_try_merge_pair(
    a_id: int,
    b_id: int,
    w: WState,
    n_rec_cache: dict[int, dict[int, float]],
) -> bool:
    """Attempt to merge live Assembly pair (a_id < b_id) under frozen Core §2.0 item 4.

    This implementation is source-pinned to blob ed0a0e4b12191d119ea687b4c7d8b6970cfc9be9
    from commit faf361b6b95de6287b466eb1dc524ea49c732635.
    """
    if a_id not in w.assemblies or b_id not in w.assemblies:
        return False
    asm_a = w.assemblies[a_id]
    asm_b = w.assemblies[b_id]
    if asm_a.status != AssemblyStatus.LIVE or asm_b.status != AssemblyStatus.LIVE:
        return False
    if _is_in_merge_split_cooldown(asm_a, w) or _is_in_merge_split_cooldown(asm_b, w):
        return False

    set_a = set(asm_a.member_cell_ids)
    set_b = set(asm_b.member_cell_ids)
    union_set = set_a | set_b
    if len(union_set) > K_MAX or not union_set:
        return False

    inter_set = set_a & set_b
    jaccard = float(len(inter_set)) / float(len(union_set))
    if jaccard < THETA_MERGE:
        return False

    excl_a = sorted(set_a - set_b)
    excl_b = sorted(set_b - set_a)
    if not excl_a or not excl_b:
        between_strength = 0.0
    else:
        cross_vals = [
            compute_mutual_support_r_b(i, j, w)
            for i in excl_a
            for j in excl_b
        ]
        between_strength = sum(cross_vals) / float(len(cross_vals))

    if between_strength < THETA_OB:
        return False

    union_tuple = tuple(sorted(union_set))
    # Membership limit check after archiving B and keeping A
    for x in union_tuple:
        live_after = (_live_assembly_ids_for_cell(x, w) - {b_id}) | {a_id}
        if len(live_after) > M_MAX:
            return False
        if not check_maintain_keep_guards(x, union_tuple, w, n_rec_cache):
            return False

    # Merge into lower ID A, archive higher ID B
    asm_a.member_cell_ids = union_tuple
    asm_a.structural_generation += 1
    asm_a.last_mutation_close_serial = w.close_serial
    asm_a.last_merge_split_close_serial = w.completed_external_events_count

    asm_b.status = AssemblyStatus.ARCHIVED
    asm_b.structural_generation += 1
    asm_b.last_mutation_close_serial = w.close_serial
    asm_b.last_merge_split_close_serial = w.completed_external_events_count

    _rebuild_assemblies_by_member(w)
    return True


def verify_fixture_self_integrity() -> bool:
    """Verify internal cryptographic content digest of the portable fixture AST."""
    local_tree = ast.parse(inspect.getsource(_baseline_try_merge_pair))
    local_func = local_tree.body[0]
    local_func.name = "canonical_merge"
    local_func.body = [
        s for s in local_func.body
        if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
    ]
    digest = hashlib.sha256(ast.dump(local_func).encode("utf-8")).hexdigest()
    return digest == FROZEN_BASELINE_AST_SHA256


def verify_fixture_provenance_against_git() -> ProvenanceStatus:
    """Verify that this fixture AST matches the frozen repository blob if git is available.

    Returns:
    - PROVENANCE_VERIFIED: Git evidence is present and blob AST matches fixture AST exactly.
    - PROVENANCE_UNAVAILABLE: Git is unavailable or running in a shallow/isolated archive.
    - PROVENANCE_MISMATCH: Internal self-integrity failed or Git blob does not match fixture.
    """
    # 1. First assert self-integrity against pinned cryptographic digest (fails closed)
    if not verify_fixture_self_integrity():
        return ProvenanceStatus.PROVENANCE_MISMATCH

    # 2. Attempt to inspect authentic git blob from repository history
    try:
        raw_blob = subprocess.check_output(
            ["git", "cat-file", "-p", FROZEN_BASELINE_BLOB_SHA],
            text=True,
            encoding="utf-8",
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ProvenanceStatus.PROVENANCE_UNAVAILABLE

    try:
        tree = ast.parse(raw_blob)
        git_func = None
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == FROZEN_BASELINE_SYMBOL:
                git_func = node
                break

        if git_func is None:
            return ProvenanceStatus.PROVENANCE_MISMATCH

        git_func.name = "canonical_merge"
        git_func.body = [
            s for s in git_func.body
            if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
        ]
        git_digest = hashlib.sha256(ast.dump(git_func).encode("utf-8")).hexdigest()

        if git_digest == FROZEN_BASELINE_AST_SHA256:
            return ProvenanceStatus.PROVENANCE_VERIFIED
        else:
            return ProvenanceStatus.PROVENANCE_MISMATCH
    except Exception:
        return ProvenanceStatus.PROVENANCE_MISMATCH
