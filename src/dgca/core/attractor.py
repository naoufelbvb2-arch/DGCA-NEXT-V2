"""Fresh-Only Context Attractor Computation and Update (Core §2.1).

Normative reference:
- DGCA_CORE_RC4_1.md §2.1 (Fresh-only Attractor update)
"""

from __future__ import annotations

from dgca.common.numeric import clip_float64, noisy_or_float64
from dgca.core.anatomy import (
    REGION_PARAMS,
    SynapseScope,
    SynapseState,
    get_k_neural,
)
from dgca.core.sic_v1 import CELLS_PER_MICROCOLUMN, CellAddress
from dgca.core.state import (
    Assembly,
    AssemblyStatus,
    AttractorRuntimeState,
    HSlowState,
    RState,
    WState,
)

RHO_S: float = 0.90
T_MAX_ATTRACTOR: int = 30
THETA_ERR: float = 1.50
THETA_IN: float = 0.40
THETA_CTX_FORM: float = 0.50
THETA_PRED: float = 0.25
OMEGA_X: float = 0.85


def compute_assembly_cohesion(assembly: Assembly, w: WState) -> float:
    """Compute mutual reciprocal cohesion of an Assembly G from live CONSOLIDATED LOCAL/CROSS links (Core §2.0, §2.1)."""
    members = assembly.member_cell_ids
    k = len(members)
    if k < 3:
        return 0.0

    pair_supports: list[float] = []
    for idx_i in range(k):
        i = members[idx_i]
        for idx_j in range(idx_i + 1, k):
            j = members[idx_j]
            syn_ij_loc = w.synapses.get((i, j, SynapseScope.LOCAL))
            syn_ji_loc = w.synapses.get((j, i, SynapseScope.LOCAL))
            q_ij_loc = (
                syn_ij_loc.Q
                if syn_ij_loc is not None and syn_ij_loc.state == SynapseState.CONSOLIDATED
                else 0.0
            )
            q_ji_loc = (
                syn_ji_loc.Q
                if syn_ji_loc is not None and syn_ji_loc.state == SynapseState.CONSOLIDATED
                else 0.0
            )
            r_local = min(q_ij_loc, q_ji_loc)

            syn_ij_x = w.synapses.get((i, j, SynapseScope.CROSS_TERRITORY))
            syn_ji_x = w.synapses.get((j, i, SynapseScope.CROSS_TERRITORY))
            q_ij_x = (
                syn_ij_x.Q
                if syn_ij_x is not None and syn_ij_x.state == SynapseState.CONSOLIDATED
                else 0.0
            )
            q_ji_x = (
                syn_ji_x.Q
                if syn_ji_x is not None and syn_ji_x.state == SynapseState.CONSOLIDATED
                else 0.0
            )
            r_cross = OMEGA_X * min(q_ij_x, q_ji_x)
            pair_supports.append(max(r_local, r_cross))

    if not pair_supports:
        return 0.0
    return sum(pair_supports) / float(len(pair_supports))


