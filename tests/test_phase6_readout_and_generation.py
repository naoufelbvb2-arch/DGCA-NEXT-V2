"""Phase 6 Tests: Peripheral SurfaceReadoutLedgerV1, FULL vs CONTROL Readout, and GENERATE_EPISODE.

Covers normative test vectors:
- LG-T03: Stale Assembly structural_generation rejection (`GEN_STOP_STALE_ASSEMBLY`) & no backdating
- LG-T07: One-time P_T consumption debit on `INTERNAL_SELECTED` rollout step
- LG-T08: Multi-surface and same-surface/different-bundle readout ledger collisions
- LG-T09: Minimum 2 independent completed external roots for peripheral readout attestation
- LG-T10: Exact attested bundle re-injection and `EOS` stop before injection (`GEN_STOP_EOS`)
- LG-T11: Consecutive loop state signature detection (`GEN_STOP_LOOP_DETECTED`) and `GEN_STOP_MAX_LEN`
- LG-T12: `ZERO_SELECTION_LEAKAGE` (neural winner with `READOUT_UNKNOWN` stops; never picks runner-up)
- LG-T14: Held-out compositional `G3` reported separately from `G1` / `G2`
- LG-T16: Idempotent `END_EXPOSURE` peripheral outbox notifications
"""

from __future__ import annotations

from dgca.common.errors import StatusCode
from dgca.common.hashing import Region
from dgca.core.anatomy import Synapse, SynapseScope, SynapseState
from dgca.core.generator import (
    evaluate_g1_g2_g3_separated,
    generate_episode,
)
from dgca.core.readout import (
    evaluate_full_vs_control_readout,
    is_legal_readout_assembly,
)
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import (
    Assembly,
    AssemblyStatus,
    ExecutionMode,
    MachineState,
)
from dgca.encoder.envelope import (
    EventOrigin,
    Marker,
    PeripheralSurfaceEnvelopeV1,
    encode_exposure,
)
from dgca.lifecycle.exposure_tx import ExposureTransactionManager
from dgca.peripheral.outbox import (
    OutboxNotificationV1,
    build_end_exposure_outbox_notifications,
)
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1


def _connect_consolidated_synapse(
    state: MachineState,
    src: int,
    tgt: int,
    *,
    s_weight: float = 0.70,
    scope: SynapseScope = SynapseScope.LOCAL,
) -> None:
    """Create a bidirectional latent eligibility entry and a legal consolidated synapse src -> tgt."""
    state.W.commit_cell(src, 0)
    state.W.commit_cell(tgt, 0)
    if not state.W.latent_table.is_eligible(src, tgt):
        try:
            state.W.latent_table.admit_or_recycle_coactive_partner(
                src,
                tgt,
                protected_bidirectional_neighbors=state.W.get_protected_bidirectional_neighbors(src),
                event_clock=state.W.global_event_clock,
                reason="TEST_SETUP",
            )
        except Exception:
            state.W.latent_table.admit_or_recycle_coactive_partner(
                tgt,
                src,
                protected_bidirectional_neighbors=state.W.get_protected_bidirectional_neighbors(tgt),
                event_clock=state.W.global_event_clock,
                reason="TEST_SETUP",
            )
    key = (src, tgt, scope)
    syn = Synapse(
        key=key,
        S=s_weight,
        E_ext=5.0,
        external_count=3,
        confirmed_roots=(1, 2, 3),
        state=SynapseState.CONSOLIDATED,
    )
    state.W.add_or_replace_synapse(syn)


def _create_legal_triangle_assembly(
    state: MachineState,
    assembly_id: int,
    cells: tuple[int, int, int],
    *,
    structural_generation: int = 1,
    s_weight: float = 0.70,
) -> Assembly:
    """Create a 3-cell fully reciprocal CONSOLIDATED_LOCAL triangle Assembly in state.W."""
    c0, c1, c2 = cells
    for u in cells:
        for v in cells:
            if u != v:
                _connect_consolidated_synapse(state, u, v, s_weight=s_weight)
    asm = Assembly(
        assembly_id=assembly_id,
        region=Region.LANGUAGE,
        member_cell_ids=frozenset(cells),
        structural_generation=structural_generation,
        status=AssemblyStatus.LIVE,
    )
    state.W.assemblies[assembly_id] = asm
    assert is_legal_readout_assembly(asm, state.W)
    return asm


