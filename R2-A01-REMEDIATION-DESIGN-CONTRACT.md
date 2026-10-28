# DGCA NEXT V2 — R2-A01 REMEDIATION DESIGN CONTRACT (CORRECTED)
## Transaction Integrity, Provenance & State Atomicity Architecture

**Document Version:** 1.1.0  
**Phase:** Remediation Design & Specification Contract (R2-A01-C01)  
**Author:** Principal AI Systems Architect & Transaction Systems Engineer  
**Status:** **DESIGN CORRECTED — PENDING FINAL FREEZE REVIEW**  
**Repository Baseline Commit:** `31721fd1ba7559b72d9fe11f037ea0c0d1e91ed2` (`main`)  
**Submitted Design Commit:** `26cce2b066a907d888ba46a34dce487ce573be9b`  
**Current Branch:** `design/r2-a01-c01-contract-corrections`  

---

## 1. EXECUTIVE SUMMARY & REVISED MANDATE

This contract specifies the corrected formal architectural remediation design for the transaction integrity, state immutability, and event provenance defects confirmed during forensic investigations R1-F01, R1-F02, and R1-F02-C01.

This revision incorporates all mandatory corrections and ratified decision conditions issued by the Lead Engineer in review R2-A01-C01.

### Governing Constraints
1. **Design Only:** In strict compliance with the Lead Engineer's authorization, this contract constitutes a specification and design agreement only. No production behavior or production code is modified in this stage.
2. **Preservation of Normative Mechanics:** All biological/physical learning equations, local credit assignment, two-pass dynamics, and normative candidate selection rules are preserved without modification.
3. **No Remediation Scope Creep:** Structural assembly mechanics (`FORM`, `GROW`, `MERGE`, `SPLIT`), readout scoring (`READOUT_V1`), and graduation thresholds are explicitly excluded and deferred to subsequent R2 phases (R2-B and R2-C).

---

## 2. NORMATIVE SOURCES & BASELINE

This design strictly adheres to the authoritative normative specifications:
1. `DGCA_CORE_RC4_1.md`: Sections §1.3 (Latent Neighborhoods), §1.4 (Synapse Architecture), §5.1 (Contextual Gates), §9.1 (Read-Only Episodes), §9.2 (Normative Readout Thresholds), §9.4 (Peripheral Outbox & Surface Resolution), §10.1 (Exposure Lifecycle & Journaling), §10.2 (Atomic Publication Order).
2. `DGCA_LLA_RC4_1.md`: Sections §3 (Eligibility Traces), §4 (Synaptic Evidence & Update Rules), §7 (Transaction Rules 1–4).
3. `dgca_v2_dynamic_core_reconstruction_encoder_specification.md`: Sections §1.2 (SIC-V1 Determinism), §1.3 (Canonical EOS Format), §2.1 (Feature Space), §4.1 (Envelope Pipeline & Attested Re-injection).

### Authoritative Constants Verification
Directly verified against pinned production source code:
- $\theta_{\text{read}} = 0.08$ (`src/dgca/core/readout.py:32`, `THETA_READ`)
- $M_{\text{read}} = 0.04$ (`src/dgca/core/readout.py:33`, `M_READ`)
- $\theta_{\text{OB}} = 0.40$ (`src/dgca/core/assembly.py:44`, `THETA_OB`)
- $\rho_{\text{core}} = 0.70$ (`src/dgca/core/assembly.py:42`, `RHO_CORE`)
- $K_R = 12$ (`src/dgca/core/dynamics.py:50`, `K_R_PER_EVENT`)
- Marker Enum: `Marker.NONE = 0x00`, `Marker.EOS = 0x01` (`src/dgca/encoder/envelope.py:16-20`)

### Cold-Start Reference Owner Mapping
- `z=8321`: Complete Contextual Owner for Branch $AB$ / Cat (`القط يشرب حليب`).
- `z=8320`: Complete Contextual Owner for Branch $DB$ / Eagle (`النسر يشرب ماء`).

---

## 3. CONFIRMED DEFECT INVENTORY & CURRENT ARCHITECTURE

