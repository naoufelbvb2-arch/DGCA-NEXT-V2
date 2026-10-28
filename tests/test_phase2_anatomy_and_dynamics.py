"""Unit and contract tests for Phase 2: Core Anatomy, Latent Index, State, Context Gate, and 2-Pass Dynamics."""

from __future__ import annotations

import pytest

from dgca.common import DGCAError, Region, StatusCode, WitnessSourceKind
from dgca.core import (
    Assembly,
    AssemblyStatus,
    BindingStatus,
    CandidatePhase,
    CellState,
    ContextCandidateDescriptor,
    ExecutionMode,
    K_EVIDENCE_ASSOCIATIVE_DELTA1,
    LatentNeighborhoodTable,
    MachineState,
    ParentContextRef,
    StableBinding,
    Synapse,
    SynapseScope,
    SynapseState,
    derive_cell_state,
    execute_two_pass_event,
    get_k_evidence,
    get_k_neural,
)
from dgca.encoder import EventOrigin


def _make_consolidated_synapse(
    src: int,
    tgt: int,
    scope: SynapseScope,
    *,
    s: float = 0.80,
    e_ext: float = 6.0,
    ext_count: int = 3,
) -> Synapse:
    """Helper to construct a legal CONSOLIDATED synapse with Q = s * (e_ext / 10)."""
    return Synapse(
        key=(src, tgt, scope),
        S=s,
        E_ext=e_ext,
        E_int=0.0,
        external_count=ext_count,
        state=SynapseState.CONSOLIDATED,
        confirmed_roots=(1, 2, 3),
    )


class TestFIFRB01AndAnatomy:
    """Verify FIFR-B01 k_neural vs k_evidence split, Dumb Cell states, and Synapse quality."""

    def test_fifr_b01_factors_and_single_link_pt(self) -> None:
        assert get_k_neural(SynapseScope.LOCAL, 0) == 1.0
        assert get_k_neural(SynapseScope.CROSS_TERRITORY, 0) == 1.0
        assert get_k_neural(SynapseScope.ASSOCIATIVE, 1) == 1.0

        assert get_k_evidence(SynapseScope.LOCAL, 0) == 1.0
        assert get_k_evidence(SynapseScope.CROSS_TERRITORY, 0) == 1.0
        assert get_k_evidence(SynapseScope.ASSOCIATIVE, 1) == K_EVIDENCE_ASSOCIATIVE_DELTA1
        assert K_EVIDENCE_ASSOCIATIVE_DELTA1 == 0.7408182206817179

        # Illegal (scope, delta) must reject, never clamp
        with pytest.raises(DGCAError) as exc1:
            get_k_neural(SynapseScope.LOCAL, 1)
        assert exc1.value.code == StatusCode.INVALID_OBSERVATION

        with pytest.raises(DGCAError) as exc2:
            get_k_evidence(SynapseScope.ASSOCIATIVE, 0)
        assert exc2.value.code == StatusCode.INVALID_OBSERVATION

        # Core §13 FIFR-B01 factor: one A=.8, Q=.3 ASSOCIATIVE link => P_T=.24
        state = MachineState()
        src_id, tgt_id = 8200, 8300
        state.W.commit_cell(src_id, 0)
        state.W.commit_cell(tgt_id, 0)
        state.W.latent_table.admit_or_recycle_coactive_partner(src_id, tgt_id)
        # S=0.60, E_ext=5.0 => Q = 0.60 * (5.0 / 10.0) = 0.30
        syn = _make_consolidated_synapse(src_id, tgt_id, SynapseScope.ASSOCIATIVE, s=0.60, e_ext=5.0)
        assert pytest.approx(syn.Q, abs=1e-15) == 0.30
        state.W.add_or_replace_synapse(syn)

        # Freeze prior event with src_id in F_step and A=0.80
        state.R.A = {src_id: 0.80}
        state.R.F_step = frozenset({src_id})

        res = execute_two_pass_event(
            state,
            x_fixed_by_global_id={},
            x_float_by_global_id={},
            mode=ExecutionMode.RETRIEVE,
            origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=False,
            event_order=1,
        )
        assert pytest.approx(res.pt_by_cell[tgt_id], abs=1e-15) == 0.24

    def test_dumb_cell_contract_states(self) -> None:
        assert derive_cell_state(False, 0.0, 0.20) == CellState.UNCOMMITTED
        assert derive_cell_state(True, 0.0, 0.20) == CellState.DORMANT
        assert derive_cell_state(True, 0.199, 0.20) == CellState.DORMANT
        assert derive_cell_state(True, 0.20, 0.20) == CellState.ACTIVE

        with pytest.raises(DGCAError):
            derive_cell_state(False, 0.50, 0.20)


