"""DGCA NEXT V2 — EGCP E0 Baseline Reproduction Verification Suite.

Verifies:
- Test 1: Authoritative Provenance and Core Immutability (parent CF04 SHA, main SHA, zero diff in src/dgca).
- Test 2: Group A Frozen State Hash Exactness (Roots 14, 16, 27, 31, 56, 112).
- Test 3: Group B Structural Assembly Deduplication and Inventory at Root 112 (11 assemblies, Asm 1=12, Asm 4=5, Asm 6=7).
- Test 4: Autonomous Generation Rollout Trajectories across Roots 56, 57, and 112.
- Test 5: Root 56 Step 0 Readout Competition (Asm 4 vs Asm 6 on P1).
- Test 6: Root 57 StableBinding Lifecycle, Muting, and Causal Collapse (Candidate 8320 graduation, muted cells).
- Test 7: Root 112 Step 1 EOS Rollout Asymmetry (P2 control pass saturation vs P4 cold EOS).
- Test 8: Zero Selection Leakage and Determinism Invariants.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import pytest

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

MANIFEST_PATH = "tools/forensics/egcp_e0_manifest.json"

EXPECTED_FROZEN_MAIN = "f044c20b532f89749675120ffb1d8ada997e3a5e"
EXPECTED_CF04_BASELINE = "e43ba731deeb8ee4433fd633cb36f2823bce9e79"
EXPECTED_HASHES_A = {
    14: "e8ed6ba87ecf13513d738014941c872d8103dc047ace218e5055d64ae3c46196",
    16: "64eac0897b144ec04e1e7ade80441f9dc71c0971beb76d8466f665e37a9f03f8",
    27: "e8c70c791cdb689b48d291ff0dd9a14d223545385b43e7a97fb45ceae6370eb7",
    31: "fe3e013f325e49c094edc7b92c585a182f095e825086b928ffd1e7a4b11d115a",
    56: "19f3a4a24dd1145cf59d317c92f72d79c8207369e9109b61fa00645cf573129d",
    112: "56cc7b15a600fa7caaa51c0d1aeeb1e903da04cad3fc5e028724a104284857f0",
}


@pytest.fixture(scope="module")
def manifest():
    assert os.path.exists(MANIFEST_PATH), f"Missing manifest at {MANIFEST_PATH}. Run run_egcp_e0_reproduction.py first."
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_01_provenance_and_core_immutability():
    """Verify Git branch, commit ancestry, and zero modifications to src/dgca."""
    # 1. Verify parent commit contains CF04 baseline
    merge_base = subprocess.check_output(
        ["git", "merge-base", "HEAD", EXPECTED_CF04_BASELINE],
        text=True,
    ).strip()
    assert merge_base == EXPECTED_CF04_BASELINE, f"Expected merge-base {EXPECTED_CF04_BASELINE}, got {merge_base}"

    # 2. Verify main commit SHA
    main_sha = subprocess.check_output(
        ["git", "rev-parse", "main"],
        text=True,
    ).strip()
    assert main_sha == EXPECTED_FROZEN_MAIN, f"Expected main SHA {EXPECTED_FROZEN_MAIN}, got {main_sha}"

    # 3. Verify zero uncommitted or committed changes to src/dgca
    diff_core = subprocess.check_output(
        ["git", "diff", EXPECTED_CF04_BASELINE, "--", "src/dgca"],
        text=True,
    ).strip()
    assert diff_core == "", f"Experimental branch has modified src/dgca relative to CF04 baseline: {diff_core}"


def test_02_group_a_frozen_state_hashes(manifest):
    """Verify Group A state snapshot hashes are 100% byte-for-byte identical to frozen baseline."""
    hashes_a = manifest["checkpoint_hashes"]["group_a"]
    for r, exp_hash in EXPECTED_HASHES_A.items():
        assert hashes_a[str(r)] == exp_hash, f"Hash mismatch at Root {r}: got {hashes_a[str(r)]} != {exp_hash}"


def test_03_group_b_assembly_deduplication(manifest):
    """Verify Group B structural deduplication (11 assemblies) and exact memberships at Root 112."""
    asms = manifest["group_b_assemblies_112"]
    assert len(asms) == 11, f"Expected exactly 11 assemblies in Group B, got {len(asms)}"

    # Assembly 1 (<EOS>)
    asm1 = asms["1"]
    assert asm1["size"] == 12
    assert asm1["structural_generation"] == 10
    assert asm1["members"] == [8728, 8834, 9209, 10417, 10570, 10646, 10915, 11153, 11583, 11859, 12116, 12117]

    # Assembly 4 (ماء)
    asm4 = asms["4"]
    assert asm4["size"] == 5
    assert asm4["structural_generation"] == 3
    assert asm4["members"] == [8242, 8809, 9854, 11638, 11984]

    # Assembly 6 (حليب)
    asm6 = asms["6"]
    assert asm6["size"] == 7
    assert asm6["structural_generation"] == 5
    assert asm6["members"] == [9183, 9319, 9325, 10903, 11191, 11220, 11463]

    # Deduplication: duplicate water assembly 9 was eliminated
    assert "9" not in asms or asms["9"]["surface"] != "ماء"


def test_04_probe_rollout_trajectories_56_57_112(manifest):
    """Verify canonical autonomous rollout trajectories across Roots 56, 57, and 112."""
    rollouts = manifest["probe_rollouts"]

    # Root 56: P1 emits wrong water branch, P4 terminates at EOS
    r56 = rollouts["56"]
    assert r56["P1"]["stop_status"] == "GEN_STOP_EOS"
    assert r56["P1"]["emitted_surfaces"] == ["ماء"]
    assert r56["P2"]["stop_status"] == "GEN_STOP_NO_MATCH"
    assert r56["P2"]["emitted_surfaces"] == ["ماء"]
    assert r56["P3"]["stop_status"] == "GEN_STOP_NO_MATCH"
    assert r56["P3"]["emitted_surfaces"] == ["تفاح"]
    assert r56["P4"]["stop_status"] == "GEN_STOP_EOS"
    assert r56["P4"]["emitted_surfaces"] == ["ماء"]

    # Root 57: P1 becomes silent (GEN_STOP_NO_MATCH), P4 terminates at EOS
    r57 = rollouts["57"]
    assert r57["P1"]["stop_status"] == "GEN_STOP_NO_MATCH"
    assert r57["P1"]["emitted_surfaces"] == []
    assert r57["P4"]["stop_status"] == "GEN_STOP_EOS"
    assert r57["P4"]["emitted_surfaces"] == ["ماء"]

    # Root 112: Stable endpoint
    r112 = rollouts["112"]
    assert r112["P1"]["stop_status"] == "GEN_STOP_NO_MATCH"
    assert r112["P1"]["emitted_surfaces"] == []
    assert r112["P2"]["stop_status"] == "GEN_STOP_NO_MATCH"
    assert r112["P2"]["emitted_surfaces"] == ["ماء"]
    assert r112["P3"]["stop_status"] == "GEN_STOP_NO_MATCH"
    assert r112["P3"]["emitted_surfaces"] == ["تفاح"]
    assert r112["P4"]["stop_status"] == "GEN_STOP_EOS"
    assert r112["P4"]["emitted_surfaces"] == ["ماء"]


def test_05_root_56_step0_readout_competition(manifest):
    """Verify Root 56 Step 0 competition: Asm 4 (ماء) beats Asm 6 (حليب)."""
    p1_56 = manifest["root_56_step0_p1"]
    assert p1_56["winner_assembly_id"] == 4
    assert p1_56["winner_surface"] == "ماء"
    assert abs(p1_56["asm4_water_score"] - 0.633882) < 1e-4
    assert abs(p1_56["asm6_milk_score"] - 0.302480) < 1e-4
    assert p1_56["asm4_water_score"] > p1_56["asm6_milk_score"]


def test_06_root_57_stable_binding_and_gating(manifest):
    """Verify Root 57 contextual gating transition: Candidate 8320 graduation and muting."""
    trans = manifest["root_57_binding_transition"]
    assert trans["binding_8320_graduated"] is True
    assert trans["anchor_id"] == 8327
    assert trans["target_cells"] == [9319, 9325]
    assert trans["assembly6_members"] == [9183, 9319, 9325, 10903, 11191, 11220, 11463]
    assert trans["muted_uncovered_cells"] == [9183, 10903, 11191, 11220, 11463]
    assert trans["p1_step0_status"] == "NO_MATCH"
    assert trans["p1_step0_asm6_score"] < 0.08
    assert abs(trans["p1_step0_asm6_score"] - 0.027585) < 1e-4


def test_07_root_112_step1_eos_asymmetry(manifest):
    """Verify Root 112 Step 1 EOS asymmetry between P2 and P4."""
    eos = manifest["root_112_step1_eos_comparison"]
    p2 = eos["p2_trace"]
    p4 = eos["p4_trace"]

    # Assembly 1 size and eligible member counts
    assert p2["asm1_member_count"] == 12
    assert p4["asm1_member_count"] == 12
    assert p2["asm1_eligible_count"] == 8
    assert p4["asm1_eligible_count"] == 8

    # Scores
    assert abs(p2["asm1_score"] - 0.036007) < 1e-4
    assert abs(p4["asm1_score"] - 0.355377) < 1e-4

    # Control pass activation saturation
    assert p2["asm1_a_ctrl_elig_mean"] > 0.75
    assert p4["asm1_a_ctrl_elig_mean"] == 0.0

    # Stop status
    assert p2["step1_status"] == "NO_MATCH"
    assert p4["step1_status"] == "OK"


def test_08_zero_selection_leakage_and_invariants(manifest):
    """Verify scientific governance invariants."""
    inv = manifest["invariants"]
    assert inv["ZERO_SELECTION_LEAKAGE"] is True
    assert inv["NO_SEMANTIC_LEAKAGE"] is True
    assert inv["DETERMINISM_VERIFIED"] is True
