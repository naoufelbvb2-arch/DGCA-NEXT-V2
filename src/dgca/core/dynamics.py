"""Two-Pass Neural Dynamics Engine, Provenance Lanes, and Frontier Computation.

Normative references:
- DGCA_CORE_RC4_1.md §5 (Normal two-pass neural dynamics)
- DGCA_CORE_RC4_1.md §5.1 & §5.2 (Permanent conjunction G_z^ctx and target-scoped routing μ_ij)
- DGCA_CORE_RC4_1.md §6 & §6.1 (Temporal-frontier/provenance and typed physical support)
- DGCA_CORE_RC4_1.md §8 (OBS_DIRECT, OBS_ELIGIBLE, CTX_EVENT_MATCH, CTX_RUNTIME)
- DGCA_CORE_RC4_1.md §9.2 & §9.3 (FULL vs CONTROL and P_T_debit_selected)
- DGCA_LLA_RC4_1.md §3 (Eligibility traces and canonical temporal learning)
"""

from __future__ import annotations

from dataclasses import dataclass

from dgca.common.errors import StatusCode
from dgca.common.hashing import Region, WitnessSourceKind
from dgca.common.numeric import clip_float64, noisy_or_float64, q6_from_binary64
from dgca.core.anatomy import (
    H_CONTEXT,
    REGION_PARAMS,
    SynapseScope,
    SynapseState,
    get_k_neural,
)
from dgca.core.attractor import (
    compute_attractor_sigma_support,
    compute_scratch_fresh_pass,
    update_attractors_post_event,
)
from dgca.core.context_gate import (
    compute_directed_mu_ij,
    compute_temporal_source_mask_mu,
    evaluate_context_gate_for_cell,
)
from dgca.core.homeostasis import update_slow_homeostasis
from dgca.core.sic_v1 import CELLS_PER_MICROCOLUMN, CellAddress
from dgca.core.state import (
    CandidatePhase,
    ContributionLane,
    ContributionRecord,
    EligibilityEntry,
    ExecutionMode,
    MachineState,
    TypedSupportRecord,
)
from dgca.encoder.envelope import EventOrigin

ETA_B_PROBE: float = 1.0
K_R_PER_EVENT: int = 12


@dataclass(frozen=True, slots=True)
class EventExecutionResult:
    """Comprehensive snapshot of a single event's two-pass execution."""

    event_order: int
    exposure_id: int | None
    mode: ExecutionMode
    origin: EventOrigin
    boundary: bool
    committed_before_event: frozenset[int]
    newly_committed_sensory_cells: tuple[int, ...]
    obs_direct_cells: frozenset[int]
    obs_eligible_cells: frozenset[int]
    ctx_event_match_cells: frozenset[int]
    ctx_runtime_match_cells: frozenset[int]
    pt_by_cell: dict[int, float]
    ps_by_cell: dict[int, float]
    sigma_by_cell: dict[int, float]
    d1_by_cell: dict[int, float]
    a1_by_cell: dict[int, float]
    d2_by_cell: dict[int, float]
    a_plus_by_cell: dict[int, float]
    e1_frontier: frozenset[int]
    l_frontier: frozenset[int]
    lx_frontier: frozenset[int]
    f_step: frozenset[int]
    g_ctx_by_z: dict[int, int]
    g_probe_by_z: dict[int, float]
    mu_source_mask: dict[int, int]
    fresh_by_cell: dict[int, float]
    m_fresh_by_assembly: dict[int, float]
    typed_supports: dict[int, TypedSupportRecord]
    contributions: tuple[ContributionRecord, ...]
    diagnostics: tuple[StatusCode, ...]
    feature_bundle_digest: bytes = b""


