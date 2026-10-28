"""Bounded Read-Only Multi-Step Generation (GENERATE_EPISODE, Core §9.3, LLA §7.1).

Normative references:
- DGCA_CORE_RC4_1.md §9.3 (`GENERATE_EPISODE` contract, stop reasons, loop signature, `T_gen_max = 32`)
- DGCA_CORE_RC4_1.md §9.4 (`ZERO_SELECTION_LEAKAGE`: neural winner ranked before peripheral lookup)
- DGCA_CORE_RC4_1.md §13 Gate D & §14 (`LG-T03`, `LG-T07`, `LG-T08`, `LG-T09`, `LG-T10`, `LG-T11`, `LG-T12`, `LG-T14`)
- DGCA_LLA_RC4_1.md §7.1 (Generation and readout invariants)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from dgca.common.errors import ObservationError, StatusCode
from dgca.core.dynamics import EventExecutionResult, execute_two_pass_event
from dgca.core.readout import (
    M_READ,
    THETA_READ,
    ReadoutEvaluationResult,
    evaluate_full_vs_control_readout,
)
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import ExecutionMode, MachineState
from dgca.encoder.envelope import (
    CoreEventPayloadV1,
    EventOrigin,
    Marker,
    PeripheralSurfaceEnvelopeV1,
    reinject_attested_bundle,
)
from dgca.peripheral.readout_ledger import (
    ResolveReadoutResult,
    SurfaceReadoutLedgerV1,
)

# Normative maximum generated steps per episode (Core §9.3, §12)
T_GEN_MAX: int = 32


@dataclass(frozen=True, slots=True)
class GeneratedStepRecord:
    """Audit record for a single generation step inside GENERATE_EPISODE (Core §9.3)."""

    step_index: int
    readout_result: ReadoutEvaluationResult
    ledger_resolution: ResolveReadoutResult | None
    winner_assembly_id: int | None
    winner_generation: int | None
    loop_signature: tuple[int, int, tuple[int, ...]] | None
    emitted_envelope: PeripheralSurfaceEnvelopeV1 | None
    reinjected_event_result: EventExecutionResult | None


@dataclass(frozen=True, slots=True)
class GenerateEpisodeResult:
    """Result of a read-only GENERATE_EPISODE execution (Core §9.3)."""

    stop_status: StatusCode
    prompt_event_results: tuple[EventExecutionResult, ...]
    steps: tuple[GeneratedStepRecord, ...]
    emitted_envelopes: tuple[PeripheralSurfaceEnvelopeV1, ...]
    emitted_surfaces: tuple[str, ...]


def _map_readout_failure_to_gen_stop(status: StatusCode) -> StatusCode:
    if status == StatusCode.NO_ASSEMBLY:
        return StatusCode.GEN_STOP_NO_ASSEMBLY
    if status == StatusCode.NO_MATCH:
        return StatusCode.GEN_STOP_NO_MATCH
    if status == StatusCode.AMBIGUOUS:
        return StatusCode.GEN_STOP_AMBIGUOUS
    return status


def _map_ledger_failure_to_gen_stop(status: StatusCode) -> StatusCode:
    if status == StatusCode.READOUT_UNKNOWN:
        return StatusCode.GEN_STOP_READOUT_UNKNOWN
    if status == StatusCode.READOUT_AMBIGUOUS:
        return StatusCode.GEN_STOP_READOUT_AMBIGUOUS
    if status == StatusCode.READOUT_AMBIGUOUS_PENDING:
        return StatusCode.GEN_STOP_READOUT_AMBIGUOUS_PENDING
    if status == StatusCode.READOUT_UNAVAILABLE:
        return StatusCode.GEN_STOP_READOUT_UNAVAILABLE
    if status == StatusCode.GEN_STOP_STALE_ASSEMBLY:
        return StatusCode.GEN_STOP_STALE_ASSEMBLY
    return status


def generate_episode(
    state: MachineState,
    prompt_events: Sequence[CoreEventPayloadV1],
    ledger: SurfaceReadoutLedgerV1,
    *,
    max_steps: int = T_GEN_MAX,
    theta_read: float = THETA_READ,
    m_read: float = M_READ,
    override_winner_generation_by_step: dict[int, int] | None = None,
) -> GenerateEpisodeResult:
    """Execute a bounded read-only GENERATE_EPISODE rollout (Core §9.3, LLA §7.1).

    Invariants enforced:
    1. Isolated scratch `R_cold` clone and frozen `W`, `H_slow`, and `SurfaceReadoutLedgerV1` snapshot.
    2. Ingests `>= 1` prompt events with `mode = ExecutionMode.GENERATE`, `origin = READ_ONLY_OBSERVED`.
    3. At each rollout step, computes `FULL vs CONTROL` readout **before** any peripheral lookup
       (`ZERO_SELECTION_LEAKAGE`; `LG-T12`). If the neural winner has `READOUT_UNKNOWN` or collision,
       immediately stops with `GEN_STOP_*` and never falls back to a runner-up Assembly.
    4. Detects consecutive identical `(winner_AssemblyID, winner_generation, sorted(F_step))` state
       signatures and stops with `GEN_STOP_LOOP_DETECTED` (`LG-T11`).
    5. Stops with `GEN_STOP_EOS` before injecting `EOS` when `marker == Marker.EOS` (`LG-T10`).
    6. Re-injects non-EOS attested bundles via `reinject_attested_bundle` as `INTERNAL_SELECTED`
       with `apply_pt_debit_selected = True` (`LG-T07`, `LG-T10`).
    7. Resets scratch `R` to `R_cold` on exit; caller `state` and `ledger` are untouched.
    """
    if not prompt_events:
        raise ObservationError("GENERATE_EPISODE requires at least one prompt event")
    if max_steps < 0:
        raise ObservationError(f"max_steps must be non-negative, got {max_steps}")

    scratch_state = state.clone()
    scratch_state.R.reset_cold()
    ledger_snapshot = ledger.clone()

    prompt_results: list[EventExecutionResult] = []
    next_event_order = 0
    for idx, pev in enumerate(prompt_events):
        proj = project_core_event_v1(pev)
        res = execute_two_pass_event(
            scratch_state,
            proj.x_fixed_by_global_id,
            proj.x_float_by_global_id,
            mode=ExecutionMode.GENERATE,
            origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=(idx == 0 or pev.boundary),
            exposure_id=None,
            event_order=next_event_order,
            feature_bundle_digest=proj.feature_bundle_digest,
            allow_candidate_probe=False,
            admit_uncommitted_sensory=False,
        )
        prompt_results.append(res)
        next_event_order += 1

    current_f_step = prompt_results[-1].f_step
    prev_loop_signature: tuple[int, int, tuple[int, ...]] | None = None

    step_records: list[GeneratedStepRecord] = []
    emitted_envelopes: list[PeripheralSurfaceEnvelopeV1] = []

    for step_idx in range(max_steps):
        # 1. Pure neural FULL vs CONTROL selection (ZERO_SELECTION_LEAKAGE)
        readout_res = evaluate_full_vs_control_readout(
            scratch_state,
            theta_read=theta_read,
            m_read=m_read,
        )
        if readout_res.status != StatusCode.OK:
            stop_code = _map_readout_failure_to_gen_stop(readout_res.status)
            step_records.append(
                GeneratedStepRecord(
                    step_index=step_idx,
                    readout_result=readout_res,
                    ledger_resolution=None,
                    winner_assembly_id=None,
                    winner_generation=None,
                    loop_signature=None,
                    emitted_envelope=None,
                    reinjected_event_result=None,
                )
            )
            scratch_state.R.reset_cold()
            return GenerateEpisodeResult(
                stop_status=stop_code,
                prompt_event_results=tuple(prompt_results),
                steps=tuple(step_records),
                emitted_envelopes=tuple(emitted_envelopes),
                emitted_surfaces=tuple(env.surface_utf8_nfc for env in emitted_envelopes),
            )

        assert readout_res.winner_assembly_id is not None
        assert readout_res.winner_generation is not None
        winner_id = readout_res.winner_assembly_id
        winner_gen = readout_res.winner_generation
        if (
            override_winner_generation_by_step is not None
            and step_idx in override_winner_generation_by_step
        ):
            winner_gen = override_winner_generation_by_step[step_idx]

        live_asm = scratch_state.W.assemblies.get(winner_id)
        current_live_gen = live_asm.structural_generation if live_asm is not None else -1

        # 2. Check consecutive loop signature: (winner_AssemblyID, winner_generation, sorted(F_step))
        loop_sig = (winner_id, winner_gen, tuple(sorted(current_f_step)))
        if prev_loop_signature is not None and loop_sig == prev_loop_signature:
            step_records.append(
                GeneratedStepRecord(
                    step_index=step_idx,
                    readout_result=readout_res,
                    ledger_resolution=None,
                    winner_assembly_id=winner_id,
                    winner_generation=winner_gen,
                    loop_signature=loop_sig,
                    emitted_envelope=None,
                    reinjected_event_result=None,
                )
            )
            scratch_state.R.reset_cold()
            return GenerateEpisodeResult(
                stop_status=StatusCode.GEN_STOP_LOOP_DETECTED,
                prompt_event_results=tuple(prompt_results),
                steps=tuple(step_records),
                emitted_envelopes=tuple(emitted_envelopes),
                emitted_surfaces=tuple(env.surface_utf8_nfc for env in emitted_envelopes),
            )
        prev_loop_signature = loop_sig

        # 3. Peripheral lookup strictly on the neural winner ONLY (LG-T12: never fall back to runner-up)
        ledger_res = ledger_snapshot.resolve_readout(
            winner_id,
            winner_gen,
            current_live_generation=current_live_gen,
        )
        if ledger_res.status != StatusCode.OK or ledger_res.envelope is None:
            stop_code = _map_ledger_failure_to_gen_stop(ledger_res.status)
            step_records.append(
                GeneratedStepRecord(
                    step_index=step_idx,
                    readout_result=readout_res,
                    ledger_resolution=ledger_res,
                    winner_assembly_id=winner_id,
                    winner_generation=winner_gen,
                    loop_signature=loop_sig,
                    emitted_envelope=None,
                    reinjected_event_result=None,
                )
            )
            scratch_state.R.reset_cold()
            return GenerateEpisodeResult(
                stop_status=stop_code,
                prompt_event_results=tuple(prompt_results),
                steps=tuple(step_records),
                emitted_envelopes=tuple(emitted_envelopes),
                emitted_surfaces=tuple(env.surface_utf8_nfc for env in emitted_envelopes),
            )

        attested_env = ledger_res.envelope

        # 4. EOS marker check: stop before injecting EOS as an INTERNAL_SELECTED rollout event (Core §9.3, LG-T10)
        if attested_env.marker == Marker.EOS:
            step_records.append(
                GeneratedStepRecord(
                    step_index=step_idx,
                    readout_result=readout_res,
                    ledger_resolution=ledger_res,
                    winner_assembly_id=winner_id,
                    winner_generation=winner_gen,
                    loop_signature=loop_sig,
                    emitted_envelope=attested_env,
                    reinjected_event_result=None,
                )
            )
            scratch_state.R.reset_cold()
            return GenerateEpisodeResult(
                stop_status=StatusCode.GEN_STOP_EOS,
                prompt_event_results=tuple(prompt_results),
                steps=tuple(step_records),
                emitted_envelopes=tuple(emitted_envelopes),
                emitted_surfaces=tuple(env.surface_utf8_nfc for env in emitted_envelopes),
            )

        # 5. Re-inject attested bundle as INTERNAL_SELECTED with one-time P_T consumption debit (LG-T07, LG-T10)
        reinjected_core_event = reinject_attested_bundle(
            attested_env,
            exposure_id=None,
            event_order=next_event_order,
        )
        next_event_order += 1
        reinjected_proj = project_core_event_v1(reinjected_core_event)
        reinjected_res = execute_two_pass_event(
            scratch_state,
            reinjected_proj.x_fixed_by_global_id,
            reinjected_proj.x_float_by_global_id,
            mode=ExecutionMode.GENERATE,
            origin=EventOrigin.INTERNAL_SELECTED,
            boundary=False,
            exposure_id=None,
            event_order=reinjected_core_event.event_order,
            feature_bundle_digest=reinjected_proj.feature_bundle_digest,
            allow_candidate_probe=False,
            admit_uncommitted_sensory=False,
            apply_pt_debit_selected=True,
        )

        emitted_envelopes.append(attested_env)
        current_f_step = reinjected_res.f_step
        step_records.append(
            GeneratedStepRecord(
                step_index=step_idx,
                readout_result=readout_res,
                ledger_resolution=ledger_res,
                winner_assembly_id=winner_id,
                winner_generation=winner_gen,
                loop_signature=loop_sig,
                emitted_envelope=attested_env,
                reinjected_event_result=reinjected_res,
            )
        )

    scratch_state.R.reset_cold()
    return GenerateEpisodeResult(
        stop_status=StatusCode.GEN_STOP_MAX_LEN,
        prompt_event_results=tuple(prompt_results),
        steps=tuple(step_records),
        emitted_envelopes=tuple(emitted_envelopes),
        emitted_surfaces=tuple(env.surface_utf8_nfc for env in emitted_envelopes),
    )


@dataclass(frozen=True, slots=True)
class GenerationGateEvaluation:
    """Separated G1 / G2 / G3 generation benchmark evaluation report (Core §13 Gate D, §14 LG-T14).

    Enforces that held-out compositional continuation (G3) is reported separately from
    memorized continuation (G1) and context-sensitive branch selection (G2), and cannot
    be masked by averaging with G1/G2.
    """

    g1_memorized_accuracy: float
    g2_context_branch_accuracy: float
    g3_compositional_accuracy: float
    g1_passed: bool
    g2_passed: bool
    g3_passed: bool
    overall_gate_d_passed: bool


def evaluate_g1_g2_g3_separated(
    g1_outcomes: Sequence[bool],
    g2_outcomes: Sequence[bool],
    g3_outcomes: Sequence[bool],
    *,
    min_g1_accuracy: float = 1.0,
    min_g2_accuracy: float = 1.0,
    min_g3_accuracy: float = 1.0,
) -> GenerationGateEvaluation:
    """Evaluate G1, G2, and held-out compositional G3 separately without pooling (Core §13 Gate D, LG-T14).

    If any sub-benchmark is empty or falls below its threshold (especially G3),
    `overall_gate_d_passed` is False even if G1 and G2 are 1.0.
    """
    g1_acc = (sum(1 for x in g1_outcomes if x) / float(len(g1_outcomes))) if g1_outcomes else 0.0
    g2_acc = (sum(1 for x in g2_outcomes if x) / float(len(g2_outcomes))) if g2_outcomes else 0.0
    g3_acc = (sum(1 for x in g3_outcomes if x) / float(len(g3_outcomes))) if g3_outcomes else 0.0

    g1_ok = bool(g1_outcomes) and g1_acc >= min_g1_accuracy
    g2_ok = bool(g2_outcomes) and g2_acc >= min_g2_accuracy
    g3_ok = bool(g3_outcomes) and g3_acc >= min_g3_accuracy

    return GenerationGateEvaluation(
        g1_memorized_accuracy=g1_acc,
        g2_context_branch_accuracy=g2_acc,
        g3_compositional_accuracy=g3_acc,
        g1_passed=g1_ok,
        g2_passed=g2_ok,
        g3_passed=g3_ok,
        overall_gate_d_passed=(g1_ok and g2_ok and g3_ok),
    )
