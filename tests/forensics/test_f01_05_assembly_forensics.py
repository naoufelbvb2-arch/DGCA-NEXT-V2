"""Forensic Investigation Phase D: ASSEMBLY & READOUT FORENSICS (R1-M01, R1-M02, R1-M03 & Tasks 2, 3, 4).

Investigates:
- F01-05 (R1-M01): Duplicate Assemblies (Fixture exact duplicates cannot merge due to between_strength = 0.0)
- Task 2: Natural Assembly inspection at roots 34, 56, 80 (EXACT_STRUCTURAL_DUPLICATE vs SAME_SURFACE_DIFFERENT_STRUCTURE)
- Task 3 (R1-M02): Natural contextual z-cell contamination of lexical Assembly (CoreCoverage drops to 0.80 on DB)
- Task 4 (R1-M03): Readout causal analysis (exclusion of indirect Pass-2 causal gain by P_T > 0 and |G| dilution)
"""

from __future__ import annotations

import pytest
from dgca.common.hashing import Region
from dgca.core.anatomy import Synapse, SynapseScope, SynapseState
from dgca.core.assembly import (
    _is_in_merge_split_cooldown,
    _try_merge_pair,
    compute_core_coverage,
    is_eligible_assembly_member_cell,
)
from dgca.core.dynamics import execute_two_pass_event
from dgca.core.readout import evaluate_full_vs_control_readout
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import (
    Assembly,
    AssemblyStatus,
    BindingStatus,
    EventOrigin,
    ExecutionMode,
    MachineState,
    StableBinding,
)
import dataclasses
from dgca.encoder.envelope import Marker, encode_exposure, encode_lexical_token_event
from dgca.experiments.gates import _wire_consolidated_synapse
from dgca.lifecycle.exposure_tx import ExposureTransactionManager, run_read_only_episode
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1


def test_f01_05_fixture_exact_duplicate_assemblies_cannot_merge() -> None:
    """F01-05 (R1-M01 Mechanism Fixture): Verify that exact duplicate assemblies fail MERGE."""
    state = MachineState()
    c1, c2, c3 = 8200, 8208, 8216
    for c in (c1, c2, c3):
        state.W.commit_cell(c, 0)
    for u in (c1, c2, c3):
        for v in (c1, c2, c3):
            if u != v:
                _wire_consolidated_synapse(state, u, v, SynapseScope.LOCAL, s_val=0.85)

    asm1 = Assembly(
        assembly_id=1,
        region=Region.LANGUAGE,
        member_cell_ids=frozenset((c1, c2, c3)),
        structural_generation=1,
        status=AssemblyStatus.LIVE,
    )
    asm2 = Assembly(
        assembly_id=2,
        region=Region.LANGUAGE,
        member_cell_ids=frozenset((c1, c2, c3)),
        structural_generation=1,
        status=AssemblyStatus.LIVE,
    )
    state.W.assemblies[1] = asm1
    state.W.assemblies[2] = asm2

    merged = _try_merge_pair(1, 2, state.W, {})
    # Jaccard = 1.0 >= 0.70, but excl_a and excl_b are empty -> between_strength = 0.0 < THETA_OB (0.40) -> False
    assert merged is False, "DEFECT NOT OBSERVED: exact duplicates unexpectedly merged"
    assert asm1.status == AssemblyStatus.LIVE
    assert asm2.status == AssemblyStatus.LIVE


