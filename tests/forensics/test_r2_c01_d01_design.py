"""Test suite for DGCA NEXT V2 — R2-C01-D01 Design Preflight and Temporal Audit.

Verifies:
1. Authoritative normative parameter alignment (THETA_READ=0.08, M_READ=0.04, THETA_MERGE=0.70).
2. Exact temporal audit mechanics: delayed structural commit of pre-consolidated synapses at Root 15 and 17.
3. Zero modification to production code (src/ untouched).
"""

from __future__ import annotations

import dataclasses
import pytest

from dgca.core.anatomy import SynapseScope
from dgca.core.assembly import THETA_MERGE
from dgca.core.readout import M_READ, THETA_READ
from dgca.core.state import MachineState
from dgca.encoder.envelope import encode_exposure
from dgca.lifecycle.exposure_tx import ExposureTransactionManager
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1
from tools.forensics.run_r2_c01_cf01_experiment import CORPUS_GROUP_B, build_schedule


def test_d01_preflight_parameter_alignment():
    """Verify authoritative implementation parameters match normative baselines."""
    assert THETA_READ == 0.08, f"Expected THETA_READ == 0.08, got {THETA_READ}"
    assert M_READ == 0.04, f"Expected M_READ == 0.04, got {M_READ}"
    assert THETA_MERGE == 0.70, f"Expected THETA_MERGE == 0.70, got {THETA_MERGE}"


def test_d01_growth_timing_temporal_audit():
    """Verify that GROW events at Roots 15 and 17 represent legitimate delayed structural commits

    of synapses already consolidated by the end of Roots 14 and 16, respectively.
    """
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
    )

    encoded = {k: encode_exposure(v, append_eos=True) for k, v in CORPUS_GROUP_B.items()}
    schedule = build_schedule(17)

    for root_id, s_key in schedule:
        tx.begin_exposure(root_id)
        for env in encoded[s_key]:
            ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx.process_event(ev, peripheral_envelope=env.peripheral_surface)
        rep = tx.end_exposure(root_id)

        if root_id == 14:
            # Assembly 7 formed at Root 14 Stage 3 (FORM)
            assert 7 in rep.assembly_report.formed_ids
            # Synapses between 11984 and Assembly 7 founders are ALREADY consolidated at Root 14 close
            for m in [8242, 9854, 11638]:
                k = (11984, m, SynapseScope.LOCAL)
                s = state.W.synapses.get(k)
                assert s is not None and s.state.name == "CONSOLIDATED"

        elif root_id == 15:
            # Assembly 7 grew at Root 15 Stage 2 (GROW) from pre-consolidated synapses
            assert 7 in rep.assembly_report.grown_ids
            asm7 = state.W.assemblies[7]
            assert 11984 in asm7.member_cell_ids
            assert asm7.structural_generation == 2

        elif root_id == 16:
            # Assembly 9 formed at Root 16 Stage 3 (FORM)
            assert 9 in rep.assembly_report.formed_ids
            # Synapses between candidate cells and Assembly 9 founders are ALREADY consolidated at Root 16 close
            for c in [9734, 10044, 10308, 11193]:
                for f in [8809, 9740, 10634]:
                    k = (c, f, SynapseScope.LOCAL)
                    s = state.W.synapses.get(k)
                    assert s is not None and s.state.name == "CONSOLIDATED"

        elif root_id == 17:
            # Assembly 9 grew at Root 17 Stage 2 (GROW) from pre-consolidated synapses
            assert 9 in rep.assembly_report.grown_ids
            asm9 = state.W.assemblies[9]
            assert asm9.structural_generation == 5
            assert len(asm9.member_cell_ids) == 7