def compute_scratch_fresh_pass(
    x_float_by_global_id: dict[int, float],
    w: WState,
    h_slow: HSlowState,
    *,
    committed_before_event: set[int],
    has_external_input: bool,
) -> dict[int, float]:
    """Compute the separate scratch fresh pass from frozen W/H (Core §2.1).

    With A_prev=0, P_T=0, sigma=0, bootstrap=0; retains only current external SIC X
    and its one synchronized LOCAL/CROSS propagation.
    No external input => all fresh_j = 0.
    """
    if not has_external_input or not x_float_by_global_id:
        return {}

    # Pass 1 fresh: hat_D^(1) = X_j
    mc_sums_1: dict[int, float] = {}
    for cid, x_val in x_float_by_global_id.items():
        if x_val <= 0.0:
            continue
        if w.is_contextual_cell(cid):
            # Contextual cells require predecessor P which is 0 in fresh pass (A_prev=0, P_T=0)
            continue
        addr = CellAddress.from_global_id(cid)
        mc_sums_1[addr.microcolumn_index] = mc_sums_1.get(addr.microcolumn_index, 0.0) + x_val

    a_fresh_1: dict[int, float] = {}
    e_fresh_1: list[int] = []

    for cid, x_val in sorted(x_float_by_global_id.items()):
        if x_val <= 0.0 or w.is_contextual_cell(cid):
            continue
        addr = CellAddress.from_global_id(cid)
        params = REGION_PARAMS[addr.region]
        mc_mean = mc_sums_1.get(addr.microcolumn_index, 0.0) / float(CELLS_PER_MICROCOLUMN)
        d1 = x_val / (1.0 + params.beta * mc_mean)
        g_j = h_slow.get_g(cid)
        a1 = clip_float64(params.gamma_a * g_j * d1, 0.0, 1.0)
        a_fresh_1[cid] = a1
        if cid in committed_before_event and a1 >= h_slow.get_theta_emit(addr.region):
            e_fresh_1.append(cid)

    # Pass 2 fresh: P_S^fresh from E^fresh,(1) via live LOCAL/CROSS links
    ps_contributors_by_target: dict[int, list[tuple[int, int, SynapseScope, float]]] = {}
    for src_id in e_fresh_1:
        a1_src = a_fresh_1[src_id]
        for key in w.outgoing_by_source.get(src_id, ()):
            _, tgt_id, scope = key
            if scope not in (SynapseScope.LOCAL, SynapseScope.CROSS_TERRITORY):
                continue
            if w.is_contextual_cell(tgt_id):
                continue
            syn = w.synapses[key]
            q_val = syn.Q
            if q_val <= 0.0:
                continue
            contrib = a1_src * q_val * get_k_neural(scope, 0)
            if contrib > 0.0:
                ps_contributors_by_target.setdefault(tgt_id, []).append(
                    (src_id, int(scope), scope, contrib)
                )

    hat_d2_by_cell: dict[int, float] = {}
    candidate_cells = set(x_float_by_global_id.keys()) | set(ps_contributors_by_target.keys())
    mc_sums_2: dict[int, float] = {}

    for cid in sorted(candidate_cells):
        if w.is_contextual_cell(cid):
            continue
        x_val = x_float_by_global_id.get(cid, 0.0)
        contribs = ps_contributors_by_target.get(cid, [])
        if contribs:
            contribs.sort(key=lambda item: (item[0], item[1]))
            ps_val = noisy_or_float64([c[3] for c in contribs])
        else:
            ps_val = 0.0
        hat_d2 = noisy_or_float64([x_val, ps_val]) if ps_val > 0.0 else x_val
        if hat_d2 > 0.0:
            hat_d2_by_cell[cid] = hat_d2
            addr = CellAddress.from_global_id(cid)
            mc_sums_2[addr.microcolumn_index] = (
                mc_sums_2.get(addr.microcolumn_index, 0.0) + hat_d2
            )

    fresh_by_cell: dict[int, float] = {}
    for cid, hat_d2 in sorted(hat_d2_by_cell.items()):
        addr = CellAddress.from_global_id(cid)
        params = REGION_PARAMS[addr.region]
        mc_mean = mc_sums_2.get(addr.microcolumn_index, 0.0) / float(CELLS_PER_MICROCOLUMN)
        d2 = hat_d2 / (1.0 + params.beta * mc_mean)
        g_j = h_slow.get_g(cid)
        fresh_j = clip_float64(params.gamma_a * g_j * d2, 0.0, 1.0)
        if fresh_j > 0.0:
            fresh_by_cell[cid] = fresh_j

    return fresh_by_cell


def compute_assembly_fresh_mean(assembly: Assembly, fresh_by_cell: dict[int, float]) -> float:
    """Compute M_G^fresh(t) = |G|^-1 * sum_{j in G} fresh_j (Core §2.1)."""
    if assembly.status != AssemblyStatus.LIVE or not assembly.member_cell_ids:
        return 0.0
    total = sum(fresh_by_cell.get(cid, 0.0) for cid in assembly.member_cell_ids)
    return total / float(len(assembly.member_cell_ids))


def compute_attractor_sigma_support(
    w: WState,
    active_attractors: dict[int, AttractorRuntimeState],
) -> dict[int, float]:
    """Compute sigma_j(t) = rho_s * max_{G ni j} C_G(t-1) from prior event's active Attractors (Core §5)."""
    sigma_by_cell: dict[int, float] = {}
    for aid, att in active_attractors.items():
        if att.strength_c <= 0.0:
            continue
        asm = w.assemblies.get(aid)
        if asm is None or asm.status != AssemblyStatus.LIVE:
            continue
        contrib = RHO_S * att.strength_c
        for cid in asm.member_cell_ids:
            if contrib > sigma_by_cell.get(cid, 0.0):
                sigma_by_cell[cid] = contrib
    return sigma_by_cell


