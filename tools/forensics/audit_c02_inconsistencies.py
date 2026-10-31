"""Inspection script for R2-C01-CF01-C02:
Tasks A, B, and C deep audit.
"""

from __future__ import annotations
import sys
import os

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))
sys.stdout.reconfigure(encoding="utf-8")
# Keep standard stderr

from dgca.core.generator import generate_episode
from tests.test_r2_a01_patch2_acceptance import snapshot_ledger, hash_state_snapshot
from tools.forensics.run_r2_c01_cf01_experiment import (
    train_and_instrument,
    CORPUS_GROUP_A,
    CORPUS_GROUP_B,
    evaluate_probes,
)
from tools.forensics.run_r2_c01_trial import train_trial as train_r2_c01_trial

print("=== Task A: Reinspect Assembly 14 & 17, 7 & 9 in Group B ===")
cp_b, _, enc_b = train_and_instrument(CORPUS_GROUP_B, 112)

for root in [56, 112]:
    st = cp_b[root]["state"]
    led = cp_b[root]["ledger"]
    
    print(f"\n--- Group B Root {root} ---")
    for aid_a, aid_b, name in [(7, 9, "ماء"), (14, 17, "تفاح")]:
        asm_a = st.W.assemblies[aid_a]
        asm_b = st.W.assemblies[aid_b]
        
        mem_a = sorted(list(asm_a.member_cell_ids))
        mem_b = sorted(list(asm_b.member_cell_ids))
        
        inter = sorted(list(set(mem_a) & set(mem_b)))
        union = sorted(list(set(mem_a) | set(mem_b)))
        jaccard = float(len(inter)) / float(len(union)) if union else 0.0
        
        row_a = led.resolve_readout(aid_a, asm_a.structural_generation)
        row_b = led.resolve_readout(aid_b, asm_b.structural_generation)
        surf_a = row_a.envelope.surface_utf8_nfc if (row_a and row_a.envelope) else "UNATTESTED"
        surf_b = row_b.envelope.surface_utf8_nfc if (row_b and row_b.envelope) else "UNATTESTED"
        
        print(f"Pair: {name} (Aid {aid_a} vs {aid_b}):")
        print(f"  Assembly {aid_a}: gen={asm_a.structural_generation}, count={len(mem_a)}, members={mem_a}, surf={surf_a}")
        print(f"  Assembly {aid_b}: gen={asm_b.structural_generation}, count={len(mem_b)}, members={mem_b}, surf={surf_b}")
        print(f"  Intersection: count={len(inter)}, members={inter}")
        print(f"  Union: count={len(union)}, members={union}")
        print(f"  Jaccard similarity: {jaccard:.6f}")

print("\n=== Task C: Ledger Count Investigation ===")
print("--- 1. Ledger from run_r2_c01_trial (original R2-C01 script) ---")
state_c01_56, ledger_c01_56, tx_c01_56, enc_c01_56, ms_c01_56 = train_r2_c01_trial(56)
telem_c01_56 = ms_c01_56[56]
rows_c01_56 = telem_c01_56["ledger_rows"]
att_c01_56 = [r for r in rows_c01_56.values() if r["is_attested"]]
print(f"R2-C01 Root 56: total rows in milestone 56={len(rows_c01_56)}, attested={len(att_c01_56)}")

state_c01_112, ledger_c01_112, _, _, ms_c01_112 = train_r2_c01_trial(112)
telem_c01_112 = ms_c01_112[112]
rows_c01_112 = telem_c01_112["ledger_rows"]
att_c01_112 = [r for r in rows_c01_112.values() if r["is_attested"]]
print(f"R2-C01 Root 112: total rows in milestone 112={len(rows_c01_112)}, attested={len(att_c01_112)}")

print("\n--- 2. Milestones table across all roots in R2-C01 ---")
for r_id in sorted(ms_c01_112.keys()):
    t = ms_c01_112[r_id]
    total_r = len(t["ledger_rows"])
    att_r = sum(1 for r in t["ledger_rows"].values() if r["is_attested"])
    print(f"  Milestone Root {r_id}: total={total_r}, attested={att_r}")

from tools.forensics.run_r2_c01_trial import capture_telemetry
cp_a, _, enc_a = train_and_instrument(CORPUS_GROUP_A, 112)
telem_cf_a_56 = capture_telemetry(cp_a[56]["state"], cp_a[56]["ledger"], 56)
rows_cf_a_56 = telem_cf_a_56["ledger_rows"]
att_cf_a_56 = [r for r in rows_cf_a_56.values() if r["is_attested"]]
print(f"CF-1 Group A Root 56: total rows={len(rows_cf_a_56)}, attested={len(att_cf_a_56)}")

telem_cf_a_112 = capture_telemetry(cp_a[112]["state"], cp_a[112]["ledger"], 112)
rows_cf_a_112 = telem_cf_a_112["ledger_rows"]
att_cf_a_112 = [r for r in rows_cf_a_112.values() if r["is_attested"]]
print(f"CF-1 Group A Root 112: total rows={len(rows_cf_a_112)}, attested={len(att_cf_a_112)}")

print("\n--- 3. Detailed row keys comparison at Root 56 ---")
keys_c01 = set(rows_c01_56.keys())
keys_cf1 = set(rows_cf_a_56.keys())
print(f"Count in R2-C01: {len(keys_c01)}")
print(f"Count in CF-1 Group A: {len(keys_cf1)}")
diff_extra = keys_cf1 - keys_c01
diff_missing = keys_c01 - keys_cf1
print(f"Keys in CF-1 not in R2-C01: {diff_extra}")
print(f"Keys in R2-C01 not in CF-1: {diff_missing}")

print("\n=== Task B: Experimental Probes in Group A and Group B ===")
for grp_name, cp, enc in [("Group A", cp_a, enc_a), ("Group B", cp_b, enc_b)]:
    for root in [56, 112]:
        st = cp[root]["state"]
        led = cp[root]["ledger"]
        print(f"\n--- {grp_name} Root {root} ---")
        probes = {
            "P1 (القط يشرب)": [enc["S1"][0].core_event, enc["S1"][1].core_event],
            "P2 (النسر يشرب)": [enc["S2"][0].core_event, enc["S2"][1].core_event],
            "P3 (الطفل يأكل)": [enc["S3"][0].core_event, enc["S3"][1].core_event],
            "P4 (الطفل يشرب)": [enc["S4"][0].core_event, enc["S4"][1].core_event],
        }
        for p_id, p_ev in probes.items():
            res = generate_episode(st, p_ev, led, max_steps=6)
            winner = res.steps[0].winner_assembly_id if res.steps else None
            score = res.steps[0].readout_result.top_score if res.steps else None
            status = res.stop_status.name
            emitted = list(res.emitted_surfaces)
            print(f"  {p_id}: status={status}, emitted={emitted}, winner={winner}, score={score}, steps={len(res.steps)}")
            for idx, s in enumerate(res.steps):
                print(f"    step {idx}: winner={s.winner_assembly_id} gen={s.winner_generation} score={s.readout_result.top_score:.4f} margin={s.readout_result.margin:.4f} status={s.readout_result.status.name} surf={s.emitted_envelope.surface_utf8_nfc if s.emitted_envelope else None}")
