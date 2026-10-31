# DGCA NEXT V2 — R2-B07 MAIN PROMOTION & RELEASE FREEZE ATTESTATION REPORT

**Document Identifier:** `DGCA-R2-B07-MAIN-PROMOTION-AND-RELEASE-FREEZE-REPORT`  
**Date:** 2026-10-31  
**Status:** PROMOTION COMPLETED / RELEASE FROZEN  
**Author:** Principal Release Engineer, Scientific Governance Auditor, and Production Integration Verification Lead  
**Classification:** Authoritative Release Promotion & Governance Attestation  

---

## 1. Authoritative Promotion Baselines & Merge Topology

In accordance with explicit release authority authorization, the scientifically accepted **Exact-Duplicate Assembly Consolidation** amendment has been formally merged and promoted into the authoritative production branch `main`.

| Release Entity | Authoritative Commit Reference | Classification / Description |
| :--- | :--- | :--- |
| **Pre-Promotion Frozen `main`** | `faf361b6b95de6287b466eb1dc524ea49c732635` | Baseline production root (R2-A01) |
| **Authorized Release Candidate** | `613d5cb86deef6bf2b5c1be9da496c598ecd39a2` | Validated candidate branch (`experiment/r2-b03-exact-duplicate-merge`) |
| **Actual Merge Commit SHA** | `a22dcd85c272e912b29fb09b0cd48acc7fe26d34` | Production promotion merge commit |
| **Merge Parent 1 (Target `main`)** | `faf361b6b95de6287b466eb1dc524ea49c732635` | Authoritative pre-merge `main` |
| **Merge Parent 2 (Release Branch)** | `613d5cb86deef6bf2b5c1be9da496c598ecd39a2` | Complete R2-B forensic and implementation chain |
| **Merge Strategy** | `git merge --no-ff` | Preserves non-linear commit history and full audit provenance |

---

## 2. Complete 15-File Promotion Manifest

The staged and committed merge introduces exactly 15 files relative to `faf361b6b95de6287b466eb1dc524ea49c732635`:

```text
git diff --numstat faf361b6b95de6287b466eb1dc524ea49c732635 a22dcd85c272e912b29fb09b0cd48acc7fe26d34
125	0	DGCA_CORE_AMENDMENT_R2_B02_EXACT_DUPLICATE_MERGE.md
273	0	R2-B03-C01-SCIENTIFIC-ACCEPTANCE-EVIDENCE-REPORT.md
290	0	R2-B03-C02-FINAL-SCIENTIFIC-ACCEPTANCE-REPORT.md
277	0	R2-B03-CONTROLLED-IMPLEMENTATION-VERIFICATION-REPORT.md
232	0	R2-B04-FINAL-PROMOTION-READINESS-REPORT.md
248	0	R2-B05-C01-FINAL-NORMATIVE-INTEGRITY-ATTESTATION.md
172	0	R2-B05-C02-FINAL-RELEASE-GOVERNANCE-CLOSURE.md
309	0	R2-B05-NORMATIVE-PROMOTION-PREPARATION-REPORT.md
16	10	src/dgca/core/assembly.py
1	0	tests/fixtures/__init__.py
179	0	tests/fixtures/frozen_baseline_assembly.py
7	7	tests/forensics/test_f01_cold_start_and_persistence.py
2	2	tests/test_r2_a01_patch2_acceptance.py
1046	0	tests/test_r2_b03_c01_acceptance.py
645	0	tests/test_r2_b03_exact_duplicate_merge.py
```

### Categorical Classification:
1. **Production Code (1 file):**
   - [`src/dgca/core/assembly.py`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/core/assembly.py): `16  10` (+16 additions, -10 deletions; net +6 lines).
2. **Test Fixtures (2 files):**
   - [`tests/fixtures/__init__.py`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/tests/fixtures/__init__.py): `1  0`
   - [`tests/fixtures/frozen_baseline_assembly.py`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/tests/fixtures/frozen_baseline_assembly.py): `179  0` (pinned AST hash: `e9cb637e0e1675059f1ae682cdc9be455d1f754bb0e8e1f83f72c6f3406ee8d7`)
