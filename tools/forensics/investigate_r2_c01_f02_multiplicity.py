"""Deep forensic investigation of representational multiplicity in Group B:
Focusing on:
- Case 1: Surface 'ماء' (Assembly 7 vs Assembly 9)
- Case 2: Surface 'تفاح' (Assembly 14 vs Assembly 17)

Investigates:
F02-S01: Formation history (birth root, founding triangle, GROW events, generation increments)
F02-S02: Input representation analysis (SIC-V1 projection, sensory vs learned cells)
F02-S03: Context specialization (predecessor associative support from eagle/child/drink/eat)
F02-S04: Competition dynamics (readout candidate scoring, gain, margin, ambiguous stop)
F02-S05: Multiplicity benefits & costs
F02-S06: Zero selection leakage compliance
F02-S07: Hypothesis matrix evaluation
"""

from __future__ import annotations

import copy
import dataclasses
import os
import sys

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))
sys.stdout.reconfigure(encoding="utf-8")

from dgca.common.errors import StatusCode
from dgca.core.anatomy import Region, SynapseScope, SynapseState
from dgca.core.assembly import AssemblyStatus, THETA_A, THETA_MERGE, compute_mutual_support_r_b
from dgca.core.generator import generate_episode
from dgca.core.readout import M_READ, THETA_READ
from dgca.core.state import MachineState
from dgca.encoder.envelope import encode_exposure
from dgca.lifecycle.exposure_tx import ExposureTransactionManager
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1
from tools.forensics.run_r2_c01_cf01_experiment import CORPUS_GROUP_B, build_schedule


def trace_formation_history(total_roots: int = 112):
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
    )

    encoded_corpus = {
        s_key: encode_exposure(text, append_eos=True)
        for s_key, text in CORPUS_GROUP_B.items()
    }
    schedule = build_schedule(total_roots)

    # Track assembly lifecycle
    known_asms = {}
    history_log = []

    checkpoints = {}

    for root_id, s_key in schedule:
        # Pre-exposure state
        pre_asms = {
            aid: (asm.structural_generation, tuple(sorted(asm.member_cell_ids)), asm.status)
            for aid, asm in state.W.assemblies.items()
        }

        tx.begin_exposure(root_id)
        for env_idx, env in enumerate(encoded_corpus[s_key]):
            core_ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        tx.end_exposure(root_id)

        # Post-exposure inspection
        post_asms = {
            aid: (asm.structural_generation, tuple(sorted(asm.member_cell_ids)), asm.status)
            for aid, asm in state.W.assemblies.items()
        }

        # Check for newly formed assemblies
        new_ids = set(post_asms.keys()) - set(pre_asms.keys())
        for aid in sorted(new_ids):
            gen, members, status = post_asms[aid]
            # Resolve ledger surface if any
            res = ledger.resolve_readout(aid, gen)
            surf = res.envelope.surface_utf8_nfc if (res and res.envelope) else "UNATTESTED"
            history_log.append({
                "type": "FORM",
                "root_id": root_id,
                "sentence": s_key,
                "sentence_text": CORPUS_GROUP_B[s_key],
                "assembly_id": aid,
                "generation": gen,
                "members": list(members),
                "surface": surf,
            })
            known_asms[aid] = {
                "birth_root": root_id,
                "birth_sentence": s_key,
                "birth_members": list(members),
                "grow_events": [],
            }

        # Check for grown assemblies
        for aid in sorted(pre_asms.keys()):
            if aid in post_asms:
                pre_gen, pre_mem, pre_stat = pre_asms[aid]
                post_gen, post_mem, post_stat = post_asms[aid]
                if post_mem != pre_mem or post_gen != pre_gen:
                    added_cells = sorted(set(post_mem) - set(pre_mem))
                    history_log.append({
                        "type": "GROW",
                        "root_id": root_id,
                        "sentence": s_key,
                        "assembly_id": aid,
                        "from_gen": pre_gen,
                        "to_gen": post_gen,
                        "added_cells": added_cells,
                        "new_members": list(post_mem),
                    })
                    if aid in known_asms:
                        known_asms[aid]["grow_events"].append({
                            "root_id": root_id,
                            "sentence": s_key,
                            "from_gen": pre_gen,
                            "to_gen": post_gen,
                            "added_cells": added_cells,
                            "members_after": list(post_mem),
                        })

        if root_id in (56, 112):
            checkpoints[root_id] = {
                "state": state.clone(),
                "ledger": ledger.clone(),
            }

    return history_log, known_asms, checkpoints, encoded_corpus


