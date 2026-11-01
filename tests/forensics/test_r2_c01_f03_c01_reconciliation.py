"""DGCA NEXT V2 — R2-C01-F03-C01 Evidence Reconciliation Verification Tests.

Verifies:
- Task A: Normative assembly constants match frozen specification (K_MAX=16, D_MIN=2, RHO_G=0.50, SIGMA_G=0.30, SIGMA_KEEP=0.20, THETA_A=0.10).
- Task B/C/D: Cross-clique connectivity existence (11984 <-> 10634, 11984 <-> 11193 with R_b > 0.80 at Root 112) and degree-bounded GROW rejection (d = 1 < D_MIN = 2).
- Task E: Verified assembly membership (Assembly 9 size 7 excluding 10690; Assembly 17 size 7 excluding 11083).
- Task G: Authentic pre-trained post-birth-growth transactional rollback at Root 14 with FP_02.
"""

from __future__ import annotations

import dataclasses
import os
import sys
import pytest

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

from dgca.core.anatomy import SynapseScope, SynapseState
from dgca.core.assembly import (
    K_MAX,
    D_MIN,
    RHO_G,
    SIGMA_G,
    SIGMA_KEEP,
    THETA_A,
    compute_mutual_support_r_b,
)
from dgca.core.state import MachineState
from dgca.encoder.envelope import encode_exposure
from dgca.lifecycle.exposure_tx import ExposureTransactionManager
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1

CORPUS = {
    "S1": "القط يشرب حليب",
    "S2": "النسر يشرب ماء",
    "S3": "الطفل يأكل تفاح",
    "S4": "الطفل يشرب ماء",
}
SCHEDULE_ORDER = ["S1", "S2", "S3", "S4"]


def test_task_a_normative_constants():
    """Verify normative assembly constants match frozen specification exactly."""
    assert K_MAX == 16, f"Expected K_MAX=16, got {K_MAX}"
    assert D_MIN == 2, f"Expected D_MIN=2, got {D_MIN}"
    assert RHO_G == 0.50, f"Expected RHO_G=0.50, got {RHO_G}"
    assert SIGMA_G == 0.30, f"Expected SIGMA_G=0.30, got {SIGMA_G}"
    assert SIGMA_KEEP == 0.20, f"Expected SIGMA_KEEP=0.20, got {SIGMA_KEEP}"
    assert THETA_A == 0.10, f"Expected THETA_A=0.10, got {THETA_A}"


def test_task_b_c_d_e_cross_clique_connectivity_and_membership():
    """Verify assembly memberships, cross-clique connectivity at Root 112, and GROW failure causation."""
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
        enable_birth_time_grow=False,
    )
    encoded = {k: encode_exposure(v, append_eos=True) for k, v in CORPUS.items()}

    for root_id in range(1, 113):
        s_key = SCHEDULE_ORDER[(root_id - 1) % 4]
        tx.begin_exposure(root_id)
        for env in encoded[s_key]:
            core_ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        tx.end_exposure(root_id)

    w = state.W

    # Task E: Reconciled Assembly Memberships
    # Assembly 7: [8242, 9854, 11638, 11984] (size 4)
    asm7 = w.assemblies[7]
    assert sorted(list(asm7.member_cell_ids)) == [8242, 9854, 11638, 11984]
    assert len(asm7.member_cell_ids) == 4
    assert asm7.structural_generation == 2

    # Assembly 9: [8809, 9734, 9740, 10044, 10308, 10634, 11193] (size 7)
    asm9 = w.assemblies[9]
    assert sorted(list(asm9.member_cell_ids)) == [8809, 9734, 9740, 10044, 10308, 10634, 11193]
    assert len(asm9.member_cell_ids) == 7
    assert 10690 not in asm9.member_cell_ids, "Cell 10690 must NOT be in Assembly 9!"
    assert asm9.structural_generation == 5

    # Assembly 14: [9334, 9468, 10457, 11289] (size 4)
    asm14 = w.assemblies[14]
    assert sorted(list(asm14.member_cell_ids)) == [9334, 9468, 10457, 11289]
    assert len(asm14.member_cell_ids) == 4
    assert asm14.structural_generation == 2

    # Assembly 17: [8513, 8961, 10181, 10363, 10616, 10737, 11830] (size 7)
    asm17 = w.assemblies[17]
    assert sorted(list(asm17.member_cell_ids)) == [8513, 8961, 10181, 10363, 10616, 10737, 11830]
    assert len(asm17.member_cell_ids) == 7
    assert 11083 not in asm17.member_cell_ids, "Cell 11083 must NOT be in Assembly 17!"
    assert asm17.structural_generation == 5

    # Task B & C: Verified Cross-Clique Connectivity
    # Cell 11984 (in Asm 7) has consolidated reciprocal edges to 10634 and 11193 (in Asm 9)
    syn_fwd_10634 = w.synapses.get((11984, 10634, SynapseScope.LOCAL))
    syn_rev_10634 = w.synapses.get((10634, 11984, SynapseScope.LOCAL))
    assert syn_fwd_10634 is not None and syn_fwd_10634.state == SynapseState.CONSOLIDATED
    assert syn_rev_10634 is not None and syn_rev_10634.state == SynapseState.CONSOLIDATED

    r_b_10634 = compute_mutual_support_r_b(11984, 10634, w)
    assert r_b_10634 > 0.80, f"Expected R_b > 0.80 for 11984 <-> 10634, got {r_b_10634}"

    syn_fwd_11193 = w.synapses.get((11984, 11193, SynapseScope.LOCAL))
    syn_rev_11193 = w.synapses.get((11193, 11984, SynapseScope.LOCAL))
    assert syn_fwd_11193 is not None and syn_fwd_11193.state == SynapseState.CONSOLIDATED
    assert syn_rev_11193 is not None and syn_rev_11193.state == SynapseState.CONSOLIDATED

    r_b_11193 = compute_mutual_support_r_b(11984, 11193, w)
    assert r_b_11193 > 0.80, f"Expected R_b > 0.80 for 11984 <-> 11193, got {r_b_11193}"

    # Task D: GROW Rejection Causation
    # Degree into Assembly 7:
    for cand_id in [10634, 11193]:
        neighbors_in_asm7 = [
            m for m in asm7.member_cell_ids
            if compute_mutual_support_r_b(cand_id, m, w) >= THETA_A
        ]
        degree = len(neighbors_in_asm7)
        # Reconciled proof: Degree is exactly 1 (only 11984 connects), which fails D_MIN = 2
        assert degree == 1
        assert degree < D_MIN, "Degree filter d >= D_MIN (2) must fail!"


