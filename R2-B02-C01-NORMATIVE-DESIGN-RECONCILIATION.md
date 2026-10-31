# DGCA NEXT V2 — R2-B02-C01

## Formal Design Contract Normative Reconciliation Audit Report

| Parameter | Specification |
| :--- | :--- |
| **Document Version** | `1.1.0-normative-reconciled` |
| **Authoritative Baseline** | `faf361b6b95de6287b466eb1dc524ea49c732635` (`main`) |
| **Investigation Branch** | `investigation/r2-b01-assembly-forensics` |
| **Starting HEAD** | `2ea323f3afbf110028641dcd5349e61629ee9183` |
| **Accepted Forensic Baseline** | `205efa0e664dc26f31f131d5efc19ac37b3eb95d` (R2-B01 Closeout) |
| **Target Design Contract** | `R2-B02-EXACT-DUPLICATE-CONSOLIDATION-DESIGN-CONTRACT.md` |
| **Target Erratum Report** | `R2-B01-C04-FINAL-SNAPSHOT-COVERAGE-REPORT.md` |
| **Actual Remote Commit SHA** | `cb8f3cc9689d6afb813f8a6767e80d4faf7ca87d` |
| **Status** | **NORMATIVELY RECONCILED — AWAITING FINAL DESIGN FREEZE** |

---

## Executive Summary

Following formal review of the initial R2-B02 design contract (`2ea323f`), the Lead Engineer and Formal Specification Auditors approved Alternative A (Explicit Exact-Duplicate Structural Branch) in principle. However, material discrepancies between the design text and the frozen DGCA production implementation were identified across ledger attestation rules, generational timelines, transaction notification contracts, failure semantics, status code mappings, implementation touchpoints, and experimental gates.

Under task **R2-B02-C01**, a comprehensive normative audit and reconciliation was conducted. All ten directive sections (C01-S01 through C01-S10) have been fully resolved with zero changes to production source code (`src/dgca/`), test suites, runtime configurations, or scientific evidence digests.