```
+------------------------------------------------------------------------------------------------------+
|                                   CORRECTED ARCHITECTURE DEFECT MAP                                  |
+------------------------------------------------------------------------------------------------------+
|  [Input Event & Peripheral Envelope]                                                                 |
|        |                                                                                             |
|        v                                                                                             |
|  ExposureTx.process_event()                                                                          |
|    |-- [P2 / R1-B04] Inadequate provenance validation; incorrect EOS boundary assumptions            |
|    |-- [P3 / R1-H04] Idempotency check tests ONLY event_order, ignoring payload alterations          |
|    |                                                                                                 |
|    +--> execute_two_pass_event()                                                                     |
|    |      |-- [P1 / R1-B01] Mutates w.last_referenced_event during RETRIEVE (Line 677)               |
|    |      |-- [P1 & C03] Mutates binding.status = STALE in-place on permanent W                      |
|    |      \-- Returns EventExecutionResult LACKING feature_bundle_digest                             |
|    |                                                                                                 |
|    +--> _update_coactive_latent_neighborhoods()                                                      |
|           \-- [P4 / R1-H05] Mutates state.W.latent_table in-place during OPEN root                   |
|                                                                                                      |
|  ExposureTx.abort_exposure()                                                                         |
|    \-- [P4 / R1-H05] Restores H_slow, but LEAVES all latent slot & reverse-index mutations in W   |
|                                                                                                      |
|  ExposureTx.end_exposure()                                                                           |
|    |-- Step 5: [P5 / R1-B02] Calls readout_ledger.consume_outbox_batch() BEFORE committing W        |
|    \-- Step 6: Commits self.state.W = w_shadow (Outbox check was bypassed due to missing digest)    |
+------------------------------------------------------------------------------------------------------+
```

---

## 4. NORMATIVE INVARIANTS & ARCHITECTURAL BOUNDARIES

### 4.1 Invariant 1: Read-Only Immutability
$$\forall \text{State } S = (W, R, H_{\text{slow}}), \quad \text{RETRIEVE}(S, \text{Events}) \implies \Delta W = 0 \land \Delta H_{\text{slow}} = 0 \land \Delta \text{Caller}(R) = 0$$
No field, counter, timestamp, link, binding status, or membership set in permanent $W$ may be modified during read-only inference (`RETRIEVE` or `GENERATE`).

### 4.2 Invariant 2: Comprehensive Provenance & EOS Identity (C01)
$$\forall \text{Event } e, \quad \text{Digest}(e) = \text{Digest}(\text{SIC}(e)) = \text{Digest}(\text{Witness}(e)) = \text{Digest}(\text{Envelope}(e))$$
EOS events are identified strictly by their canonical reserved feature bundle:
$$\text{Features}(e) \equiv ((\texttt{"\textbackslash x1fEOS\#0"}, \texttt{"1.000000"}), (\texttt{"\textbackslash x1fEOS\#1"}, \texttt{"0.900000"}), (\texttt{"\textbackslash x1fEOS\#2"}, \texttt{"0.800000"}))$$
Canonical EOS events have $\text{boundary} = \text{False}$, $\text{Marker} = \text{Marker.EOS}$ ($0\text{x}01$), and $\text{raw\_surface} = \texttt{"<EOS>"}$. Ordinary lexical events have $\text{Marker} = \text{Marker.NONE}$ ($0\text{x}00$). Event boundary flag is NOT an EOS discriminator.

### 4.3 Invariant 3: Strict Full-Payload Idempotency (C06)
Replay of an existing `event_order` must evaluate an immutable `EventIdentityKey` encompassing all observation and envelope attributes. Exact matches return cached results; conflicting retries or retroactive envelope attachments fail fast with explicit status codes.

### 4.4 Invariant 4: Abort Rollback Completeness
$$\text{ABORT}(\text{root\_id}) \implies W_{\text{post}} = W_{\text{pre}} \cup \text{SensoryCommitments}_{\text{lawful}} \land \text{Latent}(\text{post}) \equiv \text{Latent}(\text{pre})$$

### 4.5 Invariant 5: Architectural Separation of State Ownership (C02 & C04)
Neural $W$ (`WState`) is a regular Python class holding only neural graph state. It must NEVER store `PeripheralSurfaceEnvelopeV1`, `OutboxNotificationV1`, or raw surface text. Pending outbox batches are owned exclusively by the transaction layer (`ExposureTransactionManager._pending_outbox_by_root`). Read-only inference never invokes mutating reconciliation.

---