def _make_envelope_pair(word: str, *, root_id: int = 1, order: int = 0):
    dual_envs = encode_exposure(word, exposure_id=root_id)
    # Index 0 is the word event, index 1 is EOS
    return dual_envs[order].core_event, dual_envs[order].peripheral_surface


def _get_f0_and_all_cells(proj) -> tuple[tuple[int, ...], tuple[int, ...]]:
    all_cells = tuple(sorted(proj.x_fixed_by_global_id.keys()))
    f0_cells: list[int] = []
    for det in proj.feature_details:
        if det.merged_support_u == 1_000_000:
            f0_cells.extend(det.sorted_distinct_global_ids)
    return tuple(f0_cells) if f0_cells else all_cells, all_cells


def test_full_vs_control_readout_scoring_and_thresholds() -> None:
    """Verify FULL vs CONTROL readout scoring, threshold/margin guards, and zero state mutation."""
    state = MachineState()
    prompt_ev, _ = _make_envelope_pair("الشمس")
    proj = project_core_event_v1(prompt_ev)
    _, all_cells = _get_f0_and_all_cells(proj)
    for cid in all_cells:
        state.W.commit_cell(cid, 0)

    # 1. With no assemblies in W -> NO_ASSEMBLY
    from dgca.core.dynamics import execute_two_pass_event

    scratch = state.clone()
    execute_two_pass_event(
        scratch,
        proj.x_fixed_by_global_id,
        proj.x_float_by_global_id,
        mode=ExecutionMode.RETRIEVE,
        origin=EventOrigin.READ_ONLY_OBSERVED,
        boundary=True,
    )
    res_no_asm = evaluate_full_vs_control_readout(scratch)
    assert res_no_asm.status == StatusCode.NO_ASSEMBLY

    # 2. Add a legal Assembly #10 without incoming links from prompt -> NO_MATCH
    asm1_cells = (8200, 8208, 8216)
    _create_legal_triangle_assembly(scratch, 10, asm1_cells)
    res_no_match = evaluate_full_vs_control_readout(scratch)
    assert res_no_match.status == StatusCode.NO_MATCH
    assert res_no_match.top_score == 0.0

    # 3. Connect strong CONSOLIDATED ASSOCIATIVE links from active prompt F_step cells into Assembly #10 -> OK
    prompt_f_step = sorted(scratch.R.F_step)[:3]
    for src in prompt_f_step:
        for tgt in asm1_cells:
            _connect_consolidated_synapse(
                scratch, src, tgt, s_weight=0.85, scope=SynapseScope.ASSOCIATIVE
            )

    r_snapshot_before = scratch.R.clone()
    res_ok = evaluate_full_vs_control_readout(scratch)
    assert res_ok.status == StatusCode.OK
    assert res_ok.winner_assembly_id == 10
    assert res_ok.winner_generation == 1
    assert res_ok.top_score >= 0.08
    # Verify caller R was not mutated by FULL vs CONTROL scratch pass
    assert scratch.R.step_index == r_snapshot_before.step_index
    assert scratch.R.F_step == r_snapshot_before.F_step

    # 4. Add a second Assembly #20 with identical incoming drive -> AMBIGUOUS (margin < 0.04)
    asm2_cells = (8300, 8308, 8316)
    _create_legal_triangle_assembly(scratch, 20, asm2_cells)
    for src in prompt_f_step:
        for tgt in asm2_cells:
            _connect_consolidated_synapse(
                scratch, src, tgt, s_weight=0.85, scope=SynapseScope.ASSOCIATIVE
            )

    res_ambig = evaluate_full_vs_control_readout(scratch)
    assert res_ambig.status == StatusCode.AMBIGUOUS
    assert res_ambig.margin < 0.04


