"""DGCA NEXT V2 — R2-C01-CF02 Controlled Sensory Fragmentation and Assembly Formation Counterfactual.

Investigates whether representational multiplicity requires multiple linguistic contexts
(Group A: Two Contexts) or arises from repeated sensory exposure under a single context
(Group B: Repeated Single Context).

Preserves:
- Zero modifications to production code (src/)
- Frozen Core and LLA dynamics
- ZERO_SELECTION_LEAKAGE
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
from dgca.core.anatomy import Region, SynapseScope, SynapseState
from dgca.core.assembly import AssemblyStatus, THETA_A, THETA_MERGE, compute_mutual_support_r_b
from dgca.core.generator import generate_episode
from dgca.core.readout import M_READ, THETA_READ
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import MachineState
from dgca.encoder.envelope import encode_exposure
from dgca.lifecycle.exposure_tx import ExposureTransactionManager
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1
from tests.test_r2_a01_patch2_acceptance import hash_state_snapshot, snapshot_w, snapshot_h_slow, snapshot_r

CORPUS_GROUP_A = {
    "S1": "القط يشرب حليب",
    "S2": "النسر يشرب ماء",
    "S3": "الطفل يأكل تفاح",
    "S4": "الطفل يشرب ماء",
}

CORPUS_GROUP_B = {
    "S1": "القط يشرب حليب",
    "S2": "النسر يشرب ماء",
    "S3": "الطفل يأكل تفاح",
    "S4": "النسر يشرب ماء",
}


def build_schedule(total_roots: int) -> list[tuple[int, str]]:
    schedule = []
    order = ["S1", "S2", "S3", "S4"]
    for root_id in range(1, total_roots + 1):
        s_key = order[(root_id - 1) % 4]
        schedule.append((root_id, s_key))
    return schedule


def train_and_instrument_group(group_name: str, corpus: dict[str, str], total_roots: int = 112):
    print(f"\n========================================================")
    print(f"Executing {group_name} ({total_roots} roots)")
    print(f"========================================================")
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
        for s_key, text in corpus.items()
    }
    schedule = build_schedule(total_roots)

    known_asms = {}
    history_log = []
    checkpoints = {}
    water_exposure_log = []
    water_exp_count = 0

    for root_id, s_key in schedule:
        pre_asms = {
            aid: (asm.structural_generation, tuple(sorted(asm.member_cell_ids)), asm.status)
            for aid, asm in state.W.assemblies.items()
        }

        tx.begin_exposure(root_id)
        for env_idx, env in enumerate(encoded_corpus[s_key]):
            core_ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            
            # If this is 'ماء', inspect active sensory cells before and after
            is_water = env.peripheral_surface.surface_utf8_nfc == "ماء"
            if is_water:
                water_exp_count += 1
                proj = project_core_event_v1(core_ev)
                sens_cells = sorted(list(proj.x_float_by_global_id.keys()))
                covered_cells = set()
                for aid, asm in state.W.assemblies.items():
                    if asm.status == AssemblyStatus.LIVE:
                        covered_cells.update(set(asm.member_cell_ids) & set(sens_cells))
                uncovered_cells = sorted(set(sens_cells) - covered_cells)

            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)

            if is_water:
                post_ev_covered = set()
                for aid, asm in state.W.assemblies.items():
                    if asm.status == AssemblyStatus.LIVE:
                        post_ev_covered.update(set(asm.member_cell_ids) & set(sens_cells))
                post_ev_uncovered = sorted(set(sens_cells) - post_ev_covered)
                water_exposure_log.append({
                    "exposure_num": water_exp_count,
                    "root_id": root_id,
                    "sentence_key": s_key,
                    "sensory_cells_count": len(sens_cells),
                    "covered_before": sorted(list(covered_cells)),
                    "uncovered_before": uncovered_cells,
                    "covered_after": sorted(list(post_ev_covered)),
                    "uncovered_after": post_ev_uncovered,
                })

        tx.end_exposure(root_id)

        post_asms = {
            aid: (asm.structural_generation, tuple(sorted(asm.member_cell_ids)), asm.status)
            for aid, asm in state.W.assemblies.items()
        }

        # Check for newly formed assemblies
        new_ids = set(post_asms.keys()) - set(pre_asms.keys())
        for aid in sorted(new_ids):
            gen, members, status = post_asms[aid]
            res = ledger.resolve_readout(aid, gen)
            surf = res.envelope.surface_utf8_nfc if (res and res.envelope) else "UNATTESTED"
            entry = {
                "type": "FORM",
                "root_id": root_id,
                "sentence_key": s_key,
                "sentence_text": corpus[s_key],
                "assembly_id": aid,
                "generation": gen,
                "members": list(members),
                "surface": surf,
            }
            history_log.append(entry)
            known_asms[aid] = {
                "assembly_id": aid,
                "birth_root": root_id,
                "birth_sentence": s_key,
                "birth_sentence_text": corpus[s_key],
                "birth_members": list(members),
                "surface": surf,
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
                        "sentence_key": s_key,
                        "sentence_text": corpus[s_key],
                        "assembly_id": aid,
                        "from_gen": pre_gen,
                        "to_gen": post_gen,
                        "added_cells": added_cells,
                        "new_members": list(post_mem),
                    })
                    if aid in known_asms:
                        known_asms[aid]["grow_events"].append({
                            "root_id": root_id,
                            "sentence_key": s_key,
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

    # Post-process known_asms with surfaces resolved from final ledger
    final_ledger = checkpoints[112]["ledger"]
    final_state = checkpoints[112]["state"]
    for aid, info in known_asms.items():
        gen = final_state.W.assemblies[aid].structural_generation
        res = final_ledger.resolve_readout(aid, gen)
        if res and res.envelope:
            info["surface"] = res.envelope.surface_utf8_nfc
        else:
            # check any generation in ledger
            for candidate_gen in range(gen, 0, -1):
                res = final_ledger.resolve_readout(aid, candidate_gen)
                if res and res.envelope:
                    info["surface"] = res.envelope.surface_utf8_nfc
                    break

    return {
        "group_name": group_name,
        "corpus": corpus,
        "schedule": schedule,
        "encoded_corpus": encoded_corpus,
        "known_asms": known_asms,
        "history_log": history_log,
        "water_exposure_log": water_exposure_log,
        "checkpoints": checkpoints,
    }


def analyze_sensory_projections(group_data: dict[str, Any]):
    corpus = group_data["corpus"]
    encoded = group_data["encoded_corpus"]
    st56 = group_data["checkpoints"][56]["state"]
    st112 = group_data["checkpoints"][112]["state"]
    led56 = group_data["checkpoints"][56]["ledger"]
    led112 = group_data["checkpoints"][112]["ledger"]

    # Sensory projections for all unique tokens
    sensory_footprints = {}
    for s_key, env_list in encoded.items():
        for env in env_list:
            surf = env.peripheral_surface.surface_utf8_nfc
            if surf not in sensory_footprints:
                proj = project_core_event_v1(env.core_event)
                sensory_footprints[surf] = sorted(list(proj.x_float_by_global_id.keys()))

    # Find assemblies for each surface at Root 56 and Root 112
    surface_assemblies_56 = {}
    surface_assemblies_112 = {}

    for aid, asm in st56.W.assemblies.items():
        res = led56.resolve_readout(aid, asm.structural_generation)
        surf = res.envelope.surface_utf8_nfc if (res and res.envelope) else "UNATTESTED"
        surface_assemblies_56.setdefault(surf, []).append((aid, asm.structural_generation, sorted(asm.member_cell_ids)))

    for aid, asm in st112.W.assemblies.items():
        res = led112.resolve_readout(aid, asm.structural_generation)
        surf = res.envelope.surface_utf8_nfc if (res and res.envelope) else "UNATTESTED"
        surface_assemblies_112.setdefault(surf, []).append((aid, asm.structural_generation, sorted(asm.member_cell_ids)))

    return sensory_footprints, surface_assemblies_56, surface_assemblies_112


def run_probe_evaluations(group_data: dict[str, Any], root_id: int):
    st = group_data["checkpoints"][root_id]["state"]
    led = group_data["checkpoints"][root_id]["ledger"]
    encoded = group_data["encoded_corpus"]

    probes = {}
    if "S2" in encoded and len(encoded["S2"]) >= 2:
        probes["P_eagle_drink (النسر يشرب)"] = [encoded["S2"][0].core_event, encoded["S2"][1].core_event]
    if "S4" in encoded and len(encoded["S4"]) >= 2 and group_data["corpus"]["S4"].startswith("الطفل"):
        probes["P_child_drink (الطفل يشرب)"] = [encoded["S4"][0].core_event, encoded["S4"][1].core_event]
    if "S3" in encoded and len(encoded["S3"]) >= 2:
        probes["P_child_eat (الطفل يأكل)"] = [encoded["S3"][0].core_event, encoded["S3"][1].core_event]

    probe_results = {}
    for p_name, p_events in probes.items():
        res = generate_episode(st, p_events, led, max_steps=1)
        step0 = res.steps[0]
        rr0 = step0.readout_result
        cand_list = []
        for cand in rr0.ranked_scores[:6]:
            asm_cand = st.W.assemblies.get(cand.assembly_id)
            res_led = led.resolve_readout(cand.assembly_id, cand.structural_generation)
            surf_cand = res_led.envelope.surface_utf8_nfc if (res_led and res_led.envelope) else "UNATTESTED"
            cand_list.append({
                "assembly_id": cand.assembly_id,
                "generation": cand.structural_generation,
                "surface": surf_cand,
                "score": round(cand.score_next, 6),
                "size": len(asm_cand.member_cell_ids) if asm_cand else 0,
            })
        probe_results[p_name] = {
            "stop_status": res.stop_status.name,
            "readout_status": rr0.status.name,
            "top_score": round(rr0.top_score, 6),
            "margin": round(rr0.margin, 6),
            "ranked_candidates": cand_list,
        }
    return probe_results


def main():
    print("=== DGCA NEXT V2 — R2-C01-CF02 Counterfactual Experiment ===")

    # Run Group A (Two Contexts)
    group_a = train_and_instrument_group("Group A (Two Contexts)", CORPUS_GROUP_A, 112)

    # Run Group B (Repeated Single Context)
    group_b = train_and_instrument_group("Group B (Repeated Single Context)", CORPUS_GROUP_B, 112)

    # Compare Assemblies for 'ماء' and 'تفاح'
    print("\n========================================================")
    print("1. ASSEMBLY FORMATION SUMMARY COMPARISON")
    print("========================================================")

    for g in (group_a, group_b):
        g_name = g["group_name"]
        print(f"\n--- {g_name} ---")
        water_asms = [a for a in g["known_asms"].values() if a["surface"] == "ماء"]
        apple_asms = [a for a in g["known_asms"].values() if a["surface"] == "تفاح"]

        print(f"Assemblies attesting 'ماء': {len(water_asms)}")
        for a in water_asms:
            aid = a["assembly_id"]
            asm_obj_112 = g["checkpoints"][112]["state"].W.assemblies[aid]
            print(f"  Assembly {aid}: birth Root {a['birth_root']} ({a['birth_sentence']}: {a['birth_sentence_text']}), "
                  f"founding={a['birth_members']}, gen={asm_obj_112.structural_generation}, "
                  f"size={len(asm_obj_112.member_cell_ids)}, members={sorted(asm_obj_112.member_cell_ids)}")
            for g_ev in a["grow_events"]:
                print(f"    GROW at Root {g_ev['root_id']} ({g_ev['sentence_key']}) gen {g_ev['from_gen']}->{g_ev['to_gen']}, added {g_ev['added_cells']}")

        print(f"\nAssemblies attesting 'تفاح' (Internal Control): {len(apple_asms)}")
        for a in apple_asms:
            aid = a["assembly_id"]
            asm_obj_112 = g["checkpoints"][112]["state"].W.assemblies[aid]
            print(f"  Assembly {aid}: birth Root {a['birth_root']} ({a['birth_sentence']}: {a['birth_sentence_text']}), "
                  f"founding={a['birth_members']}, gen={asm_obj_112.structural_generation}, "
                  f"size={len(asm_obj_112.member_cell_ids)}, members={sorted(asm_obj_112.member_cell_ids)}")
            for g_ev in a["grow_events"]:
                print(f"    GROW at Root {g_ev['root_id']} ({g_ev['sentence_key']}) gen {g_ev['from_gen']}->{g_ev['to_gen']}, added {g_ev['added_cells']}")

    # Sensory footprint comparison
    print("\n========================================================")
    print("2. SENSORY FOOTPRINT & CELL MEMBERSHIP OVERLAP")
    print("========================================================")
    for g in (group_a, group_b):
        g_name = g["group_name"]
        print(f"\n--- {g_name} ---")
        sensory_fps, asms_56, asms_112 = analyze_sensory_projections(g)
        water_sensory = set(sensory_fps.get("ماء", []))
        apple_sensory = set(sensory_fps.get("تفاح", []))
        print(f"ماء sensory cells ({len(water_sensory)}): {sorted(water_sensory)}")

        water_asms_112 = asms_112.get("ماء", [])
        for aid, gen, members in water_asms_112:
            m_set = set(members)
            sens_overlap = m_set & water_sensory
            non_sens = m_set - water_sensory
            print(f"  Asm {aid} (gen {gen}, size {len(members)}): {len(sens_overlap)}/{len(members)} sensory ({len(sens_overlap)/len(members):.1%}), non-sensory={sorted(non_sens)}")

        # Pairwise overlap between water assemblies
        if len(water_asms_112) >= 2:
            for i in range(len(water_asms_112)):
                for j in range(i + 1, len(water_asms_112)):
                    aid_i, _, mem_i = water_asms_112[i]
                    aid_j, _, mem_j = water_asms_112[j]
                    inter = set(mem_i) & set(mem_j)
                    union = set(mem_i) | set(mem_j)
                    jaccard = len(inter) / len(union) if union else 0.0
                    print(f"  Pair (Asm {aid_i}, Asm {aid_j}): intersection={sorted(inter)} ({len(inter)} cells), Jaccard={jaccard:.4f}")

        print(f"\nSensory Footprint Progression for 'ماء' across First 10 Exposures in {g_name}:")
        for exp in g["water_exposure_log"][:10]:
            print(f"  Exp #{exp['exposure_num']}: Root {exp['root_id']} ({exp['sentence_key']}) | "
                  f"Covered Before: {len(exp['covered_before'])}/{exp['sensory_cells_count']} -> "
                  f"Covered After: {len(exp['covered_after'])}/{exp['sensory_cells_count']} | "
                  f"Uncovered After: {len(exp['uncovered_after'])}")

    # Probing results at Root 56 and Root 112
    print("\n========================================================")
    print("3. PROBE EVALUATION RESULTS")
    print("========================================================")
    for root in (56, 112):
        print(f"\n--- Checkpoint Root {root} ---")
        for g in (group_a, group_b):
            g_name = g["group_name"]
            print(f"\n[{g_name}]")
            res = run_probe_evaluations(g, root)
            for p_name, p_info in res.items():
                print(f"  {p_name}:")
                print(f"    Stop Status: {p_info['stop_status']}, Readout Status: {p_info['readout_status']}")
                print(f"    Top Score: {p_info['top_score']}, Margin: {p_info['margin']}")
                for cand in p_info['ranked_candidates'][:4]:
                    print(f"      Aid {cand['assembly_id']} (gen {cand['generation']}, {cand['surface']}): score={cand['score']}, size={cand['size']}")

    # Save complete JSON data
    out_path = "tools/forensics/r2_c01_cf02_experiment_data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        # Convert non-serializable objects
        summary_data = {
            "group_a": {
                "name": group_a["group_name"],
                "corpus": group_a["corpus"],
                "assemblies": {
                    aid: {
                        "birth_root": a["birth_root"],
                        "birth_sentence": a["birth_sentence"],
                        "surface": a["surface"],
                        "founding_cells": a["birth_members"],
                        "grow_events": a["grow_events"],
                        "members_at_112": sorted(group_a["checkpoints"][112]["state"].W.assemblies[aid].member_cell_ids),
                        "generation_at_112": group_a["checkpoints"][112]["state"].W.assemblies[aid].structural_generation,
                    }
                    for aid, a in group_a["known_asms"].items()
                },
                "probes_56": run_probe_evaluations(group_a, 56),
                "probes_112": run_probe_evaluations(group_a, 112),
            },
            "group_b": {
                "name": group_b["group_name"],
                "corpus": group_b["corpus"],
                "assemblies": {
                    aid: {
                        "birth_root": a["birth_root"],
                        "birth_sentence": a["birth_sentence"],
                        "surface": a["surface"],
                        "founding_cells": a["birth_members"],
                        "grow_events": a["grow_events"],
                        "members_at_112": sorted(group_b["checkpoints"][112]["state"].W.assemblies[aid].member_cell_ids),
                        "generation_at_112": group_b["checkpoints"][112]["state"].W.assemblies[aid].structural_generation,
                    }
                    for aid, a in group_b["known_asms"].items()
                },
                "probes_56": run_probe_evaluations(group_b, 56),
                "probes_112": run_probe_evaluations(group_b, 112),
            },
        }
        json.dump(summary_data, f, indent=2, ensure_ascii=False)
    print(f"\nSaved structured experimental data to {out_path}")


if __name__ == "__main__":
    main()