def test_f01_task2_natural_assembly_duplication_analysis() -> None:
    """Task 2: Inspect Assemblies formed through natural cold-start learning across roots 34, 56, 80."""
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
    )

    branch_ab = encode_exposure("القط يشرب حليب", append_eos=False)
    branch_db = encode_exposure("النسر يشرب ماء", append_eos=False)

    checkpoints_data: dict[int, dict] = {}

    for root_id in range(1, 81):
        is_ab = (root_id % 2 != 0)
        envs = branch_ab if is_ab else branch_db
        tx.begin_exposure(root_id)
        for env in envs:
            core_ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        tx.end_exposure(root_id)

        if root_id in (34, 56, 80):
            live_asms = [a for a in state.W.assemblies.values() if a.status == AssemblyStatus.LIVE]
            member_sets: dict[tuple[int, ...], list[int]] = {}
            surface_map: dict[str, list[int]] = {}

            for a in live_asms:
                m_tuple = tuple(sorted(a.member_cell_ids))
                member_sets.setdefault(m_tuple, []).append(a.assembly_id)
                res_r = ledger.resolve_readout(a.assembly_id, a.structural_generation, current_live_generation=a.structural_generation)
                surf = getattr(res_r.envelope, "raw_surface_nfc_utf8", None)
                if surf:
                    surface_map.setdefault(surf, []).append(a.assembly_id)

            exact_duplicates = [ids for m, ids in member_sets.items() if len(ids) > 1]
            checkpoints_data[root_id] = {
                "live_count": len(live_asms),
                "exact_duplicates_count": len(exact_duplicates),
                "surface_map": surface_map,
            }

    # Verify Checkpoint 34
    assert checkpoints_data[34]["live_count"] == 9
    assert checkpoints_data[34]["exact_duplicates_count"] == 0
    assert len(checkpoints_data[34]["surface_map"].get("يشرب", [])) >= 2
    assert len(checkpoints_data[34]["surface_map"].get("حليب", [])) >= 2
    assert len(checkpoints_data[34]["surface_map"].get("ماء", [])) >= 2

    # Verify Checkpoint 56
    assert checkpoints_data[56]["live_count"] == 9
    assert checkpoints_data[56]["exact_duplicates_count"] == 0
    assert len(checkpoints_data[56]["surface_map"].get("يشرب", [])) >= 2
    assert len(checkpoints_data[56]["surface_map"].get("حليب", [])) >= 2
    assert len(checkpoints_data[56]["surface_map"].get("ماء", [])) >= 2

    # Verify Checkpoint 80
    assert checkpoints_data[80]["live_count"] == 9
    assert checkpoints_data[80]["exact_duplicates_count"] == 0
    assert len(checkpoints_data[80]["surface_map"].get("يشرب", [])) >= 2
    assert len(checkpoints_data[80]["surface_map"].get("حليب", [])) >= 2
    assert len(checkpoints_data[80]["surface_map"].get("ماء", [])) >= 2


def test_f01_task2_canonical_eos_structural_duplicate_collision() -> None:
    """Task 2 & R1-M01: Canonical EOS training naturally generates EXACT_STRUCTURAL_DUPLICATE Assemblies (5 & 6)."""
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
    )

    branch_ab = encode_exposure("القط يشرب حليب", append_eos=True)
    branch_db = encode_exposure("النسر يشرب ماء", append_eos=True)

    for root_id in range(1, 57):
        is_ab = (root_id % 2 != 0)
        envs = branch_ab if is_ab else branch_db
        tx.begin_exposure(root_id)
        for env in envs:
            core_ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        tx.end_exposure(root_id)

    # Verify exact duplicate assemblies exist
    member_sets: dict[tuple[int, ...], list[int]] = {}
    for a in state.W.assemblies.values():
        if a.status == AssemblyStatus.LIVE:
            m_tuple = tuple(sorted(a.member_cell_ids))
            member_sets.setdefault(m_tuple, []).append(a.assembly_id)

    exact_duplicates = {m: ids for m, ids in member_sets.items() if len(ids) > 1}
    assert len(exact_duplicates) == 1
    dup_members, dup_ids = next(iter(exact_duplicates.items()))
    assert set(dup_ids) == {5, 6}
    assert dup_members == (8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116, 12117)
    # Both are attested to EOS
    res5 = ledger.resolve_readout(5, state.W.assemblies[5].structural_generation, current_live_generation=state.W.assemblies[5].structural_generation)
    res6 = ledger.resolve_readout(6, state.W.assemblies[6].structural_generation, current_live_generation=state.W.assemblies[6].structural_generation)
    assert res5.envelope.marker == Marker.EOS
    assert res6.envelope.marker == Marker.EOS


def test_f01_task3_natural_contextual_z_contamination() -> None:
    """Task 3 (R1-M02): Verify that graduated contextual z enters lexical Assembly and depresses CoreCoverage on rival branch."""
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
    )

    branch_ab = encode_exposure("القط يشرب حليب", append_eos=False)
    branch_db = encode_exposure("النسر يشرب ماء", append_eos=False)

    for root_id in range(1, 57):
        is_ab = (root_id % 2 != 0)
        envs = branch_ab if is_ab else branch_db
        tx.begin_exposure(root_id)
        for env in envs:
            core_ev = encode_lexical_token_event(
                env.peripheral_surface.raw_surface_nfc_utf8,
                exposure_id=root_id,
                event_order=env.core_event.event_order,
                boundary=env.core_event.boundary,
            ).core_event
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        tx.end_exposure(root_id)

    # In natural learning, Assembly 1 is formed for "يشرب"
    asm1 = state.W.assemblies[1]
    z_cells_in_asm1 = [cid for cid in asm1.member_cell_ids if cid in state.W.stable_bindings]
    # Direct physical membership confirmed
    assert len(z_cells_in_asm1) == 1
    z_ab = z_cells_in_asm1[0]
    assert z_ab == 8321

    # Measure CoreCoverage under both contexts
    ro_ab = run_read_only_episode(state, [branch_ab[0].core_event, branch_ab[1].core_event])
    ro_db = run_read_only_episode(state, [branch_db[0].core_event, branch_db[1].core_event])
    cov_ab = compute_core_coverage(asm1, ro_ab.event_results[1], state.H_slow)
    cov_db = compute_core_coverage(asm1, ro_db.event_results[1], state.H_slow)

    # In branch AB, z_ab is active (G_ctx=1) -> CoreCoverage = 1.0 (5/5 cells)
    assert cov_ab == 1.0
    # In branch DB, z_ab is gated off (G_ctx=0, A=0.0) -> CoreCoverage drops to 0.80 (4/5 cells)
    assert cov_db == 0.80, "Expected CoreCoverage drop to 0.80 due to contextual z silencing on DB branch"


