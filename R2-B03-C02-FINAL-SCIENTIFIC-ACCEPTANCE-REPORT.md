# DGCA NEXT V2 — R2-B03-C02 Final Scientific Acceptance, Legacy Oracle Rebaseline & Regression Closeout Report

**Document Identifier:** `DGCA-R2-B03-C02-FINAL-SCIENTIFIC-ACCEPTANCE-REPORT-20261031`  
**Role:** Principal Scientific Verification Engineer, Deterministic Runtime Auditor, and Release Governance Engineer  
**Status:** SCIENTIFIC ACCEPTANCE COMPLETE — READY FOR FINAL PROMOTION REVIEW  
**Date:** 2026-10-31  

---

## 1. Authoritative Baselines & Starting Git Provenance (C02-S01)

- **Repository:** `naoufelbvb2-arch/DGCA-NEXT-V2`
- **Implementation Branch:** `experiment/r2-b03-exact-duplicate-merge`
- **Verified Starting HEAD SHA:** [`0456861b17a9b6cbc6076765544dfcf2f9673a49`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2) (verified via `git rev-parse HEAD`)
- **Frozen Production Baseline SHA:** [`faf361b6b95de6287b466eb1dc524ea49c732635`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2) (`origin/main`)
- **R2-B03 Implementation Baseline SHA:** [`49d9abbbb7de3b2979e9336fcee7bf25e0c58390`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2)
- **Corrected Design Documentation SHA:** [`9b1c31acf508d32a1738dfcc987e1082529332e9`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2)
- **Accepted Scientific Forensic Baseline SHA:** [`205efa0e664dc26f31f131d5efc19ac37b3eb95d`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2)
- **Frozen Design Identifier:** `DGCA-R2-B02-DESIGN-FROZEN-20261030`
- **Final Actual Git SHA:** Recorded post-commit and post-push via `git rev-parse HEAD` per C02-S01 directive (no circular pre-computation).

---

## 2. Production Source Integrity & Strict Non-Interference