def test_outbox_idempotency_and_no_backdating_lg_t03_t09_t16() -> None:
    """Verify LG-T03, LG-T09, and LG-T16:
    - Newly formed or mutated assemblies in a root do NOT get backdated outbox attestation.
    - Pre-existing LIVE assemblies require >= 2 distinct completed external roots.
    - Duplicate outbox notifications are idempotent.
    - Stale structural_generation is rejected with GEN_STOP_STALE_ASSEMBLY.
    """
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()

    core_ev1, periph_env1 = _make_envelope_pair("تشرق", root_id=1)
    proj1 = project_core_event_v1(core_ev1)
    f0_all, all_cells1 = _get_f0_and_all_cells(proj1)
    f0_cells = f0_all[:3]
    for cid in all_cells1:
        state.W.commit_cell(cid, 0)

    # Pre-create Assembly #1 on the 3 F0 cells of "تشرق" before Root 1 begins
    asm1 = _create_legal_triangle_assembly(state, 1, (f0_cells[0], f0_cells[1], f0_cells[2]))

    # Suppose Assembly #2 is formed DURING Root 1 (not in preexisting_live_assemblies)
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=False,
        enable_assembly_pipeline=False,
        readout_ledger=ledger,
    )
    tx.begin_exposure(1)
    ev_res1 = tx.process_event(core_ev1, peripheral_envelope=periph_env1)

    # Even if Assembly #2 is added before check, if it wasn't pre-existing with the same generation, it is excluded
    asm2 = Assembly(
        assembly_id=2,
        region=Region.LANGUAGE,
        member_cell_ids=frozenset(f0_cells),
        structural_generation=1,
        status=AssemblyStatus.LIVE,
    )
    state.W.assemblies[2] = asm2
    notifs_no_backdate = build_end_exposure_outbox_notifications(
        1,
        state.W,
        state.H_slow,
        [ev_res1],
        {0: periph_env1},
        preexisting_live_assemblies=[asm1],  # asm2 did not exist prior to root 1
    )
    assert [n.assembly_id for n in notifs_no_backdate] == [1]
    del state.W.assemblies[2]

    rep1 = tx.end_exposure(1)
    assert len(rep1.outbox_notifications) == 1

    # After 1 root, external_count == 1 -> READOUT_UNKNOWN (LG-T09)
    res_after_1 = ledger.resolve_readout(1, 1)
    assert res_after_1.status == StatusCode.READOUT_UNKNOWN
    assert res_after_1.external_count == 1

    # Re-delivering the exact same outbox notification or another event from root 1 is idempotent (LG-T16)
    notif = rep1.outbox_notifications[0]
    assert isinstance(notif, OutboxNotificationV1)
    assert ledger.consume_outbox_notification(notif) is False
    assert ledger.resolve_readout(1, 1).status == StatusCode.READOUT_UNKNOWN

    # Root 2: second independent external root confirms Assembly #1 -> external_count == 2 -> OK (LG-T09)
    core_ev2, periph_env2 = _make_envelope_pair("تشرق", root_id=2)
    tx.begin_exposure(2)
    tx.process_event(core_ev2, peripheral_envelope=periph_env2)
    tx.end_exposure(2)

    res_after_2 = ledger.resolve_readout(1, 1, current_live_generation=1)
    assert res_after_2.status == StatusCode.OK
    assert res_after_2.external_count == 2
    assert res_after_2.envelope is not None
    assert res_after_2.envelope.surface_utf8_nfc == "تشرق"

    # LG-T03: If Assembly #1 mutates to structural_generation = 2, querying gen=1 against live gen=2 -> GEN_STOP_STALE_ASSEMBLY
    res_stale = ledger.resolve_readout(1, 1, current_live_generation=2)
    assert res_stale.status == StatusCode.GEN_STOP_STALE_ASSEMBLY


