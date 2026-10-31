"""R2-C01-F01 Causal Forensics of Multi-Context Learning and Generation Failure.

Authoritative forensic investigation tool that captures:
- Exact step-by-step FULL vs CONTROL activation traces for P1-P4.
- Explicit quantification of EOS-member vs candidate-specific saturation.
- Synapse-level audit of associative pathways (drink -> milk vs drink -> water).
- Candidate deadline expiration and pruning traces at Root 30.
- Contextual binding (z=8320) fan-out and downstream activation analysis.
- Premature associative excitation of EOS from subject definite prefix '^ال'.
- Cross-context intrusion pathway (water -> eat -> apple) at Root 112.
- Comparison with historical Cat/Eagle EOS dynamics.
"""

from __future__ import annotations

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
from dgca.core.generator import generate_episode
from dgca.core.dynamics import execute_two_pass_event, compute_next_step_temporal_drive
from dgca.core.readout import evaluate_full_vs_control_readout, M_READ, THETA_READ
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import ExecutionMode, MachineState
from dgca.encoder.envelope import encode_exposure, reinject_attested_bundle, EventOrigin
from dgca.lifecycle.exposure_tx import ExposureTransactionManager
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1
from tools.forensics.run_r2_c01_trial import (
    CORPUS,
    build_schedule,
    train_trial,
    snapshot_machine_state,
)
from tests.test_r2_a01_patch2_acceptance import hash_state_snapshot


def audit_f01_s01_reproduction(state56, ledger56, state112, ledger112, encoded_corpus):
    """Reproduce exact 56-root and 112-root traces and verify reproducibility."""
    h56 = hash_state_snapshot(snapshot_machine_state(state56))
    h112 = hash_state_snapshot(snapshot_machine_state(state112))
    
    probes_56 = {}
    for pid, s_key, p_text in [
        ("P1", "S1", "القط يشرب"),
        ("P2", "S2", "النسر يشرب"),
        ("P3", "S3", "الطفل يأكل"),
        ("P4", "S4", "الطفل يشرب"),
    ]:
        p_events = [encoded_corpus[s_key][0].core_event, encoded_corpus[s_key][1].core_event]
        gen = generate_episode(state56, p_events, ledger56, max_steps=4)
        probes_56[pid] = {
            "prefix": p_text,
            "stop_status": gen.stop_status.name,
            "emitted_surfaces": list(gen.emitted_surfaces),
            "step_count": len(gen.steps),
        }
    
    probes_112 = {}
    for pid, s_key, p_text in [
        ("P1", "S1", "القط يشرب"),
        ("P2", "S2", "النسر يشرب"),
        ("P3", "S3", "الطفل يأكل"),
        ("P4", "S4", "الطفل يشرب"),
    ]:
        p_events = [encoded_corpus[s_key][0].core_event, encoded_corpus[s_key][1].core_event]
        gen = generate_episode(state112, p_events, ledger112, max_steps=4)
        probes_112[pid] = {
            "prefix": p_text,
            "stop_status": gen.stop_status.name,
            "emitted_surfaces": list(gen.emitted_surfaces),
            "step_count": len(gen.steps),
        }

    return {
        "h56": h56,
        "h112": h112,
        "probes_56": probes_56,
        "probes_112": probes_112,
    }


def audit_f01_s02_step_traces(state56, ledger56, encoded_corpus):
    """Full vs Control step-by-step traces for P1-P4."""
    traces = {}
    for pid, s_key, p_text in [
        ("P1", "S1", "القط يشرب"),
        ("P2", "S2", "النسر يشرب"),
        ("P3", "S3", "الطفل يأكل"),
        ("P4", "S4", "الطفل يشرب"),
    ]:
        p_events = [encoded_corpus[s_key][0].core_event, encoded_corpus[s_key][1].core_event]
        gen = generate_episode(state56, p_events, ledger56, max_steps=4)
        step_list = []
        for s in gen.steps:
            top_scores = [
                {
                    "assembly_id": c.assembly_id,
                    "generation": c.structural_generation,
                    "score": round(c.score_next, 6),
                    "eligible_count": c.eligible_member_count,
                    "member_count": c.member_count,
                }
                for c in s.readout_result.ranked_scores[:4]
            ]
            step_list.append({
                "step_index": s.step_index,
                "winner_assembly_id": s.winner_assembly_id,
                "winner_generation": s.winner_generation,
                "status": s.readout_result.status.name,
                "top_score": round(s.readout_result.top_score, 6),
                "second_score": round(s.readout_result.second_score, 6),
                "margin": round(s.readout_result.margin, 6),
                "emitted_surface": s.emitted_envelope.raw_surface_nfc_utf8 if s.emitted_envelope else None,
                "top_candidates": top_scores,
            })
        traces[pid] = {
            "prefix": p_text,
            "stop_status": gen.stop_status.name,
            "steps": step_list,
        }
    return traces