The formal design contract [`R2-B02-EXACT-DUPLICATE-CONSOLIDATION-DESIGN-CONTRACT.md`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/R2-B02-EXACT-DUPLICATE-CONSOLIDATION-DESIGN-CONTRACT.md) has been updated to version `2.1.0-scientific-baseline-reconciled`. The final forensic documentation erratum in [`R2-B01-C04-FINAL-SNAPSHOT-COVERAGE-REPORT.md`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/R2-B01-C04-FINAL-SNAPSHOT-COVERAGE-REPORT.md#L48-L49) ($B_i = 64, B_i^x = 12$) has been corrected.

---

## Section-by-Section Normative Reconciliation

### 1. C01-S01 — Correct Attestation Requirements (`MIN_ATTESTED_EXTERNAL_ROOTS = 2`)
- **Normative Conflict:** The original design contract claimed that exactly one subsequent external exposure containing `<EOS>` was sufficient to re-attest the consolidated assembly.
- **Authoritative Rule:** Under `DGCA_CORE_RC4_1.md` §9.4, `src/dgca/peripheral/readout_ledger.py` (line 21), and `src/dgca/peripheral/outbox.py`:
  $$\text{MIN\_ATTESTED\_EXTERNAL\_ROOTS} = 2$$
  A single external exposure records `external_count = 1 < 2`, which leaves the candidate row in pending/unattested state (`is_attested = False`). Readout queries continue to fail closed.
- **Reconciliation Action:**
  All claims asserting single-exposure attestation were excised from Sections 2, 6, 7, 10, and 12 of the contract. The contract now specifies the ten mandatory normative attestation conditions:
  1. `len(confirmed_roots) >= 2` across distinct completed external roots (`root_id` distinct).
  2. Same `assembly_id`.
  3. Same `structural_generation`.
  4. Same canonical surface (`surface_utf8_nfc`) and feature bundle digest (`feature_bundle_digest`).
  5. Same marker, including `Marker.EOS` when applicable.
  6. No unresolved conflicting candidate row for `(surface, marker)` with differing bundle digest (`LG-T08`).
  7. Legal event-time coverage ($C_t \ge \rho_{\text{core}} = 0.70$) and freshness ($M_{\text{fresh}} \ge \Theta_{\text{fresh}}$).
  8. Assembly already `LIVE` before the witnessed event (no post-close witness claims).
  9. Unchanged generation across the entire root required for outbox notification.
  10. Zero retroactive attestation after structural mutation (`MERGE` or `GROW`).
- **Ledger Behavior:** Strictly preserved. Zero changes to `SurfaceReadoutLedgerV1`.

---

### 2. C01-S02 — Correct Structural Generation Timeline
- **Normative Conflict:** The original design claimed Assemblies 5 and 6 reached Gen 7 prior to consolidation at Root 9, and advanced to Gen 8 immediately upon MERGE via $\max(\text{gen}_A, \text{gen}_B) + 1$.
- **Authoritative Rule:** Inspection of the forensic replay and `src/dgca/core/assembly.py` establishes:
  - Root 8 (Eagle): Assemblies 5 and 6 born at Gen 1 during Event 3 (`Marker.EOS`) with seed sets `(8834, 9209, 10570)` and `(10646, 10915, 11153)`.
  - Root 9 (Cat) GROW: Adds 5 cells (`10646, 10915, 11153, 11583, 12116`) sequentially. Each cell addition increments `structural_generation` by 1:
    $$1 + 5 = 6$$
    Both assemblies reach Gen 6 (size 8): `(8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116)`.
  - Root 9 (Cat) MERGE: Under proposed consolidation, `_try_merge_pair()` increments both assemblies:
    $$\text{asm\_a.structural\_generation} += 1 \implies 6 + 1 = 7$$
    $$\text{asm\_b.structural\_generation} += 1 \implies 6 + 1 = 7 \quad (\text{ARCHIVED})$$
  - Root 10 (Eagle) GROW: Adds cell `12117` to survivor $A_5$:
    $$\text{asm\_a.structural\_generation} += 1 \implies 7 + 1 = 8 \quad (\text{size } 9)$$
  - First stable post-merge generation: **Gen 8** at Root 10.
- **Reconciliation Action:**
  The contract preserves the frozen production increment rule `survivor.structural_generation += 1` and rejects `max(gen_a, gen_b) + 1`. A complete counterfactual timeline table has been added to Section 6 of the contract, explicitly labeling counterfactual projections as **PREDICTED, NOT MEASURED**.

---

### 3. C01-S03 — Remove Unauthorized Outbox Extensions
- **Normative Conflict:** The original design invented an unauthorized notification contract (`AssemblyMutationNotification`), custom mutation codes (`MERGE_CONSOLIDATED_EXACT_DUPLICATE`), and referenced a nonexistent module `src/dgca/core/transaction.py`.
- **Authoritative Rule:** Production transactions are governed by `src/dgca/lifecycle/exposure_tx.py`. Assembly pass summaries use `AssemblyEndReport`, which already includes:
  ```python
  merged_pairs: tuple[tuple[int, int], ...] = ()
  ```
  Peripheral outbox notifications strictly use `OutboxNotificationV1`. There is no `AssemblyMutationNotification` schema in DGCA Core.
- **Reconciliation Action:**
  Excised all references to `AssemblyMutationNotification` and custom transaction codes. Consolidation reporting is strictly aligned with existing frozen interfaces: `AssemblyEndReport.merged_pairs = ((5, 6),)` and standard idempotent `OutboxNotificationV1` post-commit dispatch.

---

### 4. C01-S04 — Correct Transaction Failure Semantics
- **Normative Conflict:** The original design asserted that any validation failure during `MERGE` triggers a full transaction `ABORT` that discards all state changes and returns to pre-BEGIN state.
- **Authoritative Rule:**
  1. **Ordinary Ineligibility:** If a candidate pair fails any merge check, `_try_merge_pair()` returns `False`. The loop simply skips to the next pair in the active pass. The transaction does **not** abort.
  2. **Exceptional Pre-Publication Failure:** If an unhandled exception occurs in shadow execution, the transaction aborts. Under R2-A01, sensory states committed during `OPEN` are preserved; uncommitted shadow assembly mutations are discarded.
  3. **Post-Commit Outbox Delivery Failure:** Once `END_EXPOSURE` commits, neural state transitions are permanent and never rolled back. Pending outbox notifications are retained for idempotent reconciliation.
- **Reconciliation Action:**
  Section 8 of the design contract now explicitly differentiates these three operational boundaries.

---

### 5. C01-S05 — Correct Readout Failure Codes
- **Normative Conflict:** The original design introduced a nonexistent status code `StatusCode.UNATTESTED_READOUT` and labeled the Root 56 neural collision as `StatusCode.READOUT_AMBIGUOUS`.
- **Authoritative Rule:** In `src/dgca/common/errors.py`, `src/dgca/peripheral/readout_ledger.py`, and `src/dgca/core/generator.py`:
  - The Root 56 duplicate collision occurs during **neural assembly candidate ranking**:
    `ReadoutEvaluationResult.status = StatusCode.AMBIGUOUS`
    `GenerateEpisodeResult.stop_status = StatusCode.GEN_STOP_AMBIGUOUS`
  - `StatusCode.READOUT_AMBIGUOUS` belongs strictly to the peripheral ledger failure class when $\ge 2$ distinct candidate tuples are attested.
  - `SurfaceReadoutLedgerV1.resolve_readout()` returns `StatusCode.READOUT_UNKNOWN` when zero rows or a single candidate row with `external_count < 2` exists.
  - `generator.py::_map_ledger_failure_to_gen_stop()` maps `StatusCode.READOUT_UNKNOWN` to `StatusCode.GEN_STOP_READOUT_UNKNOWN`.
  - Neural winner selection occurs strictly before peripheral lookup (`LG-T12`). If the winner is unattested, generation halts fail-closed; no fallback to lower-ranked printable assemblies is permitted.
- **Reconciliation Action:**
  Replaced all occurrences of `UNATTESTED_READOUT` with `StatusCode.GEN_STOP_READOUT_UNKNOWN` (generator level) and `StatusCode.READOUT_UNKNOWN` (ledger level). Corrected the neural collision status to `StatusCode.AMBIGUOUS` / `StatusCode.GEN_STOP_AMBIGUOUS`.

---

### 6. C01-S06 — Revise Experimental Acceptance Matrix
- **Normative Conflict:** EXP-B02-01 assumed Gen 8 at Root 9; EXP-B02-04 assumed `UNATTESTED_READOUT`; EXP-B02-05 assumed 1 external root was sufficient; EXP-B02-06 assumed automatic 56-root success; negative test coverage was missing.
- **Authoritative Rule:** Acceptance experiments must verify exact frozen invariants and empirical measurements without speculative claims.
- **Reconciliation Action:**
  - Retained all 7 original experiment IDs (`EXP-B02-01` through `EXP-B02-07`).
  - Corrected `EXP-B02-01` to expect Root 9 transition to Gen 7 post-merge.
  - Corrected `EXP-B02-04` to expect fail-closed halt with `GEN_STOP_READOUT_UNKNOWN`.
  - Corrected `EXP-B02-05` to require $\ge 2$ independent qualifying external roots.
  - Corrected `EXP-B02-06` to evaluate the 56-root curriculum empirically without assuming success, adding an extended-curriculum condition to evaluate re-attestation.
  - Added 9 negative test specifications (`EXP-B02-NEG-01` through `EXP-B02-NEG-09`) covering single-root confirmation, repeated observations, old-generation reuse, bundle conflict, subset absorption, cooldown bypass, archived-ID aliasing, selection leakage, and ordinary ineligibility continuity.

---

### 7. C01-S07 — Correct Implementation Touchpoints
- **Normative Conflict:** The original design listed `src/dgca/core/transaction.py` as a permitted modification touchpoint.
- **Authoritative Rule:** `src/dgca/core/transaction.py` does not exist in the codebase. Production transactions reside in `src/dgca/lifecycle/exposure_tx.py`.
- **Reconciliation Action:**
  Excised `src/dgca/core/transaction.py`. Confined authorized production touchpoints strictly to `_try_merge_pair()` in `src/dgca/core/assembly.py`. Explicitly listed all forbidden modules (FORM, GROW, Ledger, Outbox, TransactionPublicationView, ExposureTransactionManager, Generator fallback logic).

---

### 8. C01-S08 — Retain Accepted Mathematical Design
- **Normative Consistency:** Alternative A (Explicit Exact-Duplicate Structural Branch) is retained.
- **Authoritative Parameters:**
  - $\Theta_{\text{merge}} = 0.70$
  - $\Theta_{\text{ob}} = 0.40$
  - $K_{\text{max}} = 16$
  - $M_{\text{max}} = 12$
  - $T_c = 200$
- **Predicate Boundaries:**
  - Exact duplicate check: `not excl_a and not excl_b` ($A \setminus B = \emptyset \land B \setminus A = \emptyset$).
  - Bypasses ONLY the mutual-support gate ($\text{between\_strength} \ge \Theta_{\text{ob}} = 0.40$).
  - All other guards remain strictly mandatory: live status, cooldown ($T_c = 200$), capacity ($K_{\text{max}} = 16$), Jaccard ($1.0 \ge \Theta_{\text{merge}} = 0.70$), cell membership limits ($M_{\text{live}} \le 12$), keep guards.
  - Non-identical pairs evaluate under unchanged frozen Branch 4b rules.
  - Lower-ID survivor convention $\min(a, b)$ is preserved.

---

### 9. C01-S09 — Explicit Scientific Limitations
- **Normative Conflict:** The original contract claimed exact-duplicate consolidation guarantees EOS generation success, eliminates all future readout ambiguity, guarantees immediate generation stability, and requires an additional curriculum root regardless of remaining training roots.
- **Authoritative Clarification:**
  - Consolidated assembly enters a new structural generation (Gen 7 post-merge, Gen 8 post-Root 10). It cannot emit surface strings until two qualifying external roots attest it.
  - Differentiated the four separate scientific gates:
    1. Structural duplicate elimination.
    2. New-generation attestation recovery.
    3. Neural winner selection.
    4. Language generation success.
  - Explicitly addressed the risk of differing historical surface attestations: Core merge decisions must not consult peripheral surfaces (zero selection leakage). Any lost surface distinction will be reported rather than masked by aliasing.

---

### 10. C01-S10 — Forensic Documentation Erratum Reconciliation
- **Normative Erratum:** In `R2-B01-C04-FINAL-SNAPSHOT-COVERAGE-REPORT.md` Section 2 (`WState`), lines 48–49 listed:
  - `outgoing_budget_b_i`: Outgoing synapse capacity budget $B_i$ ($16$).
  - `cross_outgoing_budget_b_i_x`: Cross-region outgoing budget $B_i^x$ ($8$).
- **Authoritative Baseline:** In `DGCA_CORE_RC4_1.md` and production constants:
  - $B_i = 64$
  - $B_i^x = 12$
- **Reconciliation Action:**
  Corrected lines 48–49 in [`R2-B01-C04-FINAL-SNAPSHOT-COVERAGE-REPORT.md`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/R2-B01-C04-FINAL-SNAPSHOT-COVERAGE-REPORT.md#L48-L49) to document $B_i = 64$ and $B_i^x = 12$. Verified zero modification to scientific evidence digests or forensic replay scripts.

---

## Normative Correction Matrix

The following matrix documents the complete reconciliation across all affected design assertions:

| Original Design Assertion | Frozen Authoritative Rule | Corrected Design Assertion | Affected Experiment | Verification Status |
| :--- | :--- | :--- | :--- | :--- |
| **Attestation Threshold:** 1 external root restores attestation for Gen 8. | `readout_ledger.py` line 21: `MIN_ATTESTED_EXTERNAL_ROOTS = 2`. | At least 2 distinct completed external roots required for attestation. | EXP-B02-05, EXP-B02-NEG-01 | **RECONCILED** |
| **Root 9 Timeline:** Asm 5 & 6 are Gen 7 before merge; survivor reaches Gen 8 upon merge. | Forensic replay: Root 9 GROW advances Gen 1 to Gen 6 ($1+5$). MERGE increments $6+1=7$. | Survivor $A_5$ reaches Gen 7 post-merge; Root 10 GROW advances it to Gen 8. | EXP-B02-01, EXP-B02-06 | **RECONCILED** |
| **Generation Update Rule:** Survivor generation updated via $\max(\text{gen}_A, \text{gen}_B) + 1$. | `assembly.py` line 564: `asm_a.structural_generation += 1`. | Preserve `survivor.structural_generation += 1`. | EXP-B02-01 | **RECONCILED** |
| **Notification Schema:** Emits `AssemblyMutationNotification` with `mutation_type = MUTATION_MERGE`. | `exposure_tx.py` & `outbox.py`: uses `AssemblyEndReport.merged_pairs` and `OutboxNotificationV1`. | Excised unauthorized notification schema; uses standard `merged_pairs` tuple. | EXP-B02-01, EXP-B02-07 | **RECONCILED** |
| **Mutation Outcome Code:** Records `MERGE_CONSOLIDATED_EXACT_DUPLICATE` in report. | `assembly.py`: returns `merged_pairs: tuple[tuple[int, int], ...]`. | No custom status code; recorded as standard merged pair `((5, 6),)`. | EXP-B02-01 | **RECONCILED** |
| **Merge Failure Semantics:** Any merge validation failure triggers full transaction abort. | `assembly.py`: merge ineligibility returns `False`; pipeline continues to next pair. | Differentiated ordinary ineligibility (`return False`) from exceptional abort. | EXP-B02-07, EXP-B02-NEG-09 | **RECONCILED** |
| **Pre-Publication Abort:** Abort restores 100% pre-BEGIN state. | R2-A01 transaction law: sensory states committed during `OPEN` are preserved. | Shadow state discarded; legal `OPEN` sensory state preserved. | EXP-B02-07 | **RECONCILED** |
| **Readout Failure Code:** Decoder emits `StatusCode.UNATTESTED_READOUT`. | `generator.py` & `readout_ledger.py`: maps `READOUT_UNKNOWN` to `GEN_STOP_READOUT_UNKNOWN`. | Code `UNATTESTED_READOUT` removed; mapped to `GEN_STOP_READOUT_UNKNOWN`. | EXP-B02-04 | **RECONCILED** |
| **Root 56 Ambiguity Code:** Labeled as `StatusCode.READOUT_AMBIGUOUS`. | `generator.py` neural evaluator: returns `StatusCode.AMBIGUOUS` / `StatusCode.GEN_STOP_AMBIGUOUS`. | Corrected to `AMBIGUOUS` / `GEN_STOP_AMBIGUOUS` during neural ranking. | Forensic Baseline | **RECONCILED** |
| **Merge Parameters:** $\Theta_{\text{merge}} = 0.80, \Theta_{\text{ob}} = 0.35$. | `assembly.py` lines 45–46: $\Theta_{\text{merge}} = 0.70, \Theta_{\text{ob}} = 0.40$. | Restored frozen parameters $\Theta_{\text{merge}} = 0.70, \Theta_{\text{ob}} = 0.40$. | EXP-B02-01, EXP-B02-02 | **RECONCILED** |
| **Implementation Touchpoint:** Permitted edit in `src/dgca/core/transaction.py`. | Path does not exist; lifecycle transactions reside in `src/dgca/lifecycle/exposure_tx.py`. | Removed nonexistent path; touchpoint strictly confined to `src/dgca/core/assembly.py`. | Implementation Scope | **RECONCILED** |
| **Snapshot Budget Values:** C04 report listed $B_i = 16, B_i^x = 8$. | Frozen production constants: $B_i = 64, B_i^x = 12$. | Updated C04 report to $B_i = 64, B_i^x = 12$. | C04 Documentation | **RECONCILED** |

---

## Verification & Integrity Audit

### 1. Production Source Code Integrity
- Zero files in `src/dgca/` have been modified.
- Full Git diff against `main` confirms only accepted forensic tools, reports, and design contracts are touched.

### 2. Scientific Evidence JSON Integrity
- File `tools/forensics/r2_b01_c03_differential_evidence.json` remains completely unmodified.

### 3. Master Test Regression Suite
The complete DGCA test suite was executed to verify zero regression:
```bash
python -m pytest tests/ -q
```
**Observed Execution Times:**
- Execution run 1: 192 passed in 106.14s.
- Execution run 2 (verification closeout): 192 passed in 72.31s.

### 4. Forensic Investigation Regression Suite
The forensic investigation test suite was executed:
```bash
python -m pytest tests/forensics/ -v
```
**Observed Execution Times:**
- Execution run 1: 9 passed in 44.46s.
- Execution run 2 (verification closeout): 9 passed in 26.67s.

---

## Final Delivery Summary

1. Updated [`R2-B02-EXACT-DUPLICATE-CONSOLIDATION-DESIGN-CONTRACT.md`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/R2-B02-EXACT-DUPLICATE-CONSOLIDATION-DESIGN-CONTRACT.md) to version `2.1.0-scientific-baseline-reconciled`.
2. Created [`R2-B02-C01-NORMATIVE-DESIGN-RECONCILIATION.md`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/R2-B02-C01-NORMATIVE-DESIGN-RECONCILIATION.md).
3. Corrected budget values in [`R2-B01-C04-FINAL-SNAPSHOT-COVERAGE-REPORT.md`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/R2-B01-C04-FINAL-SNAPSHOT-COVERAGE-REPORT.md).
4. Verified remote Git commit SHA `cb8f3cc9689d6afb813f8a6767e80d4faf7ca87d`.
5. Preserved 100% frozen status of Core specification, production code, and test assets.

---

## Final Verdict Declaration

$$\mathbf{R2-B02-C01\ DESIGN\ CONTRACT\ RECONCILED\ \text{—}\ AWAITING\ FINAL\ DESIGN\ FREEZE}$$
