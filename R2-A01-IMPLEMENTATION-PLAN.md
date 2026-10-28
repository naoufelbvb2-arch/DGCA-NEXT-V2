# DGCA NEXT V2 — R2-A01 IMPLEMENTATION PLAN
## Phased Execution Strategy, Regression Gates & Rollback Protocols

**Document Version:** 1.0.0  
**Phase:** Remediation Planning (R2-A01)  
**Author:** Principal AI Systems Architect & Transaction Systems Engineer  
**Baseline Commit:** `31721fd1ba7559b72d9fe11f037ea0c0d1e91ed2`  
**Design Branch:** `design/r2-a01-transaction-provenance-contract`  
**Status:** **SUBMITTED FOR ENGINEERING REVIEW**  

---

## 1. PHASING STRATEGY OVERVIEW

To minimize blast radius and ensure continuous scientific verifiability, the remediation of transaction integrity, state immutability, and event provenance is divided into five strictly ordered, independent patches.

```
+------------------------------------------------------------------------------------------------------+
|                                    PHASED REMEDIATION ROADMAP                                        |
+------------------------------------------------------------------------------------------------------+
|  [Patch 1: Provenance & Idempotency]                                                                 |
|        |-- Adds feature_bundle_digest to EventExecutionResult                                        |
|        |-- Pre-execution event/envelope validation                                                    |
|        \-- Exact payload collision detection for event retries                                       |
|        v                                                                                             |
|  [Patch 2: Read-Only Immutability]                                                                   |
|        |-- Guards last_referenced_event mutation by mode == LEARN                                    |
|        |-- Disables in-place binding.status = STALE mutation during RETRIEVE                         |
|        \-- Deep-copies H_slow in run_read_only_episode                                               |
|        v                                                                                             |
|  [Patch 3: ABORT Latent Rollback]                                                                    |
|        |-- Captures latent_table snapshot at BEGIN_EXPOSURE                                          |
|        \-- Restores latent_table & reverse-index atomically at ABORT_EXPOSURE                        |
|        v                                                                                             |
|  [Patch 4: In-Process Outbox Atomicity]                                                              |
|        |-- Reorders end_exposure: Commit W BEFORE dispatching outbox                                 |
|        |-- Implements pending_outbox_batches queue on WState                                         |
|        \-- Adds reconcile_outbox() protocol                                                          |
|        v                                                                                             |
|  [Patch 5: Manifest Generator & Persistence Boundary]                                                |
|        |-- Commits tools/generate_scientific_manifest.py                                             |
|        \-- Formally isolates durable persistence interfaces (R1-B03 boundary)                        |
+------------------------------------------------------------------------------------------------------+
```

---

## 2. DETAILED PATCH SPECIFICATIONS

---

### PATCH 1: Event/Envelope Provenance & Retry Identity (P2 & P3)

#### A. Objectives
1. Eliminate the outbox bypass defect (R1-B04) by adding `feature_bundle_digest` to `EventExecutionResult`.
2. Reject mismatched or corrupted CoreEvent/Envelope pairs before neural processing.
3. Reject conflicting retries under existing `event_order`.

#### B. Affected Production Files
- `src/dgca/core/dynamics.py`: Add `feature_bundle_digest` field to `EventExecutionResult`; populate in `execute_two_pass_event()`.
- `src/dgca/lifecycle/exposure_tx.py`: Add `validate_event_envelope_provenance()`; update `process_event()` idempotency check with full `EventIdentityKey`.
- `src/dgca/peripheral/outbox.py`: Assert `ev.feature_bundle_digest == envelope.feature_bundle_digest` (remove the silent `getattr(..., None)` fallback).
- `src/dgca/common/errors.py`: Add `PROVENANCE_DIGEST_MISMATCH`, `PROVENANCE_MARKER_MISMATCH`, `EVENT_RETRY_PAYLOAD_CONFLICT`, `EVENT_RETRY_PROVENANCE_ALTERATION`.

#### C. Verification & Regression Gate
- Run `pytest tests/test_fifr_b04_and_common.py tests/test_phase3_lla_and_transactions.py`.
- Run newly added provenance tests: `P2-01` through `P2-06`, `P3-01` through `P3-03`.
- Gate: 100% pass; zero baseline regressions.

#### D. Rollback Protocol
If any canonical learning sequence fails due to provenance rejection, revert `src/dgca/lifecycle/exposure_tx.py` and `src/dgca/core/dynamics.py` to baseline using `git checkout HEAD -- <files>`.

---

### PATCH 2: Read-Only Immutability (P1)

#### A. Objectives
1. Enforce strict invariant `RETRIEVE => ΔW = 0` (R1-B01).
2. Prevent `last_referenced_event` and `binding.status` from mutating during read-only inference.
3. Isolate caller `H_slow` from scratch adaptation.