def test_task_g_authentic_pretrained_post_birth_grow_rollback_fp02():
    """Verify authentic pre-trained post-birth-growth transactional rollback at Root 14 with FP_02."""
    state = MachineState()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        enable_birth_time_grow=True,
    )
    encoded = {k: encode_exposure(v, append_eos=True) for k, v in CORPUS.items()}

    # Train authentic roots 1..13
    for r in range(1, 14):
        s_key = SCHEDULE_ORDER[(r - 1) % 4]
        tx.begin_exposure(r)
        for env in encoded[s_key]:
            ev = dataclasses.replace(env.core_event, exposure_id=r)
            tx.process_event(ev, peripheral_envelope=env.peripheral_surface)
        tx.end_exposure(r)

    pre_asms = {
        aid: (asm.structural_generation, tuple(sorted(asm.member_cell_ids)))
        for aid, asm in state.W.assemblies.items()
    }
    pre_syns_count = len(state.W.synapses)
    assert len(pre_asms) == 6

    # Shadow state interceptor at FP_02
    shadow_box: dict[str, Any] = {}
    def hook(w_pre, w_shadow, h_slow, journal, diags):
        shadow_box["asms"] = {
            aid: (asm.structural_generation, tuple(sorted(asm.member_cell_ids)))
            for aid, asm in w_shadow.assemblies.items()
        }

    tx.register_end_exposure_hook(hook)
    tx._fault_injection_point = "FP_02"

    # Execute Root 14 ("النسر يشرب ماء")
    tx.begin_exposure(14)
    s_key = SCHEDULE_ORDER[(14 - 1) % 4]
    for env in encoded[s_key]:
        ev = dataclasses.replace(env.core_event, exposure_id=14)
        tx.process_event(ev, peripheral_envelope=env.peripheral_surface)

    # FP_02 fires during end_exposure
    with pytest.raises(RuntimeError, match="FP-02"):
        tx.end_exposure(14)

    # Assert shadow state formed Asm 7 and grew it to size 4 with cell 11984
    shadow_asms = shadow_box["asms"]
    assert 7 in shadow_asms, "Assembly 7 must have formed in w_shadow"
    assert shadow_asms[7] == (2, (8242, 9854, 11638, 11984)), "Assembly 7 must have recruited cell 11984 in shadow state"

    # Transactional abort
    tx.abort_exposure(14)

    # Assert active WState assemblies and synapses are 100% restored to Root 13 pre-root state
    post_asms = {
        aid: (asm.structural_generation, tuple(sorted(asm.member_cell_ids)))
        for aid, asm in state.W.assemblies.items()
    }
    assert post_asms == pre_asms, "Active assemblies mutated despite FP_02 abort!"
    assert len(state.W.synapses) == pre_syns_count, "Synapses mutated despite FP_02 abort!"
    assert 14 not in tx.publication_view.completed_roots