3. **Rebaselined Legacy Tests (2 files):**
   - [`tests/forensics/test_f01_cold_start_and_persistence.py`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/tests/forensics/test_f01_cold_start_and_persistence.py): `7  7` (canonical EOS Asm {2, 5}, Eagle EOS)
   - [`tests/test_r2_a01_patch2_acceptance.py`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/tests/test_r2_a01_patch2_acceptance.py): `2  2` (outbox count 352, Eagle EOS)
4. **New Acceptance Suites (2 files):**
   - [`tests/test_r2_b03_exact_duplicate_merge.py`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/tests/test_r2_b03_exact_duplicate_merge.py): `645  0` (16 unit tests for merge invariants)
   - [`tests/test_r2_b03_c01_acceptance.py`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/tests/test_r2_b03_c01_acceptance.py): `1046  0` (7 scientific acceptance tests)
5. **Normative Amendment (1 file):**
   - [`DGCA_CORE_AMENDMENT_R2_B02_EXACT_DUPLICATE_MERGE.md`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/DGCA_CORE_AMENDMENT_R2_B02_EXACT_DUPLICATE_MERGE.md): `125  0` (formal specification for MERGE Rule 4)
6. **Governance & Audit Reports (7 files):**
   - `R2-B03-CONTROLLED-IMPLEMENTATION-VERIFICATION-REPORT.md` (`277  0`)
   - `R2-B03-C01-SCIENTIFIC-ACCEPTANCE-EVIDENCE-REPORT.md` (`273  0`)
   - `R2-B03-C02-FINAL-SCIENTIFIC-ACCEPTANCE-REPORT.md` (`290  0`)
   - `R2-B04-FINAL-PROMOTION-READINESS-REPORT.md` (`232  0`)
   - [`R2-B05-NORMATIVE-PROMOTION-PREPARATION-REPORT.md`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/R2-B05-NORMATIVE-PROMOTION-PREPARATION-REPORT.md) (`309  0`)
   - [`R2-B05-C01-FINAL-NORMATIVE-INTEGRITY-ATTESTATION.md`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/R2-B05-C01-FINAL-NORMATIVE-INTEGRITY-ATTESTATION.md) (`248  0`)
   - [`R2-B05-C02-FINAL-RELEASE-GOVERNANCE-CLOSURE.md`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/R2-B05-C02-FINAL-RELEASE-GOVERNANCE-CLOSURE.md) (`172  0`)

---

## 3. Exact Production Code Diff

