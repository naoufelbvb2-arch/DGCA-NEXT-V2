# DGCA NEXT V2 — R2-A01 IMPLEMENTATION PLAN (FINAL TECHNICAL CONTRACT)
## Phased Execution Strategy, Regression Gates & Rollback Protocols

**Document Version:** 1.2.1  
**Phase:** Final Technical Addendum (R2-A01-ADDENDUM)  
**Author:** Independent Systems Contract Verification Engineer  
**Baseline Commit:** `31721fd1ba7559b72d9fe11f037ea0c0d1e91ed2`  
**Base Submitted Commit:** `8a5d299eed294bd98f34bcf5604d2d5b3c3c9ce8`  
**Design Branch:** `design/r2-a01-final-technical-addendum`  
**Status:** **R2-A01 FINAL ADDENDUM SUBMITTED — AWAITING FREEZE DECISION**  

---

## 1. PHASING STRATEGY OVERVIEW

To minimize blast radius, guarantee mathematical consistency, and ensure continuous scientific verifiability, the remediation of transaction integrity, state immutability, and event provenance is organized into five strictly ordered, independent patches.

```
+------------------------------------------------------------------------------------------------------+
|                                    PHASED REMEDIATION ROADMAP                                        |
+------------------------------------------------------------------------------------------------------+
|  [Patch 1: Surface-to-Feature Provenance, Exact Event Identity & Replay Validation]                  |
|        |-- Adds feature_bundle_digest to EventExecutionResult                                        |
|        |-- Mechanical feature derivation from raw surface string via frozen decompose_lexical_token  |
|        |-- 5-step pre-execution provenance validation with surface-substitution tamper protection    |
|        |-- CanonicalEnvelopeIdentity & full EventIdentityKey including envelope digest & surface     |
|        |-- Mandatory structural & provenance validation on retries before returning cached replay   |
|        \-- allow_headless_events flag on ExposureTransactionManager with migration policy            |
|        v                                                                                             |
|  [Patch 2: Read-Only Immutability, Latent Virtual Lookups & Transactional STALE]                     |
|        |-- Guards last_referenced_event mutation by mode == LEARN                                    |
|        |-- Strictly non-mutating binding validation during runtime dynamics                          |
|        |-- get_slots_read_only() non-mutating virtual lookup preventing permanent W mutation         |
|        |-- Permanent STALE transitions occur strictly via w_shadow commit                            |
|        \-- Deep-copies H_slow in run_read_only_episode                                               |
|        v                                                                                             |
|  [Patch 3: ABORT Latent Rollback & Analytical Scaling Benchmark]                                     |
|        |-- Captures latent_table snapshot in OpenExposureJournal at BEGIN_EXPOSURE                   |
|        |-- Restores latent_table & reverse-index atomically at ABORT_EXPOSURE                        |
|        |-- Preserves lawfully committed sensory cells in state.W.committed_cells (Core §10.1)        |
|        \-- Implements BENCH-R2-A01-P4 scaling benchmark and zero net memory leak verification        |
|        v                                                                                             |
|  [Patch 4: Atomic State Publication View & Pure Read-Only Policy]                                   |
|        |-- TransactionPublicationView: atomic single pointer swap publishing W, registry, & outbox   |
|        |-- Ledger status taxonomy: READOUT_UNKNOWN vs READOUT_UNAVAILABLE; GEN_STOP mappings         |
|        |-- WState remains 100% pure neural state (zero peripheral/envelope imports)                  |
|        |-- Explicit orchestration readiness API: tx.assert_outbox_ready() & tx.reconcile_outbox()    |
|        |-- 4-state lifecycle (S_pre-begin, S_pre-end, S_post-failed-end, S_post-abort) with sensory |
|        |   preservation on failed pre-commit END and root left OPEN                                  |
|        \-- Generator halts safely without ledger mutation                                            |
|        v                                                                                             |
|  [Patch 5: Manifest Generator & Durable Persistence Boundary Isolation]                              |
|        |-- Commits tools/generate_scientific_manifest.py (repo-relative, zero hardcoding)            |
|        \-- Formally isolates in-process R2-A boundary from future cross-process R1-B03 persistence   |
+------------------------------------------------------------------------------------------------------+
```