- **Production Diff vs R2-B03-C01:** **ZERO** (`git diff HEAD -- src/` yields empty output).
- **Production Code Status:** Frozen and completely untouched under this verification assignment.
- **Approved Implementation Invariant:** The production code remains strictly at the 16-line patch in [`src/dgca/core/assembly.py::_try_merge_pair()`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/core/assembly.py#L537-L557) introduced in commit `49d9abbbb7de3b2979e9336fcee7bf25e0c58390`.
- **Zero Promotion Invariant:** The branch `experiment/r2-b03-exact-duplicate-merge` has NOT been merged into `main`.
- **Subsystem Non-Interference:** Zero modifications to Ledger, Outbox, Transaction Manager, or Generator production modules.

---

## 3. Exact Changed Files Inventory

The following files on branch `experiment/r2-b03-exact-duplicate-merge` constitute the complete change footprint:

| File Path | Scope | Action |
| :--- | :--- | :--- |
| [`tests/forensics/test_f01_cold_start_and_persistence.py`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/tests/forensics/test_f01_cold_start_and_persistence.py) | Verification / Legacy Test | Authorized rebaseline of 3 obsolete assertions & docstring |
| [`tests/test_r2_a01_patch2_acceptance.py`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/tests/test_r2_a01_patch2_acceptance.py) | Verification / Legacy Test | Authorized rebaseline of 2 obsolete assertions |
| [`tests/test_r2_b03_c01_acceptance.py`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/tests/test_r2_b03_c01_acceptance.py) | Verification / Acceptance Suite | Enhanced C02 verification tests (non-empty FP_03 outbox, PublicationView snapshot, source-pinned differential) |
| [`R2-B03-C02-FINAL-SCIENTIFIC-ACCEPTANCE-REPORT.md`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/R2-B03-C02-FINAL-SCIENTIFIC-ACCEPTANCE-REPORT.md) | Release Deliverable | Final scientific acceptance and regression closeout report |

---

## 4. Authorized Legacy Assertion Rebaseline (C02-S06)

Per directive C02-S06, exactly five obsolete assertions encoding the pre-remediation defect were rebaselined on the `experiment/r2-b03-exact-duplicate-merge` branch. Baseline files on frozen `main` remain completely unchanged.

### Legacy Test File 1: `tests/forensics/test_f01_cold_start_and_persistence.py`

```diff
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
```

*Scientific Justifications:*
1. **Line 210 (`set(eos_asms) == {2, 5}`):** At Root 9, Assembly 6 merged lawfully into Assembly 5 and was archived (`status = ARCHIVED`). Only Assemblies 2 and 5 remain `LIVE` canonical EOS assemblies.
2. **Lines 232 & 238 (`gen_eagle.stop_status == StatusCode.GEN_STOP_EOS`):** Archival of duplicate Assembly 6 eliminates the readout score tie ($0.206944$ vs $0.206944$). Assembly 5 wins alone with neural margin $0.11335 \ge M_{\text{read}} = 0.04$, successfully generating `<EOS>` for both 1-event (`['النسر']`) and 2-event (`['النسر', 'يشرب']`) prompts.

### Legacy Test File 2: `tests/test_r2_a01_patch2_acceptance.py`

```diff
@@ -1201,1 +1201,1 @@
-    assert len(ledger._processed_outbox_keys) == 398, "Ledger must have consumed genuine outbox notifications!"
+    assert len(ledger._processed_outbox_keys) == 352, "Ledger must have consumed genuine outbox notifications!"
@@ -1258,1 +1258,1 @@
-    assert gen_eagle.stop_status == StatusCode.GEN_STOP_AMBIGUOUS, f"Expected GEN_STOP_AMBIGUOUS, got: {gen_eagle.stop_status}"
+    assert gen_eagle.stop_status == StatusCode.GEN_STOP_EOS, f"Expected GEN_STOP_EOS, got: {gen_eagle.stop_status}"
```

*Scientific Justifications:*
1. **Line 1201 (`len(ledger._processed_outbox_keys) == 352`):** Archived Assembly 6 generates zero outbox notifications across Roots 10 through 56. Exactly 46 redundant notifications from duplicate Assembly 6 are eliminated ($398 - 46 = 352$).
2. **Line 1258 (`gen_eagle.stop_status == StatusCode.GEN_STOP_EOS`):** Resolves the Eagle prompt duplicate collision on the acceptance curriculum, terminating cleanly at `<EOS>`.

*Preserved Invariants:* All original assertions for WState immutability, HSlowState immutability, Caller RState immutability, Ledger immutability, Outbox idempotency, SHA-256 state digests, and read-only retrieval remain 100% active and unweakened.

---

## 5. Non-Empty FP_03 Outbox Delivery Evidence (C02-S02)

In [`tests/test_r2_b03_c01_acceptance.py::test_c02_s02_non_empty_fp03_outbox_delivery`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/tests/test_r2_b03_c01_acceptance.py), the vacuous Root 1 cold-start test was replaced with a genuine Root 11 scenario (post-Root 10 where Assembly 5 is pre-existing `LIVE` at Generation 8):

1. **Pre-Exposure Live Assembly:** Prior to Root 11, Assembly 5 was `LIVE` at Generation 8 with members `(8834, 9209, 10570, 12117)`.
2. **Fault Injection at `FP_03`:** Injected `RuntimeError("Injected fault at FP-03: post-commit peripheral dispatch failure")` immediately following `self.state.W = new_view.W` at line 1115 of `exposure_tx.py`.
3. **Atomic Commit Durability:** Commit succeeded, high watermark advanced: `state.completed_roots_high_watermark == 11`.
4. **Non-Empty Pending Outbox Batch:** Exactly 5 genuine notifications were staged in `tx._publication_view.pending_outbox_by_root[11]`.
5. **No Premature Ledger Ingestion:** Ledger contained 0 candidate rows prior to reconciliation (`len(ledger._rows_by_asm_gen) == 0`).
6. **Reconciliation Dispatch:** `reconcile_outbox(ledger)` was executed: exactly 5 notifications were delivered to the ledger.
7. **Pending Queue Cleared:** `11 not in tx._publication_view.pending_outbox_by_root`.
8. **Idempotency:** A second consecutive call to `reconcile_outbox(ledger)` returned `0` delivered notifications.
9. **No Duplicate Confirmations:** Exactly 1 candidate row was registered for `(5, 8)` with `confirmed_roots == {11}`.
10. **WState Immutability:** Deep dictionary snapshot of `WState` before and after `reconcile_outbox()` was 100% bit-exact identical.

---

## 6. Complete Transaction Publication Determinism Evidence (C02-S03)

Full-state determinism was extended to cover `TransactionPublicationView` using `snapshot_publication_view()`, capturing:
- Canonical `w_snapshot` via deep dictionary serialization.
- Complete stored fields of all 56 completed root reports in `completed_roots`: `exposure_id`, `root_seed`, `commit_status`, `events_count`, `structural_mutations_count`, `synapses_allocated_count`, `active_cell_counts`, `top_assemblies`, `checksum`.
- Full `pending_outbox_by_root` mapping.
- `completed_roots_high_watermark`.
- `active_exposure_id`.

Two independent 56-root cold-start curriculum replays produced the following SHA-256 cryptographic digests:

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
PublicationView     fc09e81e8ec8c5150274e689ccf76d254c58315d038463c7  fc09e81e8ec8c5150274e689ccf76d254c58315d038463c7  EXACT
                    d60079a43a6b30f9                                  d60079a43a6b30f9                                 
Publication High WM 56                                                56                                                EXACT
Pending Outbox Roots0                                                 0                                                 EXACT
Processed Outbox Key352                                               352                                               EXACT
```

*Scientific Finding:* The complete runtime state across all five subsystems, including full transaction publication history, is **100% bit-exact deterministic**.

---

## 7. Complete Read-Only Invariance Results (C02-S04)

Deep state snapshots were taken before and after executing Cat rollout, Eagle rollout, and `run_read_only_episode()`:

| Partition | Pre-Cat Digest | Post-Cat Digest | Post-Eagle Digest | Post-RETRIEVE Digest | Equivalence |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **WState** | `c1656afee411...` | `c1656afee411...` | `c1656afee411...` | `c1656afee411...` | **Bit-exact (100%)** |
| **HSlowState** | `dec7645bc296...` | `dec7645bc296...` | `dec7645bc296...` | `dec7645bc296...` | **Bit-exact (100%)** |
| **Caller RState**| `770958e65c3d...` | `770958e65c3d...` | `770958e65c3d...` | `770958e65c3d...` | **Bit-exact (100%)** |
| **Ledger** | `10664c78e5c2...` | `10664c78e5c2...` | `10664c78e5c2...` | `10664c78e5c2...` | **Bit-exact (100%)** |
| **PublicationView**| `fc09e81e8ec8...` | `fc09e81e8ec8...` | `fc09e81e8ec8...` | `fc09e81e8ec8...` | **Bit-exact (100%)** |
| **Outbox Keys** | 352 keys | 352 keys | 352 keys | 352 keys | **Bit-exact (100%)** |

*Scientific Finding:* Autonomous generation and read-only retrieval do not mutate WState, homeostatic state, caller state, peripheral ledger, or publication history.

---

## 8. Source-Pinned Non-Identical MERGE Differential Results (C02-S05)

The differential verification harness dynamically extracts and compiles `_try_merge_pair()` directly from git commit `faf361b6b95de6287b466eb1dc524ea49c732635:src/dgca/core/assembly.py` via `git show`.

All eight non-identical scenarios were evaluated across:
- Return value (`merge_occurred`)
- Survivor and archived statuses
- Structural generations
- Membership tuples
- Reverse membership indexes
- Mutation clocks
- Merge/split cooldown clocks
- Complete canonical `snapshot_w` deep dictionaries and SHA-256 state digests

| Scenario | Structural Configuration | Frozen Baseline (`faf361b`) | Patched Implementation | Full-State Parity |
| :--- | :--- | :--- | :--- | :--- |
| **Case 1: Eligible Partial-Overlap** | 8 shared cells, 1 exclusive cell each, mutual LOCAL link ($S=0.85$). $J = 0.80 \ge 0.70$. | `True` (Merged) | `True` (Merged) | **100% Bit-exact match** |
| **Case 2: Weak Exclusive Support** | Same as Case 1, but mutual link has $S=0.20 < 0.60$. | `False` (Rejected) | `False` (Rejected) | **100% Bit-exact match** |
| **Case 3: Proper Subset** | $A \subset B$ ($|A|=4, |B|=5$, $J = 0.80$). Exclusive set $A \setminus B = \emptyset$. | `False` (Rejected) | `False` (Rejected) | **100% Bit-exact match** |
| **Case 4: Proper Superset** | $B \subset A$ ($|A|=5, |B|=4$, $J = 0.80$). Exclusive set $B \setminus A = \emptyset$. | `False` (Rejected) | `False` (Rejected) | **100% Bit-exact match** |
| **Case 5: Below-Threshold Jaccard**| Overlap yields $J = 1/7 = 0.1428 < 0.70$. | `False` (Rejected) | `False` (Rejected) | **100% Bit-exact match** |
| **Case 6: Cooldown Active** | Either assembly mutated within elapsed $50 < 200$ events ($T_c = 200$). | `False` (Rejected) | `False` (Rejected) | **100% Bit-exact match** |
| **Case 7: Capacity Exceeded** | Shared cell belongs to 12 other live assemblies post-merge ($M > 12$). | `False` (Rejected) | `False` (Rejected) | **100% Bit-exact match** |
| **Case 8: Keep-Guard Rejection** | Exclusive cells have degree $< 2$ within prospective union. | `False` (Rejected) | `False` (Rejected) | **100% Bit-exact match** |
| **Case 9: Exact Duplicate** | Identical 4 cells ($A = B$, $A \setminus B = \emptyset, B \setminus A = \emptyset$). | `False` (Pre-remediation defect) | `True` (Consolidated) | **Intended remediation** |

*Scientific Finding:* Non-identical MERGE behavior is 100% bit-exact identical to the frozen baseline across every single state attribute and deep state snapshot. Case 9 is the sole intentional behavioral divergence.

---

## 9. Genuine Eagle EOS Generation Measurements (C01-S01)

On a cold-start `MachineState` trained over the complete 56-root curriculum:

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

*Scientific Finding:* The duplicate readout-score collision is completely eliminated. Assembly 5 wins alone with margin $0.11335$ (nearly $3\times M_{\text{read}} = 0.04$).

---

## 10. Genuine 46-Root Post-Merge Attestation Evidence (C01-S02)

Inspection of the actual trained `SurfaceReadoutLedgerV1`:
- **Assembly 5 Final Structural Generation:** Generation 8.
- **Candidate Rows for Key `(5, 8)`:** Exactly 1 candidate row.
- **Confirmed Roots Population:** Exactly 46 distinct completed external roots:
  $$\text{Confirmed Roots} = \{11, 12, 13, 14, 15, \dots, 55, 56\}$$
- **First Qualifying External Root:** Root 11.
- **Second Qualifying External Root:** Root 12 ($K_{\text{attest}} \ge 2$ satisfied).
- **Stale Generation & Archival Isolation:**
  - `get_candidate_rows(5, 1) == []`
  - `get_candidate_rows(5, 7) == []`
  - `get_candidate_rows(6, g) == []` for all generations $g$.
  - `resolve_readout(5, 1, current_live_generation=8).status == StatusCode.GEN_STOP_STALE_ASSEMBLY`.

---

## 11. Full Regression Suite Execution & Measured Test Counts (C02-S07)

### Execution Command
```powershell
python -m pytest tests/ -v
```

### Measured Test Inventory & Results
- **Pre-existing Legacy Suite:** **192 passed**
- **R2-B03 Initial Acceptance Suite (`test_r2_b03_exact_duplicate_merge.py`):** **16 passed**
- **R2-B03-C01/C02 Scientific Acceptance Suite (`test_r2_b03_c01_acceptance.py`):** **7 passed**
- **Total Suite Execution:** **215 passed, 0 failed, 0 skipped, 0 xfailed** in 249.58s.
- Both rebaselined legacy tests (`test_f01_task6_canonical_eos_learning_and_multistep_rollout` and `test_non_empty_ledger_genuine_56_root_curriculum_immutability`) pass with 100% success.

---

## 12. Remaining Scientific Limitations

1. **Conservative Proper Subset Rejection ($A \subset B$):**
   - Asymmetric pairs where one assembly is a proper subset of another continue to evaluate to `between_strength = 0.0 < 0.40` under Branch 4b. This conservative behavior intentionally prevents smaller assemblies from premature absorption.
2. **Post-Merge Re-Attestation Latency:**
   - Any structurally mutated assembly enters a temporary un-attested window until $\ge 2$ subsequent completed exposures re-confirm its peripheral readout envelope. Autonomous generation during this window halts safely via `READOUT_UNKNOWN` (fail-closed behavior).

---

## 13. Acceptance Gate-by-Gate Evaluation

- **Gate A — Structural Consolidation:** **VERIFIED**
  - Exact duplicate consolidation at Root 9.
  - Survivor generation increment, archival of duplicate, reverse index updates.
  - Transaction rollback containment at `FP_01`, `FP_02`, and non-empty `FP_03`.
- **Gate B — Learning-Law Preservation:** **VERIFIED**
  - 100% bit-exact equivalence between frozen baseline and patched implementation across all 8 non-identical merge scenarios.
- **Gate C — Attestation and Transaction Integrity:** **VERIFIED**
  - Assembly 5 accumulates 46 genuine external confirmations starting at Root 11.
  - Zero evidence leakage from archived Assembly 6.
  - 100% immutable read-only execution across W, H_slow, R, Ledger, and PublicationView.
- **Gate D — Autonomous Generation:** **VERIFIED**
  - Cat rollouts generate `('يشرب', 'حليب')` $\to$ `GEN_STOP_EOS`.
  - Eagle rollouts generate `('يشرب', 'ماء')` $\to$ `GEN_STOP_EOS` with margin $0.11335 \ge 0.04$.

---

## 14. Final Recommendation & Sign-Off

```
========================================================================================
R2-B03 SCIENTIFIC ACCEPTANCE COMPLETE — READY FOR FINAL PROMOTION REVIEW
========================================================================================
All 4 primary scientific gates (Gates A, B, C, D) are verified through automated evidence.
The complete regression suite of 215 tests passes with 100% success.
Zero lines of production code were altered.
The exact-duplicate assembly consolidation patch is scientifically validated and closed.
========================================================================================
```