def compute_next_step_temporal_drive(
    state: MachineState,
    *,
    f_step_prev: frozenset[int],
    a_prev_by_cell: dict[int, float],
    mu_prev_source_mask: dict[int, int],
    mask_nonconsolidated: bool = False,
) -> tuple[dict[int, float], dict[int, list[tuple[int, float]]]]:
    """Compute one-step temporal drive P_j^T(t) from frozen F_step(t-1) and frozen mu_i(t-1) (Core §5, §5.2).

    Formula:
        P_j^T(t) = 1 - prod_{(i,j,ASSOC), i in F_step(t-1)} (1 - [1 - mu_ij(t-1)] * A_i(t-1) * Q_ij^ASSOC)
    where mu_ij(t-1) = mu_i(t-1) * 1[not ContextTarget(j, t)] (RC4.1).
    """
    w = state.W
    contribs_by_target: dict[int, list[tuple[int, int, tuple[int, int, SynapseScope], float]]] = {}
    source_pairs_by_target: dict[int, list[tuple[int, float]]] = {}

    for src_id in sorted(f_step_prev):
        a_src = a_prev_by_cell.get(src_id, 0.0)
        if a_src <= 0.0:
            continue
        for key in w.outgoing_by_source.get(src_id, ()):
            _, tgt_id, scope = key
            if scope != SynapseScope.ASSOCIATIVE:
                continue
            syn = w.synapses[key]
            if mask_nonconsolidated and syn.state != SynapseState.CONSOLIDATED:
                continue
            q_val = syn.Q
            if q_val <= 0.0:
                continue
            mu_ij = compute_directed_mu_ij(src_id, tgt_id, mu_prev_source_mask, w)
            if mu_ij == 1:
                continue
            val = (1.0 - float(mu_ij)) * a_src * q_val * get_k_neural(SynapseScope.ASSOCIATIVE, 1)
            if val > 0.0:
                contribs_by_target.setdefault(tgt_id, []).append((src_id, int(scope), key, val))
                source_pairs_by_target.setdefault(tgt_id, []).append((src_id, val))

    pt_by_cell: dict[int, float] = {}
    for tgt_id, items in sorted(contribs_by_target.items()):
        # Core §3.1: fold contributors in (source_cell_id, scope_order, link_key) ascending order
        items.sort(key=lambda item: (item[0], item[1], item[2]))
        pt_val = noisy_or_float64([item[3] for item in items])
        if pt_val > 0.0:
            pt_by_cell[tgt_id] = pt_val

    return pt_by_cell, source_pairs_by_target


