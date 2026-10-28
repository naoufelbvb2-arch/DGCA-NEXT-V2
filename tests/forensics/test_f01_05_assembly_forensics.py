"""Forensic Investigation Phase D: ASSEMBLY FORENSICS (R1-M01, R1-M02, R1-M03).

Investigates:
- F01-05: Exact duplicate Assemblies and why they fail to merge (between_strength = 0.0)
- F01-06: Contextual z cell contamination of lexical Assemblies
- F01-07: Readout score dilution and exclusion of indirect causal gain (P_T > 0 requirement)
"""

from __future__ import annotations

import pytest
from dgca.common.hashing import Region
from dgca.core.anatomy import Synapse, SynapseScope, SynapseState
from dgca.core.assembly import _try_merge_pair, execute_assembly_end_pipeline, is_eligible_assembly_member_cell
from dgca.core.generator import generate_episode
from dgca.core.readout import evaluate_full_vs_control_readout
from dgca.core.state import (
    Assembly,
    AssemblyStatus,
    BindingStatus,
    ExecutionMode,
    MachineState,
    StableBinding,
)
from dgca.experiments.gates import _wire_consolidated_synapse


def test_f01_05_exact_duplicate_assemblies_cannot_merge() -> None:
    """F01-05 (R1-M01): Verify that exact duplicate assemblies (identical member sets) fail MERGE."""
    state = MachineState()
    # Cells for triangle
    c1, c2, c3 = 8200, 8208, 8216
    for c in (c1, c2, c3):
        state.W.commit_cell(c, 0)
    for u in (c1, c2, c3):
        for v in (c1, c2, c3):
            if u != v:
                _wire_consolidated_synapse(state, u, v, SynapseScope.LOCAL, s_val=0.85)

    # Create two identical live assemblies with the EXACT SAME member cells
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

    # Attempt merge
    merged = _try_merge_pair(1, 2, state.W, {})

    # Forensic analysis:
    # Jaccard is 1.0 (>= THETA_MERGE 0.70).
    # But assembly.py:539-540:
    #   excl_a = set_a - set_b = []
    #   excl_b = set_b - set_a = []
    #   if not excl_a or not excl_b: between_strength = 0.0
    # Because 0.0 < THETA_OB (0.50), _try_merge_pair returns False!
    print(f"\n[F01-05] Did exact duplicates merge? {merged}")
    assert merged is False, "DEFECT NOT OBSERVED: exact duplicates unexpectedly merged"
    assert asm1.status == AssemblyStatus.LIVE
    assert asm2.status == AssemblyStatus.LIVE, "Duplicate assembly survived MERGE!"


def test_f01_06_contextual_z_cell_contamination() -> None:
    """F01-06 (R1-M02): Verify that a graduated contextual cell z is permitted into an Assembly."""
    state = MachineState()
    z_id = 8320
    c0, c1 = 8200, 8208
    state.W.commit_cell(z_id, 0)
    state.W.commit_cell(c0, 0)
    state.W.commit_cell(c1, 0)

    # Add active stable binding for z
    state.W.stable_bindings[z_id] = StableBinding(
        schema_version=2,
        z_cell_id=z_id,
        anchor_id=c0,
        owner_seq=1,
        binding_generation=1,
        p_keys=((8192, z_id, SynapseScope.ASSOCIATIVE), (8193, z_id, SynapseScope.ASSOCIATIVE)),
        l_z_q6=500_000,
        u_z_q6=100_000,
        tau_ctx_q6=150_000,
        c_keys=((c0, z_id, SynapseScope.LOCAL), (c1, z_id, SynapseScope.LOCAL)),
        y_keys=((z_id, 8224, SynapseScope.ASSOCIATIVE),),
        anchor_source_set=frozenset((c0, c1)),
        status=BindingStatus.ACTIVE,
        depth=1,
    )
    # Wire consolidated synapses so binding is legal
    for k in state.W.stable_bindings[z_id].p_keys:
        state.W.commit_cell(k[0], 0)
        _wire_consolidated_synapse(state, k[0], k[1], k[2])
    for k in state.W.stable_bindings[z_id].c_keys:
        _wire_consolidated_synapse(state, k[0], k[1], k[2])
    for k in state.W.stable_bindings[z_id].y_keys:
        state.W.commit_cell(k[1], 0)
        _wire_consolidated_synapse(state, k[0], k[1], k[2])

    # Check eligibility of z_id for Assembly membership
    is_eligible = is_eligible_assembly_member_cell(z_id, state.W)
    print(f"\n[F01-06] Is contextual cell z eligible for assembly membership? {is_eligible}")
    # assembly.py:78-84 explicitly allows graduated contextual cells with ACTIVE binding!
    assert is_eligible is True, "DEFECT NOT OBSERVED: contextual z was rejected from assembly membership"


def test_f01_07_readout_score_dilution_and_indirect_gain_exclusion() -> None:
    """F01-07 (R1-M03): Verify that readout score is diluted by non-target members and indirect gain is zeroed."""
    state = MachineState()
    # Create an assembly with 3 members: 1 direct target, 2 indirect members
    t1 = 8200
    m2 = 8208
    m3 = 8216
    for c in (t1, m2, m3):
        state.W.commit_cell(c, 0)
    for u in (t1, m2, m3):
        for v in (t1, m2, m3):
            if u != v:
                _wire_consolidated_synapse(state, u, v, SynapseScope.LOCAL, s_val=0.85)

    asm = Assembly(
        assembly_id=1,
        region=Region.LANGUAGE,
        member_cell_ids=frozenset((t1, m2, m3)),
        structural_generation=1,
        status=AssemblyStatus.LIVE,
    )
    state.W.assemblies[1] = asm

    # Set up source cell that projects only to t1
    src = 8300
    state.W.commit_cell(src, 0)
    _wire_consolidated_synapse(state, src, t1, SynapseScope.ASSOCIATIVE, s_val=0.80)

    # Set state.R so P_T is generated to t1
    state.R.A[src] = 0.90
    state.R.F_step = frozenset((src,))
    state.R.mu_source_mask = {src: 0}

    # Evaluate readout
    res = evaluate_full_vs_control_readout(
        state,
        theta_read=0.08,
        m_read=0.04,
    )

    # Check gains: t1 has direct gain, m2 and m3 might have synchronous gain in Pass 2
    gain_t1 = res.gain_by_cell.get(t1, 0.0)
    gain_m2 = res.gain_by_cell.get(m2, 0.0)
    gain_m3 = res.gain_by_cell.get(m3, 0.0)

    print(f"\n[F01-07] Causal gains: t1={gain_t1:.4f}, m2={gain_m2:.4f}, m3={gain_m3:.4f}")
    print(f"  Eligible next cells: {res.eligible_next_cells}")
    print(f"  Top readout score: {res.top_score:.4f}")

    # Because P_T > 0 is ONLY true for t1, eligible_next_cells contains ONLY t1!
    # Even if m2/m3 had positive activity, their gain is excluded (eligibleNext = 0).
    # And total_gain is divided by |G| = 3!
    assert t1 in res.eligible_next_cells
    assert m2 not in res.eligible_next_cells
    assert m3 not in res.eligible_next_cells

    expected_score = gain_t1 / 3.0
    assert abs(res.top_score - expected_score) < 1e-6, "Score dilution confirmed: divided by |G|=3"
