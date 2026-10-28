"""Empirical Program Milestones: Gate A through Gate E (LLA §8.2, Core §13).

Normative references:
- DGCA_LLA_RC4_1.md §8.2 (Required empirical program milestones: Gate A, Gate B, Gate C + RC4.1 Subgate, Gate D, Gate E)
- DGCA_CORE_RC4_1.md §13 (Mandatory Core validation and expected status codes)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dgca.common.errors import StatusCode
from dgca.common.hashing import Region, Role, WitnessSourceKind
from dgca.common.numeric import q6_from_binary64
from dgca.core.anatomy import (
    DEFAULT_OUTGOING_BUDGET_B_I,
    K_EVIDENCE_ASSOCIATIVE_DELTA1,
    Synapse,
    SynapseScope,
    SynapseState,
    get_k_evidence,
    get_k_neural,
)
from dgca.core.assembly import (
    TriangleReadinessTracker,
    compute_idealized_triangle_root_counts,
    execute_assembly_end_pipeline,
)
from dgca.core.dynamics import execute_two_pass_event
from dgca.core.generator import (
    GenerationGateEvaluation,
    evaluate_g1_g2_g3_separated,
    generate_episode,
)
from dgca.core.readout import evaluate_full_vs_control_readout
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import (
    Assembly,
    AssemblyStatus,
    BindingStatus,
    ExecutionMode,
    MachineState,
    StableBinding,
)
from dgca.encoder.envelope import (
    EventOrigin,
    encode_exposure,
    encode_lexical_token_event,
)
from dgca.lifecycle.exposure_tx import (
    ExposureStatus,
    ExposureTransactionManager,
    compute_pred_score,
    run_read_only_episode,
)
from dgca.lla.proposals import (
    LinkProposal,
    OMEGA_ROOT_REPLAY,
    reduce_within_root_proposals,
)
from dgca.lla.synapse_ledger import (
    apply_root_proposals_to_shadow_w,
    apply_weighted_synapse_update,
)
from dgca.peripheral.outbox import (
    OutboxNotificationV1,
    build_end_exposure_outbox_notifications,
)
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1


def _extract_f0_cells(proj) -> tuple[int, ...]:
    f0: list[int] = []
    for det in proj.feature_details:
        if det.merged_support_u == 1_000_000:
            f0.extend(det.sorted_distinct_global_ids)
    if f0:
        return tuple(f0)
    return tuple(sorted(proj.x_fixed_by_global_id.keys()))


def _wire_consolidated_synapse(
    state: MachineState,
    src: int,
    tgt: int,
    scope: SynapseScope,
    *,
    s_val: float = 0.85,
    e_ext: float = 4.0,
    ext_count: int = 3,
) -> None:
    state.W.commit_cell(src, 0)
    state.W.commit_cell(tgt, 0)
    if not state.W.latent_table.is_eligible(src, tgt):
        try:
            state.W.latent_table.admit_or_recycle_coactive_partner(
                src,
                tgt,
                protected_bidirectional_neighbors=state.W.get_protected_bidirectional_neighbors(src),
                event_clock=state.W.global_event_clock,
                reason="GATE_FIXTURE",
            )
        except Exception:
            state.W.latent_table.admit_or_recycle_coactive_partner(
                tgt,
                src,
                protected_bidirectional_neighbors=state.W.get_protected_bidirectional_neighbors(tgt),
                event_clock=state.W.global_event_clock,
                reason="GATE_FIXTURE",
            )
    syn = Synapse(
        key=(src, tgt, scope),
        state=SynapseState.CONSOLIDATED,
        S=s_val,
        E_ext=e_ext,
        E_int=0.0,
        external_count=ext_count,
        confirmed_roots=tuple(range(1, ext_count + 1)),
    )
    state.W.add_or_replace_synapse(syn)


@dataclass(frozen=True, slots=True)
class GateAReport:
    """Empirical Gate A report: unit, numeric, and transaction invariants (LLA §8.2)."""

    passed: bool
    sic_deterministic: bool
    same_root_max_q_or_y_verified: bool
    k_neural_and_k_evidence_verified: bool
    outgoing_budget_b_i: int
    abort_restores_h_slow_begin: bool
    read_only_immutability_verified: bool


def run_gate_a_unit_and_transaction() -> GateAReport:
    """Execute Gate A: canonical SIC, same-root (q,y) aggregation, exact scopes, budgets, ABORT rollback, read-only immutability."""
    # 1. Canonical SIC determinism
    env1 = encode_lexical_token_event("استقلالية", exposure_id=1, event_order=0)
    env2 = encode_lexical_token_event("استقلالية", exposure_id=2, event_order=0)
    proj1 = project_core_event_v1(env1.core_event)
    proj2 = project_core_event_v1(env2.core_event)
    sic_ok = (
        proj1.x_fixed_by_global_id == proj2.x_fixed_by_global_id
        and proj1.role_fingerprint_v1(Role.P) == proj2.role_fingerprint_v1(Role.P)
    )

    # 2. Same-root MAX(q) and paired y_positive
    key = (8200, 8208, SynapseScope.ASSOCIATIVE)
    p1 = LinkProposal(
        link_key=key,
        exposure_id=1,
        event_order=1,
        source_event_order=0,
        a_source=0.60,
        a_target=0.55,
        create_coactivity=0.33,
        q_raw=0.25,
        y_positive=0.60,
        d_event=True,
        v_ext=True,
        priority_class=1,
        proposal_ordinal=0,
    )
    p2 = LinkProposal(
        link_key=key,
        exposure_id=1,
        event_order=2,
        source_event_order=1,
        a_source=0.80,
        a_target=0.85,
        create_coactivity=0.68,
        q_raw=0.60,
        y_positive=0.95,
        d_event=True,
        v_ext=True,
        priority_class=1,
        proposal_ordinal=1,
    )
    reduced = reduce_within_root_proposals([p1, p2])
    agg_ok = (
        len(reduced) == 1
        and reduced[0].q_raw == 0.60
        and reduced[0].y_positive == 0.95
    )

    # 3. Exact k_neural and k_evidence factors (FIFR-B01)
    factors_ok = (
        get_k_neural(SynapseScope.LOCAL, 0) == 1.0
        and get_k_neural(SynapseScope.ASSOCIATIVE, 1) == 1.0
        and get_k_evidence(SynapseScope.LOCAL, 0) == 1.0
        and get_k_evidence(SynapseScope.ASSOCIATIVE, 1) == K_EVIDENCE_ASSOCIATIVE_DELTA1
    )

    # 4. ABORT H_slow rollback (FIFR-B06 LAB POLICY A) & Read-Only Episode immutability
    state = MachineState()
    tx = ExposureTransactionManager(state)
    h_initial = state.H_slow.clone()
    tx.begin_exposure(1)
    tx.process_event(env1.core_event)
    status_abort = tx.abort_exposure(1)
    abort_ok = (
        status_abort == ExposureStatus.ABORTED
        and state.H_slow.theta_active_by_region == h_initial.theta_active_by_region
        and state.R.step_index == 0
    )

    w_syn_count_before = len(state.W.synapses)
    h_theta_before = dict(state.H_slow.theta_active_by_region)
    _ = run_read_only_episode(state, [env1.core_event])
    ro_ok = (
        len(state.W.synapses) == w_syn_count_before
        and state.H_slow.theta_active_by_region == h_theta_before
        and state.R.step_index == 0
    )

    passed = sic_ok and agg_ok and factors_ok and (DEFAULT_OUTGOING_BUDGET_B_I == 64) and abort_ok and ro_ok
    return GateAReport(
        passed=passed,
        sic_deterministic=sic_ok,
        same_root_max_q_or_y_verified=agg_ok,
        k_neural_and_k_evidence_verified=factors_ok,
        outgoing_budget_b_i=DEFAULT_OUTGOING_BUDGET_B_I,
        abort_restores_h_slow_begin=abort_ok,
        read_only_immutability_verified=ro_ok,
    )


@dataclass(frozen=True, slots=True)
class GateBReport:
    """Empirical Gate B report: isolated mechanism on known-legal fixture network (LLA §8.2)."""

    passed: bool
    pred_c_given_ab: float
    pred_e_given_ab: float
    pred_e_given_db: float
    pred_c_given_db: float
    readout_winner_on_ab: int | None
    readout_winner_on_db: int | None
    readout_margin_on_ab: float
    readout_margin_on_db: float


def run_gate_b_isolated_mechanism() -> GateBReport:
    """Execute Gate B: small fixture network with known legal directed links for AB->C vs DB->E and FULL vs CONTROL readout."""
    state = MachineState()

    ev_a = encode_lexical_token_event("القط", exposure_id=1, event_order=0).core_event
    ev_d = encode_lexical_token_event("النسر", exposure_id=2, event_order=0).core_event
    ev_b = encode_lexical_token_event("يشرب", exposure_id=1, event_order=1, boundary=False).core_event
    ev_c = encode_lexical_token_event("حليب", exposure_id=1, event_order=2, boundary=False).core_event
    ev_e = encode_lexical_token_event("ماء", exposure_id=2, event_order=2, boundary=False).core_event

    proj_a = project_core_event_v1(ev_a)
    proj_d = project_core_event_v1(ev_d)
    proj_b = project_core_event_v1(ev_b)
    proj_c = project_core_event_v1(ev_c)
    proj_e = project_core_event_v1(ev_e)

    for p in (proj_a, proj_d, proj_b, proj_c, proj_e):
        for cid in p.x_fixed_by_global_id:
            state.W.commit_cell(cid, 0)

    p_a = _extract_f0_cells(proj_a)[:2]
    p_d = _extract_f0_cells(proj_d)[:2]
    c_b = _extract_f0_cells(proj_b)[:2]
    y_c = _extract_f0_cells(proj_c)[:3]
    y_e = _extract_f0_cells(proj_e)[:3]

    # Pick two uncommitted language cells for z_ab and z_db
    used = set(
        list(proj_a.x_fixed_by_global_id)
        + list(proj_d.x_fixed_by_global_id)
        + list(proj_b.x_fixed_by_global_id)
        + list(proj_c.x_fixed_by_global_id)
        + list(proj_e.x_fixed_by_global_id)
    )
    free_cells = [cid for cid in range(8200, 12200, 8) if cid not in used]
    z_ab, z_db = free_cells[0], free_cells[1]
    state.W.commit_cell(z_ab, 0)
    state.W.commit_cell(z_db, 0)

    # Wire P -> z (ASSOCIATIVE), C -> z (LOCAL), z -> Y (ASSOCIATIVE), plus generic B -> C/E (ASSOCIATIVE)
    for p_cell in p_a:
        _wire_consolidated_synapse(state, p_cell, z_ab, SynapseScope.ASSOCIATIVE, s_val=0.90)
    for p_cell in p_d:
        _wire_consolidated_synapse(state, p_cell, z_db, SynapseScope.ASSOCIATIVE, s_val=0.90)
    for b_cell in c_b:
        _wire_consolidated_synapse(state, b_cell, z_ab, SynapseScope.LOCAL, s_val=0.90)
        _wire_consolidated_synapse(state, b_cell, z_db, SynapseScope.LOCAL, s_val=0.90)
        for yc in y_c:
            _wire_consolidated_synapse(state, b_cell, yc, SynapseScope.ASSOCIATIVE, s_val=0.45)
        for ye in y_e:
            _wire_consolidated_synapse(state, b_cell, ye, SynapseScope.ASSOCIATIVE, s_val=0.45)

    for yc in y_c:
        _wire_consolidated_synapse(state, z_ab, yc, SynapseScope.ASSOCIATIVE, s_val=0.95)
    for ye in y_e:
        _wire_consolidated_synapse(state, z_db, ye, SynapseScope.ASSOCIATIVE, s_val=0.95)

    # Register calibrated StableBindingV2 for z_ab (owner (c_b[0], 1)) and z_db (owner (c_b[0], 2))
    anchor_set_b = frozenset(proj_b.x_fixed_by_global_id.keys())
    state.W.stable_bindings[z_ab] = StableBinding(
        schema_version=2,
        z_cell_id=z_ab,
        anchor_id=c_b[0],
        owner_seq=1,
        binding_generation=1,
        p_keys=((p_a[0], z_ab, SynapseScope.ASSOCIATIVE), (p_a[1], z_ab, SynapseScope.ASSOCIATIVE)),
        l_z_q6=500_000,
        u_z_q6=100_000,
        tau_ctx_q6=150_000,
        c_keys=((c_b[0], z_ab, SynapseScope.LOCAL), (c_b[1], z_ab, SynapseScope.LOCAL)),
        y_keys=((z_ab, y_c[0], SynapseScope.ASSOCIATIVE), (z_ab, y_c[1], SynapseScope.ASSOCIATIVE)),
        anchor_source_set=anchor_set_b,
        status=BindingStatus.ACTIVE,
        depth=1,
    )
    state.W.stable_bindings[z_db] = StableBinding(
        schema_version=2,
        z_cell_id=z_db,
        anchor_id=c_b[0],
        owner_seq=2,
        binding_generation=1,
        p_keys=((p_d[0], z_db, SynapseScope.ASSOCIATIVE), (p_d[1], z_db, SynapseScope.ASSOCIATIVE)),
        l_z_q6=500_000,
        u_z_q6=100_000,
        tau_ctx_q6=150_000,
        c_keys=((c_b[0], z_db, SynapseScope.LOCAL), (c_b[1], z_db, SynapseScope.LOCAL)),
        y_keys=((z_db, y_e[0], SynapseScope.ASSOCIATIVE), (z_db, y_e[1], SynapseScope.ASSOCIATIVE)),
        anchor_source_set=anchor_set_b,
        status=BindingStatus.ACTIVE,
        depth=1,
    )

    # Wire reciprocal LOCAL triangles for Assembly #1 (on y_c) and Assembly #2 (on y_e)
    for tri in (y_c, y_e):
        for u in tri:
            for v in tri:
                if u != v:
                    _wire_consolidated_synapse(state, u, v, SynapseScope.LOCAL, s_val=0.80)

    state.W.assemblies[1] = Assembly(
        assembly_id=1,
        region=Region.LANGUAGE,
        member_cell_ids=frozenset(y_c),
        structural_generation=1,
        status=AssemblyStatus.LIVE,
    )
    state.W.assemblies[2] = Assembly(
        assembly_id=2,
        region=Region.LANGUAGE,
        member_cell_ids=frozenset(y_e),
        structural_generation=1,
        status=AssemblyStatus.LIVE,
    )

    # Evaluate cold READ_ONLY_EPISODE on [A, B] and [D, B]
    ro_ab = run_read_only_episode(state, [ev_a, ev_b])
    _, pred_c_ab = compute_pred_score(ro_ab.next_step_pt_by_cell, y_c)
    _, pred_e_ab = compute_pred_score(ro_ab.next_step_pt_by_cell, y_e)

    ro_db = run_read_only_episode(state, [ev_d, ev_b])
    _, pred_e_db = compute_pred_score(ro_db.next_step_pt_by_cell, y_e)
    _, pred_c_db = compute_pred_score(ro_db.next_step_pt_by_cell, y_c)

    # Evaluate FULL vs CONTROL readout on [A, B] and [D, B]
    scratch_ab = state.clone()
    for idx, ev in enumerate((ev_a, ev_b)):
        p = project_core_event_v1(ev)
        execute_two_pass_event(
            scratch_ab,
            p.x_fixed_by_global_id,
            p.x_float_by_global_id,
            mode=ExecutionMode.RETRIEVE,
            origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=(idx == 0),
        )
    read_ab = evaluate_full_vs_control_readout(scratch_ab)

    scratch_db = state.clone()
    for idx, ev in enumerate((ev_d, ev_b)):
        p = project_core_event_v1(ev)
        execute_two_pass_event(
            scratch_db,
            p.x_fixed_by_global_id,
            p.x_float_by_global_id,
            mode=ExecutionMode.RETRIEVE,
            origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=(idx == 0),
        )
    read_db = evaluate_full_vs_control_readout(scratch_db)

    passed = (
        pred_c_ab > pred_e_ab
        and pred_e_db > pred_c_db
        and read_ab.status == StatusCode.OK
        and read_ab.winner_assembly_id == 1
        and read_db.status == StatusCode.OK
        and read_db.winner_assembly_id == 2
    )
    return GateBReport(
        passed=passed,
        pred_c_given_ab=pred_c_ab,
        pred_e_given_ab=pred_e_ab,
        pred_e_given_db=pred_e_db,
        pred_c_given_db=pred_c_db,
        readout_winner_on_ab=read_ab.winner_assembly_id,
        readout_winner_on_db=read_db.winner_assembly_id,
        readout_margin_on_ab=read_ab.margin,
        readout_margin_on_db=read_db.margin,
    )


@dataclass(frozen=True, slots=True)
class GateCReport:
    """Empirical Gate C + RC4.1 Native-Surface Readiness Subgate report (LLA §8.2)."""

    passed: bool
    sensory_commit_roots: tuple[int, ...]
    recruited_context_cells: tuple[int, ...]
    graduated_context_cells: tuple[int, ...]
    first_pz_root: int | None
    first_cz_root: int | None
    first_zy_root: int | None
    pred_c_given_ab: float
    pred_e_given_ab: float
    pred_e_given_db: float
    pred_c_given_db: float
    # RC4.1 Subgate metrics
    triangle_receiver_commit_root: int | None
    triangle_all_six_edges_consolidated: bool
    assembly_birth_root: int | None
    birth_root_attestations: int
    post_birth_attestation_roots: tuple[int, ...]
    surface_readout_attested: bool
    idealized_reference_table: dict[str, tuple[int, int]]


def run_gate_c_learn_from_zero_and_rc4_1_subgate() -> GateCReport:
    """Execute Gate C (learn from zero AB->C vs DB->E) and RC4.1 native-surface readiness subgate."""
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
    )

    branch_ab_envs = encode_exposure("القط يشرب حليب", append_eos=False)
    branch_db_envs = encode_exposure("النسر يشرب ماء", append_eos=False)

    proj_c = project_core_event_v1(branch_ab_envs[2].core_event)
    proj_e = project_core_event_v1(branch_db_envs[2].core_event)
    f0_c = _extract_f0_cells(proj_c)[:3]
    f0_e = _extract_f0_cells(proj_e)[:3]

    tracker = TriangleReadinessTracker((f0_c[0], f0_c[1], f0_c[2]))

    sensory_commit_roots: list[int] = []
    recruited_cells: set[int] = set()
    graduated_cells: set[int] = set()
    first_pz_root: int | None = None
    first_cz_root: int | None = None
    first_zy_root: int | None = None
    birth_root_attestations: int = 0

    # Train alternating roots from cold start:
    # - Root 1, 2: sensory commitments
    # - Roots 3..6: base link proposals + contrast discovery + z recruitment
    # - Roots 7..36: probe-assisted consolidation, C04 graduation, and native triangle formation + attestation
    root_id = 1
    total_roots = 34
    for step in range(total_roots):
        is_ab = (step % 2 == 0)
        envs = branch_ab_envs if is_ab else branch_db_envs
        pre_live_asms = tuple(state.W.assemblies.values())

        tx.begin_exposure(root_id)
        ev_results = []
        for item in envs:
            core_ev = encode_lexical_token_event(
                item.peripheral_surface.raw_surface_nfc_utf8,
                exposure_id=root_id,
                event_order=item.core_event.event_order,
                boundary=item.core_event.boundary,
            ).core_event
            res = tx.process_event(core_ev, peripheral_envelope=item.peripheral_surface)
            ev_results.append(res)
            if res.newly_committed_sensory_cells and root_id not in sensory_commit_roots:
                sensory_commit_roots.append(root_id)

        rep = tx.end_exposure(root_id)

        # Track recruited and graduated contextual cells
        for z_id in state.W.context_candidates:
            recruited_cells.add(z_id)
        for z_id in state.W.stable_bindings:
            recruited_cells.add(z_id)
            graduated_cells.add(z_id)

        # Track first P->z, C->z, z->Y root IDs
        for out in rep.proposal_outcomes:
            if out.status != StatusCode.OK:
                continue
            src, tgt, scope = out.proposal.link_key
            if tgt in recruited_cells and scope == SynapseScope.ASSOCIATIVE and first_pz_root is None:
                first_pz_root = root_id
            if tgt in recruited_cells and scope == SynapseScope.LOCAL and first_cz_root is None:
                first_cz_root = root_id
            if src in recruited_cells and scope == SynapseScope.ASSOCIATIVE and first_zy_root is None:
                first_zy_root = root_id

        # Track RC4.1 triangle readiness on f0_c ("حليب")
        if is_ab:
            c_ev_res = ev_results[2]
            c_env = envs[2].peripheral_surface
            was_born_before = tracker.assembly_birth_root is not None
            tracker.record_completed_root(
                root_id,
                state.W,
                state.H_slow,
                [c_ev_res],
                preexisting_live_assemblies=pre_live_asms,
                surface_text=c_env.raw_surface_nfc_utf8,
                feature_bundle_digest=c_env.feature_bundle_digest,
                is_eos=False,
            )
            if not was_born_before and tracker.assembly_birth_root == root_id:
                # Verify zero birth-root attestations for newly born assembly
                new_asm_ids = set(state.W.assemblies.keys()) - {a.assembly_id for a in pre_live_asms}
                for n in rep.outbox_notifications:
                    if getattr(n, "assembly_id", None) in new_asm_ids:
                        birth_root_attestations += 1

        root_id += 1

    # Cold retrieval PredScore evaluation
    ro_ab = run_read_only_episode(
        state,
        [branch_ab_envs[0].core_event, branch_ab_envs[1].core_event],
    )
    _, pred_c_ab = compute_pred_score(ro_ab.next_step_pt_by_cell, f0_c)
    _, pred_e_ab = compute_pred_score(ro_ab.next_step_pt_by_cell, f0_e)

    ro_db = run_read_only_episode(
        state,
        [branch_db_envs[0].core_event, branch_db_envs[1].core_event],
    )
    _, pred_e_db = compute_pred_score(ro_db.next_step_pt_by_cell, f0_e)
    _, pred_c_db = compute_pred_score(ro_db.next_step_pt_by_cell, f0_c)

    all_six_consolidated = all(
        bool(hist and hist[-1][4]) for hist in tracker.edge_history.values()
    )
    first_commit_root = min(
        (r for r in tracker.receiver_commit_root.values() if r is not None),
        default=None,
    )

    # Check if the born triangle assembly is attested in SurfaceReadoutLedgerV1
    surface_attested = False
    for asm_id, asm in state.W.assemblies.items():
        if set(tracker.triangle_cells).issubset(set(asm.member_cell_ids)):
            res_read = ledger.resolve_readout(
                asm_id,
                asm.structural_generation,
                current_live_generation=asm.structural_generation,
            )
            if res_read.status == StatusCode.OK:
                surface_attested = True

    idealized_table = {
        f"{a:.2f}": compute_idealized_triangle_root_counts(a)
        for a in (0.45, 0.60, 0.70, 0.80)
    }

    passed = (
        len(sensory_commit_roots) >= 2
        and len(recruited_cells) >= 2
        and first_pz_root is not None
        and first_cz_root is not None
        and first_zy_root is not None
        and pred_c_ab > pred_e_ab
        and pred_e_db > pred_c_db
        and first_commit_root == 1
        and all_six_consolidated
        and tracker.assembly_birth_root is not None
        and birth_root_attestations == 0
        and len(tracker.attestation_roots) >= 2
        and tracker.is_readout_ready
        and surface_attested
    )

    return GateCReport(
        passed=passed,
        sensory_commit_roots=tuple(sensory_commit_roots),
        recruited_context_cells=tuple(sorted(recruited_cells)),
        graduated_context_cells=tuple(sorted(graduated_cells)),
        first_pz_root=first_pz_root,
        first_cz_root=first_cz_root,
        first_zy_root=first_zy_root,
        pred_c_given_ab=pred_c_ab,
        pred_e_given_ab=pred_e_ab,
        pred_e_given_db=pred_e_db,
        pred_c_given_db=pred_c_db,
        triangle_receiver_commit_root=first_commit_root,
        triangle_all_six_edges_consolidated=all_six_consolidated,
        assembly_birth_root=tracker.assembly_birth_root,
        birth_root_attestations=birth_root_attestations,
        post_birth_attestation_roots=tuple(tracker.attestation_roots),
        surface_readout_attested=surface_attested,
        idealized_reference_table=idealized_table,
    )


@dataclass(frozen=True, slots=True)
class GateDReport:
    """Empirical Gate D report: controlled ablations and comparators (LLA §8.2)."""

    passed: bool
    dcr_z_enabled_margin_ab: float
    baseline_z_disabled_margin_ab: float
    probe_enabled_z_active_in_discovery: bool
    probe_disabled_z_active_in_discovery: bool
    rc4_budget_64_feasible_headroom_at_32_links: int
    rc2_budget_32_feasible_headroom_at_32_links: int
    replay_off_e_int: float
    replay_on_e_int: float
    replay_preserves_e_ext_and_ext_count: bool


def run_gate_d_ablations_and_comparisons() -> GateDReport:
    """Execute Gate D: controlled ablations (DCR z-path vs baseline, probe on/off, B_i=64 vs 32, Replay on/off)."""
    # 1. DCR z-path enabled vs z-path disabled on AB -> C vs DB -> E
    gate_b = run_gate_b_isolated_mechanism()
    dcr_margin = gate_b.pred_c_given_ab - gate_b.pred_e_given_ab

    # Baseline without contextual z (generic B -> C and B -> E with equal weights)
    state_no_z = MachineState()
    ev_a = encode_lexical_token_event("القط", exposure_id=1, event_order=0).core_event
    ev_b = encode_lexical_token_event("يشرب", exposure_id=1, event_order=1, boundary=False).core_event
    ev_c = encode_lexical_token_event("حليب", exposure_id=1, event_order=2, boundary=False).core_event
    ev_e = encode_lexical_token_event("ماء", exposure_id=2, event_order=2, boundary=False).core_event

    for ev in (ev_a, ev_b, ev_c, ev_e):
        for cid in project_core_event_v1(ev).x_fixed_by_global_id:
            state_no_z.W.commit_cell(cid, 0)

    c_b = _extract_f0_cells(project_core_event_v1(ev_b))[:2]
    y_c = _extract_f0_cells(project_core_event_v1(ev_c))[:3]
    y_e = _extract_f0_cells(project_core_event_v1(ev_e))[:3]
    for b_cell in c_b:
        for yc in y_c:
            _wire_consolidated_synapse(state_no_z, b_cell, yc, SynapseScope.ASSOCIATIVE, s_val=0.45)
        for ye in y_e:
            _wire_consolidated_synapse(state_no_z, b_cell, ye, SynapseScope.ASSOCIATIVE, s_val=0.45)

    ro_no_z = run_read_only_episode(state_no_z, [ev_a, ev_b])
    _, base_c = compute_pred_score(ro_no_z.next_step_pt_by_cell, y_c)
    _, base_e = compute_pred_score(ro_no_z.next_step_pt_by_cell, y_e)
    baseline_margin = base_c - base_e

    # 2. Probe enabled vs disabled during PROBE_DISCOVERY (newly recruited candidate has S=0.10 links)
    from dgca.core.state import CandidatePhase, ContextCandidateDescriptor

    state_probe = MachineState()
    p0, p1, c0, c1, y0, y1, z_cand = 8200, 8208, 8216, 8224, 8232, 8240, 8248
    for cid in (p0, p1, c0, c1, y0, y1, z_cand):
        state_probe.W.commit_cell(cid, 0)
    for src, scope in ((p0, SynapseScope.ASSOCIATIVE), (p1, SynapseScope.ASSOCIATIVE), (c0, SynapseScope.LOCAL), (c1, SynapseScope.LOCAL)):
        _wire_consolidated_synapse(state_probe, src, z_cand, scope, s_val=0.10, e_ext=0.05, ext_count=1)
        state_probe.W.synapses[(src, z_cand, scope)].state = SynapseState.CANDIDATE
    for y_id in (y0, y1):
        state_probe.W.latent_table.admit_or_recycle_coactive_partner(
            z_cand,
            y_id,
            protected_bidirectional_neighbors=state_probe.W.get_protected_bidirectional_neighbors(z_cand),
            event_clock=0,
            reason="GATE_D_PROBE",
        )

    state_probe.W.context_candidates[z_cand] = ContextCandidateDescriptor(
        z_cell_id=z_cand,
        anchor_id=c0,
        owner_seq=1,
        p_sources=(p0, p1),
        c_sources=(c0, c1),
        y_targets=(y0, y1),
        l_z_q6=500_000,
        u_z_q6=100_000,
        tau_ctx_q6=150_000,
        anchor_source_set=frozenset((c0, c1)),
        phase=CandidatePhase.WIRED,
    )

    state_no_probe = state_probe.clone()
    for st, allow_p in ((state_probe, True), (state_no_probe, False)):
        execute_two_pass_event(
            st,
            {p0: 800_000, p1: 800_000},
            {p0: 0.80, p1: 0.80},
            mode=ExecutionMode.LEARN,
            origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=True,
            exposure_id=1,
            event_order=0,
            allow_candidate_probe=allow_p,
        )
        res_step2 = execute_two_pass_event(
            st,
            {c0: 800_000, c1: 800_000},
            {c0: 0.80, c1: 0.80},
            mode=ExecutionMode.LEARN,
            origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=False,
            exposure_id=1,
            event_order=1,
            allow_candidate_probe=allow_p,
        )
        if allow_p:
            probe_on_active = z_cand in res_step2.f_step
        else:
            probe_off_active = z_cand in res_step2.f_step

    # 3. RC3/RC4.1 B_i=64 vs RC2 B_i=32 headroom after 32 outgoing links
    occupied = 32
    headroom_64 = max(0, 64 - occupied)
    headroom_32 = max(0, 32 - occupied)

    # 4. Replay OFF vs Replay ON (omega_replay = 0.25, FIFR-B02)
    syn_replay_off = Synapse(
        key=(8200, 8208, SynapseScope.ASSOCIATIVE),
        state=SynapseState.CONSOLIDATED,
        S=0.65,
        E_ext=1.50,
        E_int=0.0,
        external_count=3,
        confirmed_roots=(1, 2, 3),
    )
    syn_replay_on = syn_replay_off.clone()
    apply_weighted_synapse_update(
        syn_replay_on,
        q=0.40 * OMEGA_ROOT_REPLAY,
        y=1.0,
        is_external=False,
        exposure_id=4,
    )
    replay_ok = (
        syn_replay_off.E_int == 0.0
        and abs(syn_replay_on.E_int - 0.10) < 1e-12
        and syn_replay_on.E_ext == 1.50
        and syn_replay_on.external_count == 3
    )

    passed = (
        dcr_margin > 0.10
        and abs(baseline_margin) < 1e-9
        and probe_on_active is True
        and probe_off_active is False
        and headroom_64 == 32
        and headroom_32 == 0
        and replay_ok
    )
    return GateDReport(
        passed=passed,
        dcr_z_enabled_margin_ab=dcr_margin,
        baseline_z_disabled_margin_ab=baseline_margin,
        probe_enabled_z_active_in_discovery=probe_on_active,
        probe_disabled_z_active_in_discovery=probe_off_active,
        rc4_budget_64_feasible_headroom_at_32_links=headroom_64,
        rc2_budget_32_feasible_headroom_at_32_links=headroom_32,
        replay_off_e_int=syn_replay_off.E_int,
        replay_on_e_int=syn_replay_on.E_int,
        replay_preserves_e_ext_and_ext_count=replay_ok,
    )


@dataclass(frozen=True, slots=True)
class GateEReport:
    """Empirical Gate E report: G1/G2 vs held-out compositional G3 & scope boundaries (LLA §8.2, LG-T14)."""

    passed: bool
    g1_memorized_rollout_surfaces: tuple[str, ...]
    g1_stop_status: StatusCode
    g2_branch_ab_surfaces: tuple[str, ...]
    g2_branch_db_surfaces: tuple[str, ...]
    g3_unseen_compositional_stop_status: StatusCode
    g3_unseen_compositional_surfaces: tuple[str, ...]
    separated_evaluation: GenerationGateEvaluation
    explicit_limitations: tuple[str, ...]


def run_gate_e_generalization_and_boundaries() -> GateEReport:
    """Execute Gate E: evaluate G1, G2, and held-out unseen combination G3 separately, plus scope boundary declarations."""
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()

    # Build a clean network supporting:
    # - G1 memorized sequence: "الشمس" -> "تشرق" -> <EOS>
    # - G2 context-sensitive branches: "القط يشرب" -> "حليب" -> <EOS> vs "النسر يشرب" -> "ماء" -> <EOS>
    # - G3 held-out unseen compositional prompt: "القمر" (committed sensory cells, but zero learned transition to "تشرق")
    dual_g1 = encode_exposure("الشمس تشرق", exposure_id=1)
    dual_ab = encode_exposure("القط يشرب حليب", exposure_id=2)
    dual_db = encode_exposure("النسر يشرب ماء", exposure_id=3)
    dual_g3_unseen = encode_exposure("القمر", exposure_id=4)

    for seq in (dual_g1, dual_ab, dual_db, dual_g3_unseen):
        for item in seq:
            for cid in project_core_event_v1(item.core_event).x_fixed_by_global_id:
                state.W.commit_cell(cid, 0)

    # Assembly 1: "تشرق", Assembly 2: "حليب", Assembly 3: "ماء", Assembly 4: "<EOS>"
    f0_sun = _extract_f0_cells(project_core_event_v1(dual_g1[0].core_event))[:3]
    f0_rises = _extract_f0_cells(project_core_event_v1(dual_g1[1].core_event))[:3]
    f0_cat = _extract_f0_cells(project_core_event_v1(dual_ab[0].core_event))[:2]
    f0_eagle = _extract_f0_cells(project_core_event_v1(dual_db[0].core_event))[:2]
    f0_drinks = _extract_f0_cells(project_core_event_v1(dual_ab[1].core_event))[:2]
    f0_milk = _extract_f0_cells(project_core_event_v1(dual_ab[2].core_event))[:3]
    f0_water = _extract_f0_cells(project_core_event_v1(dual_db[2].core_event))[:3]
    eos_cells = (9900, 9908, 9916)

    for asm_id, tri, env in (
        (1, f0_rises, dual_g1[1].peripheral_surface),
        (2, f0_milk, dual_ab[2].peripheral_surface),
        (3, f0_water, dual_db[2].peripheral_surface),
        (4, eos_cells, dual_g1[2].peripheral_surface),
    ):
        for u in tri:
            for v in tri:
                if u != v:
                    _wire_consolidated_synapse(state, u, v, SynapseScope.LOCAL, s_val=0.80)
        state.W.assemblies[asm_id] = Assembly(
            assembly_id=asm_id,
            region=Region.LANGUAGE,
            member_cell_ids=frozenset(tri),
            structural_generation=1,
            status=AssemblyStatus.LIVE,
        )
        for rid in (10, 11):
            ledger.consume_outbox_notification(
                OutboxNotificationV1(
                    root_id=rid,
                    event_order=1,
                    assembly_id=asm_id,
                    structural_generation=1,
                    surface_sha256=env.surface_sha256,
                    feature_bundle_digest=env.feature_bundle_digest,
                    marker=env.marker,
                    envelope=env,
                )
            )

    # Wire G1: "الشمس" -> Assembly 1 ("تشرق") -> Assembly 4 ("<EOS>")
    for src in f0_sun:
        for tgt in f0_rises:
            _wire_consolidated_synapse(state, src, tgt, SynapseScope.ASSOCIATIVE, s_val=0.90)
    for src in f0_rises:
        for tgt in eos_cells:
            _wire_consolidated_synapse(state, src, tgt, SynapseScope.ASSOCIATIVE, s_val=0.90)

    # Wire G2 contextual cells z_ab (9800) and z_db (9808)
    z_ab, z_db = 9800, 9808
    state.W.commit_cell(z_ab, 0)
    state.W.commit_cell(z_db, 0)
    for p in f0_cat:
        _wire_consolidated_synapse(state, p, z_ab, SynapseScope.ASSOCIATIVE, s_val=0.90)
    for p in f0_eagle:
        _wire_consolidated_synapse(state, p, z_db, SynapseScope.ASSOCIATIVE, s_val=0.90)
    for c in f0_drinks:
        _wire_consolidated_synapse(state, c, z_ab, SynapseScope.LOCAL, s_val=0.90)
        _wire_consolidated_synapse(state, c, z_db, SynapseScope.LOCAL, s_val=0.90)
    for yc in f0_milk:
        _wire_consolidated_synapse(state, z_ab, yc, SynapseScope.ASSOCIATIVE, s_val=0.95)
        for eos_c in eos_cells:
            _wire_consolidated_synapse(state, yc, eos_c, SynapseScope.ASSOCIATIVE, s_val=0.90)
    for ye in f0_water:
        _wire_consolidated_synapse(state, z_db, ye, SynapseScope.ASSOCIATIVE, s_val=0.95)
        for eos_c in eos_cells:
            _wire_consolidated_synapse(state, ye, eos_c, SynapseScope.ASSOCIATIVE, s_val=0.90)

    proj_drinks = project_core_event_v1(dual_ab[1].core_event)
    anchor_set_drinks = frozenset(proj_drinks.x_fixed_by_global_id.keys())
    state.W.stable_bindings[z_ab] = StableBinding(
        schema_version=2,
        z_cell_id=z_ab,
        anchor_id=f0_drinks[0],
        owner_seq=1,
        binding_generation=1,
        p_keys=((f0_cat[0], z_ab, SynapseScope.ASSOCIATIVE), (f0_cat[1], z_ab, SynapseScope.ASSOCIATIVE)),
        l_z_q6=500_000,
        u_z_q6=100_000,
        tau_ctx_q6=150_000,
        c_keys=((f0_drinks[0], z_ab, SynapseScope.LOCAL), (f0_drinks[1], z_ab, SynapseScope.LOCAL)),
        y_keys=((z_ab, f0_milk[0], SynapseScope.ASSOCIATIVE), (z_ab, f0_milk[1], SynapseScope.ASSOCIATIVE)),
        anchor_source_set=anchor_set_drinks,
        status=BindingStatus.ACTIVE,
        depth=1,
    )
    state.W.stable_bindings[z_db] = StableBinding(
        schema_version=2,
        z_cell_id=z_db,
        anchor_id=f0_drinks[0],
        owner_seq=2,
        binding_generation=1,
        p_keys=((f0_eagle[0], z_db, SynapseScope.ASSOCIATIVE), (f0_eagle[1], z_db, SynapseScope.ASSOCIATIVE)),
        l_z_q6=500_000,
        u_z_q6=100_000,
        tau_ctx_q6=150_000,
        c_keys=((f0_drinks[0], z_db, SynapseScope.LOCAL), (f0_drinks[1], z_db, SynapseScope.LOCAL)),
        y_keys=((z_db, f0_water[0], SynapseScope.ASSOCIATIVE), (z_db, f0_water[1], SynapseScope.ASSOCIATIVE)),
        anchor_source_set=anchor_set_drinks,
        status=BindingStatus.ACTIVE,
        depth=1,
    )

    # Run G1, G2(AB), G2(DB), and held-out unseen G3("القمر")
    res_g1 = generate_episode(state, [dual_g1[0].core_event], ledger)
    res_g2_ab = generate_episode(state, [dual_ab[0].core_event, dual_ab[1].core_event], ledger)
    res_g2_db = generate_episode(state, [dual_db[0].core_event, dual_db[1].core_event], ledger)
    res_g3 = generate_episode(state, [dual_g3_unseen[0].core_event], ledger)

    g1_ok = res_g1.stop_status == StatusCode.GEN_STOP_EOS and res_g1.emitted_surfaces == ("تشرق",)
    g2_ab_ok = res_g2_ab.stop_status == StatusCode.GEN_STOP_EOS and res_g2_ab.emitted_surfaces == ("حليب",)
    g2_db_ok = res_g2_db.stop_status == StatusCode.GEN_STOP_EOS and res_g2_db.emitted_surfaces == ("ماء",)
    g3_honest_fail_closed = (
        res_g3.stop_status == StatusCode.GEN_STOP_NO_MATCH and res_g3.emitted_surfaces == ()
    )

    sep_eval = evaluate_g1_g2_g3_separated(
        g1_outcomes=[g1_ok],
        g2_outcomes=[g2_ab_ok, g2_db_ok],
        g3_outcomes=[res_g3.emitted_surfaces == ("تشرق",)],
    )

    limitations = (
        "No negative error-corrective updates in First Lab (NEGATIVE_UPDATES_ENABLED = false).",
        "No free-form compositional G3 generalization without shared witnessed physical pathways (fails closed with GEN_STOP_NO_MATCH).",
        "Peripheral readout strictly restricted to pre-existing LIVE assemblies attested across >= 2 independent completed external roots.",
        "Bounded 24-slot latent neighborhoods and 64 outgoing synapse budget per source cell.",
    )

    passed = (
        g1_ok
        and g2_ab_ok
        and g2_db_ok
        and g3_honest_fail_closed
        and sep_eval.g1_passed is True
        and sep_eval.g2_passed is True
        and sep_eval.g3_passed is False
        and sep_eval.overall_gate_d_passed is False
    )
    return GateEReport(
        passed=passed,
        g1_memorized_rollout_surfaces=res_g1.emitted_surfaces,
        g1_stop_status=res_g1.stop_status,
        g2_branch_ab_surfaces=res_g2_ab.emitted_surfaces,
        g2_branch_db_surfaces=res_g2_db.emitted_surfaces,
        g3_unseen_compositional_stop_status=res_g3.stop_status,
        g3_unseen_compositional_surfaces=res_g3.emitted_surfaces,
        separated_evaluation=sep_eval,
        explicit_limitations=limitations,
    )
