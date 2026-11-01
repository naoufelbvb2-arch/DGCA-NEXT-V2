"""DGCA NEXT V2 — R2-C01-CF03 Bounded Birth-Time Structural Reuse Counterfactual Runner.

Compares:
- Group A (Frozen Baseline): MAINTAIN -> GROW -> FORM -> MERGE -> SPLIT (enable_birth_time_grow=False)
- Group B (Experimental Birth-Time Growth): After FORM and before MERGE, run bounded GROW on newly formed assemblies (enable_birth_time_grow=True)

Corpus:
S1: القط يشرب حليب
S2: النسر يشرب ماء
S3: الطفل يأكل تفاح
S4: الطفل يشرب ماء

Checkpoints:
Roots 14, 15, 16, 17, 28, 32, 56, 112.
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

CORPUS = {
    "S1": "القط يشرب حليب",
    "S2": "النسر يشرب ماء",
    "S3": "الطفل يأكل تفاح",
    "S4": "الطفل يشرب ماء",
}

CHECKPOINT_ROOTS = [14, 15, 16, 17, 28, 32, 56, 112]


def build_schedule(total_roots: int) -> list[tuple[int, str]]:
    schedule = []
    order = ["S1", "S2", "S3", "S4"]
    for root_id in range(1, total_roots + 1):
        s_key = order[(root_id - 1) % 4]
        schedule.append((root_id, s_key))
    return schedule


def train_and_instrument_cf03(
    group_name: str,
    enable_birth_time_grow: bool,
    total_roots: int = 112,
) -> dict[str, Any]:
    print(f"\n========================================================")
    print(f"Executing {group_name} (enable_birth_time_grow={enable_birth_time_grow})")
    print(f"========================================================")
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
        enable_birth_time_grow=enable_birth_time_grow,
    )

    encoded_corpus = {
        s_key: encode_exposure(text, append_eos=True)
        for s_key, text in CORPUS.items()
    }
    schedule = build_schedule(total_roots)

    known_asms = {}
    history_log = []
    checkpoints = {}
    reports_by_root = {}

    for root_id, s_key in schedule:
        pre_asms = {
            aid: (asm.structural_generation, tuple(sorted(asm.member_cell_ids)), asm.status)
            for aid, asm in state.W.assemblies.items()
        }

        tx.begin_exposure(root_id)
        for env_idx, env in enumerate(encoded_corpus[s_key]):
            core_ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        rep = tx.end_exposure(root_id)
        reports_by_root[root_id] = rep

        post_asms = {
            aid: (asm.structural_generation, tuple(sorted(asm.member_cell_ids)), asm.status)
            for aid, asm in state.W.assemblies.items()
        }

        # Check for newly formed assemblies
        new_ids = set(post_asms.keys()) - set(pre_asms.keys())
        for aid in sorted(new_ids):
            gen, members, status = post_asms[aid]
            history_log.append({
                "type": "FORM",
                "root_id": root_id,
                "sentence_key": s_key,
                "sentence_text": CORPUS[s_key],
                "assembly_id": aid,
                "generation": gen,
                "members": list(members),
            })
            known_asms[aid] = {
                "assembly_id": aid,
                "birth_root": root_id,
                "birth_sentence": s_key,
                "birth_members": list(members),
                "birth_generation": gen,
                "surface": "UNRESOLVED",
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
                        "sentence_text": CORPUS[s_key],
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

        if root_id in CHECKPOINT_ROOTS:
            checkpoints[root_id] = {
                "state": state.clone(),
                "ledger": ledger.clone(),
                "state_hash": hash_state_snapshot({
                    "W": snapshot_w(state.W),
                    "H_slow": snapshot_h_slow(state.H_slow),
                    "R": snapshot_r(state.R),
                }),
                "assembly_snapshot": {
                    aid: {
                        "members": sorted(list(asm.member_cell_ids)),
                        "gen": asm.structural_generation,
                        "status": asm.status.name,
                    }
                    for aid, asm in sorted(state.W.assemblies.items())
                },
            }

    # Resolve surfaces from Root 112 ledger
    final_ledger = checkpoints[112]["ledger"]
    final_state = checkpoints[112]["state"]
    for aid, info in known_asms.items():
        gen = final_state.W.assemblies[aid].structural_generation
        res = final_ledger.resolve_readout(aid, gen)
        if res and res.envelope:
            info["surface"] = res.envelope.surface_utf8_nfc
        else:
            for candidate_gen in range(gen, 0, -1):
                res = final_ledger.resolve_readout(aid, candidate_gen)
                if res and res.envelope:
                    info["surface"] = res.envelope.surface_utf8_nfc
                    break

    return {
        "group_name": group_name,
        "enable_birth_time_grow": enable_birth_time_grow,
        "corpus": CORPUS,
        "encoded_corpus": encoded_corpus,
        "known_asms": known_asms,
        "history_log": history_log,
        "checkpoints": checkpoints,
        "reports_by_root": reports_by_root,
    }


def evaluate_probes(group_data: dict[str, Any], root_id: int) -> dict[str, Any]:
    st = group_data["checkpoints"][root_id]["state"]
    led = group_data["checkpoints"][root_id]["ledger"]
    encoded = group_data["encoded_corpus"]

    probes = {
        "P1 (القط يشرب)": [encoded["S1"][0].core_event, encoded["S1"][1].core_event],
        "P2 (النسر يشرب)": [encoded["S2"][0].core_event, encoded["S2"][1].core_event],
        "P3 (الطفل يأكل)": [encoded["S3"][0].core_event, encoded["S3"][1].core_event],
        "P4 (الطفل يشرب)": [encoded["S4"][0].core_event, encoded["S4"][1].core_event],
    }

    results = {}
    for p_name, p_events in probes.items():
        # First-step evaluation
        res_step1 = generate_episode(st, p_events, led, max_steps=1)
        step0 = res_step1.steps[0]
        rr0 = step0.readout_result

        # Full autonomous episode evaluation (up to 4 steps)
        res_full = generate_episode(st, p_events, led, max_steps=4)
        trajectory = []
        for s in res_full.steps:
            if s.emitted_envelope:
                trajectory.append(s.emitted_envelope.surface_utf8_nfc)
            elif s.readout_result and s.readout_result.winner_assembly_id is not None:
                trajectory.append(f"Asm_{s.readout_result.winner_assembly_id}")
            else:
                trajectory.append(s.readout_result.status.name)

        ranked = []
        for cand in rr0.ranked_scores[:4]:
            asm_cand = st.W.assemblies.get(cand.assembly_id)
            res_led = led.resolve_readout(cand.assembly_id, cand.structural_generation)
            surf_cand = res_led.envelope.surface_utf8_nfc if (res_led and res_led.envelope) else "UNATTESTED"
            ranked.append({
                "assembly_id": cand.assembly_id,
                "generation": cand.structural_generation,
                "surface": surf_cand,
                "score": round(cand.score_next, 6),
                "size": len(asm_cand.member_cell_ids) if asm_cand else 0,
            })

        results[p_name] = {
            "first_step_stop_status": res_step1.stop_status.name,
            "first_step_readout_status": rr0.status.name,
            "top_score": round(rr0.top_score, 6),
            "margin": round(rr0.margin, 6),
            "ranked_candidates": ranked,
            "full_stop_status": res_full.stop_status.name,
            "full_trajectory": trajectory,
        }
    return results


def main():
    print("=== DGCA NEXT V2 — R2-C01-CF03 Experiment Runner ===")

    # Run Group A (Frozen Baseline)
    group_a = train_and_instrument_cf03("Group A (Frozen Baseline)", enable_birth_time_grow=False, total_roots=112)

    # Run Group B (Experimental Birth-Time Growth)
    group_b = train_and_instrument_cf03("Group B (Experimental Birth-Time Growth)", enable_birth_time_grow=True, total_roots=112)

    print("\n========================================================")
    print("1. STRUCTURAL TIMING COMPARISON AT CRITICAL ROOTS")
    print("========================================================")

    for r in [14, 15, 16, 17, 27, 28, 31, 32]:
        print(f"\n--- Root {r} ---")
        for g in (group_a, group_b):
            g_name = g["group_name"]
            rep = g["reports_by_root"].get(r)
            formed = rep.assembly_report.formed_ids if rep and rep.assembly_report else ()
            grown = rep.assembly_report.grown_ids if rep and rep.assembly_report else ()
            print(f"  [{g_name}] formed={formed}, grown={grown}")
            if r in g["checkpoints"]:
                asms = g["checkpoints"][r]["assembly_snapshot"]
                target_asms = {aid: info for aid, info in asms.items() if aid in (7, 8, 9, 14, 17)}
                print(f"    Target Assemblies: {target_asms}")

    print("\n========================================================")
    print("2. ASSEMBLY FORMATION SUMMARY (ROOT 112)")
    print("========================================================")
    for g in (group_a, group_b):
        g_name = g["group_name"]
        print(f"\n--- {g_name} ---")
        water_asms = [a for a in g["known_asms"].values() if a["surface"] == "ماء"]
        apple_asms = [a for a in g["known_asms"].values() if a["surface"] == "تفاح"]

        print(f"Assemblies attesting 'ماء' ({len(water_asms)}):")
        for a in water_asms:
            aid = a["assembly_id"]
            asm_112 = g["checkpoints"][112]["state"].W.assemblies[aid]
            print(f"  Assembly {aid}: birth Root {a['birth_root']}, birth_members={a['birth_members']}, "
                  f"final_size={len(asm_112.member_cell_ids)}, members={sorted(asm_112.member_cell_ids)}, "
                  f"final_gen={asm_112.structural_generation}")

        print(f"Assemblies attesting 'تفاح' ({len(apple_asms)}):")
        for a in apple_asms:
            aid = a["assembly_id"]
            asm_112 = g["checkpoints"][112]["state"].W.assemblies[aid]
            print(f"  Assembly {aid}: birth Root {a['birth_root']}, birth_members={a['birth_members']}, "
                  f"final_size={len(asm_112.member_cell_ids)}, members={sorted(asm_112.member_cell_ids)}, "
                  f"final_gen={asm_112.structural_generation}")

    print("\n========================================================")
    print("3. GENERATION PROBES AT ROOT 56 AND ROOT 112")
    print("========================================================")
    for r in [56, 112]:
        print(f"\n--- Checkpoint Root {r} ---")
        for g in (group_a, group_b):
            g_name = g["group_name"]
            print(f"\n[{g_name}]")
            probes = evaluate_probes(g, r)
            for p_name, p_info in probes.items():
                print(f"  {p_name}:")
                print(f"    First Step: status={p_info['first_step_stop_status']} (readout={p_info['first_step_readout_status']}), top={p_info['top_score']}, margin={p_info['margin']}")
                for cand in p_info["ranked_candidates"][:2]:
                    print(f"      Aid {cand['assembly_id']} ({cand['surface']}, gen {cand['generation']}, size {cand['size']}): score={cand['score']}")
                print(f"    Full Trajectory: {p_info['full_trajectory']} (stop={p_info['full_stop_status']})")

    # Save full JSON dataset
    out_path = "tools/forensics/r2_c01_cf03_experiment_data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json_data = {
            "group_a": {
                "name": group_a["group_name"],
                "checkpoints_hashes": {r: group_a["checkpoints"][r]["state_hash"] for r in CHECKPOINT_ROOTS},
                "known_asms": group_a["known_asms"],
                "probes_56": evaluate_probes(group_a, 56),
                "probes_112": evaluate_probes(group_a, 112),
            },
            "group_b": {
                "name": group_b["group_name"],
                "checkpoints_hashes": {r: group_b["checkpoints"][r]["state_hash"] for r in CHECKPOINT_ROOTS},
                "known_asms": group_b["known_asms"],
                "probes_56": evaluate_probes(group_b, 56),
                "probes_112": evaluate_probes(group_b, 112),
            },
        }
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    print(f"\nSaved structured experimental data to {out_path}")


if __name__ == "__main__":
    main()