def test_readout_ledger_collisions_and_unavailable_lg_t08() -> None:
    """Verify LG-T08: multi-surface collisions, pending collisions, same-surface/different-bundle collisions, and unavailable."""
    ledger = SurfaceReadoutLedgerV1()
    _, env_a = _make_envelope_pair("ذهب", root_id=1)
    _, env_b = _make_envelope_pair("عاد", root_id=2)

    # 1. Two conflicting pending tuples (each with 1 root) -> READOUT_AMBIGUOUS_PENDING
    n_a1 = OutboxNotificationV1(
        root_id=1,
        event_order=0,
        assembly_id=5,
        structural_generation=1,
        surface_sha256=env_a.surface_sha256,
        feature_bundle_digest=env_a.feature_bundle_digest,
        marker=env_a.marker,
        envelope=env_a,
    )
    n_b1 = OutboxNotificationV1(
        root_id=2,
        event_order=0,
        assembly_id=5,
        structural_generation=1,
        surface_sha256=env_b.surface_sha256,
        feature_bundle_digest=env_b.feature_bundle_digest,
        marker=env_b.marker,
        envelope=env_b,
    )
    ledger.consume_outbox_notification(n_a1)
    ledger.consume_outbox_notification(n_b1)
    assert ledger.resolve_readout(5, 1).status == StatusCode.READOUT_AMBIGUOUS_PENDING

    # 2. Attest env_a in root 3 while env_b remains pending -> still READOUT_AMBIGUOUS_PENDING
    n_a2 = OutboxNotificationV1(
        root_id=3,
        event_order=0,
        assembly_id=5,
        structural_generation=1,
        surface_sha256=env_a.surface_sha256,
        feature_bundle_digest=env_a.feature_bundle_digest,
        marker=env_a.marker,
        envelope=env_a,
    )
    ledger.consume_outbox_notification(n_a2)
    assert ledger.resolve_readout(5, 1).status == StatusCode.READOUT_AMBIGUOUS_PENDING

    # 3. Attest env_b in root 4 -> both attested -> READOUT_AMBIGUOUS
    n_b2 = OutboxNotificationV1(
        root_id=4,
        event_order=0,
        assembly_id=5,
        structural_generation=1,
        surface_sha256=env_b.surface_sha256,
        feature_bundle_digest=env_b.feature_bundle_digest,
        marker=env_b.marker,
        envelope=env_b,
    )
    ledger.consume_outbox_notification(n_b2)
    assert ledger.resolve_readout(5, 1).status == StatusCode.READOUT_AMBIGUOUS

    # 4. Same surface_utf8_nfc and marker but different feature_bundle_digest -> READOUT_AMBIGUOUS_PENDING
    env_a_alt_bundle = PeripheralSurfaceEnvelopeV1(
        raw_surface_nfc_utf8=env_a.raw_surface_nfc_utf8,
        surface_sha256=env_a.surface_sha256,
        feature_bundle_digest=b"\xff" * 32,
        canonical_features_copy=env_a.canonical_features_copy,
        marker=env_a.marker,
    )
    for rid in (10, 11):
        ledger.consume_outbox_notification(
            OutboxNotificationV1(
                root_id=rid,
                event_order=0,
                assembly_id=6,
                structural_generation=1,
                surface_sha256=env_a.surface_sha256,
                feature_bundle_digest=env_a.feature_bundle_digest,
                marker=env_a.marker,
                envelope=env_a,
            )
        )
    ledger.consume_outbox_notification(
        OutboxNotificationV1(
            root_id=12,
            event_order=0,
            assembly_id=6,
            structural_generation=1,
            surface_sha256=env_a_alt_bundle.surface_sha256,
            feature_bundle_digest=env_a_alt_bundle.feature_bundle_digest,
            marker=env_a_alt_bundle.marker,
            envelope=env_a_alt_bundle,
        )
    )
    assert ledger.resolve_readout(6, 1).status == StatusCode.READOUT_AMBIGUOUS_PENDING

    # 5. Ledger unavailable -> READOUT_UNAVAILABLE
    ledger.available = False
    assert ledger.resolve_readout(6, 1).status == StatusCode.READOUT_UNAVAILABLE


def test_zero_selection_leakage_and_unknown_winner_lg_t12() -> None:
    """Verify LG-T12 (ZERO_SELECTION_LEAKAGE):
    When the top neural Assembly winner has READOUT_UNKNOWN (only 1 root) and the runner-up
    Assembly has a valid attested readout (2 roots), GENERATE_EPISODE selects the neural winner,
    stops with GEN_STOP_READOUT_UNKNOWN, and NEVER falls back to the runner-up Assembly.
    """
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()

    prompt_ev, _ = _make_envelope_pair("الطقس")
    proj_p = project_core_event_v1(prompt_ev)
    f0_p, all_p = _get_f0_and_all_cells(proj_p)
    for cid in all_p:
        state.W.commit_cell(cid, 0)

    # Winner Assembly #1 (stronger incoming synapses s=0.90) vs Runner-up Assembly #2 (weaker s=0.55)
    asm_winner = _create_legal_triangle_assembly(state, 1, (8300, 8308, 8316))
    asm_runner_up = _create_legal_triangle_assembly(state, 2, (8400, 8408, 8416))

    for src in f0_p[:3]:
        for tgt in asm_winner.member_cell_ids:
            _connect_consolidated_synapse(
                state, src, tgt, s_weight=0.90, scope=SynapseScope.ASSOCIATIVE
            )
        for tgt in asm_runner_up.member_cell_ids:
            _connect_consolidated_synapse(
                state, src, tgt, s_weight=0.55, scope=SynapseScope.ASSOCIATIVE
            )

    _, env_winner = _make_envelope_pair("جميل", root_id=1)
    _, env_runner = _make_envelope_pair("بارد", root_id=1)

    # Winner Assembly #1 has only 1 root (READOUT_UNKNOWN)
    ledger.consume_outbox_notification(
        OutboxNotificationV1(
            root_id=1,
            event_order=0,
            assembly_id=1,
            structural_generation=1,
            surface_sha256=env_winner.surface_sha256,
            feature_bundle_digest=env_winner.feature_bundle_digest,
            marker=env_winner.marker,
            envelope=env_winner,
        )
    )
    # Runner-up Assembly #2 has 2 roots (fully attested)
    for rid in (1, 2):
        ledger.consume_outbox_notification(
            OutboxNotificationV1(
                root_id=rid,
                event_order=0,
                assembly_id=2,
                structural_generation=1,
                surface_sha256=env_runner.surface_sha256,
                feature_bundle_digest=env_runner.feature_bundle_digest,
                marker=env_runner.marker,
                envelope=env_runner,
            )
        )

    gen_res = generate_episode(state, [prompt_ev], ledger)
    assert gen_res.stop_status == StatusCode.GEN_STOP_READOUT_UNKNOWN
    assert gen_res.emitted_surfaces == ()
    assert len(gen_res.steps) == 1
    assert gen_res.steps[0].winner_assembly_id == 1