class TestLatentNeighborhoodAndCapacity:
    """Verify 24-slot latent anatomy, D_ij, reverse index, and candidate pin protection (LLA-T07)."""

    def test_24_slots_and_bidirectional_d_ij(self) -> None:
        table = LatentNeighborhoodTable()
        c1, c2 = 8200, 9000
        slots_c1 = table.get_slots(c1)
        assert len(slots_c1) == 24
        # Fixed local (6..11) and topographic (18..23) are populated deterministically
        assert all(slots_c1[i] is not None for i in range(6, 12))
        assert all(slots_c1[i] is not None for i in range(18, 24))

        assert not table.is_eligible(c1, c2)
        slot_idx = table.admit_or_recycle_coactive_partner(c1, c2, event_clock=1)
        assert slot_idx in range(0, 6)
        # Bidirectional eligibility D_ij = 1[j in N(i) or i in N(j)]
        assert table.is_eligible(c1, c2)
        assert table.is_eligible(c2, c1)
        assert c1 in table.reverse_neighbors(c2)

    def test_lla_t07_candidate_pin_blocks_recycling(self) -> None:
        """LLA-T07: Contextual pinned latent slot under recycling raises RECYCLE_BLOCKED_CANDIDATE."""
        table = LatentNeighborhoodTable()
        z_id = 8500
        partners = [8200, 8208, 8216, 8224, 8232, 8240]
        pinned_indices = table.pin_context_candidate_roles(z_id, partners, event_clock=1)
        assert len(pinned_indices) == 6

        # Attempting to recycle any of the 6 intra coactive slots on z_id must fail with RECYCLE_BLOCKED_CANDIDATE
        with pytest.raises(DGCAError) as exc:
            table.admit_or_recycle_coactive_partner(z_id, 8300, event_clock=2)
        assert exc.value.code == StatusCode.RECYCLE_BLOCKED_CANDIDATE

        # After releasing candidate pins, unprotected slots can be recycled
        table.release_candidate_pins(z_id)
        recycled_idx = table.admit_or_recycle_coactive_partner(z_id, 8300, event_clock=3)
        assert recycled_idx == 0
        assert table.is_eligible(z_id, 8300)


class TestTwoPassDynamicsAndFrontiers:
    """Verify first sensory commitment (LLA-T01), residual timeline, R_cold (LLA-T13), and homeostasis."""

    def test_lla_t01_first_sensory_commitment_and_residual_timeline(self) -> None:
        state = MachineState()
        c_a = 8200
        c_b = 8300

        # Event 0: c_a is initially uncommitted; receives X=1.0 in LEARN
        res0 = execute_two_pass_event(
            state,
            x_fixed_by_global_id={c_a: 1_000_000},
            x_float_by_global_id={c_a: 1.0},
            mode=ExecutionMode.LEARN,
            origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=True,
            exposure_id=1,
            event_order=0,
        )
        # c_a was uncommitted before event 0 => OBS_DIRECT is True, OBS_ELIGIBLE is False, not in F_step
        assert c_a in res0.obs_direct_cells
        assert c_a not in res0.obs_eligible_cells
        assert c_a not in res0.f_step
        assert c_a in res0.newly_committed_sensory_cells
        assert state.W.is_committed(c_a)

        # Commit c_b before next exposure
        state.W.commit_cell(c_b, 1)

        # New exposure 2: Event 0 stimulates committed c_a
        state.R.reset_cold()
        res1 = execute_two_pass_event(
            state,
            x_fixed_by_global_id={c_a: 1_000_000},
            x_float_by_global_id={c_a: 1.0},
            mode=ExecutionMode.LEARN,
            origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=True,
            exposure_id=2,
            event_order=0,
        )
        assert c_a in res1.obs_eligible_cells
        assert c_a in res1.f_step
        assert state.R.A[c_a] >= 0.70

        # Event 1 of exposure 2: stimulate c_b only; c_a has residual A = (1 - 0.20) * A_prev > theta_emit,
        # but c_a MUST NOT re-enter F_step(1) from residual alone (Core §6 & §13)!
        res2 = execute_two_pass_event(
            state,
            x_fixed_by_global_id={c_b: 1_000_000},
            x_float_by_global_id={c_b: 1.0},
            mode=ExecutionMode.LEARN,
            origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=False,
            exposure_id=2,
            event_order=1,
        )
        assert state.R.A[c_a] > 0.50  # Residual remains in R.A
        assert c_a not in res2.f_step  # Residual is NOT a new event in F_step!
        assert c_b in res2.f_step


