"""Forensic Investigation F01-01: READ_ONLY_W_IMMUTABILITY (R1-B01).

Investigates mutation of permanent W state during read-only RETRIEVE execution.
Normative contract: Read-only inference must NOT mutate W, H_slow, or caller R.
"""

from __future__ import annotations

from dgca.common.errors import StatusCode
from dgca.core.anatomy import SynapseScope
from dgca.core.context_gate import evaluate_context_gate_for_cell
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import (
    BindingStatus,
    ExecutionMode,
    MachineState,
    StableBinding,
)
from dgca.encoder.envelope import encode_lexical_token_event
from dgca.lifecycle.exposure_tx import run_read_only_episode


def test_f01_01_scenario_a_activity_timestamps_mutation() -> None:
    """F01-01 Scenario A: verify whether last_referenced_event in W is mutated during RETRIEVE."""
    state = MachineState()
    ev_a = encode_lexical_token_event("القط", exposure_id=None, event_order=0, boundary=True).core_event
    proj = project_core_event_v1(ev_a)
    cids = list(proj.x_fixed_by_global_id.keys())
    cid = cids[0]

    state.W.commit_cell(cid, 0)
    state.W.last_referenced_event[cid] = 42
    state.W.global_event_clock = 999

    before_val = state.W.last_referenced_event[cid]
    # Execute genuine read-only episode
    ro_res = run_read_only_episode(state, [ev_a])
    after_val = state.W.last_referenced_event[cid]

    # Forensic verification (R1-B01):
    # Under normative contract, last_referenced_event should not be mutated.
    # In actual implementation (dynamics.py:678), w.last_referenced_event[cid] is updated to 999!
    is_mutated = (before_val != after_val)
    print(f"\n[F01-01 Scenario A] Mutated: {is_mutated} (Before: {before_val}, After: {after_val})")
    assert is_mutated is True, "DEFECT NOT OBSERVED: last_referenced_event was unexpectedly not mutated"
    assert after_val == 999


def test_f01_01_scenario_b_stale_binding_mutation_during_read_only() -> None:
    """F01-01 Scenario B: verify whether an ACTIVE binding with an invalid link mutates W during read-only inference."""
    state = MachineState()
    z_id = 8300
    p0, p1 = 8200, 8208
    c0 = 8216
    y0 = 8224

    for c in (z_id, p0, p1, c0, y0):
        state.W.commit_cell(c, 0)

    # Add active binding with a required P synapse that is MISSING from W.synapses
    binding = StableBinding(
        schema_version=2,
        z_cell_id=z_id,
        anchor_id=c0,
        owner_seq=1,
        binding_generation=1,
        p_keys=((p0, z_id, SynapseScope.ASSOCIATIVE), (p1, z_id, SynapseScope.ASSOCIATIVE)),
        l_z_q6=500_000,
        u_z_q6=100_000,
        tau_ctx_q6=150_000,
        c_keys=((c0, z_id, SynapseScope.LOCAL),),
        y_keys=((z_id, y0, SynapseScope.ASSOCIATIVE),),
        anchor_source_set=frozenset((c0,)),
        status=BindingStatus.ACTIVE,
        depth=1,
    )
    state.W.stable_bindings[z_id] = binding

    # Check status before inference
    assert state.W.stable_bindings[z_id].status == BindingStatus.ACTIVE

    # Invoke read-only context gate evaluation
    g_ctx, g_probe, diags = evaluate_context_gate_for_cell(
        z_id,
        state.W,
        boundary=False,
        prev_supports={},
        curr_supports={},
        mode=ExecutionMode.RETRIEVE,
        committed_before_event=state.W.committed_cells,
    )

    # 1. Correctly refuses invalid route
    assert g_ctx == 0
    assert StatusCode.STALE_CONTEXT_BINDING in diags

    # 2. Defect confirmation (R1-B01): binding status was mutated from ACTIVE to STALE in permanent W!
    assert state.W.stable_bindings[z_id].status == BindingStatus.STALE, (
        "Expected binding.status to be mutated to STALE in W, confirming R1-B01"
    )
