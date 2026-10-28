"""FULL vs CONTROL Causal Next-Event Readout (Core §9.2).

Normative references:
- DGCA_CORE_RC4_1.md §9.2 (FULL vs CONTROL causal next-event readout)
- DGCA_CORE_RC4_1.md §9.3 & §9.4 (ZERO_SELECTION_LEAKAGE invariant: neural ranking before peripheral lookup)
"""

from __future__ import annotations

from dataclasses import dataclass

from dgca.common.errors import StatusCode
from dgca.common.hashing import Region
from dgca.common.numeric import q6_from_binary64
from dgca.core.assembly import (
    K_MAX,
    K_MIN,
    check_maintain_keep_guards,
    is_eligible_assembly_member_cell,
)
from dgca.core.dynamics import execute_two_pass_event
from dgca.core.state import (
    Assembly,
    AssemblyStatus,
    ExecutionMode,
    MachineState,
    WState,
)
from dgca.encoder.envelope import EventOrigin

# Core §9.2 & §12 Normative Readout Thresholds
THETA_READ: float = 0.08
M_READ: float = 0.04


@dataclass(frozen=True, slots=True)
class AssemblyReadoutScore:
    """Causal next-event readout score for a single legal LIVE Assembly G (Core §9.2)."""

    assembly_id: int
    structural_generation: int
    score_next: float
    score_next_q6: int
    eligible_member_count: int
    member_count: int


@dataclass(frozen=True, slots=True)
class ReadoutEvaluationResult:
    """Result of a read-only FULL vs CONTROL causal next-event readout step (Core §9.2).

    Contains zero peripheral surface text or lexical metadata (ZERO_SELECTION_LEAKAGE).
    """

    status: StatusCode
    winner_assembly_id: int | None
    winner_generation: int | None
    top_score: float
    second_score: float
    margin: float
    ranked_scores: tuple[AssemblyReadoutScore, ...]
    gain_by_cell: dict[int, float]
    eligible_next_cells: frozenset[int]
    a_full_by_cell: dict[int, float]
    a_control_by_cell: dict[int, float]


def is_legal_readout_assembly(
    assembly: Assembly,
    w: WState,
    n_rec_cache: dict[int, dict[int, float]] | None = None,
) -> bool:
    """Check if Assembly G is a LIVE, structurally legal consolidated Assembly in W (Core §2.0, §9.2, §9.3).

    Requires:
    - status == LIVE, region == LANGUAGE
    - K_min (3) <= |G| <= K_max (16)
    - All members are committed LANGUAGE cells (no incomplete contextual candidate)
    - Every member satisfies the reciprocal CONSOLIDATED LOCAL structural guards (d>=2, D>=0.35, Spec>=0.20)
    """
    if assembly.status != AssemblyStatus.LIVE or assembly.region != Region.LANGUAGE:
        return False
    members = assembly.member_cell_ids
    if not (K_MIN <= len(members) <= K_MAX):
        return False
    for cid in members:
        if not is_eligible_assembly_member_cell(cid, w):
            return False
        if not check_maintain_keep_guards(cid, members, w, n_rec_cache):
            return False
    return True


