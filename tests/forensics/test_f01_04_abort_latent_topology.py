"""Forensic Investigation F01-04: ABORT_LATENT_TOPOLOGY (R1-H05).

Investigates whether an ABORT_EXPOSURE leaves behind structural coactivity latent wiring modifications.
Normative contract: ABORT must roll back uncommitted root staging;
while committed sensory cells legally persist (Core §10.1), unauthorized learning effects and
latent coactivity modifications from the aborted exposure should not pollute the permanent topology.
"""

from __future__ import annotations

from dgca.core.state import MachineState
from dgca.encoder.envelope import encode_lexical_token_event
from dgca.lifecycle.exposure_tx import ExposureStatus, ExposureTransactionManager


def test_f01_04_latent_topology_mutations_survive_abort() -> None:
    """Verify whether latent topology admissions/recycling survive an ABORT_EXPOSURE transaction."""
    state = MachineState()
    tx = ExposureTransactionManager(state, auto_coactive_latent=True)

    # 1. Capture W's full latent topology and reverse index before
    before_latent_slots = {
        cid: tuple(sorted(state.W.latent_table.forward_neighbors(cid)))
        for cid in state.W.committed_cells
    }

    # 2. Begin external exposure 1
    root_id = 1
    tx.begin_exposure(root_id)

    # 3. Process events that cause sensory commitment and co-active latent admission
    ev_a = encode_lexical_token_event("القط", exposure_id=root_id, event_order=0, boundary=True)
    ev_b = encode_lexical_token_event("يشرب", exposure_id=root_id, event_order=1, boundary=False)
    tx.process_event(ev_a.core_event, peripheral_envelope=ev_a.peripheral_surface)
    tx.process_event(ev_b.core_event, peripheral_envelope=ev_b.peripheral_surface)

    # 4. Capture modified topology while OPEN
    open_committed = set(state.W.committed_cells)
    open_latent_slots = {
        cid: tuple(sorted(state.W.latent_table.forward_neighbors(cid)))
        for cid in open_committed
    }
    assert len(open_latent_slots) > 0

    # 5. ABORT the exposure
    tx.abort_exposure(root_id)
    assert tx.status == ExposureStatus.CLOSED

    # 6. Capture resulting topology after ABORT
    after_committed = set(state.W.committed_cells)
    after_latent_slots = {
        cid: tuple(sorted(state.W.latent_table.forward_neighbors(cid)))
        for cid in after_committed
    }

    # Sensory commitments legally persist (Core §10.1)
    assert after_committed == open_committed

    # Forensic check (R1-H05):
    # Did the co-active latent slots allocated during the aborted exposure survive?
    # In exposure_tx.py:378-386: abort_exposure ONLY restores H_slow and resets R;
    # it does NOT roll back W.latent_table!
    slots_survived_abort = (after_latent_slots == open_latent_slots)
    print(f"\n[F01-04] Coactive latent slots survived ABORT: {slots_survived_abort}")
    print(f"  Total cells with persistent latent co-activity: {len(after_latent_slots)}")
    
    # Assert defect confirmation: latent topology was not rolled back upon ABORT
    assert slots_survived_abort is True, (
        "Expected latent topology changes to have survived ABORT in current implementation"
    )
