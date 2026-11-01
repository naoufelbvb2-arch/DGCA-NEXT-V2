"""Tests for DGCA NEXT V2 — R2-C01-F03 Forensic Verification.

Sensory Cross-Clique Connectivity, Synaptic Evidence & Structural Reuse Forensics.
"""

from __future__ import annotations

import dataclasses
import os
import sys
import pytest

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

from dgca.common.errors import DGCAError
from dgca.core.anatomy import Region, SynapseScope, SynapseState
from dgca.core.assembly import (
    AssemblyStatus,
    THETA_A,
    D_MIN,
    compute_mutual_support_r_b,
)
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import MachineState
from dgca.encoder.envelope import encode_exposure
from dgca.lifecycle.exposure_tx import ExposureTransactionManager
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1
from tools.forensics.run_r2_c01_cf01_experiment import CORPUS_GROUP_B, build_schedule
from tools.forensics.investigate_r2_c01_f03_connectivity import (
    audit_subgraph,
    decompose_grow_eligibility,
    extract_sensory_footprints,
)


@pytest.fixture(scope="module")
def trained_forensic_state():
    """Trains Group B up to Root 16 to inspect birth of Assemblies 7 and 9."""
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        readout_ledger=ledger,
    )

    encoded = {
        k: encode_exposure(v, append_eos=True)
        for k, v in CORPUS_GROUP_B.items()
    }
    schedule = build_schedule(16)

    checkpoints = {}
    for root_id, s_key in schedule:
        tx.begin_exposure(root_id)
        for env in encoded[s_key]:
            core_ev = dataclasses.replace(env.core_event, exposure_id=root_id)
            tx.process_event(core_ev, peripheral_envelope=env.peripheral_surface)
        rep = tx.end_exposure(root_id)
        if root_id in (14, 16):
            checkpoints[root_id] = {
                "state": state.clone(),
                "ledger": ledger.clone(),
            }

    footprints = extract_sensory_footprints(encoded)
    return checkpoints, footprints


def test_water_subgraph_cross_clique_isolation_at_birth(trained_forensic_state):
    """F03-S01 & S02: Verify zero cross-clique reciprocal support between Assembly 7 and 9."""
    checkpoints, footprints = trained_forensic_state
    water_cells = footprints["ماء"]
    top_clique = [8242, 9854, 11638, 11984]
    sec_clique = [c for c in water_cells if c not in top_clique]

    # At Root 14 Close (Assembly 7 born)
    sg14 = audit_subgraph(checkpoints[14]["state"], water_cells)
    assert sg14["reciprocal_eligible_edge_count"] == 6
    assert sg14["components"][0] == top_clique
    assert len(sg14["components"]) == 13  # 1 4-clique + 12 isolates

    # At Root 16 Close (Assembly 9 born)
    st16 = checkpoints[16]["state"]
    sg16 = audit_subgraph(st16, water_cells)
    assert sg16["reciprocal_eligible_edge_count"] == 24
    assert len(sg16["components"]) == 6

    # Verify Component 1 is Assembly 7 founders
    assert top_clique in sg16["components"]
    asm9_founder_comp = [8809, 9734, 9740, 10044, 10308, 10634, 10690, 11193]
    assert asm9_founder_comp in sg16["components"]

    # Crucial causal proof: ZERO cross-clique reciprocal support between Assembly 7 and 9
    for c_top in top_clique:
        for c_sec in asm9_founder_comp:
            r_b = compute_mutual_support_r_b(c_top, c_sec, st16.W)
            assert r_b == 0.0, f"Expected 0 reciprocal support between {c_top} and {c_sec}, got {r_b}"
            # Check directed synapses
            k1 = (c_top, c_sec, SynapseScope.LOCAL)
            k2 = (c_sec, c_top, SynapseScope.LOCAL)
            assert k1 not in st16.W.synapses
            assert k2 not in st16.W.synapses


def test_grow_eligibility_decomposition_degree_failure(trained_forensic_state):
    """F03-S03: Verify all non-member cells fail GROW eligibility specifically at d < D_MIN."""
    checkpoints, footprints = trained_forensic_state
    water_cells = footprints["ماء"]

    # Inspect Assembly 7 at Root 14 close
    # At Root 14 close, Assembly 7 has 3 members [8242, 9854, 11638].
    # Cell 11984 (from top clique) is ELIGIBLE with d=3, while all 12 secondary clique cells fail with d=0 < 2.
    grow14 = decompose_grow_eligibility(checkpoints[14]["state"], 7, water_cells)
    assert len(grow14) == 13
    assert grow14[11984]["verdict"] == "ELIGIBLE"
    assert grow14[11984]["d_x"] == 3

    secondary_cells = [c for c in water_cells if c not in (8242, 9854, 11638, 11984)]
    assert len(secondary_cells) == 12
    for cand in secondary_cells:
        info = grow14[cand]
        assert info["verdict"] == f"DEGREE_BELOW_D_MIN (d=0 < {D_MIN})"
        assert info["d_x"] == 0
        assert info["reciprocal_neighbors_in_asm"] == []

    # Inspect Assembly 7 at Root 16 close
    # Cell 11984 has now joined Assembly 7 (members: [8242, 9854, 11638, 11984]).
    # Exactly the 12 secondary cells remain, all failing with d=0 < 2.
    grow16 = decompose_grow_eligibility(checkpoints[16]["state"], 7, water_cells)
    assert len(grow16) == 12
    for cand in secondary_cells:
        info = grow16[cand]
        assert info["verdict"] == f"DEGREE_BELOW_D_MIN (d=0 < {D_MIN})"
        assert info["d_x"] == 0
        assert info["reciprocal_neighbors_in_asm"] == []


def test_latent_table_partitioning_mechanism(trained_forensic_state):
    """F03-S05: Verify LLA latent neighborhood partitioning blocks cross-clique proposal generation."""
    checkpoints, footprints = trained_forensic_state
    w14 = checkpoints[14]["state"].W
    top_clique = [8242, 9854, 11638, 11984]
    sec_founder = [8809, 9734, 9740, 10044, 10308, 10634, 10690, 11193]

    # Verify all pairs within top clique are admitted and eligible in latent table
    for i in range(len(top_clique)):
        for j in range(i + 1, len(top_clique)):
            c1, c2 = top_clique[i], top_clique[j]
            assert w14.latent_table.is_eligible(c1, c2) or w14.latent_table.is_eligible(c2, c1)

    # Verify zero cross-clique pairs between top clique and Assembly 9 founders are admitted
    for c_top in top_clique:
        for c_sec in sec_founder:
            assert not w14.latent_table.is_eligible(c_top, c_sec)
            assert not w14.latent_table.is_eligible(c_sec, c_top)


def test_post_assembly_transactional_rollback_fp02():
    """F03-S06 Part B: Verify transactional atomicity when FP_02 fires after assembly pipeline."""
    state = MachineState()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=True,
        enable_assembly_pipeline=True,
        enable_birth_time_grow=True,
    )
    tx._fault_injection_point = "FP_02"

    encoded = encode_exposure("النسر يشرب ماء", append_eos=True)

    tx.begin_exposure(14)
    for env in encoded:
        ev = dataclasses.replace(env.core_event, exposure_id=14)
        tx.process_event(ev, peripheral_envelope=env.peripheral_surface)

    with pytest.raises(RuntimeError, match="FP-02"):
        tx.end_exposure(14)

    # Confirm complete uncommitted rollback
    assert 14 not in tx.publication_view.completed_roots
    assert len(state.W.assemblies) == 0
    assert state.W.completed_roots_high_watermark == 0