---

## 2. DETAILED PATCH SPECIFICATIONS

---

### PATCH 1: Surface-to-Feature Provenance & Exact Event Identity (P2, P3 & Addendum)

#### A. Objectives
1. Eliminate the outbox bypass defect (R1-B04) by adding `feature_bundle_digest: bytes` to `EventExecutionResult`.
2. Reject mismatched or tampered CoreEvent/Envelope pairs prior to neural dynamics via the 5-step provenance check.
3. Mechanically reconstruct expected canonical features directly from `envelope.raw_surface_nfc_utf8` using `decompose_lexical_token()`, defeating surface-substitution attacks while keeping raw text strictly outside neural ranking.
4. Reject solitary EOS exposures presented at `event_order == 0` fast with `ObservationError(EMPTY_LEXICAL_EXPOSURE)`.
5. Enforce exact event identity via `EventIdentityKey` incorporating `CanonicalEnvelopeIdentity`.
6. Mandate complete structural and provenance validation on retries before returning cached replay.
7. Provide `allow_headless_events: bool = False` on `ExposureTransactionManager` with default production strictness.

#### B. Affected Production Files
- `src/dgca/core/dynamics.py`: Add `feature_bundle_digest: bytes` to `EventExecutionResult`; assign directly from `projection.feature_bundle_digest`.
- `src/dgca/lifecycle/exposure_tx.py`:
  - Add `allow_headless_events: bool = False` to `ExposureTransactionManager.__init__`.
  - Add `CanonicalEnvelopeIdentity` and updated `EventIdentityKey`.
  - Add `validate_event_envelope_provenance()` with mechanical feature derivation.
  - Update `process_event()`: perform full provenance validation on all events (including retries); verify `current_key == recorded_key`; raise explicit `ObservationError`.
- `src/dgca/peripheral/outbox.py`: Assert `ev.feature_bundle_digest == envelope.feature_bundle_digest`.
- `src/dgca/common/errors.py`: Add status codes `PROVENANCE_DIGEST_MISMATCH`, `PROVENANCE_MARKER_MISMATCH`, `PROVENANCE_FEATURE_COPY_MISMATCH`, `PROVENANCE_ENVELOPE_MISSING`, `INVALID_SURFACE_HASH`, `EMPTY_LEXICAL_EXPOSURE`, `EVENT_RETRY_PAYLOAD_CONFLICT`, `EVENT_RETRY_PROVENANCE_ALTERATION`.

#### C. Verification & Acceptance Gates
- Run unit suites: `python -m pytest tests/test_fifr_b04_and_common.py tests/test_phase3_lla_and_transactions.py -q`.
- Run acceptance tests: `P2-01` through `P2-09` (9 tests) and `P3-01` through `P3-06` (6 tests). Total: 15 acceptance tests.
- Gate: 100% pass; zero baseline regressions.

---

### PATCH 2: Read-Only Immutability, Latent Virtual Lookups & Transactional STALE (P1 & Addendum)

#### A. Objectives
1. Enforce strict invariant `RETRIEVE => ΔW = 0` (R1-B01).
2. Guard `last_referenced_event` so that it never mutates during read-only inference (`mode == ExecutionMode.RETRIEVE`).
3. Make `evaluate_context_gate_for_cell()` non-mutating during runtime inference: corrupted bindings close the context gate ($G^{\text{ctx}}=0$) and record diagnostic telemetry without modifying permanent $W$.
4. Implement `LatentNeighborhoodTable.get_slots_read_only(cell_id)`: compute local and topographic slots virtually on the fly, preventing lazy materialization from writing to `self._slots_by_cell` on permanent $W$ during read-only inference.
5. Guarantee that permanent `STALE` transitions occur strictly through legally committed `w_shadow` transactions, with zero STALE leakage on ABORT.
6. Isolate caller `H_slow` by executing read-only inference against a deep scratch copy.