class TestContextualConjunctionAndRoutingRC4_1:
    """Verify RC3.1 calibrated G_z^ctx (LLA-T25, T26, T36, T37) and RC4.1 directed μ_ij (LLA-T27, LG-T15)."""

    def test_lla_t25_t36_t37_calibrated_predecessor_gate(self) -> None:
        state = MachineState()
        p0, p1 = 8200, 8208
        c0, c1 = 8300, 8308
        y0, y1 = 8400, 8408
        z_id = 8500

        for cid in (p0, p1, c0, c1, y0, y1, z_id):
            state.W.commit_cell(cid, 0)
        state.W.latent_table.pin_context_candidate_roles(z_id, [p0, p1, c0, c1, y0, y1])

        # Consolidate P->z, C->z, z->Y links
        for p in (p0, p1):
            state.W.add_or_replace_synapse(
                _make_consolidated_synapse(p, z_id, SynapseScope.ASSOCIATIVE, s=0.85, e_ext=8.0)
            )
        state.W.add_or_replace_synapse(
            _make_consolidated_synapse(c0, z_id, SynapseScope.LOCAL, s=0.85, e_ext=8.0)
        )
        state.W.add_or_replace_synapse(
            _make_consolidated_synapse(z_id, y0, SynapseScope.ASSOCIATIVE, s=0.85, e_ext=8.0)
        )

        # LLA-T37 exact boundary: L_z = 250_000, U_z = 200_000, m_P = 50_000 => tau_ctx_q6 = 250_000
        binding = StableBinding(
            schema_version=2,
            z_cell_id=z_id,
            anchor_id=c0,
            owner_seq=1,
            binding_generation=1,
            p_keys=((p0, z_id, SynapseScope.ASSOCIATIVE), (p1, z_id, SynapseScope.ASSOCIATIVE)),
            l_z_q6=250_000,
            u_z_q6=200_000,
            tau_ctx_q6=250_000,
            c_keys=((c0, z_id, SynapseScope.LOCAL),),
            y_keys=((z_id, y0, SynapseScope.ASSOCIATIVE),),
            anchor_source_set=frozenset({c0, c1}),
        )
        state.W.stable_bindings[z_id] = binding

        # 1. LLA-T25: Cold B-only (strong C->z without P) => G_ctx=0, A_z=0, no z in F_step
        state.R.reset_cold()
        res_b_only = execute_two_pass_event(
            state,
            x_fixed_by_global_id={c0: 1_000_000, c1: 1_000_000},
            x_float_by_global_id={c0: 1.0, c1: 1.0},
            mode=ExecutionMode.RETRIEVE,
            origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=True,
            event_order=0,
        )
        assert res_b_only.g_ctx_by_z[z_id] == 0
        assert res_b_only.a_plus_by_cell.get(z_id, 0.0) == 0.0
        assert z_id not in res_b_only.f_step

        # 2. LLA-T36/T37 Rival P (both P positive at 200_000 < tau=250_000) followed by B => G_ctx=0
        state.R.reset_cold()
        execute_two_pass_event(
            state,
            x_fixed_by_global_id={p0: 200_000, p1: 200_000},
            x_float_by_global_id={p0: 0.20, p1: 0.20},
            mode=ExecutionMode.RETRIEVE,
            origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=True,
            event_order=0,
        )
        res_rival = execute_two_pass_event(
            state,
            x_fixed_by_global_id={c0: 1_000_000, c1: 1_000_000},
            x_float_by_global_id={c0: 1.0, c1: 1.0},
            mode=ExecutionMode.RETRIEVE,
            origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=False,
            event_order=1,
        )
        assert res_rival.g_ctx_by_z[z_id] == 0
        assert res_rival.a_plus_by_cell.get(z_id, 0.0) == 0.0

        # 3. Owned P at exact boundary 250_000 (>= tau=250_000) followed by B => G_ctx=1 and z emits!
        state.R.reset_cold()
        execute_two_pass_event(
            state,
            x_fixed_by_global_id={p0: 250_000, p1: 250_000},
            x_float_by_global_id={p0: 0.25, p1: 0.25},
            mode=ExecutionMode.RETRIEVE,
            origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=True,
            event_order=0,
        )
        res_owned = execute_two_pass_event(
            state,
            x_fixed_by_global_id={c0: 1_000_000, c1: 1_000_000},
            x_float_by_global_id={c0: 1.0, c1: 1.0},
            mode=ExecutionMode.RETRIEVE,
            origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=False,
            event_order=1,
        )
        assert res_owned.g_ctx_by_z[z_id] == 1
        assert z_id in res_owned.f_step
        assert res_owned.mu_source_mask.get(c0, 0) == 0  # c0 has no outgoing ASSOC yet

    def test_lg_t15_rc4_1_target_scoped_routing_preserves_depth2_context_target(self) -> None:
        """LG-T15: Depth-1 z1 masks generic p1->Y_generic (μ_p1,Y=1) while preserving p1->z2 (μ_p1,z2=0)."""
        state = MachineState()
        w1_a, w1_b = 8200, 8208
        p1, c_b2 = 8300, 8308
        y_generic = 8400
        y_ctx1 = 8408
        z1 = 8500
        z2 = 8600
        c_w3 = 8700
        y_ctx2 = 8800

        for cid in (w1_a, w1_b, p1, c_b2, y_generic, y_ctx1, z1, z2, c_w3, y_ctx2):
            state.W.commit_cell(cid, 0)

        # Wire z1 (depth 1): P=(w1_a, w1_b), C=(p1, c_b2), Y=(y_ctx1,)
        state.W.latent_table.pin_context_candidate_roles(z1, [w1_a, w1_b, p1, c_b2, y_ctx1])
        for p in (w1_a, w1_b):
            state.W.add_or_replace_synapse(
                _make_consolidated_synapse(p, z1, SynapseScope.ASSOCIATIVE, s=0.90, e_ext=8.0)
            )
        state.W.add_or_replace_synapse(
            _make_consolidated_synapse(p1, z1, SynapseScope.LOCAL, s=0.90, e_ext=8.0)
        )
        state.W.add_or_replace_synapse(
            _make_consolidated_synapse(z1, y_ctx1, SynapseScope.ASSOCIATIVE, s=0.90, e_ext=8.0)
        )
        state.W.stable_bindings[z1] = StableBinding(
            schema_version=2,
            z_cell_id=z1,
            anchor_id=p1,
            owner_seq=1,
            binding_generation=1,
            p_keys=((w1_a, z1, SynapseScope.ASSOCIATIVE), (w1_b, z1, SynapseScope.ASSOCIATIVE)),
            l_z_q6=800_000,
            u_z_q6=100_000,
            tau_ctx_q6=150_000,
            c_keys=((p1, z1, SynapseScope.LOCAL),),
            y_keys=((z1, y_ctx1, SynapseScope.ASSOCIATIVE),),
            anchor_source_set=frozenset({p1, c_b2}),
        )

        # Generic associative link p1 -> y_generic (strong old link)
        state.W.latent_table.admit_or_recycle_coactive_partner(p1, y_generic)
        state.W.add_or_replace_synapse(
            _make_consolidated_synapse(p1, y_generic, SynapseScope.ASSOCIATIVE, s=0.90, e_ext=8.0)
        )

        # Wire z2 (depth 2): P=(z1, p1), C=(c_w3, c_b2), Y=(y_ctx2, y_generic)
        state.W.latent_table.pin_context_candidate_roles(z2, [z1, p1, c_w3, c_b2, y_ctx2, y_generic])
        state.W.add_or_replace_synapse(
            _make_consolidated_synapse(z1, z2, SynapseScope.ASSOCIATIVE, s=0.90, e_ext=8.0)
        )
        state.W.add_or_replace_synapse(
            _make_consolidated_synapse(p1, z2, SynapseScope.ASSOCIATIVE, s=0.90, e_ext=8.0)
        )
        state.W.add_or_replace_synapse(
            _make_consolidated_synapse(c_w3, z2, SynapseScope.LOCAL, s=0.90, e_ext=8.0)
        )
        state.W.add_or_replace_synapse(
            _make_consolidated_synapse(z2, y_ctx2, SynapseScope.ASSOCIATIVE, s=0.90, e_ext=8.0)
        )
        state.W.stable_bindings[z2] = StableBinding(
            schema_version=3,
            z_cell_id=z2,
            anchor_id=c_w3,
            owner_seq=1,
            binding_generation=1,
            p_keys=((z1, z2, SynapseScope.ASSOCIATIVE), (p1, z2, SynapseScope.ASSOCIATIVE)),
            l_z_q6=500_000,
            u_z_q6=100_000,
            tau_ctx_q6=150_000,
            c_keys=((c_w3, z2, SynapseScope.LOCAL),),
            y_keys=((z2, y_ctx2, SynapseScope.ASSOCIATIVE),),
            anchor_source_set=frozenset({c_w3}),
            depth=2,
            p_source_kinds=(WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT, WitnessSourceKind.DIRECT),
            parent_refs={
                z1: ParentContextRef(
                    parent_z_cell_id=z1,
                    parent_anchor_id=p1,
                    parent_owner_seq=1,
                    parent_binding_generation=1,
                    depth=1,
                )
            },
        )

        # Step 0: observe W1 (w1_a, w1_b)
        state.R.reset_cold()
        execute_two_pass_event(
            state,
            x_fixed_by_global_id={w1_a: 1_000_000, w1_b: 1_000_000},
            x_float_by_global_id={w1_a: 1.0, w1_b: 1.0},
            mode=ExecutionMode.LEARN,
            origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=True,
            exposure_id=10,
            event_order=0,
        )

        # Step 1: observe W2 (p1, c_b2) -> z1 fires and sets mu_p1 = 1!
        res_w2 = execute_two_pass_event(
            state,
            x_fixed_by_global_id={p1: 1_000_000, c_b2: 1_000_000},
            x_float_by_global_id={p1: 1.0, c_b2: 1.0},
            mode=ExecutionMode.LEARN,
            origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=False,
            exposure_id=10,
            event_order=1,
        )
        assert z1 in res_w2.f_step
        assert res_w2.mu_source_mask[p1] == 1
        assert res_w2.typed_supports[z1].origin_kind == "DERIVED_EXTERNAL_CONTEXT"

        # Step 2: observe W3 (c_w3) -> check next-step P_T:
        # Generic p1 -> y_generic is masked (pt_by_cell[y_generic] == 0),
        # while p1 -> z2 is NOT masked (z2 is a ContextTarget, so μ_{p1, z2} = 0),
        # and z2's own G_ctx = 1 fires!
        res_w3 = execute_two_pass_event(
            state,
            x_fixed_by_global_id={c_w3: 1_000_000},
            x_float_by_global_id={c_w3: 1.0},
            mode=ExecutionMode.LEARN,
            origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=False,
            exposure_id=10,
            event_order=2,
        )
        assert res_w3.pt_by_cell.get(y_generic, 0.0) == 0.0
        assert res_w3.pt_by_cell.get(z2, 0.0) > 0.40
        assert res_w3.g_ctx_by_z[z2] == 1
        assert z2 in res_w3.f_step

    def test_lg_t07_pt_debit_selected_in_generate(self) -> None:
        """LG-T07: Selected X_int zeroes P_T on selected receivers only, preserving P_T to context z."""
        state = MachineState()
        src_a = 8200
        rx_j = 8300
        z_ctx = 8500
        for cid in (src_a, rx_j, z_ctx):
            state.W.commit_cell(cid, 0)

        state.W.latent_table.admit_or_recycle_coactive_partner(src_a, rx_j)
        state.W.latent_table.admit_or_recycle_coactive_partner(src_a, z_ctx)
        state.W.add_or_replace_synapse(
            _make_consolidated_synapse(src_a, rx_j, SynapseScope.ASSOCIATIVE, s=0.80, e_ext=6.0)
        )
        state.W.add_or_replace_synapse(
            _make_consolidated_synapse(src_a, z_ctx, SynapseScope.ASSOCIATIVE, s=0.80, e_ext=6.0)
        )
        # Register z_ctx as a candidate so it is a contextual cell
        state.W.context_candidates[z_ctx] = ContextCandidateDescriptor(
            z_cell_id=z_ctx,
            anchor_id=rx_j,
            owner_seq=1,
            p_sources=(src_a, rx_j),
            c_sources=(rx_j, src_a),
            y_targets=(src_a, rx_j),
            l_z_q6=500_000,
            u_z_q6=100_000,
            tau_ctx_q6=150_000,
            anchor_source_set=frozenset({rx_j}),
            phase=CandidatePhase.WIRED,
        )

        state.R.A = {src_a: 0.80}
        state.R.F_step = frozenset({src_a})

        res_gen = execute_two_pass_event(
            state,
            x_fixed_by_global_id={rx_j: 1_000_000},
            x_float_by_global_id={rx_j: 1.0},
            mode=ExecutionMode.GENERATE,
            origin=EventOrigin.INTERNAL_SELECTED,
            boundary=False,
            event_order=1,
            apply_pt_debit_selected=True,
        )
        # P_T to selected receiver rx_j is debited to 0, while P_T to z_ctx is preserved!
        assert res_gen.pt_by_cell.get(rx_j, 0.0) == 0.0
        assert res_gen.pt_by_cell.get(z_ctx, 0.0) > 0.30