def test_generate_episode_rollout_reinject_and_eos_lg_t07_t10() -> None:
    """Verify LG-T07 & LG-T10:
    Multi-step rollout re-injects the exact attested PeripheralSurfaceEnvelopeV1 as INTERNAL_SELECTED
    with one-time P_T debit, advances to the next assembly, and stops with GEN_STOP_EOS before
    injecting EOS.
    """
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()

    dual_envs = encode_exposure("الشمس تشرق", exposure_id=1)
    ev_prompt, env_prompt = dual_envs[0].core_event, dual_envs[0].peripheral_surface
    ev_word2, env_word2 = dual_envs[1].core_event, dual_envs[1].peripheral_surface
    ev_eos, env_eos = dual_envs[2].core_event, dual_envs[2].peripheral_surface
    assert env_eos.marker == Marker.EOS

    proj_prompt = project_core_event_v1(ev_prompt)
    proj_word2 = project_core_event_v1(ev_word2)
    f0_prompt, all_prompt = _get_f0_and_all_cells(proj_prompt)
    f0_word2, all_word2 = _get_f0_and_all_cells(proj_word2)
    for cid in all_prompt + all_word2:
        state.W.commit_cell(cid, 0)

    # Assembly #1 represents "تشرق" on its 3 F0 cells
    asm1_cells = (
        f0_word2[0],
        f0_word2[1],
        f0_word2[2],
    )
    _create_legal_triangle_assembly(state, 1, asm1_cells)

    # Assembly #2 represents <EOS> on 3 distinct language cells
    asm2_cells = (8900, 8908, 8916)
    _create_legal_triangle_assembly(state, 2, asm2_cells)

    # Connect Prompt F0 -> Assembly #1 ("تشرق") via ASSOCIATIVE temporal links
    for src in f0_prompt[:3]:
        for tgt in asm1_cells:
            _connect_consolidated_synapse(
                state, src, tgt, s_weight=0.90, scope=SynapseScope.ASSOCIATIVE
            )

    # Connect Word2 ("تشرق") F0 -> Assembly #2 (<EOS>) via ASSOCIATIVE temporal links
    for src in asm1_cells:
        for tgt in asm2_cells:
            _connect_consolidated_synapse(
                state, src, tgt, s_weight=0.90, scope=SynapseScope.ASSOCIATIVE
            )

    # Attest Assembly #1 -> env_word2 ("تشرق") and Assembly #2 -> env_eos ("<EOS>") across 2 roots
    for rid in (1, 2):
        ledger.consume_outbox_notification(
            OutboxNotificationV1(
                root_id=rid,
                event_order=1,
                assembly_id=1,
                structural_generation=1,
                surface_sha256=env_word2.surface_sha256,
                feature_bundle_digest=env_word2.feature_bundle_digest,
                marker=env_word2.marker,
                envelope=env_word2,
            )
        )
        ledger.consume_outbox_notification(
            OutboxNotificationV1(
                root_id=rid,
                event_order=2,
                assembly_id=2,
                structural_generation=1,
                surface_sha256=env_eos.surface_sha256,
                feature_bundle_digest=env_eos.feature_bundle_digest,
                marker=env_eos.marker,
                envelope=env_eos,
            )
        )

    w_clock_before = state.W.global_event_clock
    gen_res = generate_episode(state, [ev_prompt], ledger)

    assert gen_res.stop_status == StatusCode.GEN_STOP_EOS
    assert gen_res.emitted_surfaces == ("تشرق",)
    assert len(gen_res.steps) == 2
    # Step 0 emitted "تشرق" and re-injected it as INTERNAL_SELECTED
    assert gen_res.steps[0].winner_assembly_id == 1
    assert gen_res.steps[0].reinjected_event_result is not None
    assert gen_res.steps[0].reinjected_event_result.origin == EventOrigin.INTERNAL_SELECTED
    # Step 1 selected Assembly #2 (EOS) and stopped before re-injecting EOS
    assert gen_res.steps[1].winner_assembly_id == 2
    assert gen_res.steps[1].emitted_envelope == env_eos
    assert gen_res.steps[1].reinjected_event_result is None
    # Caller state was not mutated
    assert state.W.global_event_clock == w_clock_before
    assert state.R.step_index == 0


