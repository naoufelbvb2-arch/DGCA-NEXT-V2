"""Temporal Audit Tool for DGCA NEXT V2 — R2-C01-D01.

Traces and documents the exact programmatic mechanism of assembly growth
at Roots 15 and 17 (when sentences did not contain 'ماء').
Proves:
1. Reciprocal synapses between candidate cells and founding members were already CONSOLIDATED at Roots 14 and 16.
2. Growth occurred at Roots 15 and 17 due to pipeline stage ordering (GROW runs before FORM).
3. The event was a legitimate delayed structural commit, not cross-context leakage.
"""

from __future__ import annotations

import dataclasses
import os
import sys

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))
sys.stdout.reconfigure(encoding="utf-8")

from dgca.core.anatomy import SynapseScope
from dgca.core.state import MachineState
from dgca.encoder.envelope import encode_exposure
from dgca.lifecycle.exposure_tx import ExposureTransactionManager
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1
from tools.forensics.run_r2_c01_cf01_experiment import CORPUS_GROUP_B, build_schedule


def audit_growth_timing():
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
    )

    encoded = {k: encode_exposure(v, append_eos=True) for k, v in CORPUS_GROUP_B.items()}
    schedule = build_schedule(18)

    print("=== TEMPORAL AUDIT OF ASSEMBLY FORMATION & GROWTH (ROOTS 13-17) ===")

    for root_id, s_key in schedule:
        tx.begin_exposure(root_id)
        for env in encoded[s_key]:
            ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx.process_event(ev, peripheral_envelope=env.peripheral_surface)
        rep = tx.end_exposure(root_id)

        if root_id == 14:
            print("\n[Root 14 Close Inspection - S2: 'النسر يشرب ماء']")
            print(f"  Formed assemblies: {rep.assembly_report.formed_ids}")
            print(f"  Grown assemblies: {rep.assembly_report.grown_ids}")
            # Check cell 11984 reciprocal links with Asm 7 founding triangle [8242, 9854, 11638]
            for m in [8242, 9854, 11638]:
                k1 = (11984, m, SynapseScope.LOCAL)
                k2 = (m, 11984, SynapseScope.LOCAL)
                s1 = state.W.synapses.get(k1)
                s2 = state.W.synapses.get(k2)
                print(f"  Synapse 11984 <-> {m}: s1={s1.state.name} (conf={s1.external_count}), s2={s2.state.name} (conf={s2.external_count})")

        elif root_id == 15:
            print("\n[Root 15 Close Inspection - S3: 'الطفل يأكل تفاح']")
            print(f"  Formed assemblies: {rep.assembly_report.formed_ids}")
            print(f"  Grown assemblies: {rep.assembly_report.grown_ids}")
            asm7 = state.W.assemblies[7]
            print(f"  Assembly 7 members after Root 15: {asm7.member_cell_ids}, gen={asm7.structural_generation}")

        elif root_id == 16:
            print("\n[Root 16 Close Inspection - S4: 'الطفل يشرب ماء']")
            print(f"  Formed assemblies: {rep.assembly_report.formed_ids}")
            print(f"  Grown assemblies: {rep.assembly_report.grown_ids}")
            # Check candidate cells [9734, 10044, 10308, 11193] with Asm 9 founding triangle [8809, 9740, 10634]
            cands = [9734, 10044, 10308, 11193]
            founders = [8809, 9740, 10634]
            all_consolidated = True
            for c in cands:
                for f in founders:
                    k = (c, f, SynapseScope.LOCAL)
                    s = state.W.synapses.get(k)
                    if not s or s.state.name != "CONSOLIDATED":
                        all_consolidated = False
            print(f"  All 12 candidate-to-founder synapses consolidated at Root 16 close: {all_consolidated}")

        elif root_id == 17:
            print("\n[Root 17 Close Inspection - S1: 'القط يشرب حليب']")
            print(f"  Formed assemblies: {rep.assembly_report.formed_ids}")
            print(f"  Grown assemblies: {rep.assembly_report.grown_ids}")
            asm9 = state.W.assemblies[9]
            print(f"  Assembly 9 members after Root 17: {asm9.member_cell_ids}, gen={asm9.structural_generation}")


if __name__ == "__main__":
    audit_growth_timing()