def audit_f01_s03_associative_pathways(state56, state112):
    """Direct associative pathways supporting drink -> milk vs drink -> water."""
    drink_f0 = (8327, 9005, 10167, 10696)
    asm11_members = state56.W.assemblies[11].member_cell_ids # milk
    asm6_members = state56.W.assemblies[6].member_cell_ids   # water

    def extract_synapses(st, tgts):
        data = {}
        for src in drink_f0:
            for tgt in tgts:
                syn = st.W.synapses.get((src, tgt, 2)) # ASSOCIATIVE
                if syn:
                    data[f"{src}->{tgt}"] = {
                        "state": syn.state.name,
                        "S": round(syn.S, 4),
                        "E_ext": round(syn.E_ext, 4),
                        "confirmed_roots": sorted(list(syn.confirmed_roots)),
                        "last_evidence_root": syn.last_evidence_root,
                    }
        return data

    return {
        "root56": {
            "drink_to_milk": extract_synapses(state56, asm11_members),
            "drink_to_water": extract_synapses(state56, asm6_members),
        },
        "root112": {
            "drink_to_milk": extract_synapses(state112, asm11_members),
            "drink_to_water": extract_synapses(state112, asm6_members),
        },
    }


def audit_f01_s04_context_bindings(state56):
    """Audit contextual bindings and forward targets."""
    bindings = {}
    for bid, b in sorted(state56.W.stable_bindings.items()):
        fwd_syns = {}
        for (src, tgt, scope), syn in state56.W.synapses.items():
            if src == b.z_cell_id:
                fwd_syns[f"{src}->{tgt}({scope.name})"] = {
                    "state": syn.state.name,
                    "S": round(syn.S, 4),
                    "E_ext": round(syn.E_ext, 4),
                    "confirmed_roots": sorted(list(syn.confirmed_roots)),
                }
        bindings[bid] = {
            "z_cell_id": b.z_cell_id,
            "anchor_id": b.anchor_id,
            "p_sources": list(b.p_sources),
            "depth": b.depth,
            "forward_synapses": fwd_syns,
        }
    return bindings


def audit_f01_s05_eos_pathways(state56, encoded_corpus, ledger56):
    """Audit EOS activation and explain premature saturation."""
    eos_members = sorted(list(state56.W.assemblies[2].member_cell_ids))
    
    # Trace P2 (النسر يشرب) prompt events
    p2_events = [encoded_corpus["S2"][0].core_event, encoded_corpus["S2"][1].core_event]
    gen2 = generate_episode(state56, p2_events, ledger56, max_steps=4)
    
    ev0_res = gen2.prompt_event_results[0] # eagle
    ev1_res = gen2.prompt_event_results[1] # drink
    step0_reinj = gen2.steps[0].reinjected_event_result # water reinjected

    ev0_eos = {c: round(ev0_res.a_plus_by_cell.get(c, 0.0), 4) for c in eos_members}
    ev1_eos = {c: round(ev1_res.a_plus_by_cell.get(c, 0.0), 4) for c in eos_members}
    ev1_pt_eos = {c: round(ev1_res.pt_by_cell.get(c, 0.0), 4) for c in eos_members}
    reinj_eos = {c: round(step0_reinj.a_plus_by_cell.get(c, 0.0), 4) for c in eos_members}

    # Step 1 full and ctrl
    step1 = gen2.steps[1]
    step1_full_eos = {c: round(step1.readout_result.a_full_by_cell.get(c, 0.0), 4) for c in eos_members}
    step1_ctrl_eos = {c: round(step1.readout_result.a_control_by_cell.get(c, 0.0), 4) for c in eos_members}
    step1_gain_eos = {c: round(step1.readout_result.gain_by_cell.get(c, 0.0), 4) for c in eos_members}

    # Compare with historical Cat/Eagle
    state_hist = MachineState()
    ledger_hist = SurfaceReadoutLedgerV1()
    tx_hist = ExposureTransactionManager(state_hist, enable_context_pipeline=True, enable_assembly_pipeline=True, readout_ledger=ledger_hist)
    branch_ab = encode_exposure("القط يشرب حليب", append_eos=True)
    branch_db = encode_exposure("النسر يشرب ماء", append_eos=True)
    for root_id in range(1, 57):
        envs = branch_ab if root_id % 2 != 0 else branch_db
        tx_hist.begin_exposure(root_id)
        for env in envs:
            core_ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx_hist.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        tx_hist.end_exposure(root_id)

    gen_hist = generate_episode(state_hist, [branch_ab[0].core_event, branch_ab[1].core_event], ledger_hist, max_steps=4)
    hist_ev1_eos = {c: round(gen_hist.prompt_event_results[1].a_plus_by_cell.get(c, 0.0), 4) for c in (8728, 10417, 11859, 12117)}

    return {
        "r2_c01": {
            "eos_members": eos_members,
            "ev0_eagle_a_plus": ev0_eos,
            "ev1_drink_a_plus": ev1_eos,
            "ev1_drink_pt": ev1_pt_eos,
            "step0_water_reinj_a_plus": reinj_eos,
            "step1_a_full": step1_full_eos,
            "step1_a_ctrl": step1_ctrl_eos,
            "step1_gain": step1_gain_eos,
        },
        "historical_cat_eagle": {
            "ev1_drink_a_plus": hist_ev1_eos,
            "step1_stop_status": gen_hist.stop_status.name,
            "step1_top_score": round(gen_hist.steps[1].readout_result.top_score, 6),
            "step1_winner_assembly_id": gen_hist.steps[1].winner_assembly_id,
        },
    }