def test_f01_task4_readout_causal_gain_and_dilution_analysis() -> None:
    """Task 4 (R1-M03): Measure member-level gains, exclusion of Pass-2 lateral gain, and score dilution."""
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
    )

    branch_ab = encode_exposure("القط يشرب حليب", append_eos=False)
    branch_db = encode_exposure("النسر يشرب ماء", append_eos=False)

    for root_id in range(1, 35):
        is_ab = (root_id % 2 != 0)
        envs = branch_ab if is_ab else branch_db
        tx.begin_exposure(root_id)
        for env in envs:
            core_ev = encode_lexical_token_event(
                env.peripheral_surface.raw_surface_nfc_utf8,
                exposure_id=root_id,
                event_order=env.core_event.event_order,
                boundary=env.core_event.boundary,
            ).core_event
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        tx.end_exposure(root_id)

    # Ingest prompt 'القط يشرب'
    scratch = state.clone()
    scratch.R.reset_cold()
    for idx, ev in enumerate([branch_ab[0].core_event, branch_ab[1].core_event]):
        proj = project_core_event_v1(ev)
        execute_two_pass_event(
            scratch,
            proj.x_fixed_by_global_id,
            proj.x_float_by_global_id,
            mode=ExecutionMode.RETRIEVE,
            origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=(idx == 0),
            event_order=idx,
            allow_candidate_probe=False,
            admit_uncommitted_sensory=False,
        )

    # Run FULL vs CONTROL
    scratch_full = scratch.clone()
    scratch_ctrl = scratch.clone()
    res_full = execute_two_pass_event(
        scratch_full, {}, {},
        mode=ExecutionMode.RETRIEVE, origin=EventOrigin.READ_ONLY_OBSERVED,
        boundary=False, event_order=2, allow_candidate_probe=False,
        admit_uncommitted_sensory=False, control_zero_pt=False,
    )
    res_ctrl = execute_two_pass_event(
        scratch_ctrl, {}, {},
        mode=ExecutionMode.RETRIEVE, origin=EventOrigin.READ_ONLY_OBSERVED,
        boundary=False, event_order=2, allow_candidate_probe=False,
        admit_uncommitted_sensory=False, control_zero_pt=True,
    )

    # Inspect Assembly 5 ("حليب", |G|=4)
    asm5 = state.W.assemblies[5]
    members = sorted(asm5.member_cell_ids)
    assert len(members) == 4

    gains = [max(res_full.a_plus_by_cell.get(m, 0.0) - res_ctrl.a_plus_by_cell.get(m, 0.0), 0.0) for m in members]
    pts = [res_full.pt_by_cell.get(m, 0.0) for m in members]
    pss = [res_full.ps_by_cell.get(m, 0.0) for m in members]
    eligs = [(pt > 0.0 and g > 0.0) for pt, g in zip(pts, gains)]

    # Exactly 2 members have P_T > 0 (direct targets)
    assert sum(1 for pt in pts if pt > 0.0) == 2
    # Exactly 2 members have P_T == 0 but P_S > 0 and positive causal gain!
    excluded_gains = [g for g, pt in zip(gains, pts) if pt == 0.0 and g > 0.0]
    assert len(excluded_gains) == 2, "Expected 2 members with positive causal gain to be excluded due to P_T == 0"

    # Production score divides sum of eligible gains by |G| = 4
    prod_readout = evaluate_full_vs_control_readout(scratch, theta_read=0.08, m_read=0.04)
    assert prod_readout.status.name == "NO_MATCH"
    assert prod_readout.top_score < 0.08
    assert abs(prod_readout.top_score - (sum(g for g, e in zip(gains, eligs) if e) / 4.0)) < 1e-4
