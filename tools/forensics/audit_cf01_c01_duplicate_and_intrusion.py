"""Audit script for R2-C01-CF01-C01:
- Task 3: Duplicate assembly analysis (7 vs 9 for 'ماء', 14 vs 17 for 'تفاح').
- Task 4: Causal intrusion attribution (post-object evaluation of 'يأكل').
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from dgca.core.anatomy import SynapseScope
from dgca.core.assembly import (
    AssemblyStatus,
    K_MAX,
    THETA_A,
    THETA_MERGE,
    _is_in_merge_split_cooldown,
    check_maintain_keep_guards,
    compute_mutual_support_r_b,
)
from dgca.core.generator import generate_episode
from dgca.core.readout import M_READ, THETA_READ
from tools.forensics.run_r2_c01_cf01_experiment import train_and_instrument, CORPUS_GROUP_A, CORPUS_GROUP_B


def inspect_pair(aid_a: int, aid_b: int, w, ledger):
    asm_a = w.assemblies[aid_a]
    asm_b = w.assemblies[aid_b]

    set_a = set(asm_a.member_cell_ids)
    set_b = set(asm_b.member_cell_ids)
    inter = set_a & set_b
    union = set_a | set_b
    jaccard = float(len(inter)) / float(len(union)) if union else 0.0

    cooldown_a = _is_in_merge_split_cooldown(asm_a, w)
    cooldown_b = _is_in_merge_split_cooldown(asm_b, w)

    # Check mutual support gate for exclusive members
    excl_a = sorted(set_a - set_b)
    excl_b = sorted(set_b - set_a)
    mutual_ok = True
    mutual_details = []
    for x in excl_a:
        for y in excl_b:
            r_xy = compute_mutual_support_r_b(x, y, w)
            mutual_details.append((x, y, round(r_xy, 4)))
            if r_xy < THETA_A:
                mutual_ok = False

    # Keep guards check on union
    keep_guards_ok = True
    n_rec_cache = {}
    for m in union:
        kg = check_maintain_keep_guards(m, union, w, n_rec_cache)
        if not kg:
            keep_guards_ok = False

    row_a = ledger.resolve_readout(aid_a, asm_a.structural_generation)
    row_b = ledger.resolve_readout(aid_b, asm_b.structural_generation)
    surf_a = row_a.envelope.raw_surface_nfc_utf8 if (row_a and row_a.envelope) else "UNATTESTED"
    surf_b = row_b.envelope.raw_surface_nfc_utf8 if (row_b and row_b.envelope) else "UNATTESTED"

    return {
        "assembly_a": aid_a,
        "generation_a": asm_a.structural_generation,
        "surface_a": surf_a,
        "members_a": sorted(list(set_a)),
        "assembly_b": aid_b,
        "generation_b": asm_b.structural_generation,
        "surface_b": surf_b,
        "members_b": sorted(list(set_b)),
        "intersection": sorted(list(inter)),
        "union": sorted(list(union)),
        "jaccard_similarity": round(jaccard, 4),
        "theta_merge": THETA_MERGE,
        "jaccard_passes_theta_merge": jaccard >= THETA_MERGE,
        "union_len": len(union),
        "k_max": K_MAX,
        "union_passes_k_max": len(union) <= K_MAX,
        "cooldown_a": cooldown_a,
        "cooldown_b": cooldown_b,
        "mutual_support_ok": mutual_ok,
        "keep_guards_ok": keep_guards_ok,
        "is_true_structural_duplicate": (not excl_a and not excl_b),
        "is_merge_eligible": (
            not cooldown_a and not cooldown_b
            and len(union) <= K_MAX
            and jaccard >= THETA_MERGE
            and mutual_ok
            and keep_guards_ok
        ),
    }


def main():
    print("=== Training Group B for 56 and 112 roots... ===")
    cp_b, _, enc_b = train_and_instrument(CORPUS_GROUP_B, 112)
    state_56 = cp_b[56]["state"]
    ledger_56 = cp_b[56]["ledger"]
    state_112 = cp_b[112]["state"]
    ledger_112 = cp_b[112]["ledger"]

    print("\n--- Root 56: Assemblies 7 vs 9 ('ماء') ---")
    res_water_56 = inspect_pair(7, 9, state_56.W, ledger_56)
    for k, v in res_water_56.items():
        print(f"  {k}: {v}")

    print("\n--- Root 56: Assemblies 14 vs 17 ('تفاح') ---")
    res_apple_56 = inspect_pair(14, 17, state_56.W, ledger_56)
    for k, v in res_apple_56.items():
        print(f"  {k}: {v}")

    print("\n--- Root 112: Assemblies 7 vs 9 ('ماء') ---")
    res_water_112 = inspect_pair(7, 9, state_112.W, ledger_112)
    for k, v in res_water_112.items():
        print(f"  {k}: {v}")

    print("\n--- Root 112: Assemblies 14 vs 17 ('تفاح') ---")
    res_apple_112 = inspect_pair(14, 17, state_112.W, ledger_112)
    for k, v in res_apple_112.items():
        print(f"  {k}: {v}")

    print("\n=== Task 4: Causal Intrusion Attribution at Root 112 ===")
    # Probe with object fed: [النسر, يشرب, ماء]
    p_events = [enc_b["S2"][0].core_event, enc_b["S2"][1].core_event, enc_b["S2"][2].core_event]
    gen_with_water = generate_episode(state_112, p_events, ledger_112, max_steps=3)
    print("Generation stop status:", gen_with_water.stop_status.name)
    print("Emitted surfaces:", gen_with_water.emitted_surfaces)
    s0 = gen_with_water.steps[0]
    print("Post-water step 0 winner:", s0.winner_assembly_id, "top_score:", s0.readout_result.top_score)
    for c in s0.readout_result.ranked_scores[:8]:
        res_r = ledger_112.resolve_readout(c.assembly_id, c.structural_generation)
        surf = res_r.envelope.raw_surface_nfc_utf8 if (res_r and res_r.envelope) else "UNATTESTED"
        print(f"  candidate aid={c.assembly_id} gen={c.structural_generation} score={c.score_next:.6f} surf={surf}")


if __name__ == "__main__":
    main()