## 5. DETAILED REMEDIATION DESIGNS

---

### 5.1 R2-A01-P1 & C03: Read-Only Immutability & Transactional STALE Transitions

#### A. Root Cause Analysis
1. `src/dgca/core/dynamics.py` Line 677 mutates `w.last_referenced_event[cid] = w.global_event_clock` unconditionally.
2. `src/dgca/core/context_gate.py` Lines 143, 146, 149, 154, 158 execute `binding.status = BindingStatus.STALE` directly on permanent $W$ objects during runtime validation.

#### B. Architectural Correction
1. **Mode Guard on Dynamics:**
   ```python
   if mode == ExecutionMode.LEARN and origin == EventOrigin.EXTERNAL_DIRECT:
       w.last_referenced_event[cid] = w.global_event_clock
   ```
2. **Non-Mutating Context Gate Validation:**
   In `src/dgca/core/context_gate.py`, refactor `validate_and_refresh_stable_binding(binding: StableBinding, w: WState, *, mutate_stale: bool = False) -> tuple[bool, StatusCode]`.
   - During `execute_two_pass_event()` (across ALL modes: `LEARN`, `RETRIEVE`, `GENERATE`): call with `mutate_stale = False`.
   - If validation fails, return `(False, StatusCode)`. The cell's context gate $G_z^{\text{ctx}}$ closes ($0$), and the diagnostic code is appended to `r.context_diagnostics`. **Zero mutations are written to `binding.status` during event processing.**
3. **Transactional STALE Transitions in `w_shadow` (C03):**
   - Permanent `STALE` transitions occur strictly at `END_EXPOSURE` during candidate and assembly maintenance on `w_shadow`.
   - If the root commits, `self.state.W = w_shadow` persists the legitimate STALE transitions atomically.
   - If the root aborts, `w_shadow` is discarded. Permanent $W$ retains zero unauthorized STALE transitions.
4. **State Isolation in Read-Only Runner:**
   In `run_read_only_episode()`:
   - Instantiate scratch state with `h_slow=state.H_slow.clone()`.
   - Execute strictly with `mode=ExecutionMode.RETRIEVE`.

---

### 5.2 R2-A01-P2 & C01: Provenance Validation & EOS Identity

#### A. The Seven Mandatory Pre-Execution Checks
Prior to any neural execution, proposal staging, or journal modification, `ExposureTransactionManager.process_event()` executes `validate_event_envelope_provenance(core_event, envelope, projection)`:

1. **Check 1 (Canonical Feature Bundle Identity):**
   Verify if features match `EOS_CANONICAL_FEATURES` ($((\texttt{"\textbackslash x1fEOS\#0"}, \texttt{"1.000000"}), (\texttt{"\textbackslash x1fEOS\#1"}, \texttt{"0.900000"}), (\texttt{"\textbackslash x1fEOS\#2"}, \texttt{"0.800000"}))$).
   - If matching: event is canonical EOS.
   - If not matching: features must NOT contain reserved byte `\x1f`.
2. **Check 2 (Projection Digest Equality):**
   `projection.feature_bundle_digest == core_event.feature_bundle_digest`. If unequal, raise `ObservationError("Projection digest mismatch", code=StatusCode.PROVENANCE_DIGEST_MISMATCH)`.
3. **Check 3 (Envelope Digest Equality):**
   `envelope.feature_bundle_digest == core_event.feature_bundle_digest`. If unequal, raise `ObservationError("Envelope digest mismatch", code=StatusCode.PROVENANCE_DIGEST_MISMATCH)`.
4. **Check 4 (Canonical Feature Copy Integrity):**
   `envelope.canonical_features_copy == core_event.features`. If unequal, raise `ObservationError("Envelope feature copy mismatch", code=StatusCode.PROVENANCE_FEATURE_COPY_MISMATCH)`.
5. **Check 5 (Marker Consistency):**
   - If canonical EOS: `envelope.marker == Marker.EOS` ($0\text{x}01$).
   - If ordinary lexical: `envelope.marker == Marker.NONE` ($0\text{x}00$).
   If mismatched, raise `ObservationError("Marker mismatch", code=StatusCode.PROVENANCE_MARKER_MISMATCH)`.
