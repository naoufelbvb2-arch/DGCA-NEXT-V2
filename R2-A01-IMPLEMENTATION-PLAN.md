# DGCA NEXT V2 — R2-A01 IMPLEMENTATION PLAN (CORRECTED)
## Phased Execution Strategy, Regression Gates & Rollback Protocols

**Document Version:** 1.1.0  
**Phase:** Remediation Planning (R2-A01-C01)  
**Author:** Principal AI Systems Architect & Transaction Systems Engineer  
**Baseline Commit:** `31721fd1ba7559b72d9fe11f037ea0c0d1e91ed2`  
**Base Submitted Commit:** `26cce2b066a907d888ba46a34dce487ce573be9b`  
**Design Branch:** `design/r2-a01-c01-contract-corrections`  
**Status:** **PLAN CORRECTED — PENDING FINAL FREEZE REVIEW**  

---

## 1. PHASING STRATEGY OVERVIEW

To minimize blast radius and ensure continuous scientific verifiability, the remediation of transaction integrity, state immutability, and event provenance is divided into five strictly ordered, independent patches.

```
+------------------------------------------------------------------------------------------------------+
|                                    PHASED REMEDIATION ROADMAP                                        |
+------------------------------------------------------------------------------------------------------+
|  [Patch 1: Provenance & Idempotency]                                                                 |
|        |-- Adds feature_bundle_digest to EventExecutionResult                                        |
|        |-- 7-point pre-execution event/envelope validation (proper EOS identity & Marker.NONE/EOS)   |
|        |-- Exact payload collision detection via 12-attribute EventIdentityKey                       |
|        \-- allow_headless_events flag on ExposureTransactionManager with migration policy            |
|        v                                                                                             |
|  [Patch 2: Read-Only Immutability & Transactional STALE]                                             |
|        |-- Guards last_referenced_event mutation by mode == LEARN                                    |
|        |-- Strictly non-mutating binding validation during runtime dynamics                          |
|        |-- Permanent STALE transitions occur strictly via w_shadow commit                            |
|        \-- Deep-copies H_slow in run_read_only_episode                                               |
|        v                                                                                             |
|  [Patch 3: ABORT Latent Rollback & Benchmarking]                                                     |
|        |-- Captures latent_table snapshot in OpenExposureJournal at BEGIN_EXPOSURE                   |
|        |-- Restores latent_table & reverse-index atomically at ABORT_EXPOSURE                        |
|        \-- Implements BENCH-R2-A01-P4 scaling benchmark                                              |
|        v                                                                                             |
|  [Patch 4: In-Process Outbox Atomicity & Pure Read-Only Policy]                                      |
|        |-- Reorders end_exposure: Commit W BEFORE dispatching outbox                                 |
|        |-- Owns pending outbox queue in ExposureTransactionManager._pending_outbox_by_root           |
|        |-- WState remains 100% pure neural state (zero peripheral/envelope imports)                  |
|        \-- Read-only episodes NEVER invoke reconcile_outbox()                                        |
|        v                                                                                             |
|  [Patch 5: Manifest Generator & Persistence Boundary]                                                |
|        |-- Commits tools/generate_scientific_manifest.py (repo-relative, zero hardcoding)            |
|        \-- Formally defines durable persistence boundary for future R1-B03                           |
+------------------------------------------------------------------------------------------------------+
```

---

## 2. DETAILED PATCH SPECIFICATIONS

---

### PATCH 1: Event/Envelope Provenance & Retry Identity (P2 & P3)

#### A. Objectives
1. Eliminate the outbox bypass defect (R1-B04) by adding `feature_bundle_digest` to `EventExecutionResult`.
2. Reject mismatched or corrupted CoreEvent/Envelope pairs prior to neural dynamics via 7 mandatory checks.
3. Reject conflicting retries under existing `event_order` using full 12-attribute `EventIdentityKey`.
4. Provide `allow_headless_events: bool = False` on `ExposureTransactionManager` to maintain backward compatibility with synthetic unit tests.

