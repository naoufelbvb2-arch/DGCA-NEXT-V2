"""Phase 5 Verification Suite: Hierarchical Derived Contexts (Depth <= 8) & Native Assembly Operators.

Covers normative test gates from DGCA_CORE_RC4_1.md & DGCA_LLA_RC4_1.md:
- LG-T01: Reciprocal CONSOLIDATED LOCAL triangle (R >= 0.10) forms size-3 Assembly; K_FORM_PER_END=12 cap
- LG-T02: One-direction consolidated or non-consolidated triangle yields NO_RECIPROCAL_TRIANGLE (0 assemblies)
- LG-T03: MAINTAIN, GROW, MERGE, SPLIT operators, generation increments, T_c=200 cooldown, non-reused IDs
- LG-T04: Depth-2 DERIVED_EXTERNAL_CONTEXT admission (OwnerProfileV2, FP-ROLE-V2, StableBindingV3) & single root q credit
- LG-T05: Probe-supported or non-external (RETRIEVE/GENERATE/REPLAY) z1 cannot emit DERIVED_EXTERNAL_CONTEXT
- LG-T06: Depth-8 bound (9th level -> CONTEXT_CHAIN_DEPTH_EXCEEDED), stale parent, cycle rejection, no fallback to DIRECT
- LG-T13: Direct-only z1, wrong prior event order, or synthetic unverified source rejected (DERIVED_PROVENANCE_UNVERIFIED)
- LG-T16: Gate C / RC4.1 native-surface readiness subgate (idealized 15/9/7/5 post-commit & 18/12/10/8 cold totals, 0 birth-root attestations, 2 post-birth roots)
"""

from __future__ import annotations

import pytest

from dgca.common.errors import StatusCode
from dgca.common.hashing import Region, WitnessSourceKind
from dgca.common.numeric import MILLION, q6_from_binary64
from dgca.core.anatomy import Synapse, SynapseKey, SynapseScope, SynapseState
from dgca.core.assembly import (
    K_FORM_PER_END,
    TriangleReadinessTracker,
    compute_idealized_triangle_root_counts,
    execute_assembly_end_pipeline,
)
from dgca.core.dynamics import execute_two_pass_event
from dgca.core.state import (
    Assembly,
    AssemblyStatus,
    BindingStatus,
    CandidatePhase,
    ContextCandidateDescriptor,
    ContributionLane,
    ExecutionMode,
    MachineState,
    ParentContextRef,
    StableBinding,
    TypedSupportRecord,
)
from dgca.encoder.envelope import EventOrigin
from dgca.lla.contrast_ledger import BranchSummary, ContrastEpisodeRecord
from dgca.lla.graduation_c04 import check_c04_durable_path, commit_c04_graduation, evaluate_c04_graduation
from dgca.lla.hierarchy import (
    validate_child_context_admission_hierarchy,
    verify_derived_context_chain,
)
from dgca.lla.recruitment import recruit_contextual_candidate
from dgca.lla.synapse_ledger import apply_weighted_synapse_update
from dgca.lla.witness import eligible_external_p


def _add_consolidated_synapse(
    state: MachineState,
    src: int,
    tgt: int,
    scope: SynapseScope,
    *,
    s_val: float = 0.85,
    e_ext: float = 5.0,
    ext_count: int = 3,
) -> SynapseKey:
    """Helper to commit endpoints, wire latent eligibility, and insert a CONSOLIDATED synapse."""
    state.W.commit_cell(src, 0)
    state.W.commit_cell(tgt, 0)
    if not state.W.latent_table.is_eligible(src, tgt):
        try:
            state.W.latent_table.admit_or_recycle_coactive_partner(
                src,
                tgt,
                event_clock=0,
                protected_bidirectional_neighbors=state.W.get_protected_bidirectional_neighbors(src),
            )
        except Exception:
            state.W.latent_table.admit_or_recycle_coactive_partner(
                tgt,
                src,
                event_clock=0,
                protected_bidirectional_neighbors=state.W.get_protected_bidirectional_neighbors(tgt),
            )
    key: SynapseKey = (src, tgt, scope)
    syn = Synapse(
        key=key,
        state=SynapseState.CONSOLIDATED,
        S=s_val,
        E_ext=e_ext,
        E_int=0.0,
        external_count=ext_count,
        created_event_id=0,
        created_exposure_id=1,
        last_external_event_id=1,
        last_evidence_root=ext_count,
        confirmed_roots=tuple(range(1, ext_count + 1)),
    )
    state.W.add_or_replace_synapse(syn)
    return key


def _add_reciprocal_local_pair(
    state: MachineState,
    u: int,
    v: int,
    *,
    s_val: float = 0.80,
    e_ext: float = 5.0,
) -> None:
    """Add bidirectional CONSOLIDATED LOCAL links between u and v in LANGUAGE region."""
    state.W.commit_cell(u, 0)
    state.W.commit_cell(v, 0)
    if not state.W.latent_table.is_eligible(u, v):
        try:
            state.W.latent_table.admit_or_recycle_coactive_partner(
                u,
                v,
                event_clock=0,
                protected_bidirectional_neighbors=state.W.get_protected_bidirectional_neighbors(u),
            )
        except Exception:
            state.W.latent_table.admit_or_recycle_coactive_partner(
                v,
                u,
                event_clock=0,
                protected_bidirectional_neighbors=state.W.get_protected_bidirectional_neighbors(v),
            )

    for src, tgt in ((u, v), (v, u)):
        syn = Synapse(
            key=(src, tgt, SynapseScope.LOCAL),
            state=SynapseState.CONSOLIDATED,
            S=s_val,
            E_ext=e_ext,
            E_int=0.0,
            external_count=3,
            created_event_id=0,
            created_exposure_id=1,
            last_external_event_id=1,
            last_evidence_root=3,
            confirmed_roots=(1, 2, 3),
        )
        state.W.add_or_replace_synapse(syn)


