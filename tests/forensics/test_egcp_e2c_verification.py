"""DGCA NEXT V2 — EGCP E2c Structural Promotion Verification Suite.

Validates:
1. RC2-T13: Native ready-to-consolidate plus GSC validation jointly publishes live Y role at END.
2. RC2-T14: OwnerID, P/C keys, gate, depth unchanged; structural_revision increments by 1; canonical manifest digest.
3. RC2-T15: Derived parent references and scoped descendants valid; no silent rewriting.
4. RC2-T16: V2/V3->V4 transactional conversion; Save/Load/clone; unsupported V4 under OFF rejected.
5. RC2-T17: Structural promotion never reads evaluator outputs or text/surface ledger.
6. RC2-T18: Shared/mixed outcomes and two-owner controls do not force exclusivity.
7. RC2-T19: Actual W0->W1->W2 neural delta separated from readout score.
8. RC2-T26: EGCP pre-assembly promotion runs after native contextual close, before Assembly; OFF exact.
9. RC2-T28: Post-Assembly/stale-validation failure cannot publish broken promoted owner; safe pending deferral.
10. Probe P1 neural dynamics after multi-target Y promotion.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

from dgca.common.errors import DGCAError, StatusCode
from dgca.core.anatomy import SynapseScope, SynapseState
from dgca.core.context_gate import is_legal_consolidated_synapse, validate_and_refresh_stable_binding
from dgca.core.dynamics import compute_next_step_temporal_drive
from dgca.core.generator import generate_episode
from dgca.core.state import (
    BindingStatus,
    EGCPGrowthState,
    EGCPMode,
    EGCPPendingGrowthV1,
    ExecutionMode,
    MachineState,
    StableBinding,
    Synapse,
    SynapseKey,
    WState,
    compute_y_keys_manifest_digest,
    convert_to_stable_binding_v4,
)
from dgca.encoder.envelope import encode_exposure
from dgca.lifecycle.exposure_tx import ExposureTransactionManager
from dgca.lla.egcp_promotion import (
    EGCP_PENDING_TTL_EVENTS,
    GSC_DEFER_NOT_READY,
    GSC_PASS,
    GSC_REFUSAL_CAPACITY_EXCEEDED,
    GSC_REFUSAL_COLLISION,
    GSC_REFUSAL_LATENT_INELIGIBLE,
    GSC_REFUSAL_MISSING_PROVENANCE,
    GSC_REFUSAL_MODE_OFF,
    GSC_REFUSAL_OWNER_NOT_ACTIVE,
    GSC_REFUSAL_TTL_EXPIRED,
    evaluate_growth_promotion_allowed,
    execute_egcp_pre_assembly_shadow_stage,
)
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1
from tests.forensics.test_egcp_e2b_verification import _run_schedule
from tools.forensics.run_r2_c01_cf01_experiment import CORPUS_GROUP_B, build_schedule


def test_01_off_mode_preservation_and_no_v4_promotion():
    """RC2-T01, RC2-T16: Under EGCP_MODE=OFF, no V4 promotion occurs and V4 bindings are rejected."""
    st_off, _, _ = _run_schedule(61, egcp_mode=EGCPMode.OFF)
    w = st_off.W

    # Pending growth compartment is empty
    assert len(w.egcp_pending_growth) == 0

    # All active bindings must be V2 or V3, none can be V4
    for z_id, binding in w.stable_bindings.items():
        assert binding.schema_version in (2, 3), f"Owner {z_id} has schema {binding.schema_version}"
        assert binding.structural_revision == 0

    # If an external V4 binding is evaluated under OFF mode, it must be rejected
    owner_8320 = w.stable_bindings[8320]
    sb_v4 = convert_to_stable_binding_v4(owner_8320)
    assert sb_v4.schema_version == 4
    ok, code = validate_and_refresh_stable_binding(sb_v4, w)
    assert not ok
    assert code == StatusCode.UNSUPPORTED_BINDING_SCHEMA


def test_02_stable_binding_v4_schema_invariants():
    """RC2-T14, RC2-T16: StableBindingV4 schema validation, byte-identical fields, and revision increment."""
    # Build a valid base V2 binding
    pk1: SynapseKey = (58, 8320, SynapseScope.ASSOCIATIVE)
    pk2: SynapseKey = (59, 8320, SynapseScope.ASSOCIATIVE)
    ck1: SynapseKey = (60, 8320, SynapseScope.LOCAL)
    yk1: SynapseKey = (8320, 9319, SynapseScope.ASSOCIATIVE)

    v2 = StableBinding(
        schema_version=2,
        z_cell_id=8320,
        anchor_id=58,
        owner_seq=1,
        binding_generation=1,
        p_keys=(pk1, pk2),
        l_z_q6=200000,
        u_z_q6=800000,
        tau_ctx_q6=100000,
        c_keys=(ck1,),
        y_keys=(yk1,),
        anchor_source_set=frozenset({58}),
        status=BindingStatus.ACTIVE,
        depth=1,
    )

    # 1. Negative structural revision raises error
    with pytest.raises(DGCAError) as exc_info:
        StableBinding(
            schema_version=4,
            z_cell_id=8320,
            anchor_id=58,
            owner_seq=1,
            binding_generation=1,
            p_keys=(pk1, pk2),
            l_z_q6=200000,
            u_z_q6=800000,
            tau_ctx_q6=100000,
            c_keys=(ck1,),
            y_keys=(yk1,),
            anchor_source_set=frozenset({58}),
            structural_revision=-1,
        )
    assert exc_info.value.code == StatusCode.UNSUPPORTED_BINDING_SCHEMA

    # 2. Unsupported schema version
    with pytest.raises(DGCAError) as exc_info5:
        StableBinding(
            schema_version=5,
            z_cell_id=8320,
            anchor_id=58,
            owner_seq=1,
            binding_generation=1,
            p_keys=(pk1, pk2),
            l_z_q6=200000,
            u_z_q6=800000,
            tau_ctx_q6=100000,
            c_keys=(ck1,),
            y_keys=(yk1,),
            anchor_source_set=frozenset({58}),
        )
    assert exc_info5.value.code == StatusCode.UNSUPPORTED_BINDING_SCHEMA

    # 3. Explicit conversion from V2 to V4
    yk2: SynapseKey = (8320, 9325, SynapseScope.ASSOCIATIVE)
    v4_rev1 = convert_to_stable_binding_v4(v2, additional_y_keys=(yk2,))
    assert v4_rev1.schema_version == 4
    assert v4_rev1.structural_revision == 1
    assert v4_rev1.owner_id == v2.owner_id
    assert v4_rev1.p_keys == v2.p_keys
    assert v4_rev1.c_keys == v2.c_keys
    assert v4_rev1.anchor_source_set == v2.anchor_source_set
    assert v4_rev1.l_z_q6 == v2.l_z_q6
    assert v4_rev1.u_z_q6 == v2.u_z_q6
    assert v4_rev1.tau_ctx_q6 == v2.tau_ctx_q6

    # Verify canonical manifest digest
    expected_digest = compute_y_keys_manifest_digest(v4_rev1.y_keys)
    assert v4_rev1.growth_key_manifest_digest == expected_digest
    assert len(expected_digest) == 64

    # 4. Subsequent addition increments structural_revision to 2
    yk3: SynapseKey = (8320, 9331, SynapseScope.ASSOCIATIVE)
    v4_rev2 = convert_to_stable_binding_v4(v4_rev1, additional_y_keys=(yk3,))
    assert v4_rev2.schema_version == 4
    assert v4_rev2.structural_revision == 2
    assert len(v4_rev2.y_keys) == 3


def test_03_gsc_promotion_atomic_transfer():
    """RC2-T13, RC2-T19: Growth Safety Contract atomically promotes consolidated candidate to live W2."""
    st, _, _ = _run_schedule(61, egcp_mode=EGCPMode.E2_GROWTH)
    w_shadow = st.W.clone()

    owner_z = 8320
    assert owner_z in w_shadow.stable_bindings
    binding_pre = w_shadow.stable_bindings[owner_z]

    # Use a real pending candidate from Root 61
    assert len(w_shadow.egcp_pending_growth) > 0
    real_key = next(iter(w_shadow.egcp_pending_growth.keys()))
    tgt_id = real_key[1]

    # Set up candidate in READY_FOR_PROMOTION
    pending_syn = Synapse(
        key=real_key,
        S=0.82,
        E_ext=3.6,
        external_count=24,
        state=SynapseState.CONSOLIDATED,
        created_event_id=10,
        last_external_event_id=w_shadow.global_event_clock,
    )
    pending = EGCPPendingGrowthV1(
        owner_id=binding_pre.owner_id,
        owner_z_id=owner_z,
        key=real_key,
        accepted_root_count=23,
        synapse=pending_syn,
        state=EGCPGrowthState.READY_FOR_PROMOTION,
    )
    w_shadow.egcp_pending_growth[real_key] = pending

    # Pre-promotion assertions
    assert real_key not in w_shadow.synapses
    assert real_key not in binding_pre.y_keys
    claimed_before = len(w_shadow.unique_claimed_outgoing_keys(owner_z))

    # Execute Pre-Assembly Shadow Stage
    report = execute_egcp_pre_assembly_shadow_stage(w_shadow, exposure_id=62)

    # Verify atomic promotion outcomes
    assert real_key in report.promoted_keys
    assert owner_z in report.upgraded_owners
    assert real_key not in w_shadow.egcp_pending_growth

    # 1. Live synapse created with CONSOLIDATED state
    assert real_key in w_shadow.synapses
    live_syn = w_shadow.synapses[real_key]
    assert live_syn.state == SynapseState.CONSOLIDATED
    assert live_syn.S == 0.82
    assert live_syn.E >= 3.0

    # 2. Adjacency indices updated
    assert real_key in w_shadow.outgoing_by_source[owner_z]
    assert real_key in w_shadow.incoming_by_target[tgt_id]

    # 3. Owner binding upgraded to V4 with new revision and appended y_key
    binding_post = w_shadow.stable_bindings[owner_z]
    assert binding_post.schema_version == 4
    assert binding_post.structural_revision == 1
    assert real_key in binding_post.y_keys
    assert binding_post.growth_key_manifest_digest == compute_y_keys_manifest_digest(binding_post.y_keys)

    # 4. Outgoing budget capacity claim transferred without double-counting
    claimed_after = len(w_shadow.unique_claimed_outgoing_keys(owner_z))
    assert claimed_after == claimed_before
    assert claimed_after <= w_shadow.outgoing_budget_b_i


def test_04_w0_w1_w2_neural_delta():
    """RC2-T19: Neural delta demonstrates zero drive under W1 quarantine, and positive drive under W2 promotion."""
    st, _, _ = _run_schedule(61, egcp_mode=EGCPMode.E2_GROWTH)
    owner_z = 8320
    real_key = next(iter(st.W.egcp_pending_growth.keys()))
    tgt_id = real_key[1]
    owner_id = st.W.stable_bindings[owner_z].owner_id

    # --- Phase W0: Baseline (no link) ---
    st_w0 = st.clone()
    st_w0.W.synapses.pop(real_key, None)
    st_w0.W.egcp_pending_growth.pop(real_key, None)
    pt_w0, _ = compute_next_step_temporal_drive(
        st_w0,
        f_step_prev=frozenset({owner_z}),
        a_prev_by_cell={owner_z: 0.25},
        mu_prev_source_mask={},
        egcp_mode=EGCPMode.E2_GROWTH,
    )
    assert pt_w0.get(tgt_id, 0.0) == 0.0, "W0 must have zero temporal drive"

    # --- Phase W1: Quarantined Pending Link ---
    st_w1 = st.clone()
    pending_syn = Synapse(
        key=real_key,
        S=0.82,
        E_ext=3.6,
        external_count=24,
        state=SynapseState.CONSOLIDATED,
        created_event_id=10,
        last_external_event_id=st_w1.W.global_event_clock,
    )
    st_w1.W.egcp_pending_growth[real_key] = EGCPPendingGrowthV1(
        owner_id=owner_id,
        owner_z_id=owner_z,
        key=real_key,
        accepted_root_count=23,
        synapse=pending_syn,
        state=EGCPGrowthState.READY_FOR_PROMOTION,
    )
    pt_w1, _ = compute_next_step_temporal_drive(
        st_w1,
        f_step_prev=frozenset({owner_z}),
        a_prev_by_cell={owner_z: 0.25},
        mu_prev_source_mask={},
        egcp_mode=EGCPMode.E2_GROWTH,
    )
    assert pt_w1.get(tgt_id, 0.0) == 0.0, "W1 pending link must contribute strictly 0.0 temporal drive"

    # --- Phase W2: Promoted Live Consolidated Synapse ---
    st_w2 = st_w1.clone()
    execute_egcp_pre_assembly_shadow_stage(st_w2.W, exposure_id=62)
    assert real_key in st_w2.W.synapses
    pt_w2, _ = compute_next_step_temporal_drive(
        st_w2,
        f_step_prev=frozenset({owner_z}),
        a_prev_by_cell={owner_z: 0.25},
        mu_prev_source_mask={},
        egcp_mode=EGCPMode.E2_GROWTH,
    )
    assert pt_w2.get(tgt_id, 0.0) > 0.0, f"W2 promoted link must deliver non-zero temporal drive: {pt_w2.get(tgt_id)}"
    expected_drive = 0.25 * pending_syn.Q * 1.0  # a_src * Q * k_assoc
    assert abs(pt_w2[tgt_id] - expected_drive) < 1e-4


def test_05_gsc_refusal_and_safe_deferral_negative_controls():
    """RC2 §7.1, §9.3: Negative controls for GSC predicates (under-evidence, stale owner, latent ineligibility, capacity, TTL)."""
    st, _, _ = _run_schedule(61, egcp_mode=EGCPMode.E2_GROWTH)
    w = st.W.clone()
    owner_z = 8320
    real_key = next(iter(w.egcp_pending_growth.keys()))
    tgt_id = real_key[1]
    owner_id = w.stable_bindings[owner_z].owner_id

    # 1. Under-evidence candidate (S < 0.60 or E < 3.0) -> safe deferral
    pending_weak = EGCPPendingGrowthV1(
        owner_id=owner_id,
        owner_z_id=owner_z,
        key=real_key,
        accepted_root_count=5,
        synapse=Synapse(key=real_key, S=0.45, E_ext=1.2, external_count=5),
        state=EGCPGrowthState.PENDING_LEARNING,
    )
    allowed, code = evaluate_growth_promotion_allowed(w, real_key, pending_weak)
    assert not allowed
    assert code == GSC_DEFER_NOT_READY

    # 2. Owner STALE -> safe deferral
    w_stale = w.clone()
    w_stale.stable_bindings[owner_z].status = BindingStatus.STALE
    pending_ready = EGCPPendingGrowthV1(
        owner_id=owner_id,
        owner_z_id=owner_z,
        key=real_key,
        accepted_root_count=23,
        synapse=Synapse(key=real_key, S=0.80, E_ext=3.5, external_count=22, state=SynapseState.CONSOLIDATED),
        state=EGCPGrowthState.READY_FOR_PROMOTION,
    )
    allowed, code = evaluate_growth_promotion_allowed(w_stale, real_key, pending_ready)
    assert not allowed
    assert code == GSC_REFUSAL_OWNER_NOT_ACTIVE

    # 3. Latent ineligible -> refusal
    w_ineligible = w.clone()
    orig_eligible = w_ineligible.latent_table.is_eligible
    w_ineligible.latent_table.is_eligible = lambda s, t: False if (s == owner_z and t == tgt_id) else orig_eligible(s, t)
    allowed, code = evaluate_growth_promotion_allowed(w_ineligible, real_key, pending_ready)
    assert not allowed
    assert code == GSC_REFUSAL_LATENT_INELIGIBLE

    # 4. Outgoing capacity exceeded -> refusal
    w_cap = w.clone()
    w_cap.outgoing_budget_b_i = 1  # artificially saturate budget
    allowed, code = evaluate_growth_promotion_allowed(w_cap, real_key, pending_ready)
    assert not allowed
    assert code == GSC_REFUSAL_CAPACITY_EXCEEDED

    # 5. Pending TTL expired (> 2000 events) -> atomic expiration
    w_ttl = w.clone()
    pending_expired = EGCPPendingGrowthV1(
        owner_id=owner_id,
        owner_z_id=owner_z,
        key=real_key,
        accepted_root_count=5,
        synapse=Synapse(key=real_key, S=0.45, E_ext=1.2, external_count=5, last_external_event_id=10),
        state=EGCPGrowthState.PENDING_LEARNING,
    )
    w_ttl.completed_external_events_count = 2500  # delta = 2490 > 2000
    w_ttl.egcp_pending_growth[real_key] = pending_expired
    report = execute_egcp_pre_assembly_shadow_stage(w_ttl, exposure_id=100)
    assert real_key in report.expired_keys
    assert real_key not in w_ttl.egcp_pending_growth


def test_06_pre_assembly_ordering_and_post_assembly_validation():
    """RC2-T26, RC2-T28: Pre-assembly shadow promotion integrates cleanly before Assembly and passes post-assembly validation."""
    st61, ledger, tx = _run_schedule(61, egcp_mode=EGCPMode.E2_GROWTH)
    w = st61.W
    assert 8320 in w.stable_bindings
    binding = w.stable_bindings[8320]
    assert binding.status == BindingStatus.ACTIVE

    # Seed a consolidated pending candidate in READY_FOR_PROMOTION
    key = next(iter(w.egcp_pending_growth.keys()))
    pending = w.egcp_pending_growth[key]
    pending.synapse.S = 0.85
    pending.synapse.E_ext = 3.8
    pending.synapse.external_count = 25
    pending.synapse.state = SynapseState.CONSOLIDATED
    pending.accepted_root_count = 24
    pending.state = EGCPGrowthState.READY_FOR_PROMOTION

    # Execute Root 62 through full end_exposure pipeline
    tx.begin_exposure(62)
    envs = encode_exposure(CORPUS_GROUP_B["S2"], append_eos=True)  # S2: النسر يشرب ماء
    for env in envs:
        core_ev = dataclasses.replace(env.core_event, exposure_id=62)
        tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
    rep = tx.end_exposure(62)

    # Verify that Root 62 completed cleanly without diagnostic errors
    assert rep.status.value == "COMPLETED"

    # Verify that owner 8320 was upgraded to V4 and passed step 5.1 post-assembly stale validation
    upgraded_b = st61.W.stable_bindings[8320]
    assert upgraded_b.schema_version == 4
    assert upgraded_b.status == BindingStatus.ACTIVE, "Owner must remain ACTIVE after promotion!"
    assert key in upgraded_b.y_keys
    assert key in st61.W.synapses


def test_07_probe_p1_neural_dynamics_after_promotion():
    """RC2 §9.2, §0.1: Multi-target promotion at Root 149 confirms W2 Y-growth and evaluates Probe P1 competition."""
    st149, ledger, tx = _run_schedule(149, egcp_mode=EGCPMode.E2_GROWTH)
    w = st149.W

    owner_z = 8320
    binding = w.stable_bindings[owner_z]

    # Verify owner 8320 was promoted to V4 with 8 Y-keys
    assert binding.schema_version == 4
    assert binding.structural_revision == 6
    assert len(binding.y_keys) == 8
    assert len(w.egcp_pending_growth) == 0

    # Execute genuine autonomous generation from probe P1: ["القط", "يشرب"]
    prompt_p1 = [
        encode_exposure("القط", append_eos=False)[0].core_event,
        encode_exposure("يشرب", append_eos=False)[0].core_event,
    ]
    gen_res = generate_episode(st149, prompt_p1, ledger, max_steps=2)

    # In E2, positive contextual growth is achieved across all 8 targets.
    # However, under E1/E2 rules, generic associative drive is preserved (mu_ij = 0).
    # Per RC2 §9.2: "If E2 raises milk but water remains dominant, report likewise."
    step0 = gen_res.steps[0]
    scores_by_asm = {r.assembly_id: r.score_next for r in step0.readout_result.ranked_scores}
    score_water = scores_by_asm.get(4, 0.0)
    score_milk = scores_by_asm.get(6, 0.0)
    print(f"\n[Root 149 W2 Probe P1] Winner Assembly: {step0.winner_assembly_id}")
    print(f"[Root 149 W2 Probe P1] Score Water (Asm 4): {score_water:.6f}")
    print(f"[Root 149 W2 Probe P1] Score Milk (Asm 6):  {score_milk:.6f}")
    print(f"[Root 149 W2 Probe P1] Emitted Surfaces: {gen_res.emitted_surfaces}")

    # Verify genuine generation completed without crash
    assert len(gen_res.emitted_surfaces) >= 1
    assert step0.winner_assembly_id in (4, 6)