def execute_two_pass_event(
    state: MachineState,
    x_fixed_by_global_id: dict[int, int],
    x_float_by_global_id: dict[int, float],
    *,
    mode: ExecutionMode = ExecutionMode.LEARN,
    origin: EventOrigin = EventOrigin.EXTERNAL_DIRECT,
    boundary: bool = False,
    exposure_id: int | None = None,
    event_order: int = 0,
    feature_bundle_digest: bytes = b"",
    allow_candidate_probe: bool = True,
    control_zero_pt: bool = False,
    apply_pt_debit_selected: bool = False,
    mask_nonconsolidated_candidate_links: bool = False,
    admit_uncommitted_sensory: bool = True,
    k_r_budget: int = K_R_PER_EVENT,
) -> EventExecutionResult:
    """Execute normal two-pass neural dynamics for a single event on MachineState (Core §5, §6).

    Enforces:
    - Frozen pre-event W and H_slow during both passes
    - Permanent physical conjunction G_z^ctx on contextual cells before microcolumn normalization
    - LEARN-only candidate probe inside valid G_z^ctx
    - RC4.1 target-scoped temporal source mask mu_ij
    - P_T_debit_selected when origin == INTERNAL_SELECTED (or apply_pt_debit_selected=True)
    - Provenance lane tagging and typed physical supports o^train / o^runtime
    - Post-event sensory cell commitment (in LEARN) without retroactive same-event evidence
    """
    w = state.W
    r = state.R
    h_slow = state.H_slow

    # 1. Snapshot commitment and handle HARD_BOUNDARY
    committed_before: set[int] = set(w.committed_cells.keys())
    if boundary:
        a_prev_map: dict[int, float] = {}
        f_step_prev: frozenset[int] = frozenset()
        mu_prev_map: dict[int, int] = {}
        prev_supports: dict[int, TypedSupportRecord] = {}
        r.active_attractors.clear()
        r.eligibility_traces.clear()
    else:
        a_prev_map = dict(r.A)
        f_step_prev = r.F_step
        mu_prev_map = dict(r.mu_source_mask)
        prev_supports = dict(r.typed_supports_current)

    r.A_prev = dict(a_prev_map)
    r.F_step_prev = f_step_prev
    r.mu_prev_source_mask = dict(mu_prev_map)
    r.typed_supports_prev = dict(prev_supports)

    # 2. Direct observation predicates (Core §8, LLA §2.1)
    is_real_external = origin == EventOrigin.EXTERNAL_DIRECT
    obs_direct_cells = frozenset(
        cid for cid, u_val in x_fixed_by_global_id.items() if u_val > 0 and is_real_external
    )
    obs_eligible_cells = frozenset(
        cid for cid in obs_direct_cells if cid in committed_before and not w.is_contextual_cell(cid)
    )

    # Build direct typed supports for committed non-contextual receivers (Core §6.1)
    curr_supports: dict[int, TypedSupportRecord] = {}
    for cid, u_val in sorted(x_fixed_by_global_id.items()):
        if u_val <= 0 or cid not in committed_before or w.is_contextual_cell(cid):
            continue
        x_flt = x_float_by_global_id[cid]
        if mode == ExecutionMode.LEARN and origin == EventOrigin.EXTERNAL_DIRECT:
            curr_supports[cid] = TypedSupportRecord(
                cell_id=cid,
                event_order=event_order,
                origin_kind=EventOrigin.EXTERNAL_DIRECT.value,
                o_train=x_flt,
                o_runtime=x_flt,
                q6_train=u_val,
                q6_runtime=u_val,
                depth=0,
            )
        elif origin == EventOrigin.INTERNAL_SELECTED:
            # Core §6.1: NEW_SELECTED_INTERNAL is disabled for standalone RETRIEVE, enabled in GENERATE
            if mode == ExecutionMode.GENERATE:
                curr_supports[cid] = TypedSupportRecord(
                    cell_id=cid,
                    event_order=event_order,
                    origin_kind=EventOrigin.INTERNAL_SELECTED.value,
                    o_train=0.0,
                    o_runtime=x_flt,
                    q6_train=0,
                    q6_runtime=u_val,
                    depth=0,
                )
        else:
            curr_supports[cid] = TypedSupportRecord(
                cell_id=cid,
                event_order=event_order,
                origin_kind=EventOrigin.READ_ONLY_OBSERVED.value,
                o_train=0.0,
                o_runtime=x_flt,
                q6_train=0,
                q6_runtime=u_val,
                depth=0,
            )

    # 3. Evaluate contextual gate G_z^ctx(t) and candidate probe G_z^probe(t) for all contextual cells
    all_contextual_cells = sorted(set(w.stable_bindings.keys()) | set(w.context_candidates.keys()))
    g_ctx_by_z: dict[int, int] = {}
    g_probe_by_z: dict[int, float] = {}
    diagnostics: list[StatusCode] = []

    for z_id in all_contextual_cells:
        g_ctx, g_probe, diags = evaluate_context_gate_for_cell(
            z_id,
            w,
            boundary=boundary,
            prev_supports=prev_supports,
            curr_supports=curr_supports,
            mode=mode,
            committed_before_event=committed_before,
            mask_nonconsolidated_candidate_links=mask_nonconsolidated_candidate_links,
        )
        g_ctx_by_z[z_id] = g_ctx
        g_probe_by_z[z_id] = g_probe
        diagnostics.extend(diags)

    # 4. Compute temporal drive P_j^T(t) and Attractor support sigma_j(t)
    sigma_by_cell = compute_attractor_sigma_support(w, r.active_attractors)
    if boundary or control_zero_pt:
        pt_by_cell: dict[int, float] = {}
        pt_sources_by_target: dict[int, list[tuple[int, float]]] = {}
    else:
        pt_by_cell, pt_sources_by_target = compute_next_step_temporal_drive(
            state,
            f_step_prev=f_step_prev,
            a_prev_by_cell=a_prev_map,
            mu_prev_source_mask=mu_prev_map,
            mask_nonconsolidated=mask_nonconsolidated_candidate_links,
        )

    # Core §9.3 No-double-count rule (P_T_debit_selected):
    # On an INTERNAL_SELECTED event, zero P_T,j(t+1) ONLY for targets j with X_int,j > 0;
    # leave P_T intact for all other targets (especially contextual cells z).
    if apply_pt_debit_selected or origin == EventOrigin.INTERNAL_SELECTED:
        for rx_id, u_val in x_fixed_by_global_id.items():
            if u_val > 0 and rx_id in pt_by_cell:
                del pt_by_cell[rx_id]
                pt_sources_by_target.pop(rx_id, None)

    # 5. Pass 1: hat_D_j^(1) = NoisyOR(X_j, P_j^T, sigma_j), gate contextual z, normalize by microcolumn
    pass1_cells = (
        set(x_float_by_global_id.keys())
        | set(pt_by_cell.keys())
        | set(sigma_by_cell.keys())
        | set(a_prev_map.keys())
    )
    hat_d1_by_cell: dict[int, float] = {}
    mc_sums_1: dict[int, float] = {}

    for cid in sorted(pass1_cells):
        x_val = x_float_by_global_id.get(cid, 0.0)
        pt_val = pt_by_cell.get(cid, 0.0)
        sig_val = sigma_by_cell.get(cid, 0.0)
        hat_d1_base = noisy_or_float64([x_val, pt_val, sig_val])
        if cid in g_ctx_by_z:
            hat_d1 = float(g_ctx_by_z[cid]) * hat_d1_base
        else:
            hat_d1 = hat_d1_base

        if hat_d1 > 0.0:
            hat_d1_by_cell[cid] = hat_d1
            addr = CellAddress.from_global_id(cid)
            mc_sums_1[addr.microcolumn_index] = (
                mc_sums_1.get(addr.microcolumn_index, 0.0) + hat_d1
            )

    d1_by_cell: dict[int, float] = {}
    a1_by_cell: dict[int, float] = {}
    e1_list: list[int] = []

    for cid in sorted(pass1_cells):
        addr = CellAddress.from_global_id(cid)
        params = REGION_PARAMS[addr.region]
        hat_d1 = hat_d1_by_cell.get(cid, 0.0)
        mc_mean_1 = mc_sums_1.get(addr.microcolumn_index, 0.0) / float(CELLS_PER_MICROCOLUMN)
        d1 = hat_d1 / (1.0 + params.beta * mc_mean_1) if hat_d1 > 0.0 else 0.0
        a_prev_val = a_prev_map.get(cid, 0.0)
        g_j = h_slow.get_g(cid)
        a1 = clip_float64((1.0 - params.delta_a) * a_prev_val + params.gamma_a * g_j * d1, 0.0, 1.0)
        if cid in g_ctx_by_z:
            a1 = float(g_ctx_by_z[cid]) * a1

        if d1 > 0.0:
            d1_by_cell[cid] = d1
        if a1 > 0.0:
            a1_by_cell[cid] = a1
            if cid in committed_before and a1 >= h_slow.get_theta_emit(addr.region):
                e1_list.append(cid)

    e1_frontier = frozenset(e1_list)

    # 6. Pass 2: synchronous drive P_j^S from E_t^(1) over live LOCAL and CROSS_TERRITORY links
    ps_contribs_by_target: dict[int, list[tuple[int, int, tuple[int, int, SynapseScope], float]]] = {}
    for src_id in e1_list:
        a1_src = a1_by_cell[src_id]
        for key in w.outgoing_by_source.get(src_id, ()):
            _, tgt_id, scope = key
            if scope not in (SynapseScope.LOCAL, SynapseScope.CROSS_TERRITORY):
                continue
            syn = w.synapses[key]
            if mask_nonconsolidated_candidate_links and syn.state != SynapseState.CONSOLIDATED:
                continue
            q_val = syn.Q
            if q_val <= 0.0:
                continue
            val = a1_src * q_val * get_k_neural(scope, 0)
            if val > 0.0:
                ps_contribs_by_target.setdefault(tgt_id, []).append((src_id, int(scope), key, val))

    ps_by_cell: dict[int, float] = {}
    for tgt_id, items in sorted(ps_contribs_by_target.items()):
        items.sort(key=lambda item: (item[0], item[1], item[2]))
        ps_val = noisy_or_float64([item[3] for item in items])
        if ps_val > 0.0:
            ps_by_cell[tgt_id] = ps_val

    pass2_cells = pass1_cells | set(ps_by_cell.keys()) | set(g_ctx_by_z.keys())
    hat_d2_by_cell: dict[int, float] = {}
    mc_sums_2: dict[int, float] = {}
    bootstrapped_cells: dict[int, float] = {}

    for cid in sorted(pass2_cells):
        x_val = x_float_by_global_id.get(cid, 0.0)
        pt_val = pt_by_cell.get(cid, 0.0)
        ps_val = ps_by_cell.get(cid, 0.0)
        sig_val = sigma_by_cell.get(cid, 0.0)
        hat_d2_base = noisy_or_float64([x_val, pt_val, ps_val, sig_val])

        if cid in g_ctx_by_z:
            g_ctx = g_ctx_by_z[cid]
            if g_ctx == 0:
                hat_d2 = 0.0
            else:
                hat_d2 = hat_d2_base
                # Core §7.5: Candidate-only bootstrap probe inside valid G_z^ctx=1 in OPEN genuine LEARN
                cand = w.context_candidates.get(cid)
                probe_eligible = (
                    mode == ExecutionMode.LEARN
                    and origin == EventOrigin.EXTERNAL_DIRECT
                    and allow_candidate_probe
                    and cand is not None
                    and cand.phase
                    in (
                        CandidatePhase.WIRED,
                        CandidatePhase.PROBE_INCOMING,
                        CandidatePhase.LEARN_OUTCOME,
                        CandidatePhase.NO_PROBE_TEST,
                    )
                    and cid in committed_before
                )
                if probe_eligible:
                    g_probe = g_probe_by_z.get(cid, 0.0)
                    if g_probe > 0.0:
                        hat_d2 = 1.0 - (1.0 - hat_d2_base) * (1.0 - ETA_B_PROBE * g_probe)
                        bootstrapped_cells[cid] = ETA_B_PROBE * g_probe
        else:
            hat_d2 = hat_d2_base

        if hat_d2 > 0.0:
            hat_d2_by_cell[cid] = hat_d2
            addr = CellAddress.from_global_id(cid)
            mc_sums_2[addr.microcolumn_index] = (
                mc_sums_2.get(addr.microcolumn_index, 0.0) + hat_d2
            )

    d2_by_cell: dict[int, float] = {}
    a_plus_by_cell: dict[int, float] = {}
    l_list: list[int] = []
    lx_list: list[int] = []

    for cid in sorted(pass2_cells):
        addr = CellAddress.from_global_id(cid)
        params = REGION_PARAMS[addr.region]
        hat_d2 = hat_d2_by_cell.get(cid, 0.0)
        mc_mean_2 = mc_sums_2.get(addr.microcolumn_index, 0.0) / float(CELLS_PER_MICROCOLUMN)
        d2 = hat_d2 / (1.0 + params.beta * mc_mean_2) if hat_d2 > 0.0 else 0.0
        a_prev_val = a_prev_map.get(cid, 0.0)
        g_j = h_slow.get_g(cid)
        a_plus = clip_float64(
            (1.0 - params.delta_a) * a_prev_val + params.gamma_a * g_j * d2, 0.0, 1.0
        )
        if cid in g_ctx_by_z:
            a_plus = float(g_ctx_by_z[cid]) * a_plus

        if d2 > 0.0:
            d2_by_cell[cid] = d2
        if a_plus > 0.0:
            a_plus_by_cell[cid] = a_plus
            if cid in committed_before:
                if a_plus >= h_slow.get_theta_active(addr.region):
                    l_list.append(cid)
                if a_plus >= h_slow.get_theta_bind(addr.region):
                    lx_list.append(cid)

    l_frontier = frozenset(l_list)
    lx_frontier = frozenset(lx_list)

    # 7. Evaluate contextual matches, derived contextual supports, and F_t^step (Core §6, §6.1, §8)
    ctx_event_match_list: list[int] = []
    ctx_runtime_match_list: list[int] = []
    f_step_list: list[int] = []

    for cid in sorted(committed_before):
        a_plus = a_plus_by_cell.get(cid, 0.0)
        addr = CellAddress.from_global_id(cid)
        theta_emit = h_slow.get_theta_emit(addr.region)
        if a_plus < theta_emit:
            continue

        if cid in g_ctx_by_z:
            # Contextual cell z: RC3 physical G_z^ctx is enforced; no off-context F_step is permitted
            if g_ctx_by_z[cid] == 1:
                if mode == ExecutionMode.LEARN and origin == EventOrigin.EXTERNAL_DIRECT:
                    ctx_event_match_list.append(cid)
                    f_step_list.append(cid)
                else:
                    # In read-only / generate, completed owners (or diagnostic candidates) with G_ctx=1 & A>=theta_emit
                    ctx_runtime_match_list.append(cid)
                    f_step_list.append(cid)
        else:
            # Ordinary cell: requires NEW_OBSERVED (direct external, read-only observed, or internal selected in GENERATE)
            if cid in curr_supports:
                rec = curr_supports[cid]
                if rec.o_train > 0.0 or rec.o_runtime > 0.0:
                    f_step_list.append(cid)

    f_step = frozenset(f_step_list)
    ctx_event_match_cells = frozenset(ctx_event_match_list)
    ctx_runtime_match_cells = frozenset(ctx_runtime_match_list)

    # Record DERIVED_EXTERNAL_CONTEXT / DERIVED_RUNTIME_CONTEXT supports for completed owners in F_step (Core §6.1)
    for z_id in sorted(w.stable_bindings.keys()):
        if z_id in w.context_candidates:
            continue
        if z_id not in f_step or g_ctx_by_z.get(z_id, 0) != 1:
            continue
        binding = w.stable_bindings[z_id]
        a_z = a_plus_by_cell.get(z_id, 0.0)
        q6_a = q6_from_binary64(a_z)
        o_val = float(q6_a) / 1_000_000.0
        if o_val <= 0.0:
            continue

        p0, p1 = binding.p_sources
        rec_p0 = prev_supports.get(p0)
        rec_p1 = prev_supports.get(p1)
        valid_parent_order = (
            rec_p0 is not None
            and rec_p1 is not None
            and rec_p0.event_order == event_order - 1
            and rec_p1.event_order == event_order - 1
            and rec_p0.parent_proof_verified
            and rec_p1.parent_proof_verified
        )
        pure_external_chain = (
            mode == ExecutionMode.LEARN
            and origin == EventOrigin.EXTERNAL_DIRECT
            and event_order >= binding.depth
            and valid_parent_order
            and rec_p0 is not None
            and rec_p1 is not None
            and rec_p0.o_train > 0.0
            and rec_p1.o_train > 0.0
            and z_id not in bootstrapped_cells
        )
        if pure_external_chain:
            curr_supports[z_id] = TypedSupportRecord(
                cell_id=z_id,
                event_order=event_order,
                origin_kind=ContributionLane.DERIVED_EXTERNAL_CONTEXT.value,
                o_train=o_val,
                o_runtime=o_val,
                q6_train=q6_a,
                q6_runtime=q6_a,
                depth=binding.depth,
                owner_id=binding.owner_id,
                binding_generation=binding.binding_generation,
                parent_proof_verified=True,
            )
        else:
            curr_supports[z_id] = TypedSupportRecord(
                cell_id=z_id,
                event_order=event_order,
                origin_kind=ContributionLane.DERIVED_RUNTIME_CONTEXT.value,
                o_train=0.0,
                o_runtime=o_val,
                q6_train=0,
                q6_runtime=q6_a,
                depth=binding.depth,
                owner_id=binding.owner_id,
                binding_generation=binding.binding_generation,
                parent_proof_verified=valid_parent_order,
            )

    # 8. Build tagged contribution lanes (Core §6, LLA §2.2)
    contributions: list[ContributionRecord] = []
    root_tuple = (exposure_id,) if exposure_id is not None else ()
    step_id = r.step_index

    for cid in sorted(pass2_cells):
        x_val = x_float_by_global_id.get(cid, 0.0)
        if x_val > 0.0:
            if origin == EventOrigin.EXTERNAL_DIRECT:
                lane = ContributionLane.DIRECT_OBSERVED
            elif origin == EventOrigin.INTERNAL_SELECTED:
                lane = ContributionLane.INTERNAL_SELECTED
            else:
                lane = ContributionLane.READ_ONLY_OBSERVED
            contributions.append(
                ContributionRecord(
                    target_cell_id=cid,
                    source_cell_id=None,
                    event_order=event_order,
                    lane=lane,
                    nonnegative_support=x_val,
                    witness_roots=root_tuple if origin == EventOrigin.EXTERNAL_DIRECT else (),
                    step_id=step_id,
                )
            )

        for src_id, contrib_val in pt_sources_by_target.get(cid, []):
            contributions.append(
                ContributionRecord(
                    target_cell_id=cid,
                    source_cell_id=src_id,
                    event_order=event_order,
                    lane=ContributionLane.PREDICTED,
                    nonnegative_support=contrib_val,
                    witness_roots=(),
                    step_id=step_id,
                )
            )

        for src_id, _, _, contrib_val in ps_contribs_by_target.get(cid, []):
            contributions.append(
                ContributionRecord(
                    target_cell_id=cid,
                    source_cell_id=src_id,
                    event_order=event_order,
                    lane=ContributionLane.SPATIALLY_COMPLETED,
                    nonnegative_support=contrib_val,
                    witness_roots=(),
                    step_id=step_id,
                )
            )

        if cid in g_ctx_by_z and g_ctx_by_z[cid] == 1 and a_plus_by_cell.get(cid, 0.0) > 0.0:
            contributions.append(
                ContributionRecord(
                    target_cell_id=cid,
                    source_cell_id=None,
                    event_order=event_order,
                    lane=ContributionLane.CONTEXT_MATCHED,
                    nonnegative_support=a_plus_by_cell[cid],
                    witness_roots=root_tuple if mode == ExecutionMode.LEARN else (),
                    step_id=step_id,
                )
            )

        if cid in bootstrapped_cells:
            contributions.append(
                ContributionRecord(
                    target_cell_id=cid,
                    source_cell_id=None,
                    event_order=event_order,
                    lane=ContributionLane.BOOTSTRAPPED,
                    nonnegative_support=bootstrapped_cells[cid],
                    witness_roots=(),
                    step_id=step_id,
                )
            )

        a_prev_val = a_prev_map.get(cid, 0.0)
        if a_prev_val > 0.0:
            addr = CellAddress.from_global_id(cid)
            res_val = (1.0 - REGION_PARAMS[addr.region].delta_a) * a_prev_val
            if res_val > 0.0:
                contributions.append(
                    ContributionRecord(
                        target_cell_id=cid,
                        source_cell_id=cid,
                        event_order=event_order,
                        lane=ContributionLane.RESIDUAL,
                        nonnegative_support=res_val,
                        witness_roots=(),
                        step_id=step_id,
                    )
                )

        sig_val = sigma_by_cell.get(cid, 0.0)
        if sig_val > 0.0:
            contributions.append(
                ContributionRecord(
                    target_cell_id=cid,
                    source_cell_id=None,
                    event_order=event_order,
                    lane=ContributionLane.ATTRACTOR,
                    nonnegative_support=sig_val,
                    witness_roots=(),
                    step_id=step_id,
                )
            )

    # 9. Compute and freeze mu_i(t) from the completed event (Core §5.2 Critical sequencing)
    theta_emit_by_cell = {
        cid: h_slow.get_theta_emit(CellAddress.from_global_id(cid).region)
        for cid in committed_before
    }
    mu_source_mask, mu_diags = compute_temporal_source_mask_mu(
        w,
        g_ctx_by_z=g_ctx_by_z,
        a_plus_by_id=a_plus_by_cell,
        f_step=f_step,
        curr_supports=curr_supports,
        theta_emit_by_cell=theta_emit_by_cell,
    )
    diagnostics.extend(mu_diags)

    # 10. Update RState working fields and bounded eligibility traces (LLA §3)
    # Only committed cells hold persistent R.A (Core §1.2 UNCOMMITTED => A=0)
    r.A = {cid: val for cid, val in a_plus_by_cell.items() if cid in committed_before}
    r.A_pass1 = {cid: val for cid, val in a1_by_cell.items() if cid in committed_before}
    for cid in committed_before:
        cur_a = r.A.get(cid, 0.0)
        old_hist = r.A_hist.get(cid, ()) if not boundary else ()
        if cur_a > 0.0 or old_hist:
            new_hist = (old_hist + (cur_a,))[-H_CONTEXT:]
            r.A_hist[cid] = new_hist
            if mode == ExecutionMode.LEARN:
                w.last_referenced_event[cid] = w.global_event_clock

    r.E1_frontier = e1_frontier
    r.L_frontier = l_frontier
    r.Lx_frontier = lx_frontier
    r.F_step = f_step
    r.g_ctx_by_z = g_ctx_by_z
    r.mu_source_mask = mu_source_mask
    r.context_diagnostics = list(diagnostics)
    r.contribution_lanes = list(contributions)
    r.typed_supports_current = curr_supports

    # Append eligibility trace entries for cells committed before this event (LLA §3)
    witness_id = (exposure_id, event_order, feature_bundle_digest) if feature_bundle_digest else None
    for cid in sorted(committed_before):
        a_val = r.A.get(cid, 0.0)
        a1_val = r.A_pass1.get(cid, 0.0)
        if a_val > 0.0 or a1_val > 0.0 or cid in r.eligibility_traces:
            entry = EligibilityEntry(
                cell_id=cid,
                a_eligible=a_val,
                a_pass1=a1_val,
                in_e1_frontier=(cid in e1_frontier),
                in_f_step=(cid in f_step),
                in_l_frontier=(cid in l_frontier),
                in_lx_frontier=(cid in lx_frontier),
                event_order=event_order,
                exposure_id=exposure_id,
                origin_kind=origin.value,
                witness_id=witness_id,
            )
            trace_list = r.eligibility_traces.setdefault(cid, [])
            trace_list.append(entry)
            # Prune entries older than H_context = 5 steps
            if len(trace_list) > H_CONTEXT:
                del trace_list[:-H_CONTEXT]

    # 11. Compute scratch fresh pass and update Attractors for the NEXT event (Core §2.1)
    has_external_input = (origin == EventOrigin.EXTERNAL_DIRECT) and bool(x_float_by_global_id)
    fresh_by_cell = compute_scratch_fresh_pass(
        x_float_by_global_id,
        w,
        h_slow,
        committed_before_event=committed_before,
        has_external_input=has_external_input,
    )
    direct_o_map = {
        cid: rec.o_train
        for cid, rec in curr_supports.items()
        if rec.origin_kind == EventOrigin.EXTERNAL_DIRECT.value and rec.o_train > 0.0
    }
    m_fresh_by_assembly = update_attractors_post_event(
        r,
        w,
        boundary=boundary,
        fresh_by_cell=fresh_by_cell,
        has_external_input=has_external_input,
        comparable_external_outcome=(has_external_input and bool(direct_o_map)),
        direct_observed_o_by_cell=direct_o_map,
        a_prev_by_cell=a_prev_map,
        f_step_prev=f_step_prev,
    )

    # 12. Slow homeostatic adaptation (ONLY in LEARN, after Pass 2 frontiers are frozen, Core §5)
    if mode == ExecutionMode.LEARN:
        update_slow_homeostasis(
            h_slow,
            w,
            r.A,
            committed_before_event=committed_before,
            mode=mode,
        )

    # 13. Admit uncommitted direct sensory receivers at END of event (ONLY in LEARN, up to K_R=12)
    # Core §10.1 & LLA §7 rule 2: admitted at end of event; do not enter same-event learning
    newly_committed: list[int] = []
    if (
        mode == ExecutionMode.LEARN
        and origin == EventOrigin.EXTERNAL_DIRECT
        and admit_uncommitted_sensory
        and k_r_budget > 0
    ):
        uncommitted_candidates = [
            (cid, x_float_by_global_id[cid])
            for cid in sorted(obs_direct_cells)
            if cid not in committed_before and x_float_by_global_id.get(cid, 0.0) > 1e-6
        ]
        # Sort by (-support, cell_id) deterministically
        uncommitted_candidates.sort(key=lambda item: (-item[1], item[0]))
        for cid, _ in uncommitted_candidates[:k_r_budget]:
            if w.commit_cell(cid, w.global_event_clock):
                newly_committed.append(cid)

    r.step_index += 1
    if mode == ExecutionMode.LEARN and origin == EventOrigin.EXTERNAL_DIRECT:
        w.global_event_clock += 1

    return EventExecutionResult(
        event_order=event_order,
        exposure_id=exposure_id,
        mode=mode,
        origin=origin,
        boundary=boundary,
        committed_before_event=frozenset(committed_before),
        newly_committed_sensory_cells=tuple(newly_committed),
        obs_direct_cells=obs_direct_cells,
        obs_eligible_cells=obs_eligible_cells,
        ctx_event_match_cells=ctx_event_match_cells,
        ctx_runtime_match_cells=ctx_runtime_match_cells,
        pt_by_cell=pt_by_cell,
        ps_by_cell=ps_by_cell,
        sigma_by_cell=sigma_by_cell,
        d1_by_cell=d1_by_cell,
        a1_by_cell=a1_by_cell,
        d2_by_cell=d2_by_cell,
        a_plus_by_cell=a_plus_by_cell,
        e1_frontier=e1_frontier,
        l_frontier=l_frontier,
        lx_frontier=lx_frontier,
        f_step=f_step,
        g_ctx_by_z=g_ctx_by_z,
        g_probe_by_z=g_probe_by_z,
        mu_source_mask=mu_source_mask,
        fresh_by_cell=fresh_by_cell,
        m_fresh_by_assembly=m_fresh_by_assembly,
        typed_supports=curr_supports,
        contributions=tuple(contributions),
        diagnostics=tuple(diagnostics),
        feature_bundle_digest=feature_bundle_digest,
    )


def compute_pred_score(
    next_step_pt_by_cell: dict[int, float],
    evaluator_target_cells: set[int] | frozenset[int] | tuple[int, ...] | list[int],
) -> tuple[StatusCode, float]:
    """Compute PredScore_W(Y | P, B) = |Y|^-1 * sum_{j in Y} P_j^T(next) (Core §9.1).

    Y is an evaluator-only observed footprint, never supplied as current input nor looked up by Core.
    If Y is empty -> (StatusCode.UNRESOLVED, 0.0).
    """
    target_set = sorted(set(evaluator_target_cells))
    if not target_set:
        return StatusCode.UNRESOLVED, 0.0
    total_pt = sum(next_step_pt_by_cell.get(cid, 0.0) for cid in target_set)
    return StatusCode.OK, total_pt / float(len(target_set))
