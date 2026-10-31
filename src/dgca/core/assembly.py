"""RC4 Executable Structural Assembly Operators (MAINTAIN -> GROW -> FORM -> MERGE -> SPLIT).

Normative references:
- DGCA_CORE_RC4_1.md §2 & §2.0 (Assembly and Context Attractor; RC4 executable Assembly operators)
- DGCA_CORE_RC4_1.md §9.4.1 (RC4.1 Assembly birth-to-attestation training budget)
- DGCA_LLA_RC4_1.md §6.6, §8.2 & §8.3 (LG-T01, LG-T02, LG-T03, LG-T16)
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from dgca.common.errors import DGCAError, StatusCode
from dgca.common.hashing import Region
from dgca.common.numeric import q6_from_binary64
from dgca.core.anatomy import SynapseKey, SynapseScope
from dgca.core.context_gate import is_legal_consolidated_synapse
from dgca.core.dynamics import EventExecutionResult
from dgca.core.sic_v1 import CellAddress
from dgca.core.state import (
    Assembly,
    AssemblyStatus,
    ContributionLane,
    HSlowState,
    WState,
)
from dgca.encoder.envelope import EventOrigin

# Core §2.0 & §12.1 Normative Assembly Parameters
THETA_A: float = 0.10
OMEGA_X: float = 0.85
K_MIN: int = 3
K_MAX: int = 16
M_MAX: int = 12
D_MIN: int = 2
RHO_CORE: float = 0.70
RHO_G: float = 0.50
SIGMA_G: float = 0.30
RHO_KEEP: float = 0.35
SIGMA_KEEP: float = 0.20
K_FORM_PER_END: int = 12
THETA_MERGE: float = 0.70
THETA_OB: float = 0.40
T_C_COOLDOWN: int = 200
N_MIN_SPLIT: int = 6
THETA_WEAK: float = 0.15
THETA_SEP: float = 0.10
THETA_FRESH_ADMIT: float = 0.40


@dataclass(frozen=True, slots=True)
class AssemblyEndReport:
    """Summary of one deterministic END_EXPOSURE Assembly update pass (Core §2.0)."""

    maintained_ids: tuple[int, ...] = ()
    archived_by_maintain_ids: tuple[int, ...] = ()
    grown_ids: tuple[int, ...] = ()
    formed_ids: tuple[int, ...] = ()
    merged_pairs: tuple[tuple[int, int], ...] = ()
    split_pairs: tuple[tuple[int, int], ...] = ()
    diagnostics: tuple[StatusCode, ...] = ()


def is_eligible_assembly_member_cell(cell_id: int, w: WState) -> bool:
    """Check if cell_id is a committed LANGUAGE cell and not an incomplete contextual candidate (Core §2.0)."""
    if cell_id not in w.committed_cells:
        return False
    if cell_id in w.context_candidates:
        return False
    addr = CellAddress.from_global_id(cell_id)
    if addr.region != Region.LANGUAGE:
        return False
    # If cell_id is a completed contextual cell, its StableBinding must be ACTIVE
    if cell_id in w.stable_bindings:
        from dgca.core.context_gate import validate_and_refresh_stable_binding

        ok, _ = validate_and_refresh_stable_binding(w.stable_bindings[cell_id], w)
        if not ok:
            return False
    return True


def compute_mutual_support_r_b(i: int, j: int, w: WState) -> float:
    """Compute reciprocal structural support R_ij^B from live CONSOLIDATED links only (Core §2.0).

    Formula:
        R_ij^B = max(min(Q_ij^LOCAL, Q_ji^LOCAL), omega_X * min(Q_ij^CROSS, Q_ji^CROSS))
    In the first laboratory, all Assembly members must be committed LANGUAGE cells and
    mutual LOCAL links construct it; absent/illegal/nonconsolidated directed keys yield R^B = 0.
    """
    if i == j:
        return 0.0
    if not (is_eligible_assembly_member_cell(i, w) and is_eligible_assembly_member_cell(j, w)):
        return 0.0

    key_ij_loc: SynapseKey = (i, j, SynapseScope.LOCAL)
    key_ji_loc: SynapseKey = (j, i, SynapseScope.LOCAL)
    if is_legal_consolidated_synapse(key_ij_loc, w) and is_legal_consolidated_synapse(key_ji_loc, w):
        r_local = min(w.synapses[key_ij_loc].Q, w.synapses[key_ji_loc].Q)
    else:
        r_local = 0.0

    return r_local


def has_reciprocal_edge_e_b(i: int, j: int, w: WState) -> bool:
    """Evaluate e_ij^B = 1[R_ij^B >= theta_A = 0.10] (Core §2.0)."""
    return compute_mutual_support_r_b(i, j, w) >= THETA_A


def get_reciprocal_neighbors_n_rec(
    x: int,
    w: WState,
    cache: dict[int, dict[int, float]] | None = None,
) -> dict[int, float]:
    """Return N_rec(x) = {k != x : e_xk^B == 1} mapped to R_xk^B across committed LANGUAGE cells (Core §2.0)."""
    if cache is not None and x in cache:
        return cache[x]

    if not is_eligible_assembly_member_cell(x, w):
        if cache is not None:
            cache[x] = {}
        return {}

    neighbors: dict[int, float] = {}
    for key in w.outgoing_by_source.get(x, ()):
        _, k, scope = key
        if scope != SynapseScope.LOCAL or k == x:
            continue
        r_xk = compute_mutual_support_r_b(x, k, w)
        if r_xk >= THETA_A:
            neighbors[k] = r_xk

    if cache is not None:
        cache[x] = neighbors
    return neighbors


def compute_assembly_member_metrics(
    x: int,
    member_ids: Iterable[int],
    w: WState,
    n_rec_cache: dict[int, dict[int, float]] | None = None,
) -> tuple[int, float, float]:
    """Compute (d(x, A), D(x, A), Spec(x, A)) for cell x relative to member set A (Core §2.0).

    Formulas:
        d(x, A) = sum_{j in A \\ {x}} e_xj^B
        D(x, A) = d(x, A) / |A \\ {x}|  if |A \\ {x}| > 0 else 0
        Spec(x, A) = (sum_{j in A \\ {x}} R_xj^B) / (sum_{k in N_rec(x)} R_xk^B)
                     if sum_{k in N_rec(x)} R_xk^B > 0 else 0
    """
    others = [j for j in member_ids if j != x]
    if not others or not is_eligible_assembly_member_cell(x, w):
        return 0, 0.0, 0.0

    n_rec_x = get_reciprocal_neighbors_n_rec(x, w, n_rec_cache)
    denom_spec = sum(n_rec_x.values())

    d_val = 0
    num_spec = 0.0
    for j in others:
        r_xj = compute_mutual_support_r_b(x, j, w)
        if r_xj >= THETA_A:
            d_val += 1
        num_spec += r_xj

    density_d = float(d_val) / float(len(others))
    spec_val = (num_spec / denom_spec) if denom_spec > 0.0 else 0.0
    return d_val, density_d, spec_val


def check_maintain_keep_guards(
    x: int,
    member_ids: Iterable[int],
    w: WState,
    n_rec_cache: dict[int, dict[int, float]] | None = None,
) -> bool:
    """Return True if x satisfies d(x, A) >= 2, D(x, A) >= 0.35, Spec(x, A) >= 0.20 (Core §2.0)."""
    d_val, density_d, spec_val = compute_assembly_member_metrics(x, member_ids, w, n_rec_cache)
    return d_val >= D_MIN and density_d >= RHO_KEEP and spec_val >= SIGMA_KEEP


def compute_core_coverage(
    assembly: Assembly,
    event_res: EventExecutionResult,
    h_slow: HSlowState,
) -> float:
    """Compute CoreCoverage(A, t) = |{j in A: committed_before_event(j, t), A_j^+(t) >= theta_emit}| / |A| (Core §2.0)."""
    if assembly.status != AssemblyStatus.LIVE or not assembly.member_cell_ids:
        return 0.0
    theta_emit = h_slow.get_theta_emit(assembly.region)
    covered = sum(
        1
        for j in assembly.member_cell_ids
        if j in event_res.committed_before_event
        and event_res.a_plus_by_cell.get(j, 0.0) >= theta_emit
    )
    return float(covered) / float(len(assembly.member_cell_ids))


def compute_m_fresh(assembly: Assembly, event_res: EventExecutionResult) -> float:
    """Compute M_A^fresh(t) = |A|^{-1} sum_{j in A} fresh_j(t) (Core §2.0, §2.1)."""
    if assembly.status != AssemblyStatus.LIVE or not assembly.member_cell_ids:
        return 0.0
    total_fresh = sum(event_res.fresh_by_cell.get(j, 0.0) for j in assembly.member_cell_ids)
    return total_fresh / float(len(assembly.member_cell_ids))


def _live_assembly_ids_for_cell(cell_id: int, w: WState) -> set[int]:
    """Return the set of LIVE AssemblyIDs currently containing cell_id."""
    return {
        aid
        for aid in w.assemblies_by_member.get(cell_id, set())
        if aid in w.assemblies and w.assemblies[aid].status == AssemblyStatus.LIVE
    }


def _rebuild_assemblies_by_member(w: WState) -> None:
    """Rebuild w.assemblies_by_member from LIVE Assemblies and validate invariants."""
    new_index: dict[int, set[int]] = {}
    for aid, asm in sorted(w.assemblies.items()):
        if asm.status != AssemblyStatus.LIVE:
            continue
        if not (K_MIN <= len(asm.member_cell_ids) <= K_MAX):
            raise DGCAError(
                StatusCode.INVALID_FEATURE_FORMAT,
                f"LIVE Assembly {aid} size {len(asm.member_cell_ids)} outside [{K_MIN}, {K_MAX}]",
            )
        for cid in asm.member_cell_ids:
            s = new_index.setdefault(cid, set())
            s.add(aid)
            if len(s) > M_MAX:
                raise DGCAError(
                    StatusCode.SOURCE_OUTGOING_CAPACITY,
                    f"Cell {cid} exceeds M_max={M_MAX} Assembly memberships",
                )
    w.assemblies_by_member = new_index


def _is_in_merge_split_cooldown(asm: Assembly, w: WState) -> bool:
    """Return True if asm was modified by MERGE/SPLIT within the last T_c=200 completed external events (Core §2.0)."""
    if asm.last_merge_split_close_serial is None:
        return False
    elapsed = w.completed_external_events_count - asm.last_merge_split_close_serial
    return elapsed < T_C_COOLDOWN


def _run_maintain_stage(
    w: WState,
    n_rec_cache: dict[int, dict[int, float]],
) -> tuple[list[int], list[int]]:
    """Stage 1: MAINTAIN (Core §2.0 item 1).

    Visit AssemblyID ascending; repeatedly remove the lowest physical cell_id among members
    failing d>=2, D>=rho_keep, Spec>=sigma_keep on the current shadow set until no violation
    remains, or size<3; archive a subminimum Assembly. Never remove underlying consolidated synapses.
    Each membership change increments structural_generation.
    """
    maintained_ids: list[int] = []
    archived_ids: list[int] = []

    for aid in sorted(w.assemblies.keys()):
        asm = w.assemblies[aid]
        if asm.status != AssemblyStatus.LIVE:
            continue

        members = list(asm.member_cell_ids)
        mutated = False

        while len(members) >= K_MIN:
            failing = sorted(
                cid
                for cid in members
                if not check_maintain_keep_guards(cid, members, w, n_rec_cache)
            )
            if not failing:
                break
            lowest_failing = failing[0]
            members.remove(lowest_failing)
            asm.member_cell_ids = tuple(members)
            asm.structural_generation += 1
            asm.last_mutation_close_serial = w.close_serial
            mutated = True

        if len(members) < K_MIN:
            asm.member_cell_ids = tuple(members)
            asm.status = AssemblyStatus.ARCHIVED
            asm.structural_generation += 1
            asm.last_mutation_close_serial = w.close_serial
            archived_ids.append(aid)
        elif mutated:
            maintained_ids.append(aid)

    _rebuild_assemblies_by_member(w)
    return maintained_ids, archived_ids


def _run_grow_stage(
    w: WState,
    n_rec_cache: dict[int, dict[int, float]],
) -> list[int]:
    """Stage 2: GROW (Core §2.0 item 2).

    For each still-live A in ascending AssemblyID, while |A| < 16, enumerate distinct committed
    neighborhood nodes of its reciprocal members (not a whole-region scan); rank by
    (-sum_{j in A} R_xj^B, cell_id). Inspect each once in that order; add if on prospective A U {x}:
    d(x, A) >= 2, D(x, A) >= 0.50, Spec(x, A) >= 0.30, no invalidated existing member keep guards,
    and membership cap M_max=12 allows it. Increment structural_generation on each addition.
    """
    grown_ids: list[int] = []

    for aid in sorted(w.assemblies.keys()):
        asm = w.assemblies[aid]
        if asm.status != AssemblyStatus.LIVE:
            continue
        if len(asm.member_cell_ids) >= K_MAX:
            continue

        initial_members = set(asm.member_cell_ids)
        candidate_neighbors: set[int] = set()
        for m in initial_members:
            candidate_neighbors.update(get_reciprocal_neighbors_n_rec(m, w, n_rec_cache).keys())
        candidate_neighbors -= initial_members

        # Rank once by (-sum_{j in A} R_xj^B, cell_id)
        ranked_candidates: list[tuple[int, float, int]] = []
        for x in candidate_neighbors:
            if not is_eligible_assembly_member_cell(x, w):
                continue
            sum_r = sum(compute_mutual_support_r_b(x, j, w) for j in asm.member_cell_ids)
            ranked_candidates.append((-q6_from_binary64(sum_r), -sum_r, x))
        ranked_candidates.sort()

        grew_this_asm = False
        for _, _, x in ranked_candidates:
            if len(asm.member_cell_ids) >= K_MAX:
                break
            if x in asm.member_cell_ids:
                continue
            if len(_live_assembly_ids_for_cell(x, w)) >= M_MAX:
                continue

            prospective = tuple(sorted((*asm.member_cell_ids, x)))
            d_x, dens_x, spec_x = compute_assembly_member_metrics(x, prospective, w, n_rec_cache)
            if not (d_x >= D_MIN and dens_x >= RHO_G and spec_x >= SIGMA_G):
                continue

            # Ensure no existing member keep guards are invalidated on prospective A U {x}
            if not all(
                check_maintain_keep_guards(m, prospective, w, n_rec_cache)
                for m in asm.member_cell_ids
            ):
                continue

            asm.member_cell_ids = prospective
            asm.structural_generation += 1
            asm.last_mutation_close_serial = w.close_serial
            w.assemblies_by_member.setdefault(x, set()).add(aid)
            grew_this_asm = True

        if grew_this_asm:
            grown_ids.append(aid)

    _rebuild_assemblies_by_member(w)
    return grown_ids


def _is_externally_grounded_fresh_emitter(
    cell_id: int,
    event_res: EventExecutionResult,
    h_slow: HSlowState,
    w: WState,
) -> bool:
    """Check if cell_id had externally grounded qualified fresh participation in event_res (Core §2.0)."""
    if (
        event_res.origin != EventOrigin.EXTERNAL_DIRECT
        or cell_id not in event_res.committed_before_event
        or not is_eligible_assembly_member_cell(cell_id, w)
    ):
        return False

    theta_emit = h_slow.get_theta_emit(Region.LANGUAGE)
    if event_res.a_plus_by_cell.get(cell_id, 0.0) < theta_emit:
        return False

    # Require OBS_ELIGIBLE with fresh > 0 OR COMPLETE externally derived witness
    if cell_id in event_res.obs_eligible_cells and event_res.fresh_by_cell.get(cell_id, 0.0) > 0.0:
        return True

    rec = event_res.typed_supports.get(cell_id)
    if (
        rec is not None
        and rec.origin_kind == ContributionLane.DERIVED_EXTERNAL_CONTEXT.value
        and rec.o_train > 0.0
        and rec.parent_proof_verified
    ):
        return True

    return False


def _run_form_stage(
    w: WState,
    h_slow: HSlowState,
    event_results: Sequence[EventExecutionResult],
    preexisting_live_assemblies: list[Assembly],
    n_rec_cache: dict[int, dict[int, float]],
) -> tuple[list[int], list[StatusCode]]:
    """Stage 3: FORM (Core §2.0 item 3).

    For each event of the completed root in chronological order, let U_t be ascending committed cells
    with externally grounded qualified fresh participation in that event, A^+ >= theta_emit, not already
    covered by any live A with CoreCoverage(A, t) >= 0.70, and under M_max=12.
    Enumerate triangles (i < j < k) in ascending lexicographic order via adjacency intersections,
    requiring each vertex d(v, {i,j,k})=2, D>=0.70, Spec>=0.30. Disjoint triangle seeds within each event;
    at most K_FORM_PER_END=12 new assemblies across all root events combined.
    """
    formed_ids: list[int] = []
    diagnostics: list[StatusCode] = []

    for event_res in sorted(event_results, key=lambda e: e.event_order):
        if len(formed_ids) >= K_FORM_PER_END:
            break

        # Cells already covered at event t by any live Assembly with CoreCoverage(A, t) >= 0.70
        covered_cells: set[int] = set()
        for asm in w.assemblies.values():
            if asm.status == AssemblyStatus.LIVE and compute_core_coverage(asm, event_res, h_slow) >= RHO_CORE:
                covered_cells.update(asm.member_cell_ids)
        for asm in preexisting_live_assemblies:
            if compute_core_coverage(asm, event_res, h_slow) >= RHO_CORE:
                covered_cells.update(asm.member_cell_ids)

        u_t = sorted(
            cid
            for cid in event_res.committed_before_event
            if cid not in covered_cells
            and len(_live_assembly_ids_for_cell(cid, w)) < M_MAX
            and _is_externally_grounded_fresh_emitter(cid, event_res, h_slow, w)
        )
        if len(u_t) < 3:
            continue

        u_set = set(u_t)
        adj_higher: dict[int, list[int]] = {}
        for u in u_t:
            n_rec_u = get_reciprocal_neighbors_n_rec(u, w, n_rec_cache)
            adj_higher[u] = sorted(v for v in n_rec_u if v > u and v in u_set)

        assigned_in_event: set[int] = set()
        for i in u_t:
            if len(formed_ids) >= K_FORM_PER_END:
                break
            if i in assigned_in_event or len(_live_assembly_ids_for_cell(i, w)) >= M_MAX:
                continue

            found_for_i = False
            for j in adj_higher[i]:
                if j in assigned_in_event or len(_live_assembly_ids_for_cell(j, w)) >= M_MAX:
                    continue
                common_k = [
                    k
                    for k in adj_higher[j]
                    if k in adj_higher[i]
                    and k not in assigned_in_event
                    and len(_live_assembly_ids_for_cell(k, w)) < M_MAX
                ]
                for k in common_k:
                    tri = (i, j, k)
                    valid_tri = True
                    for v in tri:
                        d_v, dens_v, spec_v = compute_assembly_member_metrics(v, tri, w, n_rec_cache)
                        if not (d_v == 2 and dens_v >= RHO_CORE and spec_v >= SIGMA_G):
                            valid_tri = False
                            break
                    if valid_tri:
                        new_id = w.next_assembly_id
                        w.next_assembly_id += 1
                        new_asm = Assembly(
                            assembly_id=new_id,
                            region=Region.LANGUAGE,
                            member_cell_ids=tri,
                            structural_generation=1,
                            birth_close_serial=w.close_serial,
                            last_mutation_close_serial=w.close_serial,
                            last_merge_split_close_serial=None,
                            status=AssemblyStatus.LIVE,
                        )
                        w.assemblies[new_id] = new_asm
                        for v in tri:
                            w.assemblies_by_member.setdefault(v, set()).add(new_id)
                        assigned_in_event.update(tri)
                        formed_ids.append(new_id)
                        found_for_i = True
                        break
                if found_for_i:
                    break

    _rebuild_assemblies_by_member(w)
    live_count = sum(1 for a in w.assemblies.values() if a.status == AssemblyStatus.LIVE)
    if not formed_ids and live_count == 0:
        diagnostics.append(StatusCode.NO_RECIPROCAL_TRIANGLE)

    return formed_ids, diagnostics


def _try_merge_pair(
    a_id: int,
    b_id: int,
    w: WState,
    n_rec_cache: dict[int, dict[int, float]],
) -> bool:
    """Attempt to merge live Assembly pair (a_id < b_id) under Core §2.0 item 4."""
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
    if not excl_a and not excl_b:
        # Branch 4a: Exact Structural Duplicate consolidation (Core §2.0 Operator 4)
        between_strength_passed = True
    else:
        # Branch 4b: Partial Overlap cross-support evaluation
        if not excl_a or not excl_b:
            between_strength = 0.0
        else:
            cross_vals = [
                compute_mutual_support_r_b(i, j, w)
                for i in excl_a
                for j in excl_b
            ]
            between_strength = sum(cross_vals) / float(len(cross_vals))
        between_strength_passed = (between_strength >= THETA_OB)

    if not between_strength_passed:
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


def _run_merge_stage(
    w: WState,
    n_rec_cache: dict[int, dict[int, float]],
) -> list[tuple[int, int]]:
    """Stage 4: MERGE (Core §2.0 item 4).

    Take live pairs (A.id, B.id) ascending after GROW/FORM, skipping any ID changed by MERGE/SPLIT
    within the last T_c=200 completed external events; recompute pair list once from new shadow
    state and process each initial pair at most once.
    """
    merged_pairs: list[tuple[int, int]] = []
    processed_pairs: set[tuple[int, int]] = set()

    for pass_idx in range(2):
        live_ids = sorted(
            aid for aid, asm in w.assemblies.items() if asm.status == AssemblyStatus.LIVE
        )
        initial_pairs = [
            (live_ids[idx_a], live_ids[idx_b])
            for idx_a in range(len(live_ids))
            for idx_b in range(idx_a + 1, len(live_ids))
            if (live_ids[idx_a], live_ids[idx_b]) not in processed_pairs
        ]
        any_merged_in_pass = False
        for pair in initial_pairs:
            processed_pairs.add(pair)
            if _try_merge_pair(pair[0], pair[1], w, n_rec_cache):
                merged_pairs.append(pair)
                any_merged_in_pass = True
        if not any_merged_in_pass or pass_idx == 1:
            break

    return merged_pairs


def _run_split_stage(
    w: WState,
    n_rec_cache: dict[int, dict[int, float]],
) -> list[tuple[int, int]]:
    """Stage 5: SPLIT (Core §2.0 item 5).

    For each surviving live A with size >= N_min=6 after MERGE, skipping any ID edited by MERGE/SPLIT
    in the last T_c=200 completed external events, enumerate all bipartitions (L, R) with both sides
    size >= 3, with A's smallest member in L. Require all cross-pair supports R_ij^B <= theta_weak=0.15
    and mean cross-support < theta_sep=0.10, and every member in L and R satisfies MAINTAIN guards.
    Choose (mean_cross_support, sorted_L, sorted_R) ascending; keep original ID for L, assign one new
    ID to R, increment L's generation; stop at one split per original Assembly per END.
    """
    split_pairs: list[tuple[int, int]] = []
    surviving_ids = sorted(
        aid
        for aid, asm in w.assemblies.items()
        if asm.status == AssemblyStatus.LIVE and len(asm.member_cell_ids) >= N_MIN_SPLIT
    )

    for aid in surviving_ids:
        asm = w.assemblies[aid]
        if asm.status != AssemblyStatus.LIVE or _is_in_merge_split_cooldown(asm, w):
            continue

        members = asm.member_cell_ids
        n = len(members)
        if n < N_MIN_SPLIT:
            continue

        first_member = members[0]
        rest_members = members[1:]

        best_candidate: tuple[int, float, tuple[int, ...], tuple[int, ...]] | None = None

        for left_extra_size in range(K_MIN - 1, n - K_MIN + 1):
            for extra_combo in itertools.combinations(rest_members, left_extra_size):
                left_tuple = (first_member, *extra_combo)
                left_set = set(left_tuple)
                right_tuple = tuple(m for m in members if m not in left_set)

                # Check cross-pair supports R_ij^B <= theta_weak=0.15 and mean < theta_sep=0.10
                cross_supports: list[float] = []
                weak_ok = True
                for i in left_tuple:
                    for j in right_tuple:
                        r_ij = compute_mutual_support_r_b(i, j, w)
                        if r_ij > THETA_WEAK:
                            weak_ok = False
                            break
                        cross_supports.append(r_ij)
                    if not weak_ok:
                        break
                if not weak_ok:
                    continue

                mean_cross = sum(cross_supports) / float(len(cross_supports))
                if mean_cross >= THETA_SEP:
                    continue

                # Check MAINTAIN keep guards within L and within R
                if not all(check_maintain_keep_guards(x, left_tuple, w, n_rec_cache) for x in left_tuple):
                    continue
                if not all(check_maintain_keep_guards(y, right_tuple, w, n_rec_cache) for y in right_tuple):
                    continue

                cand_key = (q6_from_binary64(mean_cross), mean_cross, left_tuple, right_tuple)
                if best_candidate is None or cand_key < best_candidate:
                    best_candidate = cand_key

        if best_candidate is not None:
            _, _, best_l, best_r = best_candidate
            new_r_id = w.next_assembly_id
            w.next_assembly_id += 1

            asm.member_cell_ids = best_l
            asm.structural_generation += 1
            asm.last_mutation_close_serial = w.close_serial
            asm.last_merge_split_close_serial = w.completed_external_events_count

            new_r_asm = Assembly(
                assembly_id=new_r_id,
                region=asm.region,
                member_cell_ids=best_r,
                structural_generation=1,
                birth_close_serial=w.close_serial,
                last_mutation_close_serial=w.close_serial,
                last_merge_split_close_serial=w.completed_external_events_count,
                status=AssemblyStatus.LIVE,
            )
            w.assemblies[new_r_id] = new_r_asm
            split_pairs.append((aid, new_r_id))
            _rebuild_assemblies_by_member(w)

    return split_pairs


def execute_assembly_end_pipeline(
    w: WState,
    h_slow: HSlowState,
    event_results: Sequence[EventExecutionResult],
) -> AssemblyEndReport:
    """Execute one deterministic END_EXPOSURE Assembly pass: MAINTAIN -> GROW -> FORM -> MERGE -> SPLIT (Core §2.0).

    Operates on a shadow copy of Assembly structures and validates all membership and reverse-index
    invariants before atomic publication into w.
    """
    # Capture pre-existing LIVE assemblies before this END's mutations
    preexisting_live = [
        asm.clone() for asm in w.assemblies.values() if asm.status == AssemblyStatus.LIVE
    ]

    w_shadow = w.clone()
    n_rec_cache: dict[int, dict[int, float]] = {}

    maintained_ids, archived_ids = _run_maintain_stage(w_shadow, n_rec_cache)
    grown_ids = _run_grow_stage(w_shadow, n_rec_cache)
    formed_ids, diagnostics = _run_form_stage(
        w_shadow, h_slow, event_results, preexisting_live, n_rec_cache
    )
    merged_pairs = _run_merge_stage(w_shadow, n_rec_cache)
    split_pairs = _run_split_stage(w_shadow, n_rec_cache)

    # Pre-commit validation of all LIVE assembly memberships and reverse indices
    _rebuild_assemblies_by_member(w_shadow)

    # Atomic publish to w
    w.assemblies = w_shadow.assemblies
    w.next_assembly_id = w_shadow.next_assembly_id
    w.assemblies_by_member = w_shadow.assemblies_by_member

    return AssemblyEndReport(
        maintained_ids=tuple(maintained_ids),
        archived_by_maintain_ids=tuple(archived_ids),
        grown_ids=tuple(grown_ids),
        formed_ids=tuple(formed_ids),
        merged_pairs=tuple(merged_pairs),
        split_pairs=tuple(split_pairs),
        diagnostics=tuple(diagnostics),
    )


def compute_idealized_triangle_root_counts(activity_a: float) -> tuple[int, int]:
    """Compute idealized post-commitment N_triangle and minimal cold-start total roots (Core §9.4.1, LLA §8.2, LG-T16).

    Formula:
        q_local = a^2
        N_triangle = ceil(3.0 / a^2)
        min_cold_total = 1 (commitment root) + N_triangle + 2 (post-birth attestation roots)
    For a = 0.45, 0.60, 0.70, 0.80:
        N_triangle     = 15,  9,  7,  5
        min_cold_total = 18, 12, 10,  8
    """
    if activity_a <= 0.0 or activity_a > 1.0:
        raise ValueError(f"activity_a must be in (0, 1], got {activity_a}")
    q_val = activity_a * activity_a
    # Use round(3.0 / q_val, 12) before ceil to avoid IEEE-754 3.0 / 0.6^2 = 8.333... vs exact integer boundaries
    n_post_commit = math.ceil(round(3.0 / q_val, 12))
    min_cold_total = 1 + n_post_commit + 2
    return n_post_commit, min_cold_total


@dataclass(slots=True)
class TriangleReadinessTracker:
    """Gate C / RC4.1 native-surface readiness subgate tracker (Core §9.4.1, LLA §8.2, LG-T16)."""

    triangle_cells: tuple[int, int, int]
    receiver_commit_root: dict[int, int | None] = field(default_factory=dict)
    first_proposal_root: dict[SynapseKey, int | None] = field(default_factory=dict)
    edge_history: dict[SynapseKey, list[tuple[int, float, float, int, bool]]] = field(
        default_factory=dict
    )
    assembly_id: int | None = None
    assembly_birth_root: int | None = None
    current_generation: int | None = None
    generation_change_roots: list[tuple[int, int]] = field(default_factory=list)
    attestation_roots: list[int] = field(default_factory=list)
    surface_by_attestation_root: dict[int, tuple[str, bytes, bool]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        c0, c1, c2 = sorted(self.triangle_cells)
        self.triangle_cells = (c0, c1, c2)
        for cid in self.triangle_cells:
            self.receiver_commit_root.setdefault(cid, None)
        for u in self.triangle_cells:
            for v in self.triangle_cells:
                if u != v:
                    k: SynapseKey = (u, v, SynapseScope.LOCAL)
                    self.first_proposal_root.setdefault(k, None)
                    self.edge_history.setdefault(k, [])

    @property
    def six_directed_keys(self) -> tuple[SynapseKey, ...]:
        return tuple(self.first_proposal_root.keys())

    def record_completed_root(
        self,
        exposure_id: int,
        w: WState,
        h_slow: HSlowState,
        event_results: Sequence[EventExecutionResult],
        *,
        preexisting_live_assemblies: Sequence[Assembly],
        surface_text: str = "",
        feature_bundle_digest: bytes = b"",
        is_eos: bool = False,
    ) -> None:
        """Update Gate C / RC4.1 triangle readiness metrics after a completed external root."""
        for cid in self.triangle_cells:
            if self.receiver_commit_root[cid] is None and cid in w.committed_cells:
                self.receiver_commit_root[cid] = exposure_id

        for key in self.six_directed_keys:
            syn = w.synapses.get(key)
            if syn is not None:
                if self.first_proposal_root[key] is None:
                    self.first_proposal_root[key] = exposure_id
                self.edge_history[key].append(
                    (
                        exposure_id,
                        syn.E_ext,
                        syn.S,
                        syn.external_count,
                        is_legal_consolidated_synapse(key, w),
                    )
                )

        # Check if a matching LIVE Assembly exists in W
        matching_asm: Assembly | None = None
        for asm in sorted(w.assemblies.values(), key=lambda a: a.assembly_id):
            if asm.status == AssemblyStatus.LIVE and set(self.triangle_cells).issubset(
                set(asm.member_cell_ids)
            ):
                matching_asm = asm
                break

        if matching_asm is not None:
            if self.assembly_id != matching_asm.assembly_id:
                self.assembly_id = matching_asm.assembly_id
                self.assembly_birth_root = exposure_id
                self.current_generation = matching_asm.structural_generation
                self.generation_change_roots.append((exposure_id, matching_asm.structural_generation))
                self.attestation_roots.clear()
                self.surface_by_attestation_root.clear()
            elif self.current_generation != matching_asm.structural_generation:
                self.current_generation = matching_asm.structural_generation
                self.generation_change_roots.append((exposure_id, matching_asm.structural_generation))
                self.attestation_roots.clear()
                self.surface_by_attestation_root.clear()

            # Check post-birth attestation eligibility:
            # Assembly with exact ID & generation MUST have existed LIVE BEFORE the root's events!
            existed_before_with_same_gen = any(
                pre.assembly_id == matching_asm.assembly_id
                and pre.status == AssemblyStatus.LIVE
                and pre.structural_generation == matching_asm.structural_generation
                for pre in preexisting_live_assemblies
            )
            if existed_before_with_same_gen and self.assembly_birth_root != exposure_id:
                qualified_in_root = any(
                    compute_core_coverage(matching_asm, ev, h_slow) >= RHO_CORE
                    and compute_m_fresh(matching_asm, ev) >= THETA_FRESH_ADMIT
                    for ev in event_results
                )
                if qualified_in_root and exposure_id not in self.attestation_roots:
                    self.attestation_roots.append(exposure_id)
                    self.surface_by_attestation_root[exposure_id] = (
                        surface_text,
                        feature_bundle_digest,
                        is_eos,
                    )

    @property
    def is_readout_ready(self) -> bool:
        """Return True iff >= 2 post-birth independent roots attested the exact same generation and surface tuple."""
        if len(self.attestation_roots) < 2:
            return False
        tuples = set(self.surface_by_attestation_root.values())
        return len(tuples) == 1