def evaluate_full_vs_control_readout(
    state: MachineState,
    *,
    theta_read: float = THETA_READ,
    m_read: float = M_READ,
) -> ReadoutEvaluationResult:
    """Execute one read-only FULL vs CONTROL scratch comparison from state (Core §9.2).

    From the identical post-event W/H/R checkpoint, advances one internal step with X=0:
    - FULL: normal one-step P_T from frozen F_step and frozen mu.
    - CONTROL: sets only P_T=0, preserving identical residual, microcolumn normalization,
      synchronous propagation, and attractor influence.
    Computes:
        gain_j = max(A_j^FULL - A_j^CONTROL, 0)
        eligibleNext_j = 1[P_j^T > 0 and gain_j > 0]
        score_next(G) = |G|^{-1} sum_{j in G} eligibleNext_j * gain_j
    Never mutates caller W, H_slow, or R.
    """
    scratch_full = state.clone()
    scratch_ctrl = state.clone()

    res_full = execute_two_pass_event(
        scratch_full,
        {},
        {},
        mode=ExecutionMode.RETRIEVE,
        origin=EventOrigin.READ_ONLY_OBSERVED,
        boundary=False,
        exposure_id=None,
        event_order=state.R.step_index,
        allow_candidate_probe=False,
        admit_uncommitted_sensory=False,
        control_zero_pt=False,
    )
    res_ctrl = execute_two_pass_event(
        scratch_ctrl,
        {},
        {},
        mode=ExecutionMode.RETRIEVE,
        origin=EventOrigin.READ_ONLY_OBSERVED,
        boundary=False,
        exposure_id=None,
        event_order=state.R.step_index,
        allow_candidate_probe=False,
        admit_uncommitted_sensory=False,
        control_zero_pt=True,
    )

    all_cells = sorted(set(res_full.a_plus_by_cell.keys()) | set(res_ctrl.a_plus_by_cell.keys()))
    gain_by_cell: dict[int, float] = {}
    eligible_list: list[int] = []

    for cid in all_cells:
        a_full = res_full.a_plus_by_cell.get(cid, 0.0)
        a_ctrl = res_ctrl.a_plus_by_cell.get(cid, 0.0)
        gain = max(a_full - a_ctrl, 0.0)
        if gain > 0.0:
            gain_by_cell[cid] = gain
            if res_full.pt_by_cell.get(cid, 0.0) > 0.0:
                eligible_list.append(cid)

    eligible_next_cells = frozenset(eligible_list)

    n_rec_cache: dict[int, dict[int, float]] = {}
    legal_assemblies = [
        asm
        for _, asm in sorted(state.W.assemblies.items())
        if is_legal_readout_assembly(asm, state.W, n_rec_cache)
    ]

    if not legal_assemblies:
        return ReadoutEvaluationResult(
            status=StatusCode.NO_ASSEMBLY,
            winner_assembly_id=None,
            winner_generation=None,
            top_score=0.0,
            second_score=0.0,
            margin=0.0,
            ranked_scores=(),
            gain_by_cell=gain_by_cell,
            eligible_next_cells=eligible_next_cells,
            a_full_by_cell=dict(res_full.a_plus_by_cell),
            a_control_by_cell=dict(res_ctrl.a_plus_by_cell),
        )

    scores: list[AssemblyReadoutScore] = []
    for asm in legal_assemblies:
        members = asm.member_cell_ids
        elig_count = 0
        total_gain = 0.0
        for cid in members:
            if cid in eligible_next_cells:
                elig_count += 1
                total_gain += gain_by_cell.get(cid, 0.0)
        score_val = total_gain / float(len(members))
        scores.append(
            AssemblyReadoutScore(
                assembly_id=asm.assembly_id,
                structural_generation=asm.structural_generation,
                score_next=score_val,
                score_next_q6=q6_from_binary64(score_val),
                eligible_member_count=elig_count,
                member_count=len(members),
            )
        )

    # Rank descending by quantized Q6 score, exact float score, then ascending assembly_id (Core §3.1, §9.2)
    scores.sort(key=lambda s: (-s.score_next_q6, -s.score_next, s.assembly_id))

    top_entry = scores[0]
    top_score = top_entry.score_next
    second_score = scores[1].score_next if len(scores) >= 2 else 0.0
    margin = top_score - second_score

    if top_score < theta_read:
        status = StatusCode.NO_MATCH
        winner_id = None
        winner_gen = None
    elif margin < m_read:
        status = StatusCode.AMBIGUOUS
        winner_id = None
        winner_gen = None
    else:
        status = StatusCode.OK
        winner_id = top_entry.assembly_id
        winner_gen = top_entry.structural_generation

    return ReadoutEvaluationResult(
        status=status,
        winner_assembly_id=winner_id,
        winner_generation=winner_gen,
        top_score=top_score,
        second_score=second_score,
        margin=margin,
        ranked_scores=tuple(scores),
        gain_by_cell=gain_by_cell,
        eligible_next_cells=eligible_next_cells,
        a_full_by_cell=dict(res_full.a_plus_by_cell),
        a_control_by_cell=dict(res_ctrl.a_plus_by_cell),
    )