#### B. Affected Production Files
- `src/dgca/core/dynamics.py`: Line 677: wrap `w.last_referenced_event[cid] = w.global_event_clock` inside `if mode == ExecutionMode.LEARN and origin == EventOrigin.EXTERNAL_DIRECT:`.
- `src/dgca/core/context_gate.py`: Add `mutate_stale: bool = False` to `validate_and_refresh_stable_binding()`. Pass `mutate_stale = (mode == ExecutionMode.LEARN)`.
- `src/dgca/lifecycle/exposure_tx.py`: In `run_read_only_episode()`, pass `h_slow=state.H_slow.clone()`.

#### C. Verification & Regression Gate
- Run `pytest tests/test_phase4_context_and_graduation.py tests/test_phase6_readout_and_generation.py`.
- Run immutability acceptance tests: `P1-01`, `P1-02`, `P1-03`.
- Gate: SHA-256 of $W$ before and after 100 episodes must match identically.

#### D. Rollback Protocol
Revert context gate and dynamics modifications via git restore.

---

### PATCH 3: Latent Topology Rollback on ABORT (P4)

#### A. Objectives
1. Guarantee that aborted exposures leave zero coactive latent mutations in `state.W.latent_table` (R1-H05).
2. Restore full reverse-index symmetry automatically.
3. Preserve legal sensory commitments in `W.committed_cells`.

#### B. Affected Production Files
- `src/dgca/lifecycle/exposure_tx.py`:
  - Add `latent_table_begin: LatentNeighborhoodTable` to `OpenExposureJournal`.
  - In `begin_exposure()`: capture `self.state.W.latent_table.clone()`.
  - In `abort_exposure()`: restore `self.state.W.latent_table = journal.latent_table_begin.clone()`.

#### C. Verification & Regression Gate
- Run `pytest tests/test_phase3_lla_and_transactions.py`.
- Run latent topology rollback tests: `P4-01` through `P4-05`.
- Gate: All 123 coactive slot mutations induced during Root 3 test must revert to 0 surviving mutations upon `abort_exposure()`.

#### D. Rollback Protocol
Revert `begin_exposure()` and `abort_exposure()` changes.

---

### PATCH 4: In-Process Outbox Atomicity & Reconciliation (P5)

#### A. Objectives
1. Eliminate pre-commit peripheral attestation leakage (R1-B02).
2. Enforce the canonical 4-phase publication order: Prepare $\to$ Commit $W$ $\to$ Dispatch Outbox $\to$ Clear Queue.
3. Implement pending outbox batch recording on `WState` and reconciliation handler.

#### B. Affected Production Files
- `src/dgca/core/state.py`: Add `pending_outbox_batches: dict[int, tuple[OutboxNotificationV1, ...]]` to `WState`.
- `src/dgca/lifecycle/exposure_tx.py`:
  - Reorder `end_exposure()`: Move Step 5 (Outbox dispatch) to execute strictly AFTER Step 6 (`self.state.W = w_shadow`).
  - Add `ExposureTransactionManager.reconcile_outbox()`.
  - Add reconciliation preflight before `run_read_only_episode()` and `generate_episode()`.

#### C. Verification & Regression Gate
- Run `pytest tests/forensics/test_f01_02_outbox_atomicity.py`.
- Run fault injection tests: `P5-01` through `P5-04`.
- Gate: Fault injected immediately before $W$ swap must produce exactly 0 attestations in `SurfaceReadoutLedgerV1`.

#### D. Rollback Protocol
Revert `end_exposure()` publication reordering and `WState` queue.

---

### PATCH 5: Scientific Manifest Generator & Persistence Boundary

#### A. Objectives
1. Commit the deterministic scientific manifest generator to the repository (`tools/generate_scientific_manifest.py`).
2. Establish repository-relative path execution independent of IDE or scratch environments.
3. Formalize the boundary between in-process R2-A remediation and full cross-process durable persistence (R1-B03).

#### B. Affected Files
- `tools/generate_scientific_manifest.py`: New committed tool.
- `src/dgca/common/serialization.py`: Documentation and interface boundary declaration for future `DurablePersistenceService`.

#### C. Verification & Regression Gate
- Run `python tools/generate_scientific_manifest.py`.
- Run full pytest regression suite: `pytest -q`.
- Gate: 95 tests pass; manifest JSON generated with valid source SHA, config hashes, and zero hard-coded fields.

---

## 3. MASTER SCIENTIFIC REGRESSION GATE

Prior to declaring R2-A remediation complete, the entire 12-item regression suite must pass in a single clean run:

```bash
# 1. Full baseline and unit suite
python -m pytest tests/test_*.py -q

# 2. Complete forensic and remediation verification suite
python -m pytest tests/forensics/ -v

# 3. Overall suite execution
python -m pytest -q

# 4. Manifest generation
python tools/generate_scientific_manifest.py
```

### Mandatory Verification Outcome:
- **Test Count:** $\ge 95$ tests collected and passed.
- **Failures:** 0.
- **Errors:** 0.
- **Rollout Behavior:** Cat branch reaches `GEN_STOP_EOS`; Eagle branch reaches `GEN_STOP_AMBIGUOUS` (preserving R1-M01 evidence).
- **Execution Time:** $< 60$ seconds.

---

# R2-A01 IMPLEMENTATION PLAN RATIFIED