class TestNativeAssemblyOperatorsSection2_0:
    """Verification of LG-T01, LG-T02, LG-T03 and Core §2.0 Assembly operators."""

    def test_lg_t01_reciprocal_consolidated_local_triangle_forms_size3_assembly(self) -> None:
        """LG-T01: Reciprocal LOCAL CONSOLIDATED triangle with R >= 0.10 and fresh emission forms size-3 Assembly."""
        state = MachineState()
        c0, c1, c2 = 8200, 8208, 8216
        _add_reciprocal_local_pair(state, c0, c1, s_val=0.80, e_ext=5.0)
        _add_reciprocal_local_pair(state, c1, c2, s_val=0.80, e_ext=5.0)
        _add_reciprocal_local_pair(state, c0, c2, s_val=0.80, e_ext=5.0)

        ev = execute_two_pass_event(
            state,
            {c0: 800_000, c1: 800_000, c2: 800_000},
            {c0: 0.80, c1: 0.80, c2: 0.80},
            mode=ExecutionMode.LEARN,
            origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=True,
            exposure_id=1,
            event_order=0,
        )

        state.W.close_serial = 1
        report = execute_assembly_end_pipeline(state.W, state.H_slow, [ev])
        assert report.formed_ids == (1,)
        assert StatusCode.NO_RECIPROCAL_TRIANGLE not in report.diagnostics

        asm = state.W.assemblies[1]
        assert asm.assembly_id == 1
        assert asm.region == Region.LANGUAGE
        assert asm.member_cell_ids == (c0, c1, c2)
        assert asm.structural_generation == 1
        assert asm.status == AssemblyStatus.LIVE
        for cid in (c0, c1, c2):
            assert state.W.assemblies_by_member[cid] == {1}

        # Verify K_FORM_PER_END = 12 cap when 14 disjoint triangles are active in one END
        state_cap = MachineState()
        x_fixed: dict[int, int] = {}
        x_float: dict[int, float] = {}
        for t_idx in range(14):
            # Place each triangle in distinct microcolumns so normalization stays minimal
            u = 8192 + (t_idx * 3 + 0) * 8
            v = 8192 + (t_idx * 3 + 1) * 8
            w_cell = 8192 + (t_idx * 3 + 2) * 8
            _add_reciprocal_local_pair(state_cap, u, v, s_val=0.85, e_ext=6.0)
            _add_reciprocal_local_pair(state_cap, v, w_cell, s_val=0.85, e_ext=6.0)
            _add_reciprocal_local_pair(state_cap, u, w_cell, s_val=0.85, e_ext=6.0)
            for cell in (u, v, w_cell):
                x_fixed[cell] = 850_000
                x_float[cell] = 0.85

        ev_cap = execute_two_pass_event(
            state_cap,
            x_fixed,
            x_float,
            mode=ExecutionMode.LEARN,
            origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=True,
            exposure_id=1,
            event_order=0,
        )
        state_cap.W.close_serial = 1
        rep_cap = execute_assembly_end_pipeline(state_cap.W, state_cap.H_slow, [ev_cap])
        assert len(rep_cap.formed_ids) == K_FORM_PER_END == 12

    def test_lg_t02_one_direction_or_unconsolidated_triangle_returns_no_reciprocal_triangle(self) -> None:
        """LG-T02: One-way consolidated or candidate-only links produce 0 assemblies and NO_RECIPROCAL_TRIANGLE."""
        state = MachineState()
        c0, c1, c2 = 8200, 8208, 8216
        _add_reciprocal_local_pair(state, c0, c1, s_val=0.80, e_ext=5.0)
        _add_reciprocal_local_pair(state, c1, c2, s_val=0.80, e_ext=5.0)
        # Only c0 -> c2 is consolidated; c2 -> c0 is CANDIDATE (not consolidated)
        _add_consolidated_synapse(state, c0, c2, SynapseScope.LOCAL, s_val=0.80, e_ext=5.0)
        state.W.add_or_replace_synapse(
            Synapse(
                key=(c2, c0, SynapseScope.LOCAL),
                state=SynapseState.CANDIDATE,
                S=0.80,
                E_ext=2.5,
                E_int=0.0,
                external_count=2,
                created_event_id=0,
                created_exposure_id=1,
            )
        )

        ev = execute_two_pass_event(
            state,
            {c0: 800_000, c1: 800_000, c2: 800_000},
            {c0: 0.80, c1: 0.80, c2: 0.80},
            mode=ExecutionMode.LEARN,
            origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=True,
            exposure_id=1,
            event_order=0,
        )
        state.W.close_serial = 1
        report = execute_assembly_end_pipeline(state.W, state.H_slow, [ev])
        assert report.formed_ids == ()
        assert len(state.W.assemblies) == 0
        assert StatusCode.NO_RECIPROCAL_TRIANGLE in report.diagnostics

    def test_lg_t03_assembly_maintain_grow_merge_split_and_generation_monotonicity(self) -> None:
        """LG-T03: Verify GROW, MAINTAIN archival, MERGE with T_c=200 cooldown, and SPLIT operators."""
        state = MachineState()
        c0, c1, c2, c3 = 8200, 8208, 8216, 8224
        for u, v in ((c0, c1), (c1, c2), (c0, c2)):
            _add_reciprocal_local_pair(state, u, v, s_val=0.85, e_ext=6.0)

        # Form initial Assembly 1 on (c0, c1, c2)
        ev1 = execute_two_pass_event(
            state,
            {c0: 800_000, c1: 800_000, c2: 800_000},
            {c0: 0.80, c1: 0.80, c2: 0.80},
            mode=ExecutionMode.LEARN,
            origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=True,
            exposure_id=1,
            event_order=0,
        )
        state.W.close_serial = 1
        rep1 = execute_assembly_end_pipeline(state.W, state.H_slow, [ev1])
        assert rep1.formed_ids == (1,)
        assert state.W.assemblies[1].structural_generation == 1

        # Connect c3 reciprocally to c0 and c1 -> GROW adds c3 to Assembly 1 and increments generation to 2
        _add_reciprocal_local_pair(state, c3, c0, s_val=0.85, e_ext=6.0)
        _add_reciprocal_local_pair(state, c3, c1, s_val=0.85, e_ext=6.0)
        state.W.close_serial = 2
        rep2 = execute_assembly_end_pipeline(state.W, state.H_slow, [])
        assert rep2.grown_ids == (1,)
        assert state.W.assemblies[1].member_cell_ids == (c0, c1, c2, c3)
        assert state.W.assemblies[1].structural_generation == 2

        # Degrade c3's reciprocal link to c1 so d(c3, A) drops to 1 < 2 -> MAINTAIN removes c3, generation -> 3
        state.W.remove_synapse((c3, c1, SynapseScope.LOCAL))
        state.W.close_serial = 3
        rep3 = execute_assembly_end_pipeline(state.W, state.H_slow, [])
        assert rep3.maintained_ids == (1,)
        assert state.W.assemblies[1].member_cell_ids == (c0, c1, c2)
        assert state.W.assemblies[1].structural_generation == 3

        # Test MERGE: create Assembly 1 (9 members: c0..c7, c8) and Assembly 2 (9 members: c0..c7, c9)
        # Jaccard = 8 / 10 = 0.80 >= 0.70 (THETA_MERGE).
        # c8 connects to (c0, c1, c2) and c9 connects to (c3, c4, c5), plus c8 <-> c9:
        # - In MAINTAIN on A1 (size 9): c8 has d=3 out of 8 others -> D = 3/8 = 0.375 >= 0.35 (RHO_KEEP), Spec = 3/4 = 0.75 >= 0.20!
        # - In GROW on A2 (size 9): c8 has d=4 (c0, c1, c2, c9) out of 9 -> D = 4/9 = 0.4444 < 0.50 (RHO_G), so GROW does NOT add c8!
        # - In MERGE on A1 U A2 (size 10): every member has D >= 4/9 = 0.4444 >= 0.35 (RHO_KEEP), and between_strength(c8, c9) >= 0.40!
        _add_reciprocal_local_pair(state, c3, c1, s_val=0.85, e_ext=6.0)
        _add_reciprocal_local_pair(state, c3, c2, s_val=0.85, e_ext=6.0)
        c4, c5, c6, c7, c8, c9 = 8232, 8240, 8248, 8256, 8264, 8272
        shared_8 = (c0, c1, c2, c3, c4, c5, c6, c7)
        for idx_u in range(len(shared_8)):
            for idx_v in range(idx_u + 1, len(shared_8)):
                _add_reciprocal_local_pair(
                    state, shared_8[idx_u], shared_8[idx_v], s_val=0.85, e_ext=6.0
                )

        for m in (c0, c1, c2):
            _add_reciprocal_local_pair(state, c8, m, s_val=0.85, e_ext=6.0)
        for m in (c3, c4, c5):
            _add_reciprocal_local_pair(state, c9, m, s_val=0.85, e_ext=6.0)
        _add_reciprocal_local_pair(state, c8, c9, s_val=0.85, e_ext=6.0)

        state.W.assemblies[1] = Assembly(
            assembly_id=1,
            region=Region.LANGUAGE,
            member_cell_ids=(*shared_8, c8),
            structural_generation=3,
            status=AssemblyStatus.LIVE,
        )
        state.W.assemblies[2] = Assembly(
            assembly_id=2,
            region=Region.LANGUAGE,
            member_cell_ids=(*shared_8, c9),
            structural_generation=1,
            status=AssemblyStatus.LIVE,
        )
        state.W.next_assembly_id = 3
        state.W.completed_external_events_count = 300
        state.W.close_serial = 4

        rep4 = execute_assembly_end_pipeline(state.W, state.H_slow, [])
        assert (1, 2) in rep4.merged_pairs
        assert state.W.assemblies[1].status == AssemblyStatus.LIVE
        assert state.W.assemblies[2].status == AssemblyStatus.ARCHIVED
        assert state.W.assemblies[1].member_cell_ids == (*shared_8, c8, c9)

        # Test SPLIT: two triangles (c0, c1, c2) and (d0, d1, d2) with zero cross-links inside a size-6 Assembly 3
        d0, d1, d2 = 8300, 8308, 8316
        for u, v in ((d0, d1), (d1, d2), (d0, d2)):
            _add_reciprocal_local_pair(state, u, v, s_val=0.85, e_ext=6.0)

        state.W.assemblies[3] = Assembly(
            assembly_id=3,
            region=Region.LANGUAGE,
            member_cell_ids=(c0, c1, c2, d0, d1, d2),
            structural_generation=1,
            last_merge_split_close_serial=300,  # In cooldown at event_count=350!
            status=AssemblyStatus.LIVE,
        )
        state.W.next_assembly_id = 4

        # While in T_c=200 cooldown (350 - 300 = 50 < 200), SPLIT is skipped
        state.W.completed_external_events_count = 350
        state.W.close_serial = 5
        rep5 = execute_assembly_end_pipeline(state.W, state.H_slow, [])
        assert rep5.split_pairs == ()
        assert len(state.W.assemblies[3].member_cell_ids) == 6

        # After T_c=200 events (550 - 300 = 250 >= 200), SPLIT partitions Assembly 3 into 3 (L) and 4 (R)
        state.W.completed_external_events_count = 550
        state.W.close_serial = 6
        rep6 = execute_assembly_end_pipeline(state.W, state.H_slow, [])
        assert rep6.split_pairs == ((3, 4),)
        assert state.W.assemblies[3].member_cell_ids == (c0, c1, c2)
        assert state.W.assemblies[3].structural_generation == 2
        assert state.W.assemblies[4].member_cell_ids == (d0, d1, d2)
        assert state.W.assemblies[4].structural_generation == 1
        assert state.W.assemblies[4].status == AssemblyStatus.LIVE


