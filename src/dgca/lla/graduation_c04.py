"""C04 Corrected Contextual Graduation, P2_DURABLE Check, and PRE/POST Retirement Equivalence.

Normative references:
- DGCA_CORE_RC4_1.md §7.6 (C04 durable role binding and graduation: two P links required)
- DGCA_LLA_RC4_1.md §6.4 (C04 corrected graduation: BOTH P, >=1 C, >=1 Y, NORMAL_W & CONSOLIDATED_W, PRE/POST equivalence)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from dgca.common.errors import StatusCode
from dgca.common.hashing import WitnessSourceKind
from dgca.common.numeric import MILLION
from dgca.common.serialization import pack_binary64_be
from dgca.core.anatomy import SynapseKey, SynapseScope, SynapseState
from dgca.core.context_gate import (
    is_legal_consolidated_synapse,
    is_valid_calibration_triple,
    validate_parent_hierarchy,
)
from dgca.core.dynamics import (
    compute_next_step_temporal_drive,
    compute_pred_score,
    execute_two_pass_event,
)
from dgca.core.sic_v1 import CellAddress
from dgca.core.state import (
    BindingStatus,
    CandidatePhase,
    ContextCandidateDescriptor,
    ExecutionMode,
    MachineState,
    OwnerState,
    StableBinding,
    TypedSupportRecord,
    WState,
)
from dgca.encoder.envelope import EventOrigin
from dgca.lla.contrast_ledger import M_REUSE
from dgca.lla.owner_registry import CompactWitnessProfile, OwnerProfile


@dataclass(frozen=True, slots=True)
class DurablePathReport:
    """Detailed evaluation of DURABLE_PATH_C04(z) on frozen post-evidence W* (Core §7.6, LLA §6.4)."""

    p0_key: SynapseKey
    p1_key: SynapseKey
    p0_consolidated: bool
    p1_consolidated: bool
    p2_durable: bool
    consolidated_c_keys: tuple[SynapseKey, ...]
    c_durable: bool
    consolidated_y_keys: tuple[SynapseKey, ...]
    y_durable: bool
    same_owned_branch: bool
    is_durable: bool
    status: StatusCode


@dataclass(frozen=True, slots=True)
class TrialSnapshotSignature:
    """Bit-exact snapshot of a cold read-only trial for PRE vs POST retirement comparison (Core §7.6, LLA-T35)."""

    ctx_runtime_match: bool
    g_ctx: int
    tau_ctx_q6: int
    mu_source_mask: tuple[tuple[int, int], ...]
    f_step: tuple[int, ...]
    a_z_bytes: bytes
    pt_next_bytes: tuple[tuple[int, bytes], ...]
    pred_score_owned_bytes: bytes
    pred_score_rival_bytes: bytes


@dataclass(frozen=True, slots=True)
class GraduationEvaluationResult:
    """Result of evaluating C04 graduation and PRE/POST retirement equivalence at END_EXPOSURE."""

    passed: bool
    status: StatusCode
    durable_report: DurablePathReport
    stable_binding: StableBinding | None = None
    normal_owned_az: float = 0.0
    consolidated_owned_az: float = 0.0
    normal_pred_margin: float = 0.0
    consolidated_pred_margin: float = 0.0
    diagnostic_detail: str = ""


def check_c04_durable_path(
    cand: ContextCandidateDescriptor,
    w_state: WState,
) -> DurablePathReport:
    """Evaluate DURABLE_PATH_C04(z) on frozen post-evidence W* (Core §7.6, LLA §6.4, LLA-T08/T09).

    Formula:
        P2_DURABLE = LC(p0 -> z, ASSOC) and LC(p1 -> z, ASSOC)
        C_DURABLE  = exists c in C_z : LC(c -> z, LOCAL)
        Y_DURABLE  = exists y in Y_z : LC(z -> y, ASSOC)
        DURABLE_PATH = P2_DURABLE and C_DURABLE and Y_DURABLE and SAME_OWNED_WITNESSED_BRANCH
    Never graduate on only one consolidated predecessor.
    """
    z_id = cand.z_cell_id
    p0_key: SynapseKey = (cand.p_sources[0], z_id, SynapseScope.ASSOCIATIVE)
    p1_key: SynapseKey = (cand.p_sources[1], z_id, SynapseScope.ASSOCIATIVE)

    p0_ok = is_legal_consolidated_synapse(p0_key, w_state)
    p1_ok = is_legal_consolidated_synapse(p1_key, w_state)
    p2_durable = p0_ok and p1_ok

    c_keys: list[SynapseKey] = []
    for cid in cand.c_sources:
        ck: SynapseKey = (cid, z_id, SynapseScope.LOCAL)
        if is_legal_consolidated_synapse(ck, w_state):
            c_keys.append(ck)
    c_durable = len(c_keys) >= 1

    y_keys: list[SynapseKey] = []
    for yid in cand.y_targets:
        yk: SynapseKey = (z_id, yid, SynapseScope.ASSOCIATIVE)
        if is_legal_consolidated_synapse(yk, w_state):
            y_keys.append(yk)
    y_durable = len(y_keys) >= 1

    # Verify links were confirmed in exposures after admission (not fabricated before admission)
    same_branch_ok = True
    for key in [p0_key, p1_key, *c_keys, *y_keys]:
        syn = w_state.synapses.get(key)
        if syn is None or syn.external_count < 2:
            same_branch_ok = False
            break

    is_durable = p2_durable and c_durable and y_durable and same_branch_ok
    return DurablePathReport(
        p0_key=p0_key,
        p1_key=p1_key,
        p0_consolidated=p0_ok,
        p1_consolidated=p1_ok,
        p2_durable=p2_durable,
        consolidated_c_keys=tuple(c_keys),
        c_durable=c_durable,
        consolidated_y_keys=tuple(y_keys),
        y_durable=y_durable,
        same_owned_branch=same_branch_ok,
        is_durable=is_durable,
        status=StatusCode.OK if is_durable else StatusCode.DURABILITY_PENDING,
    )


def build_proposed_stable_binding(
    cand: ContextCandidateDescriptor,
    durable_report: DurablePathReport,
    *,
    binding_generation: int = 1,
) -> StableBinding:
    """Construct StableBindingV2 (depth=1) or StableBindingV3 (depth>1) from durable LC keys (Core §7.6)."""
    schema_version = 2 if cand.depth == 1 else 3
    return StableBinding(
        schema_version=schema_version,
        z_cell_id=cand.z_cell_id,
        anchor_id=cand.anchor_id,
        owner_seq=cand.owner_seq,
        binding_generation=binding_generation,
        p_keys=(durable_report.p0_key, durable_report.p1_key),
        l_z_q6=cand.l_z_q6,
        u_z_q6=cand.u_z_q6,
        tau_ctx_q6=cand.tau_ctx_q6,
        c_keys=durable_report.consolidated_c_keys,
        y_keys=durable_report.consolidated_y_keys,
        anchor_source_set=cand.anchor_source_set,
        status=BindingStatus.ACTIVE,
        depth=cand.depth,
        p_source_kinds=cand.p_source_kinds,
        parent_refs=dict(cand.parent_refs),
    )


def _run_cold_trial(
    base_state: MachineState,
    z_cell_id: int,
    tau_ctx_q6: int,
    p_supports_u: dict[int, int] | None,
    p_source_kinds: dict[int, WitnessSourceKind] | None,
    c_supports_u: dict[int, int],
    owned_y_targets: set[int],
    rival_y_targets: set[int],
    *,
    mask_nonconsolidated: bool,
) -> tuple[TrialSnapshotSignature, float, float, float]:
    """Execute one isolated cold READ_ONLY trial (either P->B or B-only) with PROBE=OFF.

    Returns:
        (TrialSnapshotSignature, a_z_at_b, pred_score_owned, pred_score_rival)
    """
    scratch = base_state.clone()
    scratch.R.reset_cold()

    event_idx = 0
    if p_supports_u is not None:
        # Step 0: feed P
        direct_p_u = {
            cid: sup
            for cid, sup in p_supports_u.items()
            if (p_source_kinds or {}).get(cid, WitnessSourceKind.DIRECT) == WitnessSourceKind.DIRECT
        }
        direct_p_float = {cid: float(u) / float(MILLION) for cid, u in direct_p_u.items()}
        execute_two_pass_event(
            scratch,
            direct_p_u,
            direct_p_float,
            mode=ExecutionMode.RETRIEVE,
            origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=True,
            exposure_id=None,
            event_order=0,
            allow_candidate_probe=False,
            mask_nonconsolidated_candidate_links=mask_nonconsolidated,
            admit_uncommitted_sensory=False,
        )

        # If any P source in p_supports_u is DERIVED_EXTERNAL_CONTEXT with an ACTIVE parent binding,
        # populate its verified runtime support for 2-step compact witness replay
        if p_source_kinds:
            for pid, kind in p_source_kinds.items():
                if kind == WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT and p_supports_u.get(pid, 0) > 0:
                    parent_bind = scratch.W.stable_bindings.get(pid)
                    if parent_bind is not None and parent_bind.status == BindingStatus.ACTIVE:
                        sup_u = p_supports_u[pid]
                        sup_flt = float(sup_u) / float(MILLION)
                        scratch.R.A[pid] = max(scratch.R.A.get(pid, 0.0), sup_flt)
                        scratch.R.F_step = frozenset(set(scratch.R.F_step) | {pid})
                        scratch.R.typed_supports_current[pid] = TypedSupportRecord(
                            cell_id=pid,
                            event_order=0,
                            origin_kind="DERIVED_RUNTIME_CONTEXT",
                            o_train=0.0,
                            o_runtime=sup_flt,
                            q6_train=0,
                            q6_runtime=sup_u,
                            depth=parent_bind.depth,
                            owner_id=parent_bind.owner_id,
                            binding_generation=parent_bind.binding_generation,
                            parent_proof_verified=True,
                        )
        event_idx = 1

    # Step B: feed C (boundary=True if B-only, boundary=False if preceded by P)
    c_float = {cid: float(u) / float(MILLION) for cid, u in c_supports_u.items()}
    res_b = execute_two_pass_event(
        scratch,
        dict(c_supports_u),
        c_float,
        mode=ExecutionMode.RETRIEVE,
        origin=EventOrigin.READ_ONLY_OBSERVED,
        boundary=(p_supports_u is None),
        exposure_id=None,
        event_order=event_idx,
        allow_candidate_probe=False,
        mask_nonconsolidated_candidate_links=mask_nonconsolidated,
        admit_uncommitted_sensory=False,
    )

    pt_next, _ = compute_next_step_temporal_drive(
        scratch,
        f_step_prev=res_b.f_step,
        a_prev_by_cell=res_b.a_plus_by_cell,
        mu_prev_source_mask=res_b.mu_source_mask,
        mask_nonconsolidated=mask_nonconsolidated,
    )

    _, score_owned_val = compute_pred_score(pt_next, owned_y_targets)
    _, score_rival_val = compute_pred_score(pt_next, rival_y_targets)

    a_z = res_b.a_plus_by_cell.get(z_cell_id, 0.0)
    g_ctx = res_b.g_ctx_by_z.get(z_cell_id, 0)
    ctx_runtime = (z_cell_id in res_b.ctx_runtime_match_cells) or (
        g_ctx == 1 and z_cell_id in res_b.f_step
    )

    sig = TrialSnapshotSignature(
        ctx_runtime_match=ctx_runtime,
        g_ctx=g_ctx,
        tau_ctx_q6=tau_ctx_q6,
        mu_source_mask=tuple(sorted(res_b.mu_source_mask.items())),
        f_step=tuple(sorted(res_b.f_step)),
        a_z_bytes=pack_binary64_be(a_z),
        pt_next_bytes=tuple(
            (cid, pack_binary64_be(val)) for cid, val in sorted(pt_next.items())
        ),
        pred_score_owned_bytes=pack_binary64_be(score_owned_val),
        pred_score_rival_bytes=pack_binary64_be(score_rival_val),
    )
    return sig, a_z, score_owned_val, score_rival_val


def _resolve_graduation_witnesses(
    cand: ContextCandidateDescriptor,
    w_state: WState,
    owned_witness: CompactWitnessProfile | None,
    rival_witnesses: Sequence[CompactWitnessProfile] | None,
) -> tuple[CompactWitnessProfile | None, list[CompactWitnessProfile]]:
    """Locate the owned CompactWitnessProfile and confirmed rival witness profiles for cand."""
    resolved_owned = owned_witness
    profiles: list[OwnerProfile] = list(
        w_state.owner_profiles_by_anchor.get(cand.anchor_id, [])  # type: ignore[arg-type]
    )
    if resolved_owned is None:
        for prof in profiles:
            if prof.owner_id == cand.owner_id:
                resolved_owned = prof.witness_profiles[0]
                break

    if rival_witnesses is not None:
        resolved_rivals = list(rival_witnesses)
    else:
        resolved_rivals = []
        for prof in profiles:
            if prof.owner_id != cand.owner_id:
                resolved_rivals.append(prof.witness_profiles[0])
        if not resolved_rivals:
            # Check contrast ledger episodes under anchor_id that have different P/Y digests
            eps = w_state.contrast_episodes_by_anchor.get(cand.anchor_id, [])
            for ep in eps:
                cw = CompactWitnessProfile.from_episode(ep)  # type: ignore[arg-type]
                if resolved_owned is not None and cw.full_y_digest != resolved_owned.full_y_digest:
                    resolved_rivals.append(cw)
                    break

    return resolved_owned, resolved_rivals


def evaluate_c04_graduation(
    cand: ContextCandidateDescriptor,
    state: MachineState,
    *,
    owned_witness: CompactWitnessProfile | None = None,
    rival_witnesses: Sequence[CompactWitnessProfile] | None = None,
    binding_generation: int = 1,
) -> GraduationEvaluationResult:
    """Evaluate C04 graduation requirements, NORMAL_W / CONSOLIDATED_W cold trials, and PRE/POST equivalence (Core §7.6, LLA §6.4).

    Checks:
    1. Calibration triple validity & hierarchy validity (LLA-T40)
    2. DURABLE_PATH_C04: BOTH P links, >=1 C link, >=1 Y link consolidated (LLA-T08, LLA-T09)
    3. Both NORMAL_W and CONSOLIDATED_W cold no-probe trials:
       - Owned (P, B): G_ctx == 1, A_z >= theta_emit (else NO_PROBE_INSUFFICIENT_DRIVE),
         PredScore(Y_owned) - PredScore(Y_rival) >= 0.05
       - Rival (P_riv, B_riv): G_ctx == 0, A_z < theta_active
       - Cold B-only: G_ctx == 0, A_z < theta_active
       (If NORMAL_W passes but CONSOLIDATED_W fails -> DURABILITY_PENDING per LLA-T10!)
    4. Bit-identical PRE vs POST retirement equivalence across all trials in NORMAL_W and CONSOLIDATED_W (LLA-T35).
    """
    w_state = state.W
    durable_report = check_c04_durable_path(cand, w_state)

    if not is_valid_calibration_triple(cand.l_z_q6, cand.u_z_q6, cand.tau_ctx_q6):
        return GraduationEvaluationResult(
            passed=False,
            status=StatusCode.INVALID_CONTEXT_THRESHOLD,
            durable_report=durable_report,
            diagnostic_detail="Invalid (L_z, U_z, tau_ctx_q6) calibration triple",
        )

    if cand.depth > 1:
        ok_h, code_h = validate_parent_hierarchy(
            cand.depth,
            cand.p_sources,
            cand.p_source_kinds,
            cand.parent_refs,
            w_state,
            {cand.z_cell_id},
        )
        if not ok_h:
            return GraduationEvaluationResult(
                passed=False,
                status=code_h,
                durable_report=durable_report,
                diagnostic_detail="Parent context hierarchy invalid at graduation",
            )

    if not durable_report.is_durable:
        return GraduationEvaluationResult(
            passed=False,
            status=StatusCode.DURABILITY_PENDING,
            durable_report=durable_report,
            diagnostic_detail="C04 durable path incomplete (requires BOTH P, >=1 C, >=1 Y consolidated)",
        )

    resolved_owned, resolved_rivals = _resolve_graduation_witnesses(
        cand, w_state, owned_witness, rival_witnesses
    )
    if resolved_owned is None or not resolved_rivals:
        return GraduationEvaluationResult(
            passed=False,
            status=StatusCode.UNRESOLVED_BRANCH_MATCH,
            durable_report=durable_report,
            diagnostic_detail="Missing owned or confirmed rival witness profile for graduation trials",
        )

    proposed_binding = build_proposed_stable_binding(
        cand, durable_report, binding_generation=binding_generation
    )

    # Construct isolated PRE and POST scratch states sharing the exact same legal W synapses:
    # - PRE retains cand in context_candidates[z] AND installs hypothetical COMPLETE binding in stable_bindings[z]
    #   so compute_temporal_source_mask_mu tests post-graduation mu routing while evaluate_context_gate tests cand
    # - POST retires cand from context_candidates[z] and reserved_keys_by_candidate[z], using only proposed_binding
    pre_state = state.clone()
    pre_state.W.stable_bindings[cand.z_cell_id] = proposed_binding.clone()

    post_state = state.clone()
    post_state.W.context_candidates.pop(cand.z_cell_id, None)
    post_state.W.reserved_keys_by_candidate.pop(cand.z_cell_id, None)
    post_state.W.stable_bindings[cand.z_cell_id] = proposed_binding.clone()

    z_region = CellAddress.from_global_id(cand.z_cell_id).region
    theta_active = state.H_slow.get_theta_active(z_region)
    theta_emit = state.H_slow.get_theta_emit(z_region)

    owned_y_set = {ck[1] for ck in durable_report.consolidated_y_keys}
    rival_y_set = set(resolved_rivals[0].top8_y_supports_u.keys()) - owned_y_set
    if not rival_y_set:
        rival_y_set = set(resolved_rivals[0].top8_y_supports_u.keys())

    normal_owned_az = 0.0
    consolidated_owned_az = 0.0
    normal_pred_margin = 0.0
    consolidated_pred_margin = 0.0

    for mask_nonconsolidated in (False, True):
        # 1. Owned (P_owned -> B_owned) trial in PRE and POST
        sig_pre_owned, az_pre_owned, sc_own_pre, sc_riv_pre = _run_cold_trial(
            pre_state,
            cand.z_cell_id,
            cand.tau_ctx_q6,
            resolved_owned.top8_p_supports_u,
            resolved_owned.p_source_kinds,
            resolved_owned.top8_c_supports_u,
            owned_y_set,
            rival_y_set,
            mask_nonconsolidated=mask_nonconsolidated,
        )
        sig_post_owned, az_post_owned, sc_own_post, sc_riv_post = _run_cold_trial(
            post_state,
            cand.z_cell_id,
            cand.tau_ctx_q6,
            resolved_owned.top8_p_supports_u,
            resolved_owned.p_source_kinds,
            resolved_owned.top8_c_supports_u,
            owned_y_set,
            rival_y_set,
            mask_nonconsolidated=mask_nonconsolidated,
        )

        margin_pre = sc_own_pre - sc_riv_pre
        if not mask_nonconsolidated:
            normal_owned_az = az_pre_owned
            normal_pred_margin = margin_pre
        else:
            consolidated_owned_az = az_pre_owned
            consolidated_pred_margin = margin_pre

        # Check owned gate and emission threshold
        if sig_pre_owned.g_ctx != 1 or az_pre_owned < theta_emit:
            fail_status = (
                StatusCode.DURABILITY_PENDING
                if mask_nonconsolidated
                else StatusCode.NO_PROBE_INSUFFICIENT_DRIVE
            )
            return GraduationEvaluationResult(
                passed=False,
                status=fail_status,
                durable_report=durable_report,
                normal_owned_az=normal_owned_az,
                consolidated_owned_az=consolidated_owned_az,
                normal_pred_margin=normal_pred_margin,
                consolidated_pred_margin=consolidated_pred_margin,
                diagnostic_detail=(
                    f"Owned trial failed emission in {'CONSOLIDATED_W' if mask_nonconsolidated else 'NORMAL_W'}: "
                    f"G_ctx={sig_pre_owned.g_ctx}, A_z={az_pre_owned:.6f} < theta_emit={theta_emit:.6f}"
                ),
            )

        if margin_pre < M_REUSE:
            fail_status = (
                StatusCode.DURABILITY_PENDING
                if mask_nonconsolidated
                else StatusCode.NO_PROBE_FAIL
            )
            return GraduationEvaluationResult(
                passed=False,
                status=fail_status,
                durable_report=durable_report,
                normal_owned_az=normal_owned_az,
                consolidated_owned_az=consolidated_owned_az,
                normal_pred_margin=normal_pred_margin,
                consolidated_pred_margin=consolidated_pred_margin,
                diagnostic_detail=(
                    f"Owned trial failed PredScore margin in {'CONSOLIDATED_W' if mask_nonconsolidated else 'NORMAL_W'}: "
                    f"margin={margin_pre:.6f} < {M_REUSE}"
                ),
            )

        # Check PRE vs POST bit-identical equivalence on owned trial (LLA-T35)
        if sig_pre_owned != sig_post_owned:
            return GraduationEvaluationResult(
                passed=False,
                status=StatusCode.RETIREMENT_SEMANTICS_DRIFT,
                durable_report=durable_report,
                normal_owned_az=normal_owned_az,
                consolidated_owned_az=consolidated_owned_az,
                normal_pred_margin=normal_pred_margin,
                consolidated_pred_margin=consolidated_pred_margin,
                diagnostic_detail="PRE/POST bit-identical check failed on owned P->B trial",
            )

        # 2. Confirmed Rival (P_rival -> B_rival) trials in PRE and POST
        for riv_prof in resolved_rivals:
            sig_pre_riv, az_pre_riv, _, _ = _run_cold_trial(
                pre_state,
                cand.z_cell_id,
                cand.tau_ctx_q6,
                riv_prof.top8_p_supports_u,
                riv_prof.p_source_kinds,
                riv_prof.top8_c_supports_u,
                owned_y_set,
                rival_y_set,
                mask_nonconsolidated=mask_nonconsolidated,
            )
            sig_post_riv, _, _, _ = _run_cold_trial(
                post_state,
                cand.z_cell_id,
                cand.tau_ctx_q6,
                riv_prof.top8_p_supports_u,
                riv_prof.p_source_kinds,
                riv_prof.top8_c_supports_u,
                owned_y_set,
                rival_y_set,
                mask_nonconsolidated=mask_nonconsolidated,
            )
            if sig_pre_riv.g_ctx != 0 or az_pre_riv >= theta_active:
                return GraduationEvaluationResult(
                    passed=False,
                    status=StatusCode.NO_PROBE_FAIL,
                    durable_report=durable_report,
                    diagnostic_detail=f"Rival trial activated z: G_ctx={sig_pre_riv.g_ctx}, A_z={az_pre_riv:.6f}",
                )
            if sig_pre_riv != sig_post_riv:
                return GraduationEvaluationResult(
                    passed=False,
                    status=StatusCode.RETIREMENT_SEMANTICS_DRIFT,
                    durable_report=durable_report,
                    diagnostic_detail="PRE/POST bit-identical check failed on rival P->B trial",
                )

        # 3. Cold B-only trial in PRE and POST
        sig_pre_bonly, az_pre_bonly, _, _ = _run_cold_trial(
            pre_state,
            cand.z_cell_id,
            cand.tau_ctx_q6,
            None,
            None,
            resolved_owned.top8_c_supports_u,
            owned_y_set,
            rival_y_set,
            mask_nonconsolidated=mask_nonconsolidated,
        )
        sig_post_bonly, _, _, _ = _run_cold_trial(
            post_state,
            cand.z_cell_id,
            cand.tau_ctx_q6,
            None,
            None,
            resolved_owned.top8_c_supports_u,
            owned_y_set,
            rival_y_set,
            mask_nonconsolidated=mask_nonconsolidated,
        )
        if sig_pre_bonly.g_ctx != 0 or az_pre_bonly >= theta_active:
            return GraduationEvaluationResult(
                passed=False,
                status=StatusCode.NO_PROBE_FAIL,
                durable_report=durable_report,
                diagnostic_detail=f"Cold B-only trial activated z: G_ctx={sig_pre_bonly.g_ctx}, A_z={az_pre_bonly:.6f}",
            )
        if sig_pre_bonly != sig_post_bonly:
            return GraduationEvaluationResult(
                passed=False,
                status=StatusCode.RETIREMENT_SEMANTICS_DRIFT,
                durable_report=durable_report,
                diagnostic_detail="PRE/POST bit-identical check failed on cold B-only trial",
            )

    return GraduationEvaluationResult(
        passed=True,
        status=StatusCode.OK,
        durable_report=durable_report,
        stable_binding=proposed_binding,
        normal_owned_az=normal_owned_az,
        consolidated_owned_az=consolidated_owned_az,
        normal_pred_margin=normal_pred_margin,
        consolidated_pred_margin=consolidated_pred_margin,
    )


def commit_c04_graduation(
    cand: ContextCandidateDescriptor,
    binding: StableBinding,
    w_state: WState,
) -> None:
    """Atomically publish StableBinding, retire candidate-only metadata, and update OwnerProfile (Core §7.6, §10.2)."""
    z_id = cand.z_cell_id
    cand.phase = CandidatePhase.COMPLETE

    # Retire candidate descriptor and candidate reservation claims
    w_state.context_candidates.pop(z_id, None)
    w_state.reserved_keys_by_candidate.pop(z_id, None)
    w_state.stable_bindings[z_id] = binding

    # Prune any unconsolidated candidate-owned synapses of z_id
    consolidated_role_keys = set(binding.p_keys) | set(binding.c_keys) | set(binding.y_keys)
    for key in list(cand.reserved_synapse_keys):
        if key not in consolidated_role_keys:
            syn = w_state.synapses.get(key)
            if syn is not None and syn.state != SynapseState.CONSOLIDATED:
                w_state.remove_synapse(key)

    # Release temporary candidate pins (live consolidated links remain protected by get_protected_bidirectional_neighbors)
    w_state.latent_table.release_candidate_pins(z_id)

    # Update OwnerProfile state to COMPLETE
    profiles: list[OwnerProfile] = list(
        w_state.owner_profiles_by_anchor.get(cand.anchor_id, [])  # type: ignore[arg-type]
    )
    for prof in profiles:
        if prof.owner_id == cand.owner_id:
            prof.state = OwnerState.COMPLETE
            prof.binding_generation = binding.binding_generation
            break