#### B. Affected Production Files
- `src/dgca/core/dynamics.py`: Line 677: wrap `w.last_referenced_event[cid] = w.global_event_clock` inside `if mode == ExecutionMode.LEARN and origin == EventOrigin.EXTERNAL_DIRECT:`.
- `src/dgca/core/latent_index.py`: Add non-mutating `get_slots_read_only()`; route read-only queries to virtual evaluation.
- `src/dgca/core/context_gate.py`: Add `mutate_stale: bool = False` to `validate_and_refresh_stable_binding()`. In runtime dynamics, invoke with `mutate_stale = False`.
- `src/dgca/lifecycle/exposure_tx.py`:
  - In `end_exposure()`: apply legitimate STALE transitions strictly on `w_shadow`.
  - In `run_read_only_episode()`: pass `h_slow=state.H_slow.clone()`.

#### C. Verification & Acceptance Gates
- Run unit suites: `python -m pytest tests/test_phase4_context_and_graduation.py tests/test_phase6_readout_and_generation.py -q`.
- Run immutability acceptance tests: `P1-01` through `P1-04` (4 tests).
- Gate: SHA-256 of serialized $W$ before and after 100 episodes must match identically; `set(latent_table._slots_by_cell.keys())` must remain 100% unchanged; aborted roots retain zero STALE mutations.

---

### PATCH 3: Latent Topology Rollback on ABORT & Analytical Scaling Benchmark (P4 & Addendum)

#### A. Objectives
1. Guarantee that aborted exposures leave zero coactive latent mutations in `state.W.latent_table` (R1-H05).
2. Restore full reverse-index symmetry automatically upon abort.
3. Preserve lawfully committed sensory cells in `state.W.committed_cells` across aborts (Core §10.1).
4. Implement `BENCH-R2-A01-P4` benchmark to empirically record latent snapshot metrics and verify zero net memory leakage across 1,000 abort cycles.

#### B. Affected Production Files
- `src/dgca/lifecycle/exposure_tx.py`:
  - Add `latent_table_begin: LatentNeighborhoodTable` to `OpenExposureJournal`.
  - In `begin_exposure()`: capture `self.state.W.latent_table.clone()`.
  - In `abort_exposure()`: restore `self.state.W.latent_table = journal.latent_table_begin.clone()`.
- `benchmarks/bench_r2_a01_p4_latent_scaling.py`: Implement benchmark measuring small (300 cells), medium (2,000 cells), and high-occupancy (12,288 cells) latency and memory footprint.

#### C. Verification & Acceptance Gates
- Run unit suites: `python -m pytest tests/test_phase3_lla_and_transactions.py -q`.
- Run latent topology rollback acceptance tests: `P4-01` through `P4-05` (5 tests).
- Run benchmark `BENCH-R2-A01-P4`: Verify 0 bytes net memory leakage after explicit garbage collection across 1,000 abort/commit cycles.

---

### PATCH 4: Atomic State Publication View & Pure Read-Only Policy (P5 & Addendum)

#### A. Objectives
1. Eliminate pre-commit peripheral attestation leakage (R1-B02).
2. Implement single atomically-swapped state publication view via `TransactionPublicationView`.
3. Separate state ownership cleanly: `WState` remains 100% pure neural state; pending outbox queue is owned strictly in `TransactionPublicationView.pending_outbox_by_root`.
4. Provide explicit orchestration readiness API: `tx.assert_outbox_ready()` and `tx.reconcile_outbox()`.
5. Maintain strict generator isolation: `generate_episode()` never mutates the peripheral ledger. Distinguish missing candidate row (`StatusCode.READOUT_UNKNOWN` $\to$ `StatusCode.GEN_STOP_READOUT_UNKNOWN`) from disabled ledger (`StatusCode.READOUT_UNAVAILABLE` $\to$ `StatusCode.GEN_STOP_READOUT_UNAVAILABLE`).
6. Enforce 4-state lifecycle ($S_{\text{pre-begin}}$, $S_{\text{pre-end}}$, $S_{\text{post-failed-end}}$, $S_{\text{post-abort}}$): failures prior to publication leave root in `OPEN` status (retryable or abortable), preserving lawfully admitted sensory cells.

