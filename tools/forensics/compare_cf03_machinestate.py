"""DGCA NEXT V2 — Task F: Recursive MachineState Diff between CF03 Group A and Group B.

Compares:
- Group A: canonical baseline (enable_birth_time_grow=False)
- Group B: birth-time grow enabled (enable_birth_time_grow=True)

At checkpoints:
- Root 56
- Root 112

Partitions inspected:
- W: assemblies, synapses, latent_table, context_candidates, stable_bindings, owner_profiles, clocks.
- H_slow: homeostatic variables (r_bar, g, rho_bar, theta_active).
- R / Peripheral: SurfaceReadoutLedgerV1 (candidate rows, confirmed roots, surfaces).
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

from dgca.core.anatomy import SynapseState
from dgca.core.state import MachineState
from dgca.encoder.envelope import encode_exposure
from dgca.lifecycle.exposure_tx import ExposureTransactionManager
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1
from tests.test_r2_a01_patch2_acceptance import (
    hash_state_snapshot,
    snapshot_w,
    snapshot_h_slow,
    snapshot_r,
)

CORPUS = {
    "S1": "القط يشرب حليب",
    "S2": "النسر يشرب ماء",
    "S3": "الطفل يأكل تفاح",
    "S4": "الطفل يشرب ماء",
}

def build_schedule(total_roots: int) -> list[tuple[int, str]]:
    schedule = []
    order = ["S1", "S2", "S3", "S4"]
    for root_id in range(1, total_roots + 1):
        s_key = order[(root_id - 1) % 4]
        schedule.append((root_id, s_key))
    return schedule

def run_group(enable_birth_time_grow: bool, total_roots: int = 112):
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
        enable_birth_time_grow=enable_birth_time_grow,
    )
    encoded = {k: encode_exposure(v, append_eos=True) for k, v in CORPUS.items()}
    schedule = build_schedule(total_roots)

    checkpoints = {}
    for root_id, s_key in schedule:
        tx.begin_exposure(root_id)
        for env in encoded[s_key]:
            core_ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        tx.end_exposure(root_id)

        if root_id in (56, 112):
            snap_w = snapshot_w(state.W)
            snap_h = snapshot_h_slow(state.H_slow)
            snap_r = snapshot_r(state.R)
            checkpoints[root_id] = {
                "state": state.clone(),
                "ledger": ledger.clone(),
                "snap_w": snap_w,
                "snap_h": snap_h,
                "snap_r": snap_r,
                "hash": hash_state_snapshot({
                    "W": snap_w,
                    "H_slow": snap_h,
                    "R": snap_r,
                }),
            }
    return checkpoints

def recursive_diff(d1: Any, d2: Any, path: str = "") -> list[tuple[str, Any, Any]]:
    diffs = []
    if type(d1) != type(d2):
        diffs.append((path, f"type {type(d1).__name__}", f"type {type(d2).__name__}"))
        return diffs

    if isinstance(d1, dict):
        keys1 = set(d1.keys())
        keys2 = set(d2.keys())
        for k in keys1 - keys2:
            diffs.append((f"{path}.{k}", d1[k], "<MISSING_IN_B>"))
        for k in keys2 - keys1:
            diffs.append((f"{path}.{k}", "<MISSING_IN_A>", d2[k]))
        for k in sorted(keys1 & keys2):
            diffs.extend(recursive_diff(d1[k], d2[k], f"{path}.{k}" if path else str(k)))
    elif isinstance(d1, (list, tuple)):
        if len(d1) != len(d2):
            diffs.append((f"{path}.len", len(d1), len(d2)))
        for idx in range(min(len(d1), len(d2))):
            diffs.extend(recursive_diff(d1[idx], d2[idx], f"{path}[{idx}]"))
    elif isinstance(d1, (set, frozenset)):
        if d1 != d2:
            diffs.append((f"{path}.set_diff", sorted(list(d1 - d2)), sorted(list(d2 - d1))))
    else:
        if d1 != d2:
            diffs.append((path, d1, d2))
    return diffs

def analyze_checkpoints(cp_a: dict, cp_b: dict, root_id: int):
    print(f"\n========================================================")
    print(f"COMPARING GROUP A vs GROUP B AT ROOT {root_id}")
    print(f"========================================================")
    hash_a = cp_a[root_id]["hash"]
    hash_b = cp_b[root_id]["hash"]
    print(f"Group A State SHA256: {hash_a}")
    print(f"Group B State SHA256: {hash_b}")
    print(f"Identical States? {hash_a == hash_b}")

    # Detailed Partition Analysis
    w_a = cp_a[root_id]["snap_w"]
    w_b = cp_b[root_id]["snap_w"]

    diffs_w = recursive_diff(w_a, w_b, "W")
    print(f"\n--- WState Differences (Total field diffs: {len(diffs_w)}) ---")
    
    # Categorize W diffs
    asms_diff = [d for d in diffs_w if d[0].startswith("W.assemblies")]
    syn_diff = [d for d in diffs_w if d[0].startswith("W.synapses")]
    latent_diff = [d for d in diffs_w if d[0].startswith("W.latent_table")]
    clock_diff = [d for d in diffs_w if any(k in d[0] for k in ["clock", "close_serial", "count", "high_watermark"])]
    ctx_diff = [d for d in diffs_w if "context_candidate" in d[0] or "stable_binding" in d[0] or "owner_profile" in d[0]]
    other_w = [d for d in diffs_w if d not in asms_diff + syn_diff + latent_diff + clock_diff + ctx_diff]

    print(f"  Assembly diffs: {len(asms_diff)}")
    for d in asms_diff[:20]:
        print(f"    {d[0]}: A={d[1]} | B={d[2]}")
    if len(asms_diff) > 20:
        print(f"    ... and {len(asms_diff) - 20} more assembly diffs")

    print(f"  Synapse diffs: {len(syn_diff)}")
    print(f"    Total synapses: A={len(w_a['synapses'])}, B={len(w_b['synapses'])}")
    syn_keys_a = set(w_a['synapses'].keys())
    syn_keys_b = set(w_b['synapses'].keys())
    print(f"    Synapse keys only in A: {len(syn_keys_a - syn_keys_b)}")
    print(f"    Synapse keys only in B: {len(syn_keys_b - syn_keys_a)}")
    syn_weight_diffs = [d for d in syn_diff if d[0].endswith(".S") or d[0].endswith(".E_ext")]
    print(f"    Synapse weight/evidence diffs on shared keys: {len(syn_weight_diffs)}")
    syn_state_diffs = [d for d in syn_diff if d[0].endswith(".state")]
    print(f"    Synapse state diffs: {len(syn_state_diffs)}")
    for d in syn_state_diffs[:10]:
        print(f"      {d[0]}: A={d[1]} | B={d[2]}")

    print(f"  Latent table diffs: {len(latent_diff)}")
    for d in latent_diff[:10]:
        print(f"    {d[0]}: A={d[1]} | B={d[2]}")

    print(f"  Context candidate / Binding diffs: {len(ctx_diff)}")
    for d in ctx_diff[:10]:
        print(f"    {d[0]}: A={d[1]} | B={d[2]}")

    print(f"  Clocks and counters diffs: {len(clock_diff)}")
    for d in clock_diff:
        print(f"    {d[0]}: A={d[1]} | B={d[2]}")

    print(f"  Other W diffs: {len(other_w)}")
    for d in other_w[:10]:
        print(f"    {d[0]}: A={d[1]} | B={d[2]}")

    # HSlow analysis
    h_a = cp_a[root_id]["snap_h"]
    h_b = cp_b[root_id]["snap_h"]
    diffs_h = recursive_diff(h_a, h_b, "H_slow")
    print(f"\n--- HSlowState Differences (Total: {len(diffs_h)}) ---")
    for d in diffs_h[:10]:
        print(f"    {d[0]}: A={d[1]} | B={d[2]}")

    # RState analysis
    r_a = cp_a[root_id]["snap_r"]
    r_b = cp_b[root_id]["snap_r"]
    diffs_r = recursive_diff(r_a, r_b, "R")
    print(f"\n--- RState Differences (Total: {len(diffs_r)}) ---")
    for d in diffs_r[:10]:
        print(f"    {d[0]}: A={d[1]} | B={d[2]}")

    # Ledger analysis
    led_a: SurfaceReadoutLedgerV1 = cp_a[root_id]["ledger"]
    led_b: SurfaceReadoutLedgerV1 = cp_b[root_id]["ledger"]
    print(f"\n--- SurfaceReadoutLedgerV1 Differences ---")
    keys_a = set(led_a._rows_by_asm_gen.keys())
    keys_b = set(led_b._rows_by_asm_gen.keys())
    print(f"  Ledger (AssemblyID, Gen) keys: A={len(keys_a)}, B={len(keys_b)}")
    print(f"  Keys only in A: {keys_a - keys_b}")
    print(f"  Keys only in B: {keys_b - keys_a}")
    diff_rows = []
    for k in sorted(keys_a & keys_b):
        rows_map_a = led_a._rows_by_asm_gen[k]
        rows_map_b = led_b._rows_by_asm_gen[k]
        if set(rows_map_a.keys()) != set(rows_map_b.keys()):
            diff_rows.append((k, "key_mismatch", set(rows_map_a.keys()), set(rows_map_b.keys())))
        else:
            for t_k in rows_map_a:
                row_a = rows_map_a[t_k]
                row_b = rows_map_b[t_k]
                if row_a.confirmed_roots != row_b.confirmed_roots or row_a.surface_utf8_nfc != row_b.surface_utf8_nfc:
                    diff_rows.append((k, t_k, row_a.confirmed_roots, row_b.confirmed_roots))
    print(f"  Row differences on shared keys: {len(diff_rows)}")
    for d in diff_rows:
        print(f"    {d}")

    # Specific assembly comparisons
    print(f"\n--- Key Assemblies Breakdown at Root {root_id} ---")
    st_a = cp_a[root_id]["state"]
    st_b = cp_b[root_id]["state"]
    for aid in sorted(set(st_a.W.assemblies.keys()) | set(st_b.W.assemblies.keys())):
        asm_a = st_a.W.assemblies.get(aid)
        asm_b = st_b.W.assemblies.get(aid)
        mem_a = sorted(list(asm_a.member_cell_ids)) if asm_a else "ABSENT"
        mem_b = sorted(list(asm_b.member_cell_ids)) if asm_b else "ABSENT"
        gen_a = asm_a.structural_generation if asm_a else "N/A"
        gen_b = asm_b.structural_generation if asm_b else "N/A"
        res_a = led_a.resolve_readout(aid, gen_a if isinstance(gen_a, int) else 1)
        res_b = led_b.resolve_readout(aid, gen_b if isinstance(gen_b, int) else 1)
        surf_a = res_a.envelope.surface_utf8_nfc if (res_a and res_a.envelope) else "NONE"
        surf_b = res_b.envelope.surface_utf8_nfc if (res_b and res_b.envelope) else "NONE"
        if mem_a != mem_b or gen_a != gen_b or surf_a != surf_b:
            print(f"  Asm {aid:2d}: DIFF")
            print(f"    Group A: gen={gen_a}, size={len(mem_a) if isinstance(mem_a, list) else 0}, members={mem_a}, surf={surf_a}")
            print(f"    Group B: gen={gen_b}, size={len(mem_b) if isinstance(mem_b, list) else 0}, members={mem_b}, surf={surf_b}")
        else:
            print(f"  Asm {aid:2d}: IDENTICAL (gen={gen_a}, size={len(mem_a)}, surf={surf_a})")

def main():
    print("Running Group A...")
    cp_a = run_group(enable_birth_time_grow=False, total_roots=112)
    print("Running Group B...")
    cp_b = run_group(enable_birth_time_grow=True, total_roots=112)

    analyze_checkpoints(cp_a, cp_b, 56)
    analyze_checkpoints(cp_a, cp_b, 112)

if __name__ == "__main__":
    main()
