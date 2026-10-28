"""Forensic Investigation F01-04: ABORT_LATENT_TOPOLOGY (R1-H05 Re-verification).

TASK 1 — Rigorous re-verification of latent topology mutation survival across ABORT:
1. Establishes committed cells through legitimate completed external exposures (Roots 1 and 2).
2. Captures exact baseline latent topology (slots_by_cell) and reverse index.
3. Opens a new independent exposure (Root 3).
4. Demonstrates actual coactive-slot admission and recycling.
5. Captures exact changed slots (cell IDs, slot indices, before/after partners).
6. Explicitly asserts LATENT_MUTATION_OCCURRED == True before testing rollback.
7. Aborts the root.
8. Verifies whether mutations survived.
9. Separates legally persistent sensory admissions from unauthorized structural mutations.
"""

from __future__ import annotations

from dgca.core.state import MachineState
from dgca.encoder.envelope import encode_exposure
from dgca.lifecycle.exposure_tx import ExposureStatus, ExposureTransactionManager


def test_f01_04_reverify_latent_mutation_survival_after_abort() -> None:
    """Rigorous verification of R1-H05: Co-active latent mutations surviving ABORT_EXPOSURE."""
    state = MachineState()
    tx = ExposureTransactionManager(state, auto_coactive_latent=True)

    # Step 1: Establish committed cells through legitimate completed external exposures
    for root_id, text in [(1, "القط يشرب حليب"), (2, "النسر يشرب ماء")]:
        tx.begin_exposure(root_id)
        envs = encode_exposure(text, append_eos=False)
        for env in envs:
            tx.process_event(env.core_event, peripheral_envelope=env.peripheral_surface)
        tx.end_exposure(root_id)

    committed_baseline = set(state.W.committed_cells)
    assert len(committed_baseline) > 0, "Failed to establish baseline committed cells"

    # Step 2: Capture exact baseline latent topology and reverse index for all baseline cells
    baseline_slots = {
        cid: list(state.W.latent_table.get_slots(cid))
        for cid in committed_baseline
    }
    baseline_rev = {
        cid: set(state.W.latent_table.reverse_neighbors(cid))
        for cid in committed_baseline
    }

    # Step 3: Open an independent exposure (Root 3) with a novel cross-context combination
    root_id = 3
    tx.begin_exposure(root_id)
    envs3 = encode_exposure("القط يشرب ماء", append_eos=False)
    for env in envs3:
        tx.process_event(env.core_event, peripheral_envelope=env.peripheral_surface)

    # Step 4 & 5: Capture exact changed slots in pre-existing committed baseline cells
    mutated_slots: list[dict[str, object]] = []
    for cid in committed_baseline:
        curr_s = state.W.latent_table.get_slots(cid)
        base_s = baseline_slots[cid]
        for idx in range(24):
            if curr_s[idx] != base_s[idx]:
                mutated_slots.append({
                    "owner_cell_id": cid,
                    "slot_index": idx,
                    "before_partner": base_s[idx],
                    "after_partner": curr_s[idx],
                })

    mutated_reverse_index: dict[int, dict[str, set[int]]] = {}
    for cid in committed_baseline:
        curr_r = set(state.W.latent_table.reverse_neighbors(cid))
        base_r = baseline_rev[cid]
        if curr_r != base_r:
            mutated_reverse_index[cid] = {
                "before": base_r,
                "after": curr_r,
                "added": curr_r - base_r,
                "removed": base_r - curr_r,
            }

    print(f"\n[Task 1 — Reverify R1-H05]")
    print(f"  Baseline committed cells: {len(committed_baseline)}")
    print(f"  Mutated slots in OPEN Root 3: {len(mutated_slots)}")
    print(f"  Cells with reverse-index changes: {len(mutated_reverse_index)}")

    # Step 6: Explicitly require assertion that genuine latent mutations occurred
    LATENT_MUTATION_OCCURRED = (len(mutated_slots) > 0)
    assert LATENT_MUTATION_OCCURRED is True, (
        "TASK 1 REQUIREMENT FAILED: No co-active latent slot mutations could be induced"
    )

    # Sample reported mutation details
    sample = mutated_slots[0]
    print(f"  Sample slot mutation: Cell {sample['owner_cell_id']} slot {sample['slot_index']} "
          f"changed from {sample['before_partner']} to {sample['after_partner']}")

    # Step 7: ABORT the root transaction
    tx.abort_exposure(root_id)
    assert tx.status == ExposureStatus.CLOSED
    assert root_id in tx.aborted_roots

    # Step 8: Check whether the changes survived on the committed baseline cells
    survived_mutations: list[dict[str, object]] = []
    for cid in committed_baseline:
        after_s = state.W.latent_table.get_slots(cid)
        base_s = baseline_slots[cid]
        for idx in range(24):
            if after_s[idx] != base_s[idx]:
                survived_mutations.append({
                    "owner_cell_id": cid,
                    "slot_index": idx,
                    "baseline_partner": base_s[idx],
                    "survived_partner": after_s[idx],
                })

    survived_reverse_changes = 0
    for cid in committed_baseline:
        after_r = set(state.W.latent_table.reverse_neighbors(cid))
        base_r = baseline_rev[cid]
        if after_r != base_r:
            survived_reverse_changes += 1

    print(f"  Mutations survived after ABORT: {len(survived_mutations)}/{len(mutated_slots)}")
    print(f"  Reverse index changes survived: {survived_reverse_changes}/{len(mutated_reverse_index)}")

    # Step 9: Separate legally retained sensory admissions from unauthorized structural mutations
    # Here, ALL mutated slots tested belong to committed_baseline cells (cells committed prior to Root 3).
    # Thus, these surviving modifications represent 100% unauthorized structural mutations.
    assert len(survived_mutations) == len(mutated_slots), (
        "DEFECT NOT OBSERVED: Expected all induced latent slot mutations to have survived ABORT"
    )
    assert survived_reverse_changes == len(mutated_reverse_index)