#### B. Affected Production Files
- `src/dgca/lifecycle/exposure_tx.py`:
  - Define `TransactionPublicationView`.
  - Replace contiguous assignments with single pointer swap: `self._publication_view = new_view`.
  - Implement `has_pending_outbox()`, `pending_outbox_count()`, `assert_outbox_ready()`, and `reconcile_outbox()`.
- `src/dgca/core/generator.py`: Handle `StatusCode.READOUT_UNKNOWN` $\to$ `StatusCode.GEN_STOP_READOUT_UNKNOWN` and `StatusCode.READOUT_UNAVAILABLE` $\to$ `StatusCode.GEN_STOP_READOUT_UNAVAILABLE`.
- `src/dgca/common/errors.py`: Add `OUTBOX_DELIVERY_PENDING`, `GEN_STOP_READOUT_UNKNOWN`, `GEN_STOP_READOUT_UNAVAILABLE`.

#### C. Verification & Acceptance Gates
- Run forensic tests: `python -m pytest tests/forensics/test_f01_02_outbox_atomicity.py -q`.
- Run failure injection acceptance tests: `P5-01` through `P5-06` (6 tests).
- Gate: Failure injected at FP-01 / FP-02 must produce exactly 0 attestations in `SurfaceReadoutLedgerV1` and leave root in `OPEN` status; failure at FP-03 must preserve pending batch in transaction publication view without rolling back committed $W$.

---

### PATCH 5: Scientific Manifest Generator & Persistence Boundary Isolation

#### A. Objectives
1. Commit the deterministic scientific manifest generator to the repository (`tools/generate_scientific_manifest.py`).
2. Guarantee repository-relative path execution independent of IDE or scratch environments.
3. Formally isolate the boundary between in-process R2-A remediation and full cross-process durable persistence (R1-B03).

#### B. Affected Files
- `tools/generate_scientific_manifest.py`: New committed tool.
- `src/dgca/common/serialization.py`: Formal interface boundary declaration for future `DurablePersistenceService`.

#### C. Verification & Acceptance Gates
- Run `python tools/generate_scientific_manifest.py`.
- Run full pytest regression suite: `python -m pytest tests/ -q`.
- Gate: Manifest JSON generated with valid source SHA, config hashes, and zero hardcoded paths.

---

## 3. MASTER SCIENTIFIC REGRESSION GATE & PORTING PROTOCOL

### A. Forensic Test Porting Protocol (Zero Audit Branch Merging)
Audit branches (`audit/r1-f01-forensic-verification`, `audit/r1-f02-evidence-closure`, `audit/r1-f02-c01-eos-verification`) remain standalone forensic records.
Test files are ported as static files to `tests/forensics/` via:
```bash
git checkout origin/audit/r1-f02-evidence-closure -- tests/forensics/test_f01_02_outbox_atomicity.py
```
Each file is normalized to standard pytest assertions and committed directly to the remediation branch.

### B. Master Execution Suite
Prior to declaring R2-A remediation complete, the entire test suite must pass in a single clean run:

```bash
# 1. Full baseline unit and integration suite (76 tests, glob-free)
python -m pytest tests/ -q

# 2. Complete forensic and remediation acceptance suite (30 acceptance scenarios)
python -m pytest tests/forensics/ -v

# 3. Latent scaling benchmark execution
python benchmarks/bench_r2_a01_p4_latent_scaling.py

# 4. Deterministic manifest generation
python tools/generate_scientific_manifest.py
```

### Mandatory Verification Outcome:
- **Test Count:** $\ge 106$ tests collected and passed (76 baseline + 30 acceptance scenarios).
- **Failures:** 0.
- **Errors:** 0.
- **Rollout Behavior:** Cat branch reaches `GEN_STOP_EOS` via Assembly 2; Eagle branch reaches `GEN_STOP_AMBIGUOUS` via Assemblies 5 & 6 (preserving R1-M01 evidence).
- **Leak Invariance:** $\Delta \text{Mem}_{\text{net}} \le \text{noise floor}$ after 1,000 abort/commit cycles.

---

# R2-A01 FINAL ADDENDUM SUBMITTED — AWAITING FREEZE DECISION