class TestHierarchicalDerivedContextSection6_1And6_6:
    """Verification of LG-T04, LG-T05, LG-T06, LG-T13 and Gate C / LG-T16."""

    def _create_graduated_depth1_context(
        self,
        state: MachineState,
        *,
        z1_id: int = 8201,
        anchor1_id: int = 8200,
        p0: int = 8300,
        p1: int = 8308,
        c0: int = 8200,
        c1: int = 8208,
        y0: int = 8400,
        y1: int = 8408,
    ) -> StableBinding:
        """Create and register a COMPLETE depth-1 contextual owner z1 with consolidated P/C/Y synapses."""
        for cid in (z1_id, p0, p1, c0, c1, y0, y1):
            state.W.commit_cell(cid, 0)

        p0_key = _add_consolidated_synapse(state, p0, z1_id, SynapseScope.ASSOCIATIVE, s_val=0.85, e_ext=6.0)
        p1_key = _add_consolidated_synapse(state, p1, z1_id, SynapseScope.ASSOCIATIVE, s_val=0.85, e_ext=6.0)
        c0_key = _add_consolidated_synapse(state, c0, z1_id, SynapseScope.LOCAL, s_val=0.85, e_ext=6.0)
        c1_key = _add_consolidated_synapse(state, c1, z1_id, SynapseScope.LOCAL, s_val=0.85, e_ext=6.0)
        y0_key = _add_consolidated_synapse(state, z1_id, y0, SynapseScope.ASSOCIATIVE, s_val=0.85, e_ext=6.0)
        y1_key = _add_consolidated_synapse(state, z1_id, y1, SynapseScope.ASSOCIATIVE, s_val=0.85, e_ext=6.0)

        binding = StableBinding(
            schema_version=2,
            z_cell_id=z1_id,
            anchor_id=anchor1_id,
            owner_seq=1,
            binding_generation=1,
            p_keys=(p0_key, p1_key),
            l_z_q6=700_000,
            u_z_q6=100_000,
            tau_ctx_q6=150_000,
            c_keys=(c0_key, c1_key),
            y_keys=(y0_key, y1_key),
            anchor_source_set=frozenset({c0, c1}),
            status=BindingStatus.ACTIVE,
            depth=1,
        )
        state.W.stable_bindings[z1_id] = binding
        return binding

    def test_lg_t04_depth2_derived_external_context_admission_and_single_root_q_credit(self) -> None:
        """LG-T04: COMPLETE z1 emits without probe on external P/B; z2 recruits z1 as DERIVED_EXTERNAL_CONTEXT P (depth=2, OwnerProfileV2, StableBindingV3) and gets at most 1 root credit."""
        state = MachineState()
        z1_id = 8201
        p0, p1 = 8300, 8308
        c0, c1 = 8200, 8208
        w3_c0, w3_c1 = 8500, 8508
        y2_0, y2_1 = 8600, 8608
        alt_y0, alt_y1 = 8616, 8624
        riv_p0, riv_p1 = 8700, 8708

        for cid in (w3_c0, w3_c1, y2_0, y2_1, alt_y0, alt_y1, riv_p0, riv_p1):
            state.W.commit_cell(cid, 0)

        bind1 = self._create_graduated_depth1_context(
            state, z1_id=z1_id, anchor1_id=c0, p0=p0, p1=p1, c0=c0, c1=c1
        )

        # Run genuine external root: Event 0 (W1: p0, p1) -> Event 1 (W2: c0, c1 where z1 emits without probe)
        execute_two_pass_event(
            state,
            {p0: 800_000, p1: 800_000},
            {p0: 0.80, p1: 0.80},
            mode=ExecutionMode.LEARN,
            origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=True,
            exposure_id=10,
            event_order=0,
        )
        ev_w2 = execute_two_pass_event(
            state,
            {c0: 800_000, c1: 800_000},
            {c0: 0.80, c1: 0.80},
            mode=ExecutionMode.LEARN,
            origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=False,
            exposure_id=10,
            event_order=1,
        )

        assert z1_id in ev_w2.f_step
        kind_z1, sup_z1 = eligible_external_p(z1_id, ev_w2, state.W)
        assert kind_z1 == WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT
        assert sup_z1 > 0.40
        z1_q6 = q6_from_binary64(sup_z1)

        ref_z1 = ParentContextRef(
            parent_z_cell_id=z1_id,
            parent_anchor_id=bind1.anchor_id,
            parent_owner_seq=bind1.owner_seq,
            parent_binding_generation=bind1.binding_generation,
            depth=1,
        )

        # Recruit depth-2 candidate z2 at anchor w3_c0 with P=(z1_id, c0), C=(w3_c0, w3_c1), Y=(y2_0, y2_1)
        ep1 = ContrastEpisodeRecord(
            anchor_id=w3_c0,
            exposure_id=10,
            event_order_b=2,
            completed_event_clock=30,
            p_supports_u={z1_id: z1_q6, c0: 800_000},
            c_supports_u={w3_c0: 800_000, w3_c1: 800_000},
            y_supports_u={y2_0: 800_000, y2_1: 800_000},
            p_source_kinds={
                z1_id: WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT,
                c0: WitnessSourceKind.DIRECT,
            },
            p_parent_refs={z1_id: ref_z1},
        )
        ep2 = ContrastEpisodeRecord(
            anchor_id=w3_c0,
            exposure_id=11,
            event_order_b=2,
            completed_event_clock=33,
            p_supports_u={z1_id: z1_q6, c0: 800_000},
            c_supports_u={w3_c0: 800_000, w3_c1: 800_000},
            y_supports_u={y2_0: 800_000, y2_1: 800_000},
            p_source_kinds={
                z1_id: WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT,
                c0: WitnessSourceKind.DIRECT,
            },
            p_parent_refs={z1_id: ref_z1},
        )
        owned_branch = BranchSummary(
            anchor_id=w3_c0,
            p_digest=ep1.p_digest,
            c_digest=ep1.c_digest,
            y_digest=ep1.y_digest,
            episodes=[ep1, ep2],
        )

        riv_ep1 = ContrastEpisodeRecord(
            anchor_id=w3_c0,
            exposure_id=12,
            event_order_b=2,
            completed_event_clock=36,
            p_supports_u={riv_p0: 800_000, riv_p1: 800_000},
            c_supports_u={w3_c0: 800_000, w3_c1: 800_000},
            y_supports_u={alt_y0: 800_000, alt_y1: 800_000},
        )
        riv_ep2 = ContrastEpisodeRecord(
            anchor_id=w3_c0,
            exposure_id=13,
            event_order_b=2,
            completed_event_clock=39,
            p_supports_u={riv_p0: 800_000, riv_p1: 800_000},
            c_supports_u={w3_c0: 800_000, w3_c1: 800_000},
            y_supports_u={alt_y0: 800_000, alt_y1: 800_000},
        )
        rival_branch = BranchSummary(
            anchor_id=w3_c0,
            p_digest=riv_ep1.p_digest,
            c_digest=riv_ep1.c_digest,
            y_digest=riv_ep1.y_digest,
            episodes=[riv_ep1, riv_ep2],
        )

        rec_res = recruit_contextual_candidate(
            w3_c0,
            owned_branch,
            (rival_branch,),
            state.W,
            admitted_root_id=13,
            event_clock=39,
            remaining_k_r=4,
        )
        assert rec_res.status == StatusCode.OK
        assert rec_res.descriptor is not None
        assert rec_res.owner_profile is not None
        z2_desc = rec_res.descriptor
        assert z2_desc.depth == 2
        assert WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT in z2_desc.p_source_kinds
        assert rec_res.owner_profile.schema_version == 2

        # Consolidate z2's links and graduate via C04 -> StableBindingV3 (schema_version=3)
        z2_id = z2_desc.z_cell_id
        for p_src in z2_desc.p_sources:
            _add_consolidated_synapse(state, p_src, z2_id, SynapseScope.ASSOCIATIVE, s_val=0.85, e_ext=6.0)
        for c_src in z2_desc.c_sources:
            _add_consolidated_synapse(state, c_src, z2_id, SynapseScope.LOCAL, s_val=0.85, e_ext=6.0)
        for y_tgt in z2_desc.y_targets:
            _add_consolidated_synapse(state, z2_id, y_tgt, SynapseScope.ASSOCIATIVE, s_val=0.85, e_ext=6.0)

        from dgca.lla.owner_registry import CompactWitnessProfile

        z2_desc.phase = CandidatePhase.NO_PROBE_TEST
        grad_res = evaluate_c04_graduation(
            z2_desc,
            state,
            owned_witness=CompactWitnessProfile.from_episode(ep1),
            rival_witnesses=[CompactWitnessProfile.from_episode(riv_ep1)],
        )
        assert grad_res.status == StatusCode.OK
        assert grad_res.stable_binding is not None
        assert grad_res.stable_binding.schema_version == 3
        assert grad_res.stable_binding.depth == 2
        commit_c04_graduation(z2_desc, grad_res.stable_binding, state.W)
        bind2 = state.W.stable_bindings[z2_id]
        assert bind2.schema_version == 3

        # Verify no double promotion: one completed external root credits external_count by exactly +1
        syn_z1_z2 = state.W.synapses[(z1_id, z2_id, SynapseScope.ASSOCIATIVE)]
        prev_ext_count = syn_z1_z2.external_count
        apply_weighted_synapse_update(
            syn_z1_z2,
            q=0.25,
            y=0.70,
            is_external=True,
            exposure_id=50,
            event_id=50,
        )
        assert syn_z1_z2.external_count == prev_ext_count + 1
        # Repeated call for the same exposure_id=50 is ignored (no double promotion)
        apply_weighted_synapse_update(
            syn_z1_z2,
            q=0.25,
            y=0.70,
            is_external=True,
            exposure_id=50,
            event_id=50,
        )
        assert syn_z1_z2.external_count == prev_ext_count + 1

    def test_lg_t05_probe_or_non_external_z1_cannot_produce_derived_external_context(self) -> None:
        """LG-T05: z1 emitting via LEARN probe or in RETRIEVE/GENERATE/REPLAY yields no DERIVED_EXTERNAL_CONTEXT."""
        state = MachineState()
        z1_id = 8201
        p0, p1 = 8300, 8308
        c0, c1 = 8200, 8208
        y0, y1 = 8400, 8408
        for cid in (z1_id, p0, p1, c0, c1, y0, y1):
            state.W.commit_cell(cid, 0)
        state.W.latent_table.pin_context_candidate_roles(
            z1_id, (p0, p1, c0, c1, y0, y1), event_clock=0
        )

        # Case A: z1 is an incomplete candidate emitting only from LEARN probe
        cand1 = ContextCandidateDescriptor(
            z_cell_id=z1_id,
            anchor_id=c0,
            owner_seq=1,
            p_sources=(p0, p1),
            c_sources=(c0, c1),
            y_targets=(y0, y1),
            l_z_q6=700_000,
            u_z_q6=100_000,
            tau_ctx_q6=150_000,
            anchor_source_set=frozenset({c0, c1}),
            phase=CandidatePhase.WIRED,
            admitted_root_id=1,
        )
        state.W.context_candidates[z1_id] = cand1

        execute_two_pass_event(
            state,
            {p0: 800_000, p1: 800_000},
            {p0: 0.80, p1: 0.80},
            mode=ExecutionMode.LEARN,
            origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=True,
            exposure_id=2,
            event_order=0,
        )
        ev_probe = execute_two_pass_event(
            state,
            {c0: 800_000, c1: 800_000},
            {c0: 0.80, c1: 0.80},
            mode=ExecutionMode.LEARN,
            origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=False,
            exposure_id=2,
            event_order=1,
            allow_candidate_probe=True,
        )
        assert z1_id in ev_probe.f_step
        # Must NOT qualify as EligibleExternalP because z1 is incomplete and used probe
        kind_probe, sup_probe = eligible_external_p(z1_id, ev_probe, state.W)
        assert kind_probe is None and sup_probe == 0.0

        # Case B: z1 is COMPLETE, but event is RETRIEVE (READ_ONLY_OBSERVED) -> o_train == 0, no DERIVED_EXTERNAL_CONTEXT
        del state.W.context_candidates[z1_id]
        self._create_graduated_depth1_context(
            state, z1_id=z1_id, anchor1_id=c0, p0=p0, p1=p1, c0=c0, c1=c1, y0=y0, y1=y1
        )
        execute_two_pass_event(
            state,
            {p0: 800_000, p1: 800_000},
            {p0: 0.80, p1: 0.80},
            mode=ExecutionMode.RETRIEVE,
            origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=True,
            exposure_id=None,
            event_order=0,
        )
        ev_ro = execute_two_pass_event(
            state,
            {c0: 800_000, c1: 800_000},
            {c0: 0.80, c1: 0.80},
            mode=ExecutionMode.RETRIEVE,
            origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=False,
            exposure_id=None,
            event_order=1,
        )
        assert ev_ro.typed_supports[z1_id].origin_kind == ContributionLane.DERIVED_RUNTIME_CONTEXT.value
        assert ev_ro.typed_supports[z1_id].o_train == 0.0
        kind_ro, sup_ro = eligible_external_p(z1_id, ev_ro, state.W)
        assert kind_ro is None and sup_ro == 0.0

    def test_lg_t06_depth8_limit_stale_parent_and_cycle_rejection_without_direct_fallback(self) -> None:
        """LG-T06: Depth 8 child trying to spawn 9th-level context, stale parent, or cycle is rejected with exact StatusCode and never falls back to DIRECT."""
        state = MachineState()
        direct_p = 8300
        c0, c1 = 8200, 8208
        y0, y1 = 8400, 8408
        for cid in (direct_p, c0, c1, y0, y1):
            state.W.commit_cell(cid, 0)

        # Build a legal chain of 8 COMPLETE contextual owners z_1 (depth=1) .. z_8 (depth=8)
        z_ids = [8500 + d * 8 for d in range(1, 9)]
        for d_idx, zid in enumerate(z_ids, start=1):
            state.W.commit_cell(zid, 0)
            prev_p0 = direct_p if d_idx == 1 else z_ids[d_idx - 2]
            prev_p1 = c1
            p0_key = _add_consolidated_synapse(state, prev_p0, zid, SynapseScope.ASSOCIATIVE)
            p1_key = _add_consolidated_synapse(state, prev_p1, zid, SynapseScope.ASSOCIATIVE)
            c0_key = _add_consolidated_synapse(state, c0, zid, SynapseScope.LOCAL)
            y0_key = _add_consolidated_synapse(state, zid, y0, SynapseScope.ASSOCIATIVE)

            if d_idx == 1:
                bind = StableBinding(
                    schema_version=2,
                    z_cell_id=zid,
                    anchor_id=c0,
                    owner_seq=d_idx,
                    binding_generation=1,
                    p_keys=(p0_key, p1_key),
                    l_z_q6=700_000,
                    u_z_q6=100_000,
                    tau_ctx_q6=150_000,
                    c_keys=(c0_key,),
                    y_keys=(y0_key,),
                    anchor_source_set=frozenset({c0, c1}),
                    depth=1,
                )
            else:
                parent_z = z_ids[d_idx - 2]
                ref = ParentContextRef(
                    parent_z_cell_id=parent_z,
                    parent_anchor_id=c0,
                    parent_owner_seq=d_idx - 1,
                    parent_binding_generation=1,
                    depth=d_idx - 1,
                )
                bind = StableBinding(
                    schema_version=3,
                    z_cell_id=zid,
                    anchor_id=c0,
                    owner_seq=d_idx,
                    binding_generation=1,
                    p_keys=(p0_key, p1_key),
                    l_z_q6=700_000,
                    u_z_q6=100_000,
                    tau_ctx_q6=150_000,
                    c_keys=(c0_key,),
                    y_keys=(y0_key,),
                    anchor_source_set=frozenset({c0, c1}),
                    depth=d_idx,
                    p_source_kinds=(
                        WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT,
                        WitnessSourceKind.DIRECT,
                    ),
                    parent_refs={parent_z: ref},
                )
            state.W.stable_bindings[zid] = bind

        z8 = z_ids[-1]
        assert state.W.stable_bindings[z8].depth == 8
        ref_z8 = ParentContextRef(
            parent_z_cell_id=z8,
            parent_anchor_id=c0,
            parent_owner_seq=8,
            parent_binding_generation=1,
            depth=8,
        )

        # 1. Attempting to spawn a 9th-level context (depth=9 > 8) fails with CONTEXT_CHAIN_DEPTH_EXCEEDED
        # Even when 2 DIRECT P sources (direct_p, c1) are also present in the episode, it MUST NOT fallback to DIRECT!
        ep1_d9 = ContrastEpisodeRecord(
            anchor_id=c0,
            exposure_id=20,
            event_order_b=8,
            completed_event_clock=100,
            p_supports_u={z8: 750_000, direct_p: 800_000, c1: 800_000},
            c_supports_u={c0: 800_000, c1: 800_000},
            y_supports_u={y0: 800_000, y1: 800_000},
            p_source_kinds={
                z8: WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT,
                direct_p: WitnessSourceKind.DIRECT,
                c1: WitnessSourceKind.DIRECT,
            },
            p_parent_refs={z8: ref_z8},
        )
        ep2_d9 = ep1_d9.clone()
        ep2_d9.exposure_id = 21
        branch_d9 = BranchSummary(
            anchor_id=c0,
            p_digest=ep1_d9.p_digest,
            c_digest=ep1_d9.c_digest,
            y_digest=ep1_d9.y_digest,
            episodes=[ep1_d9, ep2_d9],
        )
        riv_ep1 = ContrastEpisodeRecord(
            anchor_id=c0,
            exposure_id=22,
            event_order_b=8,
            completed_event_clock=105,
            p_supports_u={direct_p: 100_000, c1: 100_000},
            c_supports_u={c0: 800_000, c1: 800_000},
            y_supports_u={y0: 100_000, y1: 800_000},
        )
        riv_ep2 = riv_ep1.clone()
        riv_ep2.exposure_id = 23
        riv_branch = BranchSummary(
            anchor_id=c0,
            p_digest=riv_ep1.p_digest,
            c_digest=riv_ep1.c_digest,
            y_digest=riv_ep1.y_digest,
            episodes=[riv_ep1, riv_ep2],
        )

        res_d9 = recruit_contextual_candidate(
            c0,
            branch_d9,
            (riv_branch,),
            state.W,
            admitted_root_id=23,
            event_clock=110,
            remaining_k_r=4,
        )
        assert res_d9.status == StatusCode.CONTEXT_CHAIN_DEPTH_EXCEEDED
        assert res_d9.descriptor is None

        # 2. Stale parent binding_generation -> PARENT_BINDING_STALE
        z1 = z_ids[0]
        stale_ref = ParentContextRef(
            parent_z_cell_id=z1,
            parent_anchor_id=c0,
            parent_owner_seq=1,
            parent_binding_generation=99,  # Mismatches live binding_generation=1
            depth=1,
        )
        ok_stale, code_stale, _ = validate_child_context_admission_hierarchy(
            (z1, direct_p),
            (WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT, WitnessSourceKind.DIRECT),
            {z1: stale_ref},
            state.W,
        )
        assert not ok_stale and code_stale == StatusCode.PARENT_BINDING_STALE

        # 3. Ancestral cycle (z1 depends on z2 which depends on z1) -> CONTEXT_CHAIN_CYCLE
        z2 = z_ids[1]
        ref_z2 = ParentContextRef(
            parent_z_cell_id=z2,
            parent_anchor_id=c0,
            parent_owner_seq=2,
            parent_binding_generation=1,
            depth=2,
        )
        ok_cycle, code_cycle, _ = validate_child_context_admission_hierarchy(
            (z2, direct_p),
            (WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT, WitnessSourceKind.DIRECT),
            {z2: ref_z2},
            state.W,
            candidate_z_id=z1,
        )
        assert not ok_cycle and code_cycle == StatusCode.CONTEXT_CHAIN_CYCLE

        # 4. Contextual cell z1 disguised as DIRECT source -> DERIVED_PROVENANCE_UNVERIFIED
        ok_fallback, code_fallback, _ = validate_child_context_admission_hierarchy(
            (z1, direct_p),
            (WitnessSourceKind.DIRECT, WitnessSourceKind.DIRECT),
            {},
            state.W,
        )
        assert not ok_fallback and code_fallback == StatusCode.DERIVED_PROVENANCE_UNVERIFIED

    def test_lg_t13_wrong_prior_event_order_or_direct_only_z1_or_synthetic_source_rejected(self) -> None:
        """LG-T13: Direct-only z1, wrong prior event order, or synthetic unverified source yields DERIVED_PROVENANCE_UNVERIFIED and zero external q."""
        state = MachineState()
        z1_id = 8201
        p0, p1 = 8300, 8308
        c0, c1 = 8200, 8208
        bind1 = self._create_graduated_depth1_context(
            state, z1_id=z1_id, anchor1_id=c0, p0=p0, p1=p1, c0=c0, c1=c1
        )

        # 1. Stimulating contextual cell z1 directly with SIC without prior P -> G_ctx=0, excluded from obs_eligible_cells
        ev_direct_only = execute_two_pass_event(
            state,
            {z1_id: 900_000, c0: 800_000, c1: 800_000},
            {z1_id: 0.90, c0: 0.80, c1: 0.80},
            mode=ExecutionMode.LEARN,
            origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=True,
            exposure_id=30,
            event_order=0,
        )
        assert z1_id not in ev_direct_only.obs_eligible_cells
        assert ev_direct_only.g_ctx_by_z[z1_id] == 0
        assert ev_direct_only.a_plus_by_cell.get(z1_id, 0.0) == 0.0
        kind_dir, sup_dir = eligible_external_p(z1_id, ev_direct_only, state.W)
        assert kind_dir is None and sup_dir == 0.0

        # 2. Wrong prior event order (e.g. prev_supports has event_order=0 when current event_order=2)
        wrong_order_prev = {
            p0: TypedSupportRecord(
                cell_id=p0,
                event_order=0,  # Should be 1 for curr event_order=2!
                origin_kind=EventOrigin.EXTERNAL_DIRECT.value,
                o_train=0.80,
                o_runtime=0.80,
                q6_train=800_000,
                q6_runtime=800_000,
                depth=0,
                parent_proof_verified=True,
            ),
            p1: TypedSupportRecord(
                cell_id=p1,
                event_order=0,
                origin_kind=EventOrigin.EXTERNAL_DIRECT.value,
                o_train=0.80,
                o_runtime=0.80,
                q6_train=800_000,
                q6_runtime=800_000,
                depth=0,
                parent_proof_verified=True,
            ),
        }
        curr_c = {
            c0: TypedSupportRecord(
                cell_id=c0,
                event_order=2,
                origin_kind=EventOrigin.EXTERNAL_DIRECT.value,
                o_train=0.80,
                o_runtime=0.80,
                q6_train=800_000,
                q6_runtime=800_000,
                depth=0,
                parent_proof_verified=True,
            ),
        }
        ok_order, code_order = verify_derived_context_chain(
            z1_id,
            2,
            wrong_order_prev,
            curr_c,
            state.W,
            mode=ExecutionMode.LEARN,
            origin=EventOrigin.EXTERNAL_DIRECT,
            g_ctx=1,
            in_f_step=True,
            is_bootstrapped=False,
        )
        assert not ok_order and code_order == StatusCode.DERIVED_PROVENANCE_UNVERIFIED

        # 3. Synthetic matched source with parent_proof_verified=False -> DERIVED_PROVENANCE_UNVERIFIED
        synthetic_prev = {
            p0: TypedSupportRecord(
                cell_id=p0,
                event_order=0,
                origin_kind=EventOrigin.EXTERNAL_DIRECT.value,
                o_train=0.80,
                o_runtime=0.80,
                q6_train=800_000,
                q6_runtime=800_000,
                depth=0,
                parent_proof_verified=False,
            ),
            p1: TypedSupportRecord(
                cell_id=p1,
                event_order=0,
                origin_kind=EventOrigin.EXTERNAL_DIRECT.value,
                o_train=0.80,
                o_runtime=0.80,
                q6_train=800_000,
                q6_runtime=800_000,
                depth=0,
                parent_proof_verified=True,
            ),
        }
        curr_c1 = {
            c0: TypedSupportRecord(
                cell_id=c0,
                event_order=1,
                origin_kind=EventOrigin.EXTERNAL_DIRECT.value,
                o_train=0.80,
                o_runtime=0.80,
                q6_train=800_000,
                q6_runtime=800_000,
                depth=0,
                parent_proof_verified=True,
            ),
        }
        ok_syn, code_syn = verify_derived_context_chain(
            z1_id,
            1,
            synthetic_prev,
            curr_c1,
            state.W,
            mode=ExecutionMode.LEARN,
            origin=EventOrigin.EXTERNAL_DIRECT,
            g_ctx=1,
            in_f_step=True,
            is_bootstrapped=False,
        )
        assert not ok_syn and code_syn == StatusCode.DERIVED_PROVENANCE_UNVERIFIED

    @pytest.mark.parametrize(
        ("activity_a", "expected_post_commit", "expected_cold_total"),
        [
            (0.45, 15, 18),
            (0.60, 9, 12),
            (0.70, 7, 10),
            (0.80, 5, 8),
        ],
    )
    def test_lg_t16_gate_c_rc4_1_triangle_readiness_subgate_and_idealized_root_counts(
        self,
        activity_a: float,
        expected_post_commit: int,
        expected_cold_total: int,
    ) -> None:
        """LG-T16: Verify idealized post-commitment N=15/9/7/5 and cold totals 18/12/10/8, 0 birth-root attestations, and 2 post-birth roots."""
        n_post, n_total = compute_idealized_triangle_root_counts(activity_a)
        assert n_post == expected_post_commit
        assert n_total == expected_cold_total

        state = MachineState()
        c0, c1, c2 = 8200, 8208, 8216
        tracker = TriangleReadinessTracker(triangle_cells=(c0, c1, c2))
        q_edge = activity_a * activity_a

        # Root 1: Cold start commitment root (cells uncommitted before event 0 -> committed at end of event 0, 0 link evidence)
        pre_r1 = [a.clone() for a in state.W.assemblies.values() if a.status == AssemblyStatus.LIVE]
        ev_r1 = execute_two_pass_event(
            state,
            {c0: 800_000, c1: 800_000, c2: 800_000},
            {c0: 0.80, c1: 0.80, c2: 0.80},
            mode=ExecutionMode.LEARN,
            origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=True,
            exposure_id=1,
            event_order=0,
            admit_uncommitted_sensory=True,
        )
        # Wire latent eligibility among the 3 newly committed cells
        for u, v in ((c0, c1), (c1, c2), (c0, c2)):
            state.W.latent_table.admit_or_recycle_coactive_partner(u, v, event_clock=1)
            state.W.latent_table.admit_or_recycle_coactive_partner(v, u, event_clock=1)

        state.W.close_serial = 1
        execute_assembly_end_pipeline(state.W, state.H_slow, [ev_r1])
        tracker.record_completed_root(
            1,
            state.W,
            state.H_slow,
            [ev_r1],
            preexisting_live_assemblies=pre_r1,
            surface_text="كتب",
            feature_bundle_digest=b"bundle_kataba_32_bytes__________",
        )
        assert tracker.receiver_commit_root == {c0: 1, c1: 1, c2: 1}
        assert tracker.assembly_id is None

        # Roots 2 .. 1 + expected_post_commit: accrue q = a^2 per root on all 6 directed LOCAL edges
        birth_root_id = 1 + expected_post_commit
        for r_id in range(2, birth_root_id + 1):
            pre_live = [a.clone() for a in state.W.assemblies.values() if a.status == AssemblyStatus.LIVE]
            ev_r = execute_two_pass_event(
                state,
                {c0: 800_000, c1: 800_000, c2: 800_000},
                {c0: 0.80, c1: 0.80, c2: 0.80},
                mode=ExecutionMode.LEARN,
                origin=EventOrigin.EXTERNAL_DIRECT,
                boundary=True,
                exposure_id=r_id,
                event_order=0,
            )
            for key in tracker.six_directed_keys:
                syn = state.W.synapses.get(key)
                if syn is None:
                    syn = Synapse(
                        key=key,
                        S=0.0,
                        E_ext=0.0,
                        created_event_id=r_id,
                        created_exposure_id=r_id,
                    )
                    state.W.add_or_replace_synapse(syn)
                apply_weighted_synapse_update(
                    syn,
                    q=q_edge,
                    y=0.80,
                    is_external=True,
                    exposure_id=r_id,
                    event_id=r_id,
                )

            state.W.close_serial = r_id
            asm_rep = execute_assembly_end_pipeline(state.W, state.H_slow, [ev_r])
            tracker.record_completed_root(
                r_id,
                state.W,
                state.H_slow,
                [ev_r],
                preexisting_live_assemblies=pre_live,
                surface_text="كتب",
                feature_bundle_digest=b"bundle_kataba_32_bytes__________",
            )
            if r_id < birth_root_id:
                assert asm_rep.formed_ids == ()
                assert tracker.assembly_id is None
            else:
                assert asm_rep.formed_ids == (1,)
                assert tracker.assembly_id == 1
                assert tracker.assembly_birth_root == birth_root_id
                # Newly formed assembly receives 0 birth-root attestations!
                assert tracker.attestation_roots == []
                assert not tracker.is_readout_ready

        # 2 later independent roots after birth_root_id are required for attestation
        for post_idx in (1, 2):
            r_id = birth_root_id + post_idx
            pre_live = [a.clone() for a in state.W.assemblies.values() if a.status == AssemblyStatus.LIVE]
            ev_post = execute_two_pass_event(
                state,
                {c0: 800_000, c1: 800_000, c2: 800_000},
                {c0: 0.80, c1: 0.80, c2: 0.80},
                mode=ExecutionMode.LEARN,
                origin=EventOrigin.EXTERNAL_DIRECT,
                boundary=True,
                exposure_id=r_id,
                event_order=0,
            )
            state.W.close_serial = r_id
            execute_assembly_end_pipeline(state.W, state.H_slow, [ev_post])
            tracker.record_completed_root(
                r_id,
                state.W,
                state.H_slow,
                [ev_post],
                preexisting_live_assemblies=pre_live,
                surface_text="كتب",
                feature_bundle_digest=b"bundle_kataba_32_bytes__________",
            )
            if post_idx == 1:
                assert len(tracker.attestation_roots) == 1
                assert not tracker.is_readout_ready
            else:
                assert len(tracker.attestation_roots) == 2
                assert tracker.is_readout_ready
                assert r_id == expected_cold_total
