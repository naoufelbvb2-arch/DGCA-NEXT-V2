# DGCA NEXT V2 — R2-B03-C01 Scientific Acceptance Evidence & Legacy Regression Reconciliation Report

**Document Identifier:** `DGCA-R2-B03-C01-SCIENTIFIC-ACCEPTANCE-REPORT-20261030`  
**Role:** Principal Scientific Verification Engineer, Deterministic Runtime Auditor, and Release Governance Reviewer  
**Status:** SCIENTIFIC GATES VERIFIED — LEGACY REBASELINE REVIEW PENDING  
**Date:** 2026-10-30  

---

## 1. Authoritative Baselines & Source Integrity

- **Repository:** `naoufelbvb2-arch/DGCA-NEXT-V2`
- **Implementation Branch:** `experiment/r2-b03-exact-duplicate-merge`
- **Starting Implementation HEAD:** [`49d9abbbb7de3b2979e9336fcee7bf25e0c58390`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2)
- **Frozen Production Baseline:** [`faf361b6b95de6287b466eb1dc524ea49c732635`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2) (`origin/main`)
- **Accepted Scientific Forensic Baseline:** [`205efa0e664dc26f31f131d5efc19ac37b3eb95d`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2)
- **Corrected Design Documentation SHA:** [`9b1c31acf508d32a1738dfcc987e1082529332e9`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2)
- **Frozen Design Identifier:** `DGCA-R2-B02-DESIGN-FROZEN-20261030`
- **Production Source Invariant:** Zero modifications to `src/` under this assignment. Production code remains strictly at the 16-line patch in [`src/dgca/core/assembly.py::_try_merge_pair()`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/core/assembly.py#L537-L557). Zero main branch promotion.

---

## 2. New Verification Tests Added

A dedicated scientific acceptance suite was authored in [`tests/test_r2_b03_c01_acceptance.py`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/tests/test_r2_b03_c01_acceptance.py):

| Test Identifier | Section | Gate | Primary Assertion Scope |
| :--- | :--- | :--- | :--- |
| `test_c01_s01_eagle_generation_proof` | C01-S01 | Gate D | 1-event and 2-event prompt rollouts for Cat and Eagle; runtime verification of winner Asm 5, Gen 8, top score $0.20694$, margin $0.11335 \ge M_{\text{read}} = 0.04$, `Marker.EOS`, `StatusCode.GEN_STOP_EOS`. |
| `test_c01_s02_real_post_merge_attestation_proof` | C01-S02 | Gate C | Inspection of real trained ledger for Assembly 5 at Gen 8; extracts 46 confirmed roots $[11, 56]$; first root 11, second root 12; zero evidence leakage from archived Assembly 6. |
| `test_c01_s03_read_only_generation_integrity` | C01-S03 | Gate C | 100% dictionary equality and SHA-256 equivalence across W, H_slow, R, Ledger before and after Cat rollout, Eagle rollout, and read-only retrieval. |
| `test_c01_s04_post_assembly_pre_publication_fault_fp02` | C01-S04 | Gate A | End-exposure hook proves shadow consolidation occurred in `w_shadow` before `FP_02` failure; active W retains pre-exposure state; zero outbox published; sensory commitments preserved. |
| `test_c01_s04_post_commit_dispatch_fault_fp03` | C01-S04 | Gate A | Verifies post-commit dispatch fault containment: commit succeeds, watermark advances, outbox dispatch deferred safely. |
| `test_c01_s05_non_identical_merge_differential` | C01-S05 | Gate B | Differential harness executing frozen baseline `_baseline_try_merge_pair` against patched `_try_merge_pair` across 8 non-identical cases; bit-exact output parity. |
| `test_c01_s07_full_state_determinism` | C01-S07 | Gate A | Dual independent 56-root curriculum replays from cold start; asserts bit-exact SHA-256 digest match across W, H_slow, R, Ledger, and PublicationView. |

---

## 3. Test Execution Commands & Actual Counts

### Execution Commands
```powershell
# 1. Execute R2-B03-C01 Acceptance Suite
python -m pytest tests/test_r2_b03_c01_acceptance.py -v

# 2. Execute R2-B03 Initial Acceptance Suite
python -m pytest tests/test_r2_b03_exact_duplicate_merge.py -v

# 3. Execute Combined Acceptance Test Suites
python -m pytest tests/test_r2_b03_exact_duplicate_merge.py tests/test_r2_b03_c01_acceptance.py -v

# 4. Execute Baseline Regression Suite (Legacy Tests)
python -m pytest --ignore=tests/test_r2_b03_exact_duplicate_merge.py --ignore=tests/test_r2_b03_c01_acceptance.py
```

### Measured Test Counts
- **`tests/test_r2_b03_c01_acceptance.py`:** **7 passed**, 0 failed in 38.98s.
- **`tests/test_r2_b03_exact_duplicate_merge.py`:** **16 passed**, 0 failed in 15.90s.
- **Combined Acceptance Suites:** **23 passed**, 0 failed in 84.55s.
- **Pre-Existing Baseline Suite:** **190 passed**, **2 failed** in 33.55s (strictly the 2 obsolete pre-remediation assertions analyzed in Section 10).

---

## 4. Genuine Eagle EOS Generation Result (C01-S01)

On a genuinely cold `MachineState` trained over the complete 56-root Cat/Eagle curriculum without hand-wiring or synthetic insertions:

### Rollout Summary
- **Cat 1-Event Prompt (`['القط']`):** Emitted surfaces: `('يشرب', 'حليب')` $\to$ `StatusCode.GEN_STOP_EOS`
- **Cat 2-Event Prompt (`['القط', 'يشرب']`):** Emitted surfaces: `('حليب',)` $\to$ `StatusCode.GEN_STOP_EOS`
- **Eagle 1-Event Prompt (`['النسر']`):** Emitted surfaces: `('يشرب', 'ماء')` $\to$ `StatusCode.GEN_STOP_EOS`
- **Eagle 2-Event Prompt (`['النسر', 'يشرب']`):** Emitted surfaces: `('ماء',)` $\to$ `StatusCode.GEN_STOP_EOS`

### Runtime Measurements at Eagle Step 2 (`ماء` $\to$ `<EOS>`)
```
Winner Assembly ID:             5
Winner Structural Generation:   8
Neural Top Score (Asm 5, Gen 8):0.20694424313392146
Second Score (Asm 2, Gen 2):    0.09358942151495935
Actual Score Margin:            0.11335482161896211
Authoritative Margin Bound:     margin (0.11335) >= M_READ (0.04000) [PASS]
Ledger Resolution Status:       StatusCode.OK
Resolved Marker:                Marker.EOS
Emitted Surface (NFC UTF-8):    "<EOS>"
Final Episode Stop Status:      StatusCode.GEN_STOP_EOS
```
*Scientific Finding:* The readout-score collision between Assemblies 5 and 6 is **completely eliminated**. Assembly 5 wins alone with a substantial margin ($0.11335$, nearly $3\times$ the required threshold $0.04$), resolving deterministically to `<EOS>`.

---

## 5. Real Post-Merge Attestation Evidence (C01-S02)

Inspection of the actual `SurfaceReadoutLedgerV1` produced by the 56-root curriculum:

- **Assembly 5 Final Structural Generation:** Generation 8 (formed at Gen 1, grown to Gen 6, merged at Gen 7, recruited cell 12117 at Gen 8).
- **Candidate Rows for Key `(5, 8)`:** Exactly 1 candidate row (`len = 1`).
- **Surface & Marker:** Surface = `"<EOS>"`, Marker = `Marker.EOS`, Feature Bundle Digest length = 32 bytes.
- **Confirmed Roots Population:** Exactly 46 distinct completed external roots:
  $$\text{Confirmed Roots} = \{11, 12, 13, 14, 15, \dots, 55, 56\}$$
- **First Qualifying External Root:** **Root 11** (the first exposure begun with Assembly 5 pre-existing at Generation 8).
- **Second Qualifying External Root:** **Root 12** (the second qualifying exposure, satisfying $K_{\text{attest}} \ge 2$).
- **Evidence Isolation Checks:**
  - `get_candidate_rows(5, 1) == []` (No stale Gen 1 rows).
  - `get_candidate_rows(5, 7) == []` (No stale Gen 7 rows).
  - `resolve_readout(5, 1, current_live_generation=8).status == StatusCode.GEN_STOP_STALE_ASSEMBLY`.
  - Archived Assembly 6 candidate rows across all generations: **0** (`get_candidate_rows(6, g) == []` $\forall g$).

---

## 6. Read-Only Generation Integrity (C01-S03)

Authoritative deep state snapshots were captured before and after rollouts using the full 100% dataclass coverage snapshot infrastructure:

| Partition | Pre-Cat Digest | Post-Cat Digest | Post-Eagle Digest | Post-RETRIEVE Digest | Equivalence |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **WState** | `c1656afee411...` | `c1656afee411...` | `c1656afee411...` | `c1656afee411...` | **Bit-exact (100%)** |
| **HSlowState** | `dec7645bc296...` | `dec7645bc296...` | `dec7645bc296...` | `dec7645bc296...` | **Bit-exact (100%)** |
| **Caller RState**| `770958e65c3d...` | `770958e65c3d...` | `770958e65c3d...` | `770958e65c3d...` | **Bit-exact (100%)** |
| **Ledger** | `10664c78e5c2...` | `10664c78e5c2...` | `10664c78e5c2...` | `10664c78e5c2...` | **Bit-exact (100%)** |
| **Outbox Keys** | 352 keys | 352 keys | 352 keys | 352 keys | **Bit-exact (100%)** |

*Scientific Finding:* `generate_episode()` and `run_read_only_episode()` are strictly read-only and leave 100% of the machine state, homeostatic state, caller state, and peripheral ledger intact.

---

## 7. Post-Assembly Pre-Publication Fault Verification (C01-S04)

### `FP_02` Execution Trace (Post-Assembly Pre-Publication Failure)
1. **Curriculum Staging:** Trained Roots 1–8. Pre-exposure assemblies at Root 8:
   - Assembly 5: `LIVE`, Generation 1, members `(8834, 9209, 10570)`.
   - Assembly 6: `LIVE`, Generation 1, members `(10646, 10915, 11153)`.
2. **Shadow Pipeline Execution:** Root 9 (Cat) processed. Registered shadow hook executed at line 1050 of `exposure_tx.py`:
   - Verified in `w_shadow`: Assembly 5 grew and merged with Assembly 6 $\implies$ Assembly 5 reached Generation 7 (`LIVE`), Assembly 6 reached Generation 7 (`ARCHIVED`).
   - Hook asserted `shadow_consolidation_verified = True`.
3. **Injected Failure:** `tx._fault_injection_point = "FP_02"` raised `RuntimeError("Injected fault at FP-02: outbox batch construction failure")` at line 1054.
4. **Active State Verification:**
   - Single pointer swap at line 1111 (`self.state.W = new_view.W`) was **never reached**.
   - Active `state.W.assemblies[5]` remained Generation 1 (`LIVE`), members `(8834, 9209, 10570)`.
   - Active `state.W.assemblies[6]` remained Generation 1 (`LIVE`), members `(10646, 10915, 11153)`.
   - Outbox publication for Root 9 was **never published** (`9 not in tx._publication_view.pending_outbox_by_root`).
   - Lawful sensory cell commitments made during `process_event` remained intact in `state.W.committed_cells` per Core §10.1 / R2-A01 rules.

### `FP_03` Execution Trace (Post-Commit Dispatch Failure)
- Post-commit dispatch failure tested at `FP_03`: transaction commit succeeds atomically, high watermark advances, and pending outbox notifications remain safely staged for idempotent retry.

---

## 8. Non-Identical MERGE Differential Results (C01-S05)

A formal differential test harness compared the frozen baseline `_baseline_try_merge_pair()` directly against the patched production `_try_merge_pair()` across 8 representative non-identical scenarios on identical initial states:

| Scenario | Structural Configuration | Baseline Decision | Patched Decision | State Parity |
| :--- | :--- | :--- | :--- | :--- |
| **Case 1: Eligible Partial-Overlap** | 8 shared cells, 1 exclusive cell each, mutual LOCAL link ($S=0.85, E_{\text{ext}}=6.0$). $J = 0.80 \ge 0.70$. | `True` (Merged) | `True` (Merged) | **100% Bit-exact match** |
| **Case 2: Weak Exclusive Support** | Same as Case 1, but mutual link has $S=0.20 < 0.60$ (fails consolidated guard). | `False` (Rejected) | `False` (Rejected) | **100% Bit-exact match** |
| **Case 3: Proper Subset** | $A \subset B$ ($|A|=4, |B|=5$, $J = 0.80$). Exclusive set $A \setminus B = \emptyset$. | `False` (Rejected) | `False` (Rejected) | **100% Bit-exact match** |
| **Case 4: Proper Superset** | $B \subset A$ ($|A|=5, |B|=4$, $J = 0.80$). Exclusive set $B \setminus A = \emptyset$. | `False` (Rejected) | `False` (Rejected) | **100% Bit-exact match** |
| **Case 5: Below-Threshold Jaccard**| Overlap yields $J = 1/7 = 0.1428 < 0.70$. | `False` (Rejected) | `False` (Rejected) | **100% Bit-exact match** |
| **Case 6: Cooldown Active** | Either assembly mutated within elapsed $50 < 200$ events ($T_c = 200$). | `False` (Rejected) | `False` (Rejected) | **100% Bit-exact match** |
| **Case 7: Capacity Exceeded** | Shared cell belongs to 12 other live assemblies post-merge ($M > 12$). | `False` (Rejected) | `False` (Rejected) | **100% Bit-exact match** |
| **Case 8: Keep-Guard Rejection** | Exclusive cells have degree $< 2$ within prospective union. | `False` (Rejected) | `False` (Rejected) | **100% Bit-exact match** |
| **Case 9: Exact Duplicate** | Identical 4 cells ($A = B$, $A \setminus B = \emptyset, B \setminus A = \emptyset$). | `False` (Pre-remediation defect) | `True` (Consolidated) | **Intended remediation** |

*Scientific Finding:* In all 8 non-identical cases, baseline and patched implementations exhibit **100% identical decisions, identical survivor/archived statuses, identical structural generations, identical memberships, and identical reverse indexes**.

---

## 9. Full-State Determinism Evidence (C01-S07)

Two independent cold-start curriculum replays from zero over 56 roots produced the following SHA-256 cryptographic digests:

```
Partition           Run 1 Cryptographic SHA-256 Digest                Run 2 Cryptographic SHA-256 Digest                Match
-----------------------------------------------------------------------------------------------------------------------------
WState              c1656afee411ac884fd968002d7c33907a9b9e2ecf0a4190  c1656afee411ac884fd968002d7c33907a9b9e2ecf0a4190  EXACT
                    16d8a972b8baed5f                                  16d8a972b8baed5f                                 
HSlowState          dec7645bc296a014d1cd0c732fce1892204a6a359b79cafb  dec7645bc296a014d1cd0c732fce1892204a6a359b79cafb  EXACT
                    c19ebe592a6ab8e6                                  c19ebe592a6ab8e6                                 
RState              770958e65c3db0b105dc18aaadc8aacc5d49b2c6e57ff522  770958e65c3db0b105dc18aaadc8aacc5d49b2c6e57ff522  EXACT
                    58755cd522fffa56                                  58755cd522fffa56                                 
Ledger              10664c78e5c2b836196fda4f4b3c98fe91a785412d7f2f2f  10664c78e5c2b836196fda4f4b3c98fe91a785412d7f2f2f  EXACT
                    c6f9f66b17ec8c74                                  c6f9f66b17ec8c74                                 
Publication High WM 56                                                56                                                EXACT
Pending Outbox Roots0                                                 0                                                 EXACT
Processed Outbox Key352                                               352                                               EXACT
```

*Scientific Finding:* The complete runtime state across all five subsystems is **100% bit-exact deterministic**.

---

## 10. Legacy Regression-Delta Matrix (C01-S06)

| Test & Location | Pre-Remediation Baseline Assertion | Post-Remediation Observed Value | Categorization | Scientific & Structural Explanation |
| :--- | :--- | :--- | :--- | :--- |
| `test_f01_cold_start_and_persistence.py:210` | `assert set(eos_asms) == {2, 5, 6}` | `set(eos_asms) == {2, 5}` | **Lawfully Changed Expected Output** | Assembly 6 is lawfully archived into Assembly 5 at Root 9. Only Assemblies 2 and 5 are live canonical `<EOS>` assemblies. |
| `test_f01_cold_start_and_persistence.py:232` | `assert gen_eagle.stop_status == StatusCode.GEN_STOP_AMBIGUOUS` | `gen_eagle.stop_status == StatusCode.GEN_STOP_EOS` | **Newly Measured Improvement** | The duplicate readout collision between Assemblies 5 and 6 is eliminated. Rollout terminates successfully at `<EOS>`. |
| `test_f01_cold_start_and_persistence.py:238` | `assert gen_eagle_drink.stop_status == StatusCode.GEN_STOP_AMBIGUOUS` | `gen_eagle_drink.stop_status == StatusCode.GEN_STOP_EOS` | **Newly Measured Improvement** | 2-event prompt rollout also terminates successfully at `<EOS>` instead of colliding. |
| `test_r2_a01_patch2_acceptance.py:1201` | `assert len(ledger._processed_outbox_keys) == 398` | `len(ledger._processed_outbox_keys) == 352` | **Lawfully Changed Expected Output** | Archived Assembly 6 ceased outbox emissions across Roots 10–56, eliminating exactly 46 redundant notifications ($398 - 46 = 352$). |
| `test_r2_a01_patch2_acceptance.py:1258` | `assert gen_eagle.stop_status == StatusCode.GEN_STOP_AMBIGUOUS` | `gen_eagle.stop_status == StatusCode.GEN_STOP_EOS` | **Newly Measured Improvement** | Same duplicate collision resolution on the acceptance curriculum test. |
| All other 190 tests | 190 existing tests pass | 190 existing tests pass | **Preserved Invariant** | Full backward compatibility and zero unexpected drift across all prior features. |
| Any unexpected drift | None | None | **Zero Genuine Regressions** | No unplanned behavioral regressions discovered. |

---

## 11. Proposed Legacy Test Rebaseline (Review Only — Not Applied)

Per directive, legacy tests have **not** been modified on the implementation branch. Below is the precise proposed patch for formal release governance review:

```diff
diff --git a/tests/forensics/test_f01_cold_start_and_persistence.py b/tests/forensics/test_f01_cold_start_and_persistence.py
index 45a6c11..b83e91a 100644
--- a/tests/forensics/test_f01_cold_start_and_persistence.py
+++ b/tests/forensics/test_f01_cold_start_and_persistence.py
@@ -175,2 +175,2 @@
-    - Prompt ['النسر'] -> ('يشرب', 'ماء') -> GEN_STOP_AMBIGUOUS (blocked by duplicate Asm 5 & 6 collision).
-    - Prompt ['النسر', 'يشرب'] -> ('ماء',) -> GEN_STOP_AMBIGUOUS (same duplicate collision).
+    - Prompt ['النسر'] -> ('يشرب', 'ماء') -> GEN_STOP_EOS (resolved via consolidated Asm 5).
+    - Prompt ['النسر', 'يشرب'] -> ('ماء',) -> GEN_STOP_EOS (resolved via consolidated Asm 5).
@@ -210,1 +210,1 @@
-    assert set(eos_asms) == {2, 5, 6}
+    assert set(eos_asms) == {2, 5}
@@ -232,1 +232,1 @@
-    assert gen_eagle.stop_status == StatusCode.GEN_STOP_AMBIGUOUS
+    assert gen_eagle.stop_status == StatusCode.GEN_STOP_EOS
@@ -238,1 +238,1 @@
-    assert gen_eagle_drink.stop_status == StatusCode.GEN_STOP_AMBIGUOUS
+    assert gen_eagle_drink.stop_status == StatusCode.GEN_STOP_EOS

diff --git a/tests/test_r2_a01_patch2_acceptance.py b/tests/test_r2_a01_patch2_acceptance.py
index 682be81..758bce4 100644
--- a/tests/test_r2_a01_patch2_acceptance.py
+++ b/tests/test_r2_a01_patch2_acceptance.py
@@ -1201,1 +1201,1 @@
-    assert len(ledger._processed_outbox_keys) == 398, "Ledger must have consumed genuine outbox notifications!"
+    assert len(ledger._processed_outbox_keys) == 352, "Ledger must have consumed genuine outbox notifications!"
@@ -1258,1 +1258,1 @@
-    assert gen_eagle.stop_status == StatusCode.GEN_STOP_AMBIGUOUS, f"Expected GEN_STOP_AMBIGUOUS, got: {gen_eagle.stop_status}"
+    assert gen_eagle.stop_status == StatusCode.GEN_STOP_EOS, f"Expected GEN_STOP_EOS, got: {gen_eagle.stop_status}"
```

---

## 12. Remaining Limitations

1. **Conservative Subset Rejection ($A \subset B$):**
   - Asymmetric pairs where one assembly is a proper subset of another continue to evaluate to `between_strength = 0.0 < 0.40` under Branch 4b. This conservative behavior intentionally prevents smaller assemblies from premature absorption.
2. **Post-Merge Re-Attestation Latency:**
   - Any structurally mutated assembly enters a temporary un-attested window until $\ge 2$ subsequent completed exposures re-confirm its peripheral readout envelope. Autonomous generation during this window halts safely via `READOUT_UNKNOWN` (safe fail-closed behavior).

---

## 13. Final Acceptance Gate Verdicts

- **Gate A — Structural Consolidation:** **VERIFIED** (Exact duplicate consolidation at Root 9, survivor generation increment, archival, reverse index update, transaction containment at `FP_01`, `FP_02`, `FP_03`).
- **Gate B — Learning-Law Preservation:** **VERIFIED** (100% bit-exact equivalence between frozen baseline and patched implementation across all 8 non-identical merge scenarios).
- **Gate C — Attestation and Transaction Integrity:** **VERIFIED** (Assembly 5 accumulates 46 genuine external confirmations starting at Root 11; zero evidence leakage from archived Assembly 6; 100% immutable read-only execution).
- **Gate D — Autonomous Generation:** **VERIFIED** (Cat rollouts generate `('يشرب', 'حليب')` $\to$ `GEN_STOP_EOS`; Eagle rollouts generate `('يشرب', 'ماء')` $\to$ `GEN_STOP_EOS` with margin $0.11335 \ge 0.04$).

---

## 14. Final Recommendation & Sign-Off

```
========================================================================================
R2-B03-C01 SCIENTIFIC GATES VERIFIED — LEGACY REBASELINE REVIEW PENDING
========================================================================================
All 4 primary scientific gates (Gates A, B, C, D) are verified through executable automated tests.
The 23 acceptance tests pass with 100% success.
The exactly two legacy failing tests are conclusively documented as obsolete assertions
of the pre-remediation defect. A precise proposed rebaseline is submitted for governance approval.
========================================================================================
```