def update_attractors_post_event(
    r: RState,
    w: WState,
    *,
    boundary: bool,
    fresh_by_cell: dict[int, float],
    has_external_input: bool,
    comparable_external_outcome: bool,
    direct_observed_o_by_cell: dict[int, float],
    a_prev_by_cell: dict[int, float],
    f_step_prev: frozenset[int],
) -> dict[int, float]:
    """Update active CONTEXT_ATTRACTOR states for the next event and return M_G^fresh by AssemblyID (Core §2.1).

    Observe collapse precedence: HARD_BOUNDARY > age >= 30 > err > Theta_err (1.50).
    Newly computed C_G(t) contributes only to the next event's sigma.
    """
    m_fresh_by_assembly: dict[int, float] = {}
    for aid, asm in sorted(w.assemblies.items()):
        if asm.status == AssemblyStatus.LIVE:
            m_fresh_by_assembly[aid] = (
                compute_assembly_fresh_mean(asm, fresh_by_cell) if has_external_input else 0.0
            )

    # 1. Collapse precedence 1: HARD_BOUNDARY collapses all existing attractors before aging/refresh
    if boundary:
        r.active_attractors.clear()

    # 2. Age and update existing active attractors
    surviving_attractors: dict[int, AttractorRuntimeState] = {}
    for aid, att in sorted(r.active_attractors.items()):
        asm = w.assemblies.get(aid)
        if asm is None or asm.status != AssemblyStatus.LIVE:
            continue

        # Age increments once per processed event (including internal steps)
        new_age = att.age + 1
        if new_age >= T_MAX_ATTRACTOR:
            # Collapse on age_G >= 30
            continue

        # Update prediction error on externally complete comparable outcomes
        new_err = att.err
        if comparable_external_outcome and not boundary:
            emitter_members = [i for i in asm.member_cell_ids if i in f_step_prev]
            if emitter_members:
                # Collect one-step predictions p_Gj = NoisyOR(A_i(prev) * Q_ij^ASSOC) for i in G \cap F_step(prev)
                preds_by_target: dict[int, list[tuple[int, float]]] = {}
                for src_id in emitter_members:
                    a_src = a_prev_by_cell.get(src_id, 0.0)
                    if a_src <= 0.0:
                        continue
                    for key in w.outgoing_by_source.get(src_id, ()):
                        if key[2] != SynapseScope.ASSOCIATIVE:
                            continue
                        syn = w.synapses[key]
                        q_val = syn.Q
                        if q_val > 0.0:
                            preds_by_target.setdefault(key[1], []).append((src_id, a_src * q_val))

                valid_misses: list[float] = []
                for tgt_j, src_contribs in sorted(preds_by_target.items()):
                    src_contribs.sort(key=lambda item: item[0])
                    p_gj = noisy_or_float64([c[1] for c in src_contribs])
                    if p_gj >= THETA_PRED:
                        o_j = direct_observed_o_by_cell.get(tgt_j, 0.0)
                        valid_misses.append(p_gj * (1.0 - o_j))

                if valid_misses:
                    miss_g = sum(valid_misses) / float(len(valid_misses))
                    new_err = min(THETA_ERR + 1.0, new_err + miss_g)

        if new_err > THETA_ERR:
            # Collapse on err_G > Theta_err = 1.50
            continue

        m_fresh = m_fresh_by_assembly.get(aid, 0.0)
        new_c = max(RHO_S * att.strength_c, m_fresh)
        if new_c > 0.0:
            surviving_attractors[aid] = AttractorRuntimeState(
                assembly_id=aid,
                strength_c=new_c,
                age=new_age,
                err=new_err,
            )

    # 3. Admit newly activating attractors from fresh M_G >= theta_in (0.40) + cohesion >= theta_ctx_form (0.50)
    if has_external_input:
        for aid, m_fresh in sorted(m_fresh_by_assembly.items()):
            if aid in surviving_attractors:
                continue
            if m_fresh >= THETA_IN:
                asm = w.assemblies[aid]
                if compute_assembly_cohesion(asm, w) >= THETA_CTX_FORM:
                    surviving_attractors[aid] = AttractorRuntimeState(
                        assembly_id=aid,
                        strength_c=m_fresh,
                        age=0,
                        err=0.0,
                    )

    r.active_attractors = surviving_attractors
    return m_fresh_by_assembly
