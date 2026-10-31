"""R2-C01 Four-Sentence Learning, Context Discrimination & Memory Retention Trial Runner.

Executes:
- Cold-start training on 4 sentences across 56 roots (and 112 roots if needed).
- Pre-registered balanced round-robin schedule.
- Primary context probes P1, P2, P3, P4.
- Ambiguity probes: 'الطفل', 'يشرب'.
- Unsupported combination diagnostics: 'النسر يأكل', 'القط يأكل'.
- Read-only state immutability verification.
- Deterministic replay verification across independent runs.
- Detailed telemetry logging for R2-C01 trial report.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from dgca.common.errors import StatusCode
from dgca.core.generator import generate_episode, GenerateEpisodeResult
from dgca.core.state import MachineState
from dgca.encoder.envelope import Marker, encode_exposure
from dgca.lifecycle.exposure_tx import ExposureTransactionManager
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1
from tests.test_r2_a01_patch2_acceptance import (
    hash_state_snapshot,
    snapshot_w,
    snapshot_h_slow,
    snapshot_r,
    snapshot_ledger,
)


def snapshot_machine_state(state: MachineState) -> dict[str, Any]:
    return {
        "W": snapshot_w(state.W),
        "H_slow": snapshot_h_slow(state.H_slow),
        "R": snapshot_r(state.R),
    }


CORPUS = {
    "S1": "القط يشرب الحليب",
    "S2": "النسر يشرب الماء",
    "S3": "الطفل يأكل التفاح",
    "S4": "الطفل يشرب الماء",
}


def build_schedule(total_roots: int) -> list[tuple[int, str]]:
    """Balanced round-robin interleaved schedule."""
    schedule = []
    order = ["S1", "S2", "S3", "S4"]
    for root_id in range(1, total_roots + 1):
        s_key = order[(root_id - 1) % 4]
        schedule.append((root_id, s_key))
    return schedule


def train_trial(total_roots: int = 56):
    """Execute cold-start training over the specified number of roots."""
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
        for s_key, text in CORPUS.items()
    }

    schedule = build_schedule(total_roots)
    milestones = {}

    for root_id, s_key in schedule:
        envs = encoded_corpus[s_key]
        tx.begin_exposure(root_id)
        for env in envs:
            core_ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        tx.end_exposure(root_id)

        if root_id in (14, 28, 42, 56, 70, 84, 98, 112):
            milestones[root_id] = capture_telemetry(state, ledger, root_id)

    return state, ledger, tx, encoded_corpus, milestones


from dgca.core.anatomy import SynapseScope, SynapseState


def capture_telemetry(state: MachineState, ledger: SurfaceReadoutLedgerV1, root_id: int) -> dict[str, Any]:
    committed_cells = len(state.W.committed_cells)
    synapse_scopes = {
        "LOCAL": sum(1 for s in state.W.synapses.values() if s.scope == SynapseScope.LOCAL),
        "CROSS_TERRITORY": sum(1 for s in state.W.synapses.values() if s.scope == SynapseScope.CROSS_TERRITORY),
        "ASSOCIATIVE": sum(1 for s in state.W.synapses.values() if s.scope == SynapseScope.ASSOCIATIVE),
    }
    synapse_states = {
        "CANDIDATE": sum(1 for s in state.W.synapses.values() if s.state == SynapseState.CANDIDATE),
        "EPISODIC_INDEXED": sum(1 for s in state.W.synapses.values() if s.state == SynapseState.EPISODIC_INDEXED),
        "CONSOLIDATED": sum(1 for s in state.W.synapses.values() if s.state == SynapseState.CONSOLIDATED),
    }
    assemblies = {}
    for aid, asm in state.W.assemblies.items():
        assemblies[aid] = {
            "status": asm.status.name,
            "structural_generation": asm.structural_generation,
            "member_count": len(asm.member_cell_ids),
            "members": list(asm.member_cell_ids),
        }

    ledger_rows = {}
    for (aid, gen), candidate_map in ledger._rows_by_asm_gen.items():
        for t_key, row in candidate_map.items():
            surf, marker, digest = t_key
            ledger_rows[f"Asm_{aid}_gen_{gen}_{surf}_{marker.name}"] = {
                "assembly_id": aid,
                "generation": gen,
                "surface": surf,
                "marker": marker.name,
                "external_count": row.external_count,
                "confirmed_roots": sorted(list(row.confirmed_roots)),
                "is_attested": row.is_attested,
                "digest": row.feature_bundle_digest.hex()[:16],
            }

    return {
        "root_id": root_id,
        "committed_cells": committed_cells,
        "synapse_scopes": synapse_scopes,
        "synapse_states": synapse_states,
        "assemblies": assemblies,
        "ledger_rows": ledger_rows,
    }


def format_gen_result(res: GenerateEpisodeResult) -> dict[str, Any]:
    steps_data = []
    for s in res.steps:
        steps_data.append({
            "step_index": s.step_index,
            "status": s.readout_result.status.name,
            "winner_assembly_id": s.winner_assembly_id,
            "winner_generation": s.winner_generation,
            "top_score": round(s.readout_result.top_score, 6),
            "second_score": round(s.readout_result.second_score, 6),
            "margin": round(s.readout_result.margin, 6),
            "emitted_surface": s.emitted_envelope.raw_surface_nfc_utf8 if s.emitted_envelope else None,
            "emitted_marker": s.emitted_envelope.marker.name if s.emitted_envelope else None,
        })
    return {
        "stop_status": res.stop_status.name,
        "emitted_surfaces": list(res.emitted_surfaces),
        "steps": steps_data,
    }


def run_experiment():
    print("=== DGCA NEXT V2 - R2-C01 EXPERIMENT TRIAL ===")
    print("Corpus:")
    for k, v in CORPUS.items():
        print(f"  {k}: {v}")

    # Phase 1: Train 56 roots
    print("\n--- Training 56 roots (14 per sentence) ---")
    state_56, ledger_56, tx_56, encoded_corpus, milestones_56 = train_trial(56)
    telem_56 = capture_telemetry(state_56, ledger_56, 56)
    print(f"Root 56 Committed Cells: {telem_56['committed_cells']}")
    print(f"Root 56 Synapse Scopes: {telem_56['synapse_scopes']}")
    print(f"Root 56 Synapse States: {telem_56['synapse_states']}")
    print(f"Root 56 Assemblies: {len(telem_56['assemblies'])}")
    for aid, info in sorted(telem_56['assemblies'].items()):
        print(f"  Asm {aid}: status={info['status']} gen={info['structural_generation']} members={info['members']}")

    print("\nRoot 56 Ledger Rows & Attestations:")
    for k, v in sorted(telem_56['ledger_rows'].items()):
        print(f"  {k}: attested={v['is_attested']} count={v['external_count']} roots={v['confirmed_roots']}")

    # Primary Probes on 56 roots
    print("\n--- Running Primary Context Probes on 56-Root State ---")
    probes = {
        "P1": ("القط يشرب", [encoded_corpus["S1"][0].core_event, encoded_corpus["S1"][1].core_event], "الحليب"),
        "P2": ("النسر يشرب", [encoded_corpus["S2"][0].core_event, encoded_corpus["S2"][1].core_event], "الماء"),
        "P3": ("الطفل يأكل", [encoded_corpus["S3"][0].core_event, encoded_corpus["S3"][1].core_event], "التفاح"),
        "P4": ("الطفل يشرب", [encoded_corpus["S4"][0].core_event, encoded_corpus["S4"][1].core_event], "الماء"),
    }

    probe_results_56 = {}
    for p_id, (p_text, p_events, expected) in probes.items():
        res = generate_episode(state_56, p_events, ledger_56, max_steps=6)
        formatted = format_gen_result(res)
        probe_results_56[p_id] = formatted
        print(f"\nProbe {p_id} ('{p_text}') -> expected '{expected}' <EOS>:")
        print(f"  Stop Status: {formatted['stop_status']}")
        print(f"  Emitted Surfaces: {formatted['emitted_surfaces']}")
        for s in formatted["steps"]:
            print(f"    Step {s['step_index']}: winner_asm={s['winner_assembly_id']} gen={s['winner_generation']} score={s['top_score']} margin={s['margin']} surface={s['emitted_surface']} marker={s['emitted_marker']} status={s['status']}")

    # Single token ambiguity probes
    print("\n--- Running Context Ambiguity Probes ---")
    ambig_probes = {
        "A1_child": ("الطفل", [encoded_corpus["S3"][0].core_event]),
        "A2_drink": ("يشرب", [encoded_corpus["S1"][1].core_event]),
    }
    ambig_results_56 = {}
    for a_id, (a_text, a_events) in ambig_probes.items():
        res = generate_episode(state_56, a_events, ledger_56, max_steps=6)
        formatted = format_gen_result(res)
        ambig_results_56[a_id] = formatted
        print(f"\nAmbiguity Probe {a_id} ('{a_text}'):")
        print(f"  Stop Status: {formatted['stop_status']}")
        print(f"  Emitted Surfaces: {formatted['emitted_surfaces']}")
        for s in formatted["steps"]:
            print(f"    Step {s['step_index']}: winner_asm={s['winner_assembly_id']} gen={s['winner_generation']} score={s['top_score']} margin={s['margin']} surface={s['emitted_surface']} marker={s['emitted_marker']} status={s['status']}")

    # Unsupported Combination Diagnostics
    print("\n--- Running Unsupported Combination Diagnostics ---")
    # Build core events for "النسر يأكل" and "القط يأكل"
    eagle_eat_events = [encoded_corpus["S2"][0].core_event, encoded_corpus["S3"][1].core_event]
    cat_eat_events = [encoded_corpus["S1"][0].core_event, encoded_corpus["S3"][1].core_event]
    unsupported = {
        "U1_eagle_eat": ("النسر يأكل", eagle_eat_events),
        "U2_cat_eat": ("القط يأكل", cat_eat_events),
    }
    unsupported_results_56 = {}
    for u_id, (u_text, u_events) in unsupported.items():
        res = generate_episode(state_56, u_events, ledger_56, max_steps=6)
        formatted = format_gen_result(res)
        unsupported_results_56[u_id] = formatted
        print(f"\nUnsupported Diagnostic {u_id} ('{u_text}'):")
        print(f"  Stop Status: {formatted['stop_status']}")
        print(f"  Emitted Surfaces: {formatted['emitted_surfaces']}")
        for s in formatted["steps"]:
            print(f"    Step {s['step_index']}: winner_asm={s['winner_assembly_id']} gen={s['winner_generation']} score={s['top_score']} margin={s['margin']} surface={s['emitted_surface']} marker={s['emitted_marker']} status={s['status']}")

    # Check 112 roots trial
    print("\n--- Training 112 roots (28 per sentence) ---")
    state_112, ledger_112, tx_112, _, milestones_112 = train_trial(112)
    telem_112 = capture_telemetry(state_112, ledger_112, 112)
    print(f"Root 112 Committed Cells: {telem_112['committed_cells']}")
    print(f"Root 112 Synapse Scopes: {telem_112['synapse_scopes']}")
    print(f"Root 112 Synapse States: {telem_112['synapse_states']}")
    print(f"Root 112 Assemblies: {len(telem_112['assemblies'])}")
    for aid, info in sorted(telem_112['assemblies'].items()):
        print(f"  Asm {aid}: status={info['status']} gen={info['structural_generation']} members={info['members']}")

    probe_results_112 = {}
    for p_id, (p_text, p_events, expected) in probes.items():
        res = generate_episode(state_112, p_events, ledger_112, max_steps=6)
        formatted = format_gen_result(res)
        probe_results_112[p_id] = formatted
        print(f"\n[112-root] Probe {p_id} ('{p_text}') -> expected '{expected}' <EOS>:")
        print(f"  Stop Status: {formatted['stop_status']}")
        print(f"  Emitted Surfaces: {formatted['emitted_surfaces']}")
        for s in formatted["steps"]:
            print(f"    Step {s['step_index']}: winner_asm={s['winner_assembly_id']} gen={s['winner_generation']} score={s['top_score']} margin={s['margin']} surface={s['emitted_surface']} marker={s['emitted_marker']} status={s['status']}")

    # Deterministic replay check: Cold start Run 2 for 56 roots
    print("\n--- Verifying Deterministic Replay (Independent Run 2 Cold Start) ---")
    state_run2, ledger_run2, _, _, _ = train_trial(56)
    snap1 = snapshot_machine_state(state_56)
    snap2 = snapshot_machine_state(state_run2)
    h1 = hash_state_snapshot(snap1)
    h2 = hash_state_snapshot(snap2)
    print(f"Run 1 SHA-256: {h1}")
    print(f"Run 2 SHA-256: {h2}")
    print(f"Bitwise Deterministic Match: {h1 == h2}")

    # Immutability during GENERATE
    print("\n--- Verifying State Immutability During GENERATE ---")
    snap_pre = snapshot_machine_state(state_56)
    ledger_snap_pre = snapshot_ledger(ledger_56)
    h_pre = hash_state_snapshot(snap_pre)

    # Run generation across all probes
    for p_id, (_, p_events, _) in probes.items():
        generate_episode(state_56, p_events, ledger_56, max_steps=6)
    for a_id, (_, a_events) in ambig_probes.items():
        generate_episode(state_56, a_events, ledger_56, max_steps=6)
    for u_id, (_, u_events) in unsupported.items():
        generate_episode(state_56, u_events, ledger_56, max_steps=6)

    snap_post = snapshot_machine_state(state_56)
    ledger_snap_post = snapshot_ledger(ledger_56)
    h_post = hash_state_snapshot(snap_post)
    print(f"Pre-GENERATE SHA-256:  {h_pre}")
    print(f"Post-GENERATE SHA-256: {h_post}")
    print(f"State Immutability Verified: {h_pre == h_post}")
    print(f"Ledger Immutability Verified: {ledger_snap_pre == ledger_snap_post}")

    # Save summary data to json
    trial_data = {
        "corpus": CORPUS,
        "telem_56": telem_56,
        "telem_112": telem_112,
        "probes_56": probe_results_56,
        "probes_112": probe_results_112,
        "ambiguity_56": ambig_results_56,
        "unsupported_56": unsupported_results_56,
        "determinism": {
            "run1_sha256": h1,
            "run2_sha256": h2,
            "match": (h1 == h2),
        },
        "immutability": {
            "pre_sha256": h_pre,
            "post_sha256": h_post,
            "state_match": (h_pre == h_post),
            "ledger_match": (ledger_snap_pre == ledger_snap_post),
        },
    }
    with open("tools/forensics/r2_c01_trial_data.json", "w", encoding="utf-8") as f:
        json.dump(trial_data, f, indent=2, ensure_ascii=False)
    print("\nSaved trial data to tools/forensics/r2_c01_trial_data.json")


if __name__ == "__main__":
    run_experiment()