#### B. Affected Production Files
- `src/dgca/core/dynamics.py`: Add `feature_bundle_digest: bytes` to `EventExecutionResult`; assign from `projection.feature_bundle_digest`.
- `src/dgca/lifecycle/exposure_tx.py`:
  - Add `allow_headless_events: bool = False` to `ExposureTransactionManager.__init__`.
  - Add `validate_event_envelope_provenance()`.
  - Update `process_event()` idempotency check with full `EventIdentityKey` and explicit `ObservationError(message="...", code=...)`.
- `src/dgca/peripheral/outbox.py`: Assert `ev.feature_bundle_digest == envelope.feature_bundle_digest` (eliminating silent fallback).
- `src/dgca/common/errors.py`: Add `PROVENANCE_DIGEST_MISMATCH`, `PROVENANCE_MARKER_MISMATCH`, `PROVENANCE_FEATURE_COPY_MISMATCH`, `PROVENANCE_ENVELOPE_MISSING`, `EVENT_RETRY_PAYLOAD_CONFLICT`, `EVENT_RETRY_PROVENANCE_ALTERATION`.

#### C. Verification & Regression Gate
- Run `pytest tests/test_fifr_b04_and_common.py tests/test_phase3_lla_and_transactions.py`.
- Run newly added provenance tests: `P2-01` through `P2-08`, `P3-01` through `P3-04`.
- Gate: 100% pass; zero baseline regressions.

#### D. Rollback Protocol
If any canonical learning sequence fails due to provenance rejection, revert `src/dgca/lifecycle/exposure_tx.py` and `src/dgca/core/dynamics.py` to baseline using `git checkout HEAD -- <files>`.

---

### PATCH 2: Read-Only Immutability & Transactional STALE (P1 & C03)

#### A. Objectives
1. Enforce strict invariant `RETRIEVE => ΔW = 0` (R1-B01).
2. Prevent `last_referenced_event` and `binding.status` from mutating during read-only inference.
3. Guarantee that permanent `STALE` transitions occur strictly through legally committed `w_shadow` transactions, with zero STALE leakage on ABORT.
4. Isolate caller `H_slow` from scratch adaptation.

#### B. Affected Production Files
- `src/dgca/core/dynamics.py`: Line 677: wrap `w.last_referenced_event[cid] = w.global_event_clock` inside `if mode == ExecutionMode.LEARN and origin == EventOrigin.EXTERNAL_DIRECT:`.
- `src/dgca/core/context_gate.py`: Add `mutate_stale: bool = False` to `validate_and_refresh_stable_binding()`. In runtime dynamics, always invoke with `mutate_stale = False`.
- `src/dgca/lifecycle/exposure_tx.py`:
  - In `end_exposure()`: apply legitimate STALE transitions strictly on `w_shadow`.
  - In `run_read_only_episode()`: pass `h_slow=state.H_slow.clone()`.

#### C. Verification & Regression Gate
- Run `pytest tests/test_phase4_context_and_graduation.py tests/test_phase6_readout_and_generation.py`.
- Run immutability acceptance tests: `P1-01` through `P1-04`.
- Gate: SHA-256 of $W$ before and after 100 episodes must match identically; aborted roots retain zero STALE mutations.

#### D. Rollback Protocol
Revert context gate and dynamics modifications via git restore.

---

### PATCH 3: Latent Topology Rollback on ABORT & Benchmarking (P4 & C07)

#### A. Objectives
1. Guarantee that aborted exposures leave zero coactive latent mutations in `state.W.latent_table` (R1-H05).
2. Restore full reverse-index symmetry automatically.
3. Preserve legal sensory commitments in `W.committed_cells`.
4. Validate memory and latency scaling via `BENCH-R2-A01-P4`.

