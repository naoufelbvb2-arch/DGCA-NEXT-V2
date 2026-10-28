"""Forensic Investigation F01-03: EVENT_RETRY_COLLISION (R1-H04).

Investigates event idempotency contract within an OPEN exposure.
Normative contract: An identical retry may be idempotent, but a conflicting retry
(different features or conflicting envelope) must NOT be silently accepted as the original event.
"""

from __future__ import annotations

import pytest
from dgca.common.errors import ObservationError
from dgca.core.state import MachineState
from dgca.encoder.envelope import encode_lexical_token_event
from dgca.lifecycle.exposure_tx import ExposureTransactionManager


def test_f01_03_identical_retry_vs_conflicting_retry_collision() -> None:
    """Verify whether a conflicting feature bundle at the same event_order is silently accepted."""
    state = MachineState()
    tx = ExposureTransactionManager(state)
    root_id = 1
    tx.begin_exposure(root_id)

    # 1. Submit valid event at order 0: "القط"
    ev1 = encode_lexical_token_event("القط", exposure_id=root_id, event_order=0, boundary=True)
    res1 = tx.process_event(ev1.core_event, peripheral_envelope=ev1.peripheral_surface)
    assert res1.event_order == 0

    # 2. Retry identical event at order 0
    res_identical = tx.process_event(ev1.core_event, peripheral_envelope=ev1.peripheral_surface)
    assert res_identical is res1, "Identical retry should return checkpointed result"

    # 3. Retry a DIFFERENT canonical feature bundle at order 0: "النسر" (different features!)
    ev_conflicting = encode_lexical_token_event("النسر", exposure_id=root_id, event_order=0, boundary=True)
    assert ev_conflicting.core_event.features != ev1.core_event.features

    # Forensic test (R1-H04):
    # Does the implementation detect the conflict, or silently return the original event's result?
    res_conflicting = tx.process_event(ev_conflicting.core_event, peripheral_envelope=ev_conflicting.peripheral_surface)

    # In current implementation (exposure_tx.py:282-283):
    # if core_event.event_order < journal.next_event_order: return journal.event_results[core_event.event_order]
    # It SILENTLY accepts the conflicting event and returns the old result!
    silently_accepted = (res_conflicting is res1)
    print(f"\n[F01-03] Conflicting feature bundle silently accepted: {silently_accepted}")
    assert silently_accepted is True, "DEFECT NOT OBSERVED: conflicting retry was unexpectedly rejected"


def test_f01_03_conflicting_peripheral_envelope_retry() -> None:
    """Verify whether a conflicting peripheral envelope for the same event is silently ignored."""
    state = MachineState()
    tx = ExposureTransactionManager(state)
    root_id = 1
    tx.begin_exposure(root_id)

    # 1. Process event at order 0 with envelope for "القط"
    ev1 = encode_lexical_token_event("القط", exposure_id=root_id, event_order=0, boundary=True)
    tx.process_event(ev1.core_event, peripheral_envelope=ev1.peripheral_surface)

    stored_env_before = tx.open_journal.peripheral_envelopes_by_order[0]
    assert stored_env_before.raw_surface_nfc_utf8 == "القط"

    # 2. Retry at order 0 with conflicting envelope for "كلب"
    ev_dog = encode_lexical_token_event("كلب", exposure_id=root_id, event_order=0, boundary=True)
    tx.process_event(ev1.core_event, peripheral_envelope=ev_dog.peripheral_surface)

    stored_env_after = tx.open_journal.peripheral_envelopes_by_order[0]
    # The conflicting envelope was silently ignored; original remains stored
    assert stored_env_after.raw_surface_nfc_utf8 == "القط"