def main():
    print("=== DGCA NEXT V2 — R2-C01-F02 Representational Multiplicity Investigation ===")
    history_log, known_asms, checkpoints, encoded_corpus = trace_formation_history(112)

    target_aids = [7, 9, 14, 17]
    print("\n--- F02-S01: Formation & Growth History for Target Assemblies ---")
    for aid in target_aids:
        info = known_asms.get(aid, {})
        print(f"\nAssembly {aid}:")
        print(f"  Birth Root: {info.get('birth_root')}")
        print(f"  Birth Sentence: {info.get('birth_sentence')} ('{CORPUS_GROUP_B.get(info.get('birth_sentence'))}')")
        print(f"  Founding Triangle: {info.get('birth_members')}")
        print(f"  Total GROW Events: {len(info.get('grow_events', []))}")
        for g_idx, g in enumerate(info.get('grow_events', [])):
            print(f"    Grow #{g_idx+1}: Root {g['root_id']} ({g['sentence']}) gen {g['from_gen']} -> {g['to_gen']}, added {g['added_cells']}")

    print("\n--- F02-S02: SIC-V1 Input Projections for 'ماء' and 'تفاح' ---")
    # Inspect sensory events for S2 ('النسر يشرب ماء'), S3 ('الطفل يأكل تفاح'), S4 ('الطفل يشرب ماء')
    st56 = checkpoints[56]["state"]
    st112 = checkpoints[112]["state"]
    led56 = checkpoints[56]["ledger"]
    led112 = checkpoints[112]["ledger"]

    from dgca.core.sic_v1 import project_core_event_v1
    s2_water_ev = encoded_corpus["S2"][2]  # event 2 is 'ماء'
    s4_water_ev = encoded_corpus["S4"][2]  # event 2 is 'ماء'
    s3_apple_ev = encoded_corpus["S3"][2]  # event 2 is 'تفاح'

    s2_water_proj = project_core_event_v1(s2_water_ev.core_event)
    s4_water_proj = project_core_event_v1(s4_water_ev.core_event)
    s3_apple_proj = project_core_event_v1(s3_apple_ev.core_event)

    print(f"S2 'ماء' sensory projected cells count: {len(s2_water_proj.x_float_by_global_id)}")
    print(f"S2 'ماء' sensory projected cells: {sorted(s2_water_proj.x_float_by_global_id.keys())}")
    print(f"S4 'ماء' sensory projected cells: {sorted(s4_water_proj.x_float_by_global_id.keys())}")
    print(f"S3 'تفاح' sensory projected cells: {sorted(s3_apple_proj.x_float_by_global_id.keys())}")

    # Compare sensory cells with assembly members
    water_sensory = set(s2_water_proj.x_float_by_global_id.keys())
    apple_sensory = set(s3_apple_proj.x_float_by_global_id.keys())

    for aid in target_aids:
        asm = st56.W.assemblies[aid]
        members = set(asm.member_cell_ids)
        target_sensory = water_sensory if aid in (7, 9) else apple_sensory
        shared_sensory = sorted(members & target_sensory)
        learned_cells = sorted(members - target_sensory)
        print(f"\nAssembly {aid} (gen {asm.structural_generation}, {len(members)} cells):")
        print(f"  Direct sensory support cells ({len(shared_sensory)}): {shared_sensory}")
        print(f"  Recruited / learned internal cells ({len(learned_cells)}): {learned_cells}")
        print(f"  Sensory overlap ratio: {len(shared_sensory)}/{len(members)} ({len(shared_sensory)/len(members):.2%})")

    print("\n--- F02-S03: Contextual Synaptic Wiring & Predecessor Connections ---")
    # Inspect incoming associative synapses into members of 7, 9, 14, 17
    for aid in target_aids:
        asm = st56.W.assemblies[aid]
        members = set(asm.member_cell_ids)
        incoming_syns = [
            s for s in st56.W.synapses.values()
            if s.target_id in members and s.scope == SynapseScope.ASSOCIATIVE
        ]
        print(f"\nAssembly {aid} at Root 56: {len(incoming_syns)} incoming associative synapses")
        # Group by source assembly / surface
        sources = {}
        for s in incoming_syns:
            # find which assembly source cell belongs to
            src_aids = [a for a, a_obj in st56.W.assemblies.items() if s.source_id in a_obj.member_cell_ids]
            src_label = f"Asm_{src_aids}" if src_aids else f"Cell_{s.source_id}"
            sources.setdefault(src_label, []).append((s.source_id, s.target_id, s.state.name, round(s.S, 4), s.external_count))
        for src_label, syn_list in sorted(sources.items()):
            print(f"  Source {src_label}: {len(syn_list)} synapses (states: {[x[2] for x in syn_list]})")
            for syn in syn_list[:3]:
                print(f"    {syn[0]} -> {syn[1]} state={syn[2]} wt={syn[3]} conf={syn[4]}")

    print("\n--- F02-S04: Readout Candidate Scoring Details on Ambiguous Probes ---")
    probes = {
        "P2 (النسر يشرب)": [encoded_corpus["S2"][0].core_event, encoded_corpus["S2"][1].core_event],
        "P4 (الطفل يشرب)": [encoded_corpus["S4"][0].core_event, encoded_corpus["S4"][1].core_event],
        "P3 (الطفل يأكل)": [encoded_corpus["S3"][0].core_event, encoded_corpus["S3"][1].core_event],
    }

    for p_name, p_events in probes.items():
        print(f"\nProbe {p_name} at Root 56:")
        res = generate_episode(st56, p_events, led56, max_steps=1)
        step0 = res.steps[0]
        rr0 = step0.readout_result
        print(f"  Stop Status: {res.stop_status.name}")
        print(f"  Readout Status: {rr0.status.name}")
        print(f"  Top Score: {rr0.top_score:.6f}, Margin: {rr0.margin:.6f}")
        print(f"  Top Candidates:")
        for cand in rr0.ranked_scores[:6]:
            asm_cand = st56.W.assemblies.get(cand.assembly_id)
            res_led = led56.resolve_readout(cand.assembly_id, cand.structural_generation)
            surf_cand = res_led.envelope.surface_utf8_nfc if (res_led and res_led.envelope) else "UNATTESTED"
            print(f"    Aid {cand.assembly_id} (gen {cand.structural_generation}, {surf_cand}): score={cand.score_next:.6f}, size={len(asm_cand.member_cell_ids) if asm_cand else '?'}")

    print("\n--- Detailed Gain & Normalization Breakdown for Competing Pairs ---")
    for p_name, p_events in probes.items():
        res = generate_episode(st56, p_events, led56, max_steps=1)
        rr = res.steps[0].readout_result

        print(f"\nBreakdown for {p_name} at Root 56:")
        pair_to_inspect = (7, 9) if "يشرب" in p_name else (14, 17)
        for aid in pair_to_inspect:
            asm = st56.W.assemblies[aid]
            mems = sorted(list(asm.member_cell_ids))
            print(f"  Assembly {aid} (|G|={len(mems)}, gen={asm.structural_generation}):")
            total_gain = 0.0
            for c in mems:
                af = rr.a_full_by_cell.get(c, 0.0)
                ac = rr.a_control_by_cell.get(c, 0.0)
                is_elig = c in rr.eligible_next_cells
                g = rr.gain_by_cell.get(c, 0.0) if is_elig else 0.0
                total_gain += g
                print(f"    Cell {c}: A_full={af:.4f}, A_ctrl={ac:.4f}, elig={is_elig}, gain={g:.4f}")
            mean_score = total_gain / len(mems)
            print(f"  -> Sum Gain: {total_gain:.6f}, Denominator: {len(mems)}, Score: {mean_score:.6f}")

    print("\n--- Detailed Gain & Normalization Breakdown at Root 112 ---")
    for p_name, p_events in probes.items():
        res = generate_episode(st112, p_events, led112, max_steps=1)
        rr = res.steps[0].readout_result

        print(f"\nBreakdown for {p_name} at Root 112:")
        pair_to_inspect = (7, 9) if "يشرب" in p_name else (14, 17)
        for aid in pair_to_inspect:
            asm = st112.W.assemblies[aid]
            mems = sorted(list(asm.member_cell_ids))
            print(f"  Assembly {aid} (|G|={len(mems)}, gen={asm.structural_generation}):")
            total_gain = 0.0
            for c in mems:
                af = rr.a_full_by_cell.get(c, 0.0)
                ac = rr.a_control_by_cell.get(c, 0.0)
                is_elig = c in rr.eligible_next_cells
                g = rr.gain_by_cell.get(c, 0.0) if is_elig else 0.0
                total_gain += g
                print(f"    Cell {c}: A_full={af:.4f}, A_ctrl={ac:.4f}, elig={is_elig}, gain={g:.4f}")
            mean_score = total_gain / len(mems)
            print(f"  -> Sum Gain: {total_gain:.6f}, Denominator: {len(mems)}, Score: {mean_score:.6f}")


if __name__ == "__main__":
    main()