#### B. Affected Production Files
- `src/dgca/lifecycle/exposure_tx.py`:
  - Add `latent_table_begin: LatentNeighborhoodTable` to `OpenExposureJournal`.
  - In `begin_exposure()`: capture `self.state.W.latent_table.clone()`.
  - In `abort_exposure()`: restore `self.state.W.latent_table = journal.latent_table_begin.clone()`.

#### C. Verification & Regression Gate
- Run `pytest tests/test_phase3_lla_and_transactions.py`.
- Run latent topology rollback tests: `P4-01` through `P4-05`.
- Run benchmark `BENCH-R2-A01-P4`: Verify memory overhead $< 100\text{ KB}$ for 56 roots and $< 3\text{ MB}$ under full materialization; verify zero memory leak across 1,000 aborts.

#### D. Rollback Protocol
Revert `begin_exposure()` and `abort_exposure()` changes.

---

### PATCH 4: In-Process Outbox Atomicity & Pure Read-Only Policy (P5, C02, C04, C08)

#### A. Objectives
1. Eliminate pre-commit peripheral attestation leakage (R1-B02).
2. Maintain `WState` as 100% pure neural state; own pending outbox queue strictly in `ExposureTransactionManager._pending_outbox_by_root`.
3. Enforce the canonical publication order: Prepare $\to$ Commit $W$ $\to$ Dispatch Outbox $\to$ Clear Queue.
4. Maintain `run_read_only_episode()` and `generate_episode()` as strictly non-mutating on ledger.
5. Implement explicit `reconcile_outbox()`.

#### B. Affected Production Files
- `src/dgca/lifecycle/exposure_tx.py`:
  - Add `_pending_outbox_by_root: dict[int, tuple[OutboxNotificationV1, ...]] = field(default_factory=dict)` to `ExposureTransactionManager`.
  - Reorder `end_exposure()`: Move Step 5 (Outbox dispatch) to execute strictly AFTER Step 6 (`self.state.W = w_shadow`).
  - Add `ExposureTransactionManager.reconcile_outbox()`.
- `src/dgca/core/generator.py`: If winning assembly attestation is unavailable, fail safely with `GEN_STOP_STALE_ASSEMBLY` without mutating ledger.

#### C. Verification & Regression Gate
- Run `pytest tests/forensics/test_f01_02_outbox_atomicity.py`.
- Run fault injection tests: `P5-01` through `P5-04`.
- Gate: Fault injected immediately before $W$ swap must produce exactly 0 attestations in `SurfaceReadoutLedgerV1`.

#### D. Rollback Protocol
Revert `end_exposure()` publication reordering and pending queue.

---

### PATCH 5: Scientific Manifest Generator & Persistence Boundary

#### A. Objectives
1. Commit the deterministic scientific manifest generator to the repository (`tools/generate_scientific_manifest.py`).
2. Establish repository-relative path execution independent of IDE or scratch environments.
3. Formally isolate the boundary between in-process R2-A remediation and full cross-process durable persistence (R1-B03).

#### B. Affected Files
- `tools/generate_scientific_manifest.py`: New committed tool.
- `src/dgca/common/serialization.py`: Documentation and interface boundary declaration for future `DurablePersistenceService`.

#### C. Verification & Regression Gate
- Run `python tools/generate_scientific_manifest.py`.
- Run full pytest regression suite: `pytest -q`.
- Gate: $\ge 95$ tests pass; manifest JSON generated with valid source SHA, config hashes, and zero hard-coded fields.

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
- **Rollout Behavior:** Cat branch reaches `GEN_STOP_EOS` via Assembly 2; Eagle branch reaches `GEN_STOP_AMBIGUOUS` via Assemblies 5 & 6 (preserving R1-M01 evidence).
- **Execution Time:** $< 60$ seconds.

---

# R2-A01 IMPLEMENTATION PLAN CORRECTED — PENDING FINAL FREEZE REVIEW