def test_generate_episode_loop_detection_and_max_len_lg_t11() -> None:
    """Verify LG-T11:
    - Consecutive identical (winner_AssemblyID, winner_generation, sorted(F_step)) stops with GEN_STOP_LOOP_DETECTED.
    - Reaching max_steps stops with GEN_STOP_MAX_LEN.
    """
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()

    ev_loop, env_loop = _make_envelope_pair("تكرار", root_id=1)
    proj_loop = project_core_event_v1(ev_loop)
    f0_loop, all_loop = _get_f0_and_all_cells(proj_loop)
    for cid in all_loop:
        state.W.commit_cell(cid, 0)

    asm_cells = (8500, 8508, 8516)
    _create_legal_triangle_assembly(state, 1, asm_cells, s_weight=0.90)
    for src in f0_loop[:3]:
        for tgt in asm_cells:
            _connect_consolidated_synapse(
                state, src, tgt, s_weight=0.90, scope=SynapseScope.ASSOCIATIVE
            )

    for rid in (1, 2):
        ledger.consume_outbox_notification(
            OutboxNotificationV1(
                root_id=rid,
                event_order=0,
                assembly_id=1,
                structural_generation=1,
                surface_sha256=env_loop.surface_sha256,
                feature_bundle_digest=env_loop.feature_bundle_digest,
                marker=env_loop.marker,
                envelope=env_loop,
            )
        )

    # 1. With max_steps=1, stops at GEN_STOP_MAX_LEN after 1 emitted step
    res_max = generate_episode(state, [ev_loop], ledger, max_steps=1)
    assert res_max.stop_status == StatusCode.GEN_STOP_MAX_LEN
    assert res_max.emitted_surfaces == ("تكرار",)

    # 2. With max_steps=32, step 1 produces the exact same (winner_id=1, gen=1, sorted(F_step)) as step 0 -> GEN_STOP_LOOP_DETECTED
    res_loop = generate_episode(state, [ev_loop], ledger, max_steps=32)
    assert res_loop.stop_status == StatusCode.GEN_STOP_LOOP_DETECTED
    assert len(res_loop.emitted_surfaces) == 1


def test_separated_g1_g2_g3_evaluation_lg_t14() -> None:
    """Verify LG-T14: held-out compositional G3 is reported separately and cannot be masked by G1/G2."""
    eval_fail_g3 = evaluate_g1_g2_g3_separated(
        g1_outcomes=[True, True, True, True],
        g2_outcomes=[True, True, True, True],
        g3_outcomes=[True, False, True, True],
        min_g1_accuracy=1.0,
        min_g2_accuracy=1.0,
        min_g3_accuracy=1.0,
    )
    assert eval_fail_g3.g1_passed is True
    assert eval_fail_g3.g2_passed is True
    assert eval_fail_g3.g3_passed is False
    assert eval_fail_g3.overall_gate_d_passed is False

    eval_pass_all = evaluate_g1_g2_g3_separated(
        g1_outcomes=[True, True],
        g2_outcomes=[True, True],
        g3_outcomes=[True, True],
    )
    assert eval_pass_all.overall_gate_d_passed is True