6. **Check 6 (Surface SHA-256 Verification):**
   `envelope.surface_sha256 == hashlib.sha256(envelope.raw_surface_nfc_utf8.encode('utf-8')).digest()`. If unequal, raise `ObservationError("Invalid surface hash", code=StatusCode.INVALID_SURFACE_HASH)`.
7. **Check 7 (EOS Surface & Feature Consistency):**
   If `envelope.marker == Marker.EOS`:
   - `envelope.raw_surface_nfc_utf8 == "<EOS>"`.
   - `envelope.canonical_features_copy == EOS_CANONICAL_FEATURES`.
   - `core_event.boundary == False` (cannot be event_order 0 alone).
   If violated, raise `ObservationError("Malformed EOS envelope", code=StatusCode.INVALID_ENCODER_INPUT)`.

#### B. Populating `EventExecutionResult.feature_bundle_digest` (D2)
Add `feature_bundle_digest: bytes` to `EventExecutionResult`. In `execute_two_pass_event()`, assign directly from `projection.feature_bundle_digest`. In `outbox.py:104`, assert `ev.feature_bundle_digest == envelope.feature_bundle_digest`.

---

### 5.3 R2-A01-P3 & C06: Full Event Identity & Replay Semantics

#### A. Comprehensive `EventIdentityKey`
```python
@dataclass(frozen=True, slots=True)
class EventIdentityKey:
    exposure_id: int | None
    event_order: int
    origin: EventOrigin
    boundary: bool
    salience: str
    features: tuple[tuple[str, str], ...]
    feature_bundle_digest: bytes
    observation_scope: ObservationScope
    has_envelope: bool
    envelope_surface_sha256: bytes | None
    envelope_marker: Marker | None
    envelope_features_copy: tuple[tuple[str, str], ...] | None
```

#### B. Replay & Collision Evaluation
When `core_event.event_order < journal.next_event_order`:
- Retrieve `recorded_key = journal.event_identities[core_event.event_order]`.
- Construct `current_key` from incoming parameters.
- **Case 1 (Exact Match):** Return `journal.event_results[core_event.event_order]` idempotently.
- **Case 2 (Payload Conflict):** Raise:
  ```python
  raise ObservationError(
      f"Event retry payload conflicts with recorded event {core_event.event_order}",
      code=StatusCode.EVENT_RETRY_PAYLOAD_CONFLICT,
  )
  ```
- **Case 3 (Retroactive Provenance Alteration):** If `recorded_key.has_envelope is False` and `current_key.has_envelope is True`:
  ```python
  raise ObservationError(
      f"Cannot retroactively attach peripheral envelope to headless event {core_event.event_order}",
      code=StatusCode.EVENT_RETRY_PROVENANCE_ALTERATION,
  )
  ```

---

### 5.4 R2-A01-P4 & C07: Latent Topology Rollback & Scaling Benchmark

#### A. Rollback Mechanism
In `OpenExposureJournal`, store `latent_table_begin = self.state.W.latent_table.clone()`.
On `abort_exposure()`:
```python
self.state.W.latent_table = journal.latent_table_begin.clone()
```

#### B. Asymptotic Complexity & Scaling Analysis
- **Memory Footprint:** $\mathcal{O}(M_{\text{mat}} \times 24 \times 8\text{ bytes} + |R_{\text{coactive}}| + P_{\text{pins}} + W_{\text{logs}})$, where $M_{\text{mat}} \le 12{,}288$ is the number of materialized cells.
- **Cloning Latency:** $\mathcal{O}(M_{\text{mat}} + |R_{\text{coactive}}| + P_{\text{pins}} + W_{\text{logs}})$.
- **Scaling Regimes:**
  - *Small Curricula ($\le 10$ roots):* $M_{\text{mat}} < 100 \implies \approx 20\text{ KB}$, latency $< 0.05\text{ ms}$.
  - *Medium Benchmark (56 roots):* $M_{\text{mat}} \approx 250..300 \implies \approx 60\text{ KB}$, latency $\approx 0.08\text{ ms}$.
  - *High Latent Occupancy (Full materialization, $M_{\text{mat}} = 12{,}288$, 6 coactive links/cell):* $|R_{\text{coactive}}| \approx 73{,}728 \implies \approx 2.5\text{ MB}$, latency $\approx 2.5\text{ ms}$.
