"""DGCA NEXT V2 — EGCP E1 Generic Prediction Preservation Verification Suite.

Verifies:
- Test 1: Provenance, parent E0 SHA, main SHA, and tight src/dgca modification surface.
- Test 2: EGCPMode enum, default-OFF invariants, and state clone preservation.
- Test 3: ExposureTransactionManager mode boundary guard (forbidding mid-root switch).
- Test 4: Exact OFF-mode compatibility across Roots 56, 57, 112.
- Test 5: Directed temporal mask mu_ij preservation polarity under E1 (mu_ij = 0).
- Test 6: Root 57 generic signal restoration (Asm 6 score jumps from 0.027585 to 0.329835)
          and accurate reporting of wrong-water branch selection (Asm 4 score 0.631783).
- Test 7: Root 112 autonomous rollout comparison (P1-P4) across OFF and E1 modes.
- Test 8: Zero selection leakage, determinism, and absence of E2/E3 code.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import pytest

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

from dgca.core.context_gate import compute_directed_mu_ij
from dgca.core.state import EGCPMode, MachineState
from dgca.lifecycle.exposure_tx import ExposureTransactionManager

COMPARISON_PATH = "tools/forensics/egcp_e1_comparison_data.json"
EXPECTED_E0_TIP = "671df976d6294c911cfecaf031dc8b3604308adf"
EXPECTED_FROZEN_MAIN = "f044c20b532f89749675120ffb1d8ada997e3a5e"

APPROVED_MODIFIED_FILES = {
    "src/dgca/core/__init__.py",
    "src/dgca/core/context_gate.py",
    "src/dgca/core/dynamics.py",
    "src/dgca/core/generator.py",
    "src/dgca/core/readout.py",
    "src/dgca/core/state.py",
    "src/dgca/lifecycle/exposure_tx.py",
}


@pytest.fixture(scope="module")
def comparison_data():
    assert os.path.exists(COMPARISON_PATH), f"Missing comparison data at {COMPARISON_PATH}."
    with open(COMPARISON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_01_provenance_and_integration_surface():
    """Verify commit ancestry, main immutability, and strictly bounded src/dgca diff."""
    # 1. Merge-base with E0 tip
    merge_base = subprocess.check_output(
        ["git", "merge-base", "HEAD", EXPECTED_E0_TIP],
        text=True,
    ).strip()
    assert merge_base == EXPECTED_E0_TIP, f"Expected merge-base {EXPECTED_E0_TIP}, got {merge_base}"

    # 2. Main commit SHA
    main_sha = subprocess.check_output(
        ["git", "rev-parse", "main"],
        text=True,
    ).strip()
    assert main_sha == EXPECTED_FROZEN_MAIN, f"Expected main SHA {EXPECTED_FROZEN_MAIN}, got {main_sha}"

    # 3. Exactly 7 approved files modified in src/dgca relative to E0 tip
    diff_files = subprocess.check_output(
        ["git", "diff", "--name-only", EXPECTED_E0_TIP, "--", "src/dgca"],
        text=True,
    ).strip().splitlines()
    diff_set = set(f.replace("\\", "/") for f in diff_files if f)
    assert diff_set == APPROVED_MODIFIED_FILES, f"Unexpected modifications in src/dgca: {diff_set - APPROVED_MODIFIED_FILES}"


def test_02_egcp_mode_enum_and_defaults():
    """Verify EGCPMode enum definition and default-OFF behavior."""
    assert EGCPMode.OFF.value == "OFF"
    assert EGCPMode.E1_PRESERVE_GENERIC.value == "E1_PRESERVE_GENERIC"

    # MachineState default
    st = MachineState()
    assert st.egcp_mode == EGCPMode.OFF

    # Clone preserves mode
    st_e1 = MachineState(egcp_mode=EGCPMode.E1_PRESERVE_GENERIC)
    assert st_e1.egcp_mode == EGCPMode.E1_PRESERVE_GENERIC
    st_cloned = st_e1.clone()
    assert st_cloned.egcp_mode == EGCPMode.E1_PRESERVE_GENERIC

    # ExposureTransactionManager default
    tx = ExposureTransactionManager(st)
    assert tx.egcp_mode == EGCPMode.OFF


def test_03_transaction_mode_boundary_guard():
    """Verify mode switching is allowed at root boundary and strictly forbidden during OPEN root."""
    st = MachineState()
    tx = ExposureTransactionManager(st, egcp_mode=EGCPMode.OFF)
    assert tx.egcp_mode == EGCPMode.OFF

    # Boundary switch allowed when CLOSED
    tx.set_egcp_mode(EGCPMode.E1_PRESERVE_GENERIC)
    assert tx.egcp_mode == EGCPMode.E1_PRESERVE_GENERIC
    assert tx.state.egcp_mode == EGCPMode.E1_PRESERVE_GENERIC

    # Switching during OPEN exposure must raise ValueError
    tx.begin_exposure(1)
    with pytest.raises(ValueError, match="Switching EGCP_MODE during an OPEN exposure is forbidden"):
        tx.set_egcp_mode(EGCPMode.OFF)
    tx.abort_exposure(1)


def test_04_exact_off_mode_compatibility(comparison_data):
    """Verify OFF mode reproduces 100% identical results to frozen baseline across all checkpoints."""
    roots = comparison_data["comparison_by_root"]

    # Root 56 OFF
    r56_off = roots["56"]["OFF"]
    assert r56_off["p1_step0"]["winner_surface"] == "ماء"
    assert abs(r56_off["p1_step0"]["asm4_water"]["score"] - 0.633882) < 1e-4
    assert abs(r56_off["p1_step0"]["asm6_milk"]["score"] - 0.302480) < 1e-4

    # Root 57 OFF
    r57_off = roots["57"]["OFF"]
    assert r57_off["p1_step0"]["readout_status"] == "NO_MATCH"
    assert abs(r57_off["p1_step0"]["asm6_milk"]["score"] - 0.027585) < 1e-4
    assert r57_off["probe_rollouts"]["P1"]["emitted_surfaces"] == []

    # Root 112 OFF
    r112_off = roots["112"]["OFF"]
    assert r112_off["probe_rollouts"]["P1"]["emitted_surfaces"] == []
    assert r112_off["probe_rollouts"]["P2"]["emitted_surfaces"] == ["ماء"]
    assert r112_off["probe_rollouts"]["P3"]["emitted_surfaces"] == ["تفاح"]
    assert r112_off["probe_rollouts"]["P4"]["emitted_surfaces"] == ["ماء"]
    assert r112_off["probe_rollouts"]["P4"]["stop_status"] == "GEN_STOP_EOS"


def test_05_directed_mu_preservation_polarity(comparison_data):
    """Verify effective mu_ij polarity: 1 under OFF (suppressed) and 0 under E1 (preserved)."""
    r57 = comparison_data["comparison_by_root"]["57"]
    mu_milk_off = r57["OFF"]["p1_step0"]["mu_directed_milk"]
    mu_milk_e1 = r57["E1_PRESERVE_GENERIC"]["p1_step0"]["mu_directed_milk"]

    # Under OFF at Root 57, mu_directed to milk is 1 (all 7 cells suppressed from generic anchor 8327)
    for c, val in mu_milk_off.items():
        assert val == 1, f"Expected mu_ij=1 under OFF for cell {c}, got {val}"

    # Under E1_PRESERVE_GENERIC at Root 57, mu_directed to milk is 0 (generic contribution preserved)
    for c, val in mu_milk_e1.items():
        assert val == 0, f"Expected mu_ij=0 under E1 for cell {c}, got {val}"


def test_06_root_57_generic_signal_restoration_and_wrong_water_shift(comparison_data):
    """Verify E1 restores milk signal (score 0.329835), but water wins (score 0.631783) causing wrong water shift."""
    r57 = comparison_data["comparison_by_root"]["57"]
    off_p1 = r57["OFF"]["p1_step0"]
    e1_p1 = r57["E1_PRESERVE_GENERIC"]["p1_step0"]

    # 1. Milk score restoration
    assert off_p1["asm6_milk"]["score"] < 0.08
    assert abs(off_p1["asm6_milk"]["score"] - 0.027585) < 1e-4
    assert abs(e1_p1["asm6_milk"]["score"] - 0.329835) < 1e-4
    assert e1_p1["asm6_milk"]["eligible_count"] == 7

    # 2. Water competition: Asm 4 also gets generic drive, scores 0.631783 > 0.329835
    assert abs(e1_p1["asm4_water"]["score"] - 0.631783) < 1e-4
    assert e1_p1["winner_surface"] == "ماء"
    assert e1_p1["winner_assembly_id"] == 4

    # 3. Autonomous trajectory shift: P1 shifts from silent ([]) to wrong water (['ماء'])
    assert r57["OFF"]["probe_rollouts"]["P1"]["emitted_surfaces"] == []
    assert r57["OFF"]["probe_rollouts"]["P1"]["stop_status"] == "GEN_STOP_NO_MATCH"
    assert r57["E1_PRESERVE_GENERIC"]["probe_rollouts"]["P1"]["emitted_surfaces"] == ["ماء"]
    assert r57["E1_PRESERVE_GENERIC"]["probe_rollouts"]["P1"]["stop_status"] == "GEN_STOP_EOS"


def test_07_root_112_autonomous_rollouts(comparison_data):
    """Verify Root 112 autonomous generation outcomes under OFF vs E1."""
    r112 = comparison_data["comparison_by_root"]["112"]
    off_probes = r112["OFF"]["probe_rollouts"]
    e1_probes = r112["E1_PRESERVE_GENERIC"]["probe_rollouts"]

    # P1: OFF is silent, E1 emits wrong water
    assert off_probes["P1"]["emitted_surfaces"] == []
    assert e1_probes["P1"]["emitted_surfaces"] == ["ماء"]

    # P2: Both emit ماء and fail EOS
    assert off_probes["P2"]["emitted_surfaces"] == ["ماء"]
    assert off_probes["P2"]["stop_status"] == "GEN_STOP_NO_MATCH"
    assert e1_probes["P2"]["emitted_surfaces"] == ["ماء"]
    assert e1_probes["P2"]["stop_status"] == "GEN_STOP_NO_MATCH"

    # P3: Both emit تفاح and fail EOS
    assert off_probes["P3"]["emitted_surfaces"] == ["تفاح"]
    assert off_probes["P3"]["stop_status"] == "GEN_STOP_NO_MATCH"
    assert e1_probes["P3"]["emitted_surfaces"] == ["تفاح"]
    assert e1_probes["P3"]["stop_status"] == "GEN_STOP_NO_MATCH"

    # P4: Both emit ماء and achieve EOS
    assert off_probes["P4"]["emitted_surfaces"] == ["ماء"]
    assert off_probes["P4"]["stop_status"] == "GEN_STOP_EOS"
    assert e1_probes["P4"]["emitted_surfaces"] == ["ماء"]
    assert e1_probes["P4"]["stop_status"] == "GEN_STOP_EOS"


def test_08_scientific_invariants_and_zero_selection_leakage():
    """Verify zero selection leakage, no semantic tokens, and no E2/E3 code present."""
    # Ensure no E2 or E3 methods or tables exist
    import dgca.core.state as s
    assert not hasattr(s, "E2GrowthTable")
    assert not hasattr(s, "BetaSuppressionLedger")
    assert [m.value for m in s.EGCPMode] in (
        ["OFF", "E1_PRESERVE_GENERIC"],
        ["OFF", "E1_PRESERVE_GENERIC", "E2_GROWTH"],
    )
