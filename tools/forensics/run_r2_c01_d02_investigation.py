"""DGCA NEXT V2 — R2-C01-D02 Readout Dynamics, Context Interference & Learned Evidence Retention Forensics.

Executes:
- S01: Exact Autonomous Generation Audit across Roots (37, 40, 48, 56, 64, 72, 80, 84, 88, 96, 104, 112) for Group A and Group B.
- S02: Deep trace of Group B Assembly 6 (حليب) retention from Root 37 to 112.
- S03: Deep causal analysis of P1 at Root 56 (ماء vs حليب).
- S04: Deep causal analysis of EOS continuation asymmetry (P2 vs P4 at Root 112).
- S05: Readout normalization hypothesis evaluation (top-k, evidence-weighted, etc.).
- S06: Relational reuse vs interference forensics.
- S07: Negative controls evaluation.
- S08: Audit of CF04 claims and automated assertions.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from dgca.common.errors import StatusCode
from dgca.core.anatomy import SynapseScope, SynapseState
from dgca.core.assembly import (
    K_MAX,
    D_MIN,
    RHO_G,
    SIGMA_G,
    SIGMA_KEEP,
    THETA_A,
    compute_mutual_support_r_b,
)
from dgca.core.dynamics import (
    EventExecutionResult,
    compute_next_step_temporal_drive,
    execute_two_pass_event,
)
from dgca.core.generator import generate_episode
from dgca.core.latent_index import COACTIVE_INTRA_SLOTS
from dgca.core.readout import (
    M_READ,
    THETA_READ,
    AssemblyReadoutScore,
    ReadoutEvaluationResult,
    evaluate_full_vs_control_readout,
    is_legal_readout_assembly,
)
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import ExecutionMode, MachineState
from dgca.encoder.envelope import (
    CoreEventPayloadV1,
    EventOrigin,
    PeripheralSurfaceEnvelopeV1,
    encode_exposure,
)
from dgca.lifecycle.exposure_tx import ExposureTransactionManager
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1
from tests.test_r2_a01_patch2_acceptance import (
    hash_state_snapshot,
    snapshot_w,
    snapshot_h_slow,
    snapshot_r,
)
from tools.forensics.run_r2_c01_cf01_experiment import CORPUS_GROUP_B, build_schedule

AUDIT_CHECKPOINTS = [37, 40, 48, 56, 64, 72, 80, 84, 88, 96, 104, 112]

PROBES = {
    "P1 (القط يشرب)": ["القط", "يشرب"],
    "P2 (النسر يشرب)": ["النسر", "يشرب"],
    "P3 (الطفل يأكل)": ["الطفل", "يأكل"],
    "P4 (الطفل يشرب)": ["الطفل", "يشرب"],
}

EXPECTED_COMPLETIONS = {
    "P1 (القط يشرب)": ("حليب", ["حليب", "<EOS>"]),
    "P2 (النسر يشرب)": ("ماء", ["ماء", "<EOS>"]),
    "P3 (الطفل يأكل)": ("تفاح", ["تفاح", "<EOS>"]),
    "P4 (الطفل يشرب)": ("ماء", ["ماء", "<EOS>"]),
}


def feed_prompt(state: MachineState, core_events: list[CoreEventPayloadV1]) -> MachineState:
    st = state.clone()
    for idx, pev in enumerate(core_events):
        proj = project_core_event_v1(pev)
        effective_boundary = True if idx == 0 else pev.boundary
        execute_two_pass_event(
            st,
            proj.x_fixed_by_global_id,
            proj.x_float_by_global_id,
            mode=ExecutionMode.RETRIEVE,
            origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=effective_boundary,
            exposure_id=None,
            event_order=idx,
            allow_candidate_probe=False,
            admit_uncommitted_sensory=False,
        )
    return st


def run_training_stream(
    enable_cross_clique_diversification: bool,
    max_roots: int = 112,
    checkpoint_roots: list[int] | None = None,
) -> dict[str, Any]:
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
        enable_birth_time_grow=False,
        enable_cross_clique_diversification=enable_cross_clique_diversification,
    )
    encoded = {k: encode_exposure(v, append_eos=True) for k, v in CORPUS_GROUP_B.items()}
    schedule = build_schedule(max_roots)

    checkpoints: dict[int, dict[str, Any]] = {}
    if checkpoint_roots is None:
        checkpoint_roots = AUDIT_CHECKPOINTS

    for root_id, s_key in schedule:
        tx.begin_exposure(root_id)
        for env in encoded[s_key]:
            core_ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        tx.end_exposure(root_id)

        if root_id in checkpoint_roots:
            checkpoints[root_id] = {
                "state": state.clone(),
                "ledger": ledger.clone(),
                "state_hash": hash_state_snapshot({
                    "W": snapshot_w(state.W),
                    "H_slow": snapshot_h_slow(state.H_slow),
                    "R": snapshot_r(state.R),
                }),
            }

    return {
        "enable_cross_clique_diversification": enable_cross_clique_diversification,
        "checkpoints": checkpoints,
    }


def classify_generation_outcome(
    p_name: str,
    first_token_surf: str,
    full_trajectory: list[str],
    first_step_stop: str,
    full_stop: str,
) -> str:
    expected_first, expected_full = EXPECTED_COMPLETIONS[p_name]

    if full_trajectory == expected_full and full_stop == "GEN_STOP_EOS":
        return "CORRECT_AUTONOMOUS_GENERATION"

    if len(full_trajectory) > 0 and full_trajectory[-1] == "<EOS>" and full_trajectory != expected_full:
        return "WRONG_BRANCH_AUTONOMOUS_GENERATION"

    if first_token_surf == expected_first and full_stop != "GEN_STOP_EOS":
        return "CORRECT_FIRST_TOKEN_WITHOUT_EOS"

    if first_step_stop == "GEN_STOP_AMBIGUOUS":
        return "NEURAL_AMBIGUITY"

    if first_step_stop == "GEN_STOP_NO_MATCH":
        return "READOUT_NO_MATCH"

    if first_step_stop in ("GEN_STOP_READOUT_UNKNOWN", "GEN_STOP_READOUT_AMBIGUOUS"):
        return "PERIPHERAL_RESOLUTION_FAILURE"

    return f"OTHER_{first_step_stop}"


def audit_s01_probes(group_data: dict[str, Any], root: int) -> dict[str, Any]:
    ckpt = group_data["checkpoints"][root]
    state = ckpt["state"]
    ledger = ckpt["ledger"]

    probes_res = {}
    for p_name, words in PROBES.items():
        # Encode prompt
        p_text = " ".join(words)
        p_envs = encode_exposure(p_text, append_eos=False)
        p_cores = [env.core_event for env in p_envs]

        # 1 step execution
        res1 = generate_episode(state.clone(), p_cores, ledger, max_steps=1)
        step0 = res1.steps[0] if res1.steps else None
        rr0 = step0.readout_result if step0 else None

        # Full autonomous execution
        res_full = generate_episode(state.clone(), p_cores, ledger, max_steps=8)
        trajectory = [
            (
                s.emitted_envelope.surface_utf8_nfc
                if s.emitted_envelope
                else (s.readout_result.status.name if s.readout_result else "STOP")
            )
            for s in res_full.steps
        ]
        if not trajectory and res_full.stop_status != StatusCode.OK:
            trajectory = [res_full.stop_status.name]

        ranked = []
        if rr0:
            for cand in rr0.ranked_scores:
                asm_cand = state.W.assemblies.get(cand.assembly_id)
                res_led = ledger.resolve_readout(cand.assembly_id, cand.structural_generation)
                surf_cand = res_led.envelope.surface_utf8_nfc if (res_led and res_led.envelope) else "UNATTESTED"
                ranked.append({
                    "assembly_id": cand.assembly_id,
                    "generation": cand.structural_generation,
                    "surface": surf_cand,
                    "score": round(cand.score_next, 6),
                    "size": len(asm_cand.member_cell_ids) if asm_cand else 0,
                    "eligible_count": cand.eligible_member_count,
                })

        winner_surf = "NONE"
        if rr0 and rr0.winner_assembly_id is not None:
            res_led = ledger.resolve_readout(rr0.winner_assembly_id, rr0.winner_generation)
            if res_led and res_led.envelope:
                winner_surf = res_led.envelope.surface_utf8_nfc

        first_stop = res1.stop_status.name
        full_stop = res_full.stop_status.name
        outcome_class = classify_generation_outcome(
            p_name,
            winner_surf,
            trajectory,
            first_stop,
            full_stop,
        )

        probes_res[p_name] = {
            "first_step_stop_status": first_stop,
            "full_stop_status": full_stop,
            "first_step_readout_status": rr0.status.name if rr0 else "NONE",
            "winner_assembly_id": rr0.winner_assembly_id if rr0 else None,
            "winner_generation": rr0.winner_generation if rr0 else None,
            "winner_surface": winner_surf,
            "top_score": round(rr0.top_score, 6) if rr0 else 0.0,
            "second_score": round(rr0.second_score, 6) if rr0 else 0.0,
            "margin": round(rr0.margin, 6) if rr0 else 0.0,
            "runner_up": ranked[1] if len(ranked) >= 2 else None,
            "ranked": ranked,
            "full_trajectory": trajectory,
            "outcome_classification": outcome_class,
        }

    return probes_res


def audit_s02_milk_representation(group_b_data: dict[str, Any]) -> dict[int, Any]:
    """Reconstruct membership and activation history of Assembly 6 (حليب) from Root 37 to 112."""
    milk_history = {}
    for r in AUDIT_CHECKPOINTS:
        ckpt = group_b_data["checkpoints"][r]
        state = ckpt["state"]
        ledger = ckpt["ledger"]
        w = state.W

        # Find milk assembly (Assembly 6 in Group B)
        asm6 = w.assemblies.get(6)
        if not asm6:
            continue

        members = sorted(list(asm6.member_cell_ids))

        # Test prompt P1: "القط يشرب"
        p_envs = encode_exposure("القط يشرب", append_eos=False)
        p_cores = [env.core_event for env in p_envs]

        # Feed prompt up to retrieval point
        probe_state = feed_prompt(state, p_cores)

        # FULL pass with X=0
        full_st = probe_state.clone()
        res_full = execute_two_pass_event(
            full_st,
            {},
            {},
            mode=ExecutionMode.RETRIEVE,
            origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=False,
            exposure_id=None,
            event_order=full_st.R.step_index,
            allow_candidate_probe=False,
            admit_uncommitted_sensory=False,
            control_zero_pt=False,
        )

        # CONTROL pass with X=0 and pt=0
        ctrl_st = probe_state.clone()
        res_ctrl = execute_two_pass_event(
            ctrl_st,
            {},
            {},
            mode=ExecutionMode.RETRIEVE,
            origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=False,
            exposure_id=None,
            event_order=ctrl_st.R.step_index,
            allow_candidate_probe=False,
            admit_uncommitted_sensory=False,
            control_zero_pt=True,
        )

        # Trace incoming synapses and per-member metrics
        member_metrics = {}
        total_eligible_gain = 0.0
        eligible_count = 0

        for mid in members:
            pt_val = res_full.pt_by_cell.get(mid, 0.0)
            a_full = res_full.a_plus_by_cell.get(mid, 0.0)
            a_ctrl = res_ctrl.a_plus_by_cell.get(mid, 0.0)
            gain = max(a_full - a_ctrl, 0.0)
            is_elig = (pt_val > 0.0 and gain > 0.0)
            if is_elig:
                eligible_count += 1
                total_eligible_gain += gain

            # Incoming consolidated predictive synapses into mid
            incoming_synapses = []
            for (src, tgt, scope), syn in w.synapses.items():
                if tgt == mid and scope == SynapseScope.ASSOCIATIVE and syn.state == SynapseState.CONSOLIDATED:
                    incoming_synapses.append({
                        "source": src,
                        "weight_q": round(syn.Q, 6),
                        "confirmations": len(syn.confirmed_roots),
                        "external_count": syn.external_count,
                        "is_contextual": w.is_contextual_cell(src),
                        "a_src_prior": round(res_full.a_plus_by_cell.get(src, 0.0), 6),
                    })

            member_metrics[str(mid)] = {
                "pt": round(pt_val, 6),
                "a_full": round(a_full, 6),
                "a_ctrl": round(a_ctrl, 6),
                "gain": round(gain, 6),
                "is_eligible": is_elig,
                "incoming_synapses_count": len(incoming_synapses),
                "incoming_synapses": incoming_synapses,
            }

        score_norm = total_eligible_gain / float(len(members))

        milk_history[r] = {
            "root": r,
            "assembly_id": 6,
            "structural_generation": asm6.structural_generation,
            "member_count": len(members),
            "members": members,
            "eligible_count": eligible_count,
            "total_eligible_gain": round(total_eligible_gain, 6),
            "normalized_score": round(score_norm, 6),
            "member_metrics": member_metrics,
        }

    return milk_history


def audit_s03_wrong_branch_p1_root56(group_b_data: dict[str, Any]) -> dict[str, Any]:
    """Deconstruct P1 at Root 56: compare neural support for Asm 4 (ماء) vs Asm 6 (حليب)."""
    ckpt = group_b_data["checkpoints"][56]
    state = ckpt["state"]
    ledger = ckpt["ledger"]
    w = state.W

    p_envs = encode_exposure("القط يشرب", append_eos=False)
    p_cores = [env.core_event for env in p_envs]

    # Step 0: "القط"
    st0 = state.clone()
    proj0 = project_core_event_v1(p_cores[0])
    res_ev0 = execute_two_pass_event(
        st0,
        proj0.x_fixed_by_global_id,
        proj0.x_float_by_global_id,
        mode=ExecutionMode.RETRIEVE,
        origin=EventOrigin.EXTERNAL_DIRECT,
        boundary=True,
        exposure_id=None,
        event_order=0,
        allow_candidate_probe=False,
        admit_uncommitted_sensory=False,
    )
    active_after_cat = sorted([c for c, a in res_ev0.a_plus_by_cell.items() if a > 0.0])
    ctx_after_cat = sorted([c for c in active_after_cat if w.is_contextual_cell(c)])

    # Step 1: "يشرب"
    st1 = st0.clone()
    proj1 = project_core_event_v1(p_cores[1])
    res_ev1 = execute_two_pass_event(
        st1,
        proj1.x_fixed_by_global_id,
        proj1.x_float_by_global_id,
        mode=ExecutionMode.RETRIEVE,
        origin=EventOrigin.EXTERNAL_DIRECT,
        boundary=False,
        exposure_id=None,
        event_order=1,
        allow_candidate_probe=False,
        admit_uncommitted_sensory=False,
    )
    active_after_drinks = sorted([c for c, a in res_ev1.a_plus_by_cell.items() if a > 0.0])
    ctx_after_drinks = sorted([c for c in active_after_drinks if w.is_contextual_cell(c)])

    # Retrieval comparison
    rr = evaluate_full_vs_control_readout(st1)

    asm4 = w.assemblies[4]  # ماء
    asm6 = w.assemblies[6]  # حليب

    def get_asm_breakdown(asm):
        mems = sorted(list(asm.member_cell_ids))
        breakdown = []
        for m in mems:
            gain = rr.gain_by_cell.get(m, 0.0)
            a_f = rr.a_full_by_cell.get(m, 0.0)
            a_c = rr.a_control_by_cell.get(m, 0.0)
            elig = (m in rr.eligible_next_cells)

            # Sources in active_after_drinks connecting to m
            sources = []
            for (src, tgt, scope), syn in w.synapses.items():
                if tgt == m and scope == SynapseScope.ASSOCIATIVE and syn.state == SynapseState.CONSOLIDATED:
                    if src in res_ev1.a_plus_by_cell and res_ev1.a_plus_by_cell[src] > 0.0:
                        sources.append({
                            "src": src,
                            "a_src": round(res_ev1.a_plus_by_cell[src], 4),
                            "weight_q": round(syn.Q, 4),
                            "is_ctx": w.is_contextual_cell(src),
                        })

            breakdown.append({
                "cell": m,
                "a_full": round(a_f, 4),
                "a_ctrl": round(a_c, 4),
                "gain": round(gain, 4),
                "is_eligible": elig,
                "sources": sources,
            })
        return breakdown

    return {
        "active_ctx_after_cat": ctx_after_cat,
        "active_ctx_after_drinks": ctx_after_drinks,
        "asm4_water_breakdown": get_asm_breakdown(asm4),
        "asm6_milk_breakdown": get_asm_breakdown(asm6),
        "asm4_score": [s for s in rr.ranked_scores if s.assembly_id == 4][0].score_next,
        "asm6_score": [s for s in rr.ranked_scores if s.assembly_id == 6][0].score_next,
    }


def audit_s04_eos_continuation_asymmetry(group_b_data: dict[str, Any]) -> dict[str, Any]:
    """Audit why P2 and P4 diverge on EOS after generating 'ماء' at Root 112."""
    ckpt = group_b_data["checkpoints"][112]
    state = ckpt["state"]
    ledger = ckpt["ledger"]
    w = state.W

    def trace_post_water(subject_word: str):
        st = state.clone()
        words = [subject_word, "يشرب", "ماء"]
        envs = encode_exposure(" ".join(words), append_eos=False)
        for idx, env in enumerate(envs):
            proj = project_core_event_v1(env.core_event)
            effective_boundary = True if idx == 0 else False
            execute_two_pass_event(
                st,
                proj.x_fixed_by_global_id,
                proj.x_float_by_global_id,
                mode=ExecutionMode.RETRIEVE,
                origin=EventOrigin.EXTERNAL_DIRECT if idx < 2 else EventOrigin.INTERNAL_SELECTED,
                boundary=effective_boundary,
                exposure_id=None,
                event_order=idx,
                allow_candidate_probe=False,
                admit_uncommitted_sensory=False,
            )

        # Evaluate readout for next step (expecting EOS)
        rr = evaluate_full_vs_control_readout(st)
        asm1 = w.assemblies.get(1)  # EOS assembly
        asm1_score = [s for s in rr.ranked_scores if s.assembly_id == 1]
        asm1_data = asm1_score[0] if asm1_score else None

        # Breakdown of EOS cells (Asm 1 members)
        eos_cells_data = []
        if asm1:
            for m in sorted(list(asm1.member_cell_ids)):
                gain = rr.gain_by_cell.get(m, 0.0)
                a_f = rr.a_full_by_cell.get(m, 0.0)
                a_c = rr.a_control_by_cell.get(m, 0.0)
                elig = (m in rr.eligible_next_cells)
                eos_cells_data.append({
                    "cell": m,
                    "gain": round(gain, 6),
                    "a_full": round(a_f, 6),
                    "a_ctrl": round(a_c, 6),
                    "is_eligible": elig,
                })

        # Contextual cells active before next step
        active_ctx = sorted([c for c in st.R.F_step if w.is_contextual_cell(c)])

        return {
            "subject": subject_word,
            "readout_status": rr.status.name,
            "winner_assembly_id": rr.winner_assembly_id,
            "top_score": round(rr.top_score, 6),
            "margin": round(rr.margin, 6),
            "asm1_score": round(asm1_data.score_next, 6) if asm1_data else 0.0,
            "asm1_elig_count": asm1_data.eligible_member_count if asm1_data else 0,
            "asm1_member_count": asm1_data.member_count if asm1_data else 0,
            "active_ctx_cells": active_ctx,
            "eos_cells_data": eos_cells_data,
        }

    return {
        "p2_eagle": trace_post_water("النسر"),
        "p4_child": trace_post_water("الطفل"),
    }


def audit_s05_readout_normalization(group_b_data: dict[str, Any], root: int = 112) -> dict[str, Any]:
    """Compare candidate scoring hypotheses offline on the exact frozen neural traces."""
    ckpt = group_b_data["checkpoints"][root]
    state = ckpt["state"]
    ledger = ckpt["ledger"]
    w = state.W

    hypotheses_results = {}

    for p_name, words in PROBES.items():
        p_text = " ".join(words)
        p_envs = encode_exposure(p_text, append_eos=False)
        p_cores = [env.core_event for env in p_envs]

        st = feed_prompt(state, p_cores)
        rr = evaluate_full_vs_control_readout(st)

        n_rec_cache = {}
        legal_assemblies = [
            asm for _, asm in sorted(w.assemblies.items())
            if is_legal_readout_assembly(asm, w, n_rec_cache)
        ]

        # Alternative A: Full assembly mean (current canonical)

        # Alternative B: Top-k mean of eligible member gains (k=3)
        scores_top3 = []
        for asm in legal_assemblies:
            gains = [rr.gain_by_cell.get(c, 0.0) for c in asm.member_cell_ids if c in rr.eligible_next_cells]
            gains.sort(reverse=True)
            top3 = gains[:3]
            s = sum(top3) / 3.0 if top3 else 0.0
            scores_top3.append((asm.assembly_id, s))
        scores_top3.sort(key=lambda x: -x[1])

        # Alternative C: Evidence-weighted aggregation
        scores_weighted = []
        for asm in legal_assemblies:
            mems = list(asm.member_cell_ids)
            tot_w = 0.0
            tot_wg = 0.0
            for c in mems:
                w_c = sum(1.0 for other in mems if other != c and compute_mutual_support_r_b(c, other, w) >= THETA_A)
                tot_w += w_c
                if c in rr.eligible_next_cells:
                    tot_wg += w_c * rr.gain_by_cell.get(c, 0.0)
            s = tot_wg / tot_w if tot_w > 0.0 else 0.0
            scores_weighted.append((asm.assembly_id, s))
        scores_weighted.sort(key=lambda x: -x[1])

        # Alternative D: Active member fraction * active member mean
        scores_active_frac = []
        for asm in legal_assemblies:
            mems = list(asm.member_cell_ids)
            eligs = [c for c in mems if c in rr.eligible_next_cells]
            if not eligs:
                s = 0.0
            else:
                frac = len(eligs) / float(len(mems))
                mean_act = sum(rr.gain_by_cell.get(c, 0.0) for c in eligs) / float(len(eligs))
                s = frac * mean_act
            scores_active_frac.append((asm.assembly_id, s))
        scores_active_frac.sort(key=lambda x: -x[1])

        def resolve_top(sc_list):
            if not sc_list:
                return "NONE", 0.0, 0.0
            top_id, top_s = sc_list[0]
            sec_s = sc_list[1][1] if len(sc_list) > 1 else 0.0
            res = ledger.resolve_readout(top_id, w.assemblies[top_id].structural_generation)
            surf = res.envelope.surface_utf8_nfc if (res and res.envelope) else "NONE"
            return surf, round(top_s, 6), round(top_s - sec_s, 6)

        hypotheses_results[p_name] = {
            "canonical_top": (
                ledger.resolve_readout(rr.winner_assembly_id, rr.winner_generation).envelope.surface_utf8_nfc
                if (rr.winner_assembly_id is not None and ledger.resolve_readout(rr.winner_assembly_id, rr.winner_generation))
                else "NONE"
            ),
            "canonical_score": round(rr.top_score, 6),
            "canonical_margin": round(rr.margin, 6),
            "top3_mean": resolve_top(scores_top3),
            "evidence_weighted": resolve_top(scores_weighted),
            "active_frac": resolve_top(scores_active_frac),
        }

    return hypotheses_results


def audit_s07_negative_controls(group_b_data: dict[str, Any], root: int = 112) -> dict[str, Any]:
    """Execute read-only negative controls without label leakage."""
    ckpt = group_b_data["checkpoints"][root]
    state = ckpt["state"]
    ledger = ckpt["ledger"]

    controls_res = {}

    # Control 1: Unseen lexical input
    unseen_words = ["حصان", "يركض"]
    u_envs = encode_exposure(" ".join(unseen_words), append_eos=False)
    st_u = feed_prompt(state, [e.core_event for e in u_envs])
    rr_unseen = evaluate_full_vs_control_readout(st_u)
    controls_res["unseen_lexical"] = {
        "status": rr_unseen.status.name,
        "top_score": round(rr_unseen.top_score, 6),
        "margin": round(rr_unseen.margin, 6),
        "winner_id": rr_unseen.winner_assembly_id,
    }

    # Control 2: Distinct words sharing orthographic features (e.g. prefix "ال")
    s_only = ["القط"]
    s_envs = encode_exposure(" ".join(s_only), append_eos=False)
    st_s = feed_prompt(state, [e.core_event for e in s_envs])
    rr_s = evaluate_full_vs_control_readout(st_s)
    controls_res["subject_only_cat"] = {
        "status": rr_s.status.name,
        "top_score": round(rr_s.top_score, 6),
        "margin": round(rr_s.margin, 6),
        "winner_id": rr_s.winner_assembly_id,
        "winner_surf": (
            ledger.resolve_readout(rr_s.winner_assembly_id, rr_s.winner_generation).envelope.surface_utf8_nfc
            if (rr_s.winner_assembly_id and ledger.resolve_readout(rr_s.winner_assembly_id, rr_s.winner_generation))
            else "NONE"
        ),
    }

    return controls_res


def main():
    print("Beginning D02 Forensic Investigation Engine...")
    print("1. Running Training Stream for Group A (Baseline)...")
    group_a = run_training_stream(enable_cross_clique_diversification=False)
    print("2. Running Training Stream for Group B (Diversification)...")
    group_b = run_training_stream(enable_cross_clique_diversification=True)

    print("\n--- S01: Autonomous Generation Audit across Checkpoints ---")
    s01_results = {"group_a": {}, "group_b": {}}
    for r in AUDIT_CHECKPOINTS:
        s01_results["group_a"][str(r)] = audit_s01_probes(group_a, r)
        s01_results["group_b"][str(r)] = audit_s01_probes(group_b, r)
        print(f"  Root {r:3d} audit complete.")

    print("\n--- S02: Group B Assembly 6 (Milk) Retention History ---")
    s02_results = audit_s02_milk_representation(group_b)
    for r, data in s02_results.items():
        print(f"  Root {r:3d}: members={data['member_count']}, elig={data['eligible_count']}, total_gain={data['total_eligible_gain']:.4f}, norm_score={data['normalized_score']:.6f}")

    print("\n--- S03: Wrong-Branch Analysis for P1 at Root 56 ---")
    s03_results = audit_s03_wrong_branch_p1_root56(group_b)
    print(f"  Asm 4 (ماء) Score: {s03_results['asm4_score']:.6f}")
    print(f"  Asm 6 (حليب) Score: {s03_results['asm6_score']:.6f}")
    print(f"  Active ctx after القط: {s03_results['active_ctx_after_cat']}")
    print(f"  Active ctx after يشرب: {s03_results['active_ctx_after_drinks']}")

    print("\n--- S04: EOS Continuation Asymmetry (P2 vs P4 at Root 112) ---")
    s04_results = audit_s04_eos_continuation_asymmetry(group_b)
    p2 = s04_results["p2_eagle"]
    p4 = s04_results["p4_child"]
    print(f"  P2 (النسر يشرب ماء -> next): status={p2['readout_status']}, top_score={p2['top_score']}, Asm 1 score={p2['asm1_score']}, elig={p2['asm1_elig_count']}/{p2['asm1_member_count']}")
    print(f"  P4 (الطفل يشرب ماء -> next): status={p4['readout_status']}, top_score={p4['top_score']}, Asm 1 score={p4['asm1_score']}, elig={p4['asm1_elig_count']}/{p4['asm1_member_count']}")

    print("\n--- S05: Readout Normalization Hypotheses at Root 112 ---")
    s05_results = audit_s05_readout_normalization(group_b, root=112)
    for p_name, hyp in s05_results.items():
        print(f"  {p_name}:")
        print(f"    Canonical: {hyp['canonical_top']} (score={hyp['canonical_score']}, margin={hyp['canonical_margin']})")
        print(f"    Top-3 Mean: {hyp['top3_mean'][0]} (score={hyp['top3_mean'][1]}, margin={hyp['top3_mean'][2]})")
        print(f"    Evidence-Weighted: {hyp['evidence_weighted'][0]} (score={hyp['evidence_weighted'][1]}, margin={hyp['evidence_weighted'][2]})")

    print("\n--- S07: Negative Controls at Root 112 ---")
    s07_results = audit_s07_negative_controls(group_b, root=112)
    print(f"  Unseen lexical: {s07_results['unseen_lexical']}")
    print(f"  Subject-only cat: {s07_results['subject_only_cat']}")

    all_forensics_data = {
        "s01_generation_audit": s01_results,
        "s02_milk_retention": s02_results,
        "s03_wrong_branch_p1_root56": s03_results,
        "s04_eos_asymmetry_root112": s04_results,
        "s05_readout_normalization": s05_results,
        "s07_negative_controls": s07_results,
    }

    out_path = "tools/forensics/r2_c01_d02_forensics_data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_forensics_data, f, indent=2, ensure_ascii=False)
    print(f"\nSaved complete D02 forensics dataset to {out_path}.")


if __name__ == "__main__":
    main()