- **Benchmark Acceptance Suite:** Candidate implementations must execute benchmark test `BENCH-R2-A01-P4` verifying linear memory scaling across small, medium, and high-occupancy loads, and proving zero memory leak over 1,000 consecutive ABORT/COMMIT cycles.

---

### 5.5 R2-A01-P5, C02, C04, C08: Outbox State Ownership & Publication Protocol

#### A. Outbox State Ownership Architecture (C02)
- **Neural `WState` (`src/dgca/core/state.py`):** Remains 100% pure neural state. Regular Python class. Holds zero peripheral envelopes, notifications, or surface texts.
- **Transaction Storage (`src/dgca/lifecycle/exposure_tx.py`):**
  `ExposureTransactionManager` maintains:
  ```python
  self._pending_outbox_by_root: dict[int, tuple[OutboxNotificationV1, ...]] = {}
  ```
  Completely eliminates circular imports between `core/state.py` and `peripheral/outbox.py`.

#### B. Commit Publication Interruption Handling (C08)
```
+------------------------------------------------------------------------------------------------------+
|                                    TRANSACTION PUBLICATION PHASES                                    |
+------------------------------------------------------------------------------------------------------+
|  1. Preparation: Compute w_shadow, candidates, assemblies. Staged in memory.                        |
|  2. Outbox Staging: build_end_exposure_outbox_notifications against w_shadow. Staged in memory.       |
|  3. Neural Commit Point:                                                                             |
|       self.state.W = w_shadow                                                                        |
|       journal.status = ExposureStatus.COMPLETED                                                      |
|       self.completed_roots[exposure_id] = report                                                     |
|       self._pending_outbox_by_root[exposure_id] = staged_notifications                               |
|       self.open_journal = None                                                                       |
|  4. Peripheral Delivery:                                                                             |
|       if self.readout_ledger:                                                                        |
|           self.readout_ledger.consume_outbox_batch(staged_notifications)                             |
|           del self._pending_outbox_by_root[exposure_id]                                              |
+------------------------------------------------------------------------------------------------------+
```
- **Interruption between Phase 1 and 3:** Root is not committed. `state.W` untouched.
- **Interruption during Phase 4 (Delivery failure):**
  - `state.W` remains committed.
  - Root remains `COMPLETED`. **It is never reverted to OPEN or ABORTED.**
  - Undelivered notifications remain safely stored in `self._pending_outbox_by_root[exposure_id]`.
- **Durable Persistence Boundary:** This provides complete **in-process transaction atomicity**. Cross-process crash recovery requires the durable persistence service (R1-B03), which will journal `_pending_outbox_by_root` to disk.

#### C. Outbox Reconciliation & Read-Only Policy (C04)
1. `run_read_only_episode()` and `generate_episode()` are strictly non-mutating on both neural state and peripheral ledger. They NEVER invoke `reconcile_outbox()`.
2. Explicit API for caller:
   ```python
   def reconcile_outbox(self, ledger: SurfaceReadoutLedgerV1 | None = None) -> tuple[int, list[StatusCode]]:
   ```
3. During generation, if a winning assembly has pending unreconciled notifications, `ledger.resolve_readout()` returns `StatusCode.READOUT_UNAVAILABLE`. `generate_episode()` halts cleanly with `StatusCode.GEN_STOP_STALE_ASSEMBLY` without corrupting state.

---

## 6. BACKWARD COMPATIBILITY & HEADLESS MIGRATION POLICY (C03 & C06)

To accommodate existing baseline tests that call `process_event(core_event)` without envelopes:
1. `ExposureTransactionManager` accepts:
   ```python
   allow_headless_events: bool = False
   ```
2. **Production Ingestion:** Always runs with `allow_headless_events = False`. Missing envelopes raise `PROVENANCE_ENVELOPE_MISSING`.
3. **Synthetic Baseline Tests:** Tests in `tests/test_phase*.py` running low-level unit checks instantiate transaction manager with `allow_headless_events = True`.
4. **Headless Invariants:**
   - Headless events produce zero outbox notifications.
   - Retroactive envelope attachment on retry is strictly forbidden.
   - Headless events are auditable via `witness.origin == EventOrigin.EXTERNAL_DIRECT` and `envelope is None`.

---

# R2-A01 DESIGN CONTRACT CORRECTED — PENDING FINAL FREEZE REVIEW