def audit_f01_s06_cross_context_intrusion(state112, encoded_corpus, ledger112):
    """Audit cross-context intrusion at 112 roots."""
    p2_events = [encoded_corpus["S2"][0].core_event, encoded_corpus["S2"][1].core_event]
    gen2 = generate_episode(state112, p2_events, ledger112, max_steps=5)
    
    return {
        "stop_status": gen2.stop_status.name,
        "emitted_surfaces": list(gen2.emitted_surfaces),
        "steps": [
            {
                "step_index": s.step_index,
                "winner_assembly_id": s.winner_assembly_id,
                "winner_generation": s.winner_generation,
                "emitted_surface": s.emitted_envelope.raw_surface_nfc_utf8 if s.emitted_envelope else None,
                "top_score": round(s.readout_result.top_score, 6),
                "margin": round(s.readout_result.margin, 6),
            }
            for s in gen2.steps
        ],
    }


def audit_f01_s07_morphological_overlap(state56):
    """Audit shared '^ال' prefix and Assembly 1 hyper-attestation."""
    words = ["القط", "النسر", "الطفل", "يشرب", "يأكل", "الحليب", "الماء", "التفاح"]
    overlap = {}
    for w in words:
        envs = encode_exposure(w, append_eos=False)
        pr = project_core_event_v1(envs[0].core_event)
        overlap[w] = {
            "contains_8416": 8416 in pr.x_fixed_by_global_id,
            "contains_8575": 8575 in pr.x_fixed_by_global_id,
            "contains_8586": 8586 in pr.x_fixed_by_global_id,
            "fixed_support": pr.x_fixed_by_global_id.get(8416, 0),
        }
    
    asm1 = state56.W.assemblies[1]
    return {
        "prefix_sharing": overlap,
        "assembly_1": {
            "id": asm1.assembly_id,
            "generation": asm1.structural_generation,
            "members": list(asm1.member_cell_ids),
        },
    }


def run_all_forensics():
    print("=== DGCA NEXT V2 — R2-C01-F01 CAUSAL FORENSIC AUDIT ===")
    
    print("\n[1/7] Training 56 roots...")
    state56, ledger56, tx56, encoded_corpus, _ = train_trial(56)

    print("\n[2/7] Training 112 roots...")
    state112, ledger112, tx112, _, _ = train_trial(112)

    print("\n[3/7] Auditing Baseline Reproduction (F01-S01)...")
    s01_data = audit_f01_s01_reproduction(state56, ledger56, state112, ledger112, encoded_corpus)

    print("\n[4/7] Auditing FULL vs CONTROL Causal Step Traces (F01-S02)...")
    s02_data = audit_f01_s02_step_traces(state56, ledger56, encoded_corpus)

    print("\n[5/7] Auditing Associative Dilution & Candidate Deadlines (F01-S03)...")
    s03_data = audit_f01_s03_associative_pathways(state56, state112)

    print("\n[6/7] Auditing Contextual Bindings and Fan-Out (F01-S04)...")
    s04_data = audit_f01_s04_context_bindings(state56)

    print("\n[7/7] Auditing EOS Transition, Intrusion, and Morphology (F01-S05, S06, S07)...")
    s05_data = audit_f01_s05_eos_pathways(state56, encoded_corpus, ledger56)
    s06_data = audit_f01_s06_cross_context_intrusion(state112, encoded_corpus, ledger112)
    s07_data = audit_f01_s07_morphological_overlap(state56)

    forensics_dataset = {
        "s01_reproduction": s01_data,
        "s02_step_traces": s02_data,
        "s03_associative_pathways": s03_data,
        "s04_context_bindings": s04_data,
        "s05_eos_pathways": s05_data,
        "s06_cross_context_intrusion": s06_data,
        "s07_morphological_overlap": s07_data,
    }

    out_path = "tools/forensics/r2_c01_f01_forensics_data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(forensics_dataset, f, indent=2, ensure_ascii=False)
    print(f"\nAuthoritative forensic dataset saved to {out_path}")


if __name__ == "__main__":
    run_all_forensics()