The production code change is strictly confined to [`src/dgca/core/assembly.py::_try_merge_pair()`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/core/assembly.py#L537-L560):

```diff
diff --git a/src/dgca/core/assembly.py b/src/dgca/core/assembly.py
index ed0a0e4..787963b 100644
--- a/src/dgca/core/assembly.py
+++ b/src/dgca/core/assembly.py
@@ -537,17 +537,23 @@ def _try_merge_pair(
 
     excl_a = sorted(set_a - set_b)
     excl_b = sorted(set_b - set_a)
-    if not excl_a or not excl_b:
-        between_strength = 0.0
+    if not excl_a and not excl_b:
+        # Branch 4a: Exact Structural Duplicate consolidation (Core §2.0 Operator 4)
+        between_strength_passed = True
     else:
-        cross_vals = [
-            compute_mutual_support_r_b(i, j, w)
-            for i in excl_a
-            for j in excl_b
-        ]
-        between_strength = sum(cross_vals) / float(len(cross_vals))
-
-    if between_strength < THETA_OB:
+        # Branch 4b: Partial Overlap cross-support evaluation
+        if not excl_a or not excl_b:
+            between_strength = 0.0
+        else:
+            cross_vals = [
+                compute_mutual_support_r_b(i, j, w)
+                for i in excl_a
+                for j in excl_b
+            ]
+            between_strength = sum(cross_vals) / float(len(cross_vals))
+        between_strength_passed = (between_strength >= THETA_OB)
+
+    if not between_strength_passed:
         return False
 
     union_tuple = tuple(sorted(union_set))
```

---

## 4. Accepted Normative Amendment Identity

- **Document Identifier:** `DGCA-CORE-AMENDMENT-R2-B02-20261031`
- **File Path:** [`DGCA_CORE_AMENDMENT_R2_B02_EXACT_DUPLICATE_MERGE.md`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/DGCA_CORE_AMENDMENT_R2_B02_EXACT_DUPLICATE_MERGE.md)
- **Target Specification:** `DGCA_CORE_RC4_1.md` §2.0 Operator 4 (`MERGE`).
- **Core Rule Amendment:** Formally supersedes the mutual-support evaluation sentence of Rule 4 by establishing:
  - **Branch 4a:** Exact Structural Duplicate pairs ($E_A = \emptyset \land E_B = \emptyset$) satisfy the exclusive mutual-support gate (`between_strength_passed = True`).
  - **Branch 4b:** Partial Overlap pairs evaluate mean reciprocal support across exclusive sets (`compute_mutual_support_r_b`) against $\Theta_{\text{ob}} = 0.40$; proper subsets/supersets fail closed (`between_strength = 0.0`).
- **Invariance Guarantee:** "Exact structural equality satisfies only the exclusive mutual-support gate, not complete merge eligibility." All surrounding gates (cooldown $T_c=200$, Jaccard $\ge 0.70$, union size $\le 16$, membership cap $\le 12$, keep guards, lower-ID survivor, generation increment) remain fully active.

---

## 5. Regression Verification Evidence

### Pre-Commit Regression (Gate P03):
- **Command:** `python -m pytest tests/ -q`
- **Timing:** 90.84s
- **Outcome:** `215 passed` (0 failures, 0 errors, 0 skips, 0 xfails).

### Post-Merge Regression (Gate P05):
- **Command:** `python -m pytest tests/ -q`
- **Timing:** 88.46s
- **Outcome:** `215 passed` (0 failures, 0 errors, 0 skips, 0 xfails).

---

## 6. Scientific Acceptance Findings & Verification Highlights

1. **Lawful Duplicate Consolidation:** Disjoint seeds that converge to identical cell sets consolidate into the lower-ID survivor with an archived higher ID and incremented generations ($g \to g+1$).
2. **Canonical Cat & Eagle Autonomous EOS Generation:** Autonomous rollout generates (`'القط'`, `'يشرب'`, `'حليب'`) $\to$ `<EOS>` and (`'النسر'`, `'يشرب'`, `'ماء'`) $\to$ `<EOS>` with `GEN_STOP_EOS`, completely eliminating the prior `GEN_STOP_AMBIGUOUS` collision.
3. **Genuine Post-Merge Attestation:** Survivor Assembly 5 re-accrues qualifying exposure attestation in the peripheral ledger across multiple generation steps, producing genuine readout envelopes without cross-generation contamination.
4. **Transaction Containment:** Pre-commit aborts (`FP_02`) cleanly discard shadow state changes while preserving lawful sensory commitments made during OPEN; post-commit peripheral faults (`FP_03`) defer outbox delivery to idempotent retry without rolling back durable state.
5. **Frozen Baseline Differential Parity:** Reference baseline fixture confirms 100% bitwise parity on non-duplicate cases while verifying divergence strictly on exact duplicates.

---

## 7. Known Scientific Limitations & Boundary Statement

In accordance with strict scientific release governance:
- **No Natural Language Generalization:** This amendment resolves duplicate assembly convergence within the controlled synthetic lexicon and curriculum; it does not constitute general natural-language understanding or open-ended reasoning.
- **Proper Subset Asymmetry:** Consolidation applies strictly to identical membership sets ($A \equiv B$). Proper subsets ($A \subset B$) produce one empty exclusive set and remain rejected under Rule 4.
- **Re-Attestation Latency:** Newly consolidated assemblies require $\ge 2$ subsequent exposures to establish peripheral readout resolution, temporarily emitting `READOUT_UNKNOWN` if queried immediately post-merge.

---

## 8. Rollback Procedure

If unexpected post-promotion regressions emerge in production:
```bash
git checkout main
git revert -m 1 --no-edit a22dcd85c272e912b29fb09b0cd48acc7fe26d34
```
- Restores the authoritative tree state of `main` to `faf361b6b95de6287b466eb1dc524ea49c732635`.
- Preserves complete immutable audit history in Git logs.
- Does not skip or mark tests as XFAIL.

---

## 9. Final Release Governance Decision

All release preflight and promotion gates have passed. Production `main` has been updated with the approved Release Candidate.

**`R2-B07 MAIN PROMOTION COMPLETE — RELEASE VERIFIED AND FROZEN`**
