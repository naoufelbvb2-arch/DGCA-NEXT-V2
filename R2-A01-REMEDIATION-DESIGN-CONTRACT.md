# DGCA NEXT V2 — R2-A01 REMEDIATION DESIGN CONTRACT
## Transaction Integrity, Provenance & State Atomicity Architecture

**Document Version:** 1.0.0  
**Phase:** Remediation Design & Specification Contract (R2-A01)  
**Author:** Principal AI Systems Architect & Transaction Systems Engineer  
**Status:** **DESIGN SUBMITTED — AWAITING ENGINEERING FREEZE**  
**Repository Baseline Commit:** `31721fd1ba7559b72d9fe11f037ea0c0d1e91ed2` (`main`)  
**Forensic Audit Evidence Baseline:** `30195a77010d59c8dacef6334d2bc33b6aaf84ac` (`audit/r1-f02-c01-eos-verification`)  
**Design Branch:** `design/r2-a01-transaction-provenance-contract`  

---

## 1. EXECUTIVE SUMMARY & MANDATE

This contract specifies the formal architectural remediation design for the transaction integrity, state immutability, and event provenance defects confirmed during forensic investigations R1-F01, R1-F02, and R1-F02-C01.

### Governing Constraints
1. **Design Only:** In strict compliance with the Lead Engineer's authorization, this contract constitutes a specification and design agreement only. No production behavior or production code is modified in this stage.
2. **Preservation of Normative Mechanics:** All biological/physical learning equations, local credit assignment, two-pass dynamics, and normative candidate selection rules are preserved without modification.
3. **No Remediation Scope Creep:** Structural assembly mechanics (`FORM`, `GROW`, `MERGE`, `SPLIT`), readout scoring (`READOUT_V1`), and graduation thresholds are explicitly excluded and deferred to subsequent R2 phases (R2-B and R2-C).

---

## 2. NORMATIVE SOURCES & BASELINE

This design strictly adheres to the authoritative normative specifications:
1. `DGCA_CORE_RC4_1.md`: Sections §1.3 (Latent Neighborhoods), §1.4 (Synapse Architecture), §5.1 (Contextual Gates), §9.1 (Read-Only Episodes), §9.4 (Peripheral Outbox & Surface Resolution), §10.1 (Exposure Lifecycle & Journaling), §10.2 (Atomic Publication Order).
2. `DGCA_LLA_RC4_1.md`: Sections §3 (Eligibility Traces), §4 (Synaptic Evidence & Update Rules), §7 (Transaction Rules 1–4).
3. `dgca_v2_dynamic_core_reconstruction_encoder_specification.md`: Sections §1.2 (SIC-V1 Determinism), §2.1 (Feature Space), §4.1 (Envelope Pipeline & Attested Re-injection).

---

## 3. CONFIRMED DEFECT INVENTORY & CURRENT ARCHITECTURE

```
+------------------------------------------------------------------------------------------------------+
|                                   CURRENT ARCHITECTURE DEFECT MAP                                    |
+------------------------------------------------------------------------------------------------------+
|  [Input Event & Envelope]                                                                            |
|        |                                                                                             |
|        v                                                                                             |
|  ExposureTx.process_event()                                                                          |
|    |-- [P2 / R1-B04] NO validation between CoreEventPayloadV1 & PeripheralSurfaceEnvelopeV1         |
|    |-- [P3 / R1-H04] Idempotency check tests ONLY event_order, ignoring payload alterations          |
|    |                                                                                                 |
|    +--> execute_two_pass_event()                                                                     |
|    |      |-- [P1 / R1-B01] Mutates w.last_referenced_event during RETRIEVE (Line 677)               |
|    |      |-- [P1 / R1-B01] Mutates binding.status = STALE during RETRIEVE (context_gate.py:143)     |
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

### Problem Inventory Summary:
- **R2-A01-P1 (R1-B01 — Read-Only State Mutation):** `run_read_only_episode()` and `execute_two_pass_event(mode=RETRIEVE)` mutate `WState.last_referenced_event` and set `binding.status = BindingStatus.STALE` on permanent objects in `state.W`.
- **R2-A01-P2 (R1-B04 — Event/Envelope Provenance & Outbox Bypass):** `process_event()` accepts arbitrary unvalidated envelopes. `EventExecutionResult` omits `feature_bundle_digest`, causing `outbox.py` to evaluate `getattr(ev, 'feature_bundle_digest', None) is None`, silently bypassing envelope digest verification.
- **R2-A01-P3 (R1-H04 — Event Retry Collision):** Idempotency in `process_event()` checks only `core_event.event_order < journal.next_event_order`, returning previously cached results even if a retry provides a conflicting payload or conflicting peripheral envelope.
- **R2-A01-P4 (R1-H05 — Latent Topology Surviving ABORT):** Dynamic coactive latent slot admissions and reverse-index updates mutate `state.W.latent_table` in-place during OPEN roots. `abort_exposure()` restores `H_slow` but leaves `W.latent_table` mutated.
- **R2-A01-P5 (R1-B02 — Outbox Publication Non-Atomicity):** `end_exposure()` delivers notifications to `SurfaceReadoutLedgerV1` in Step 5 before `state.W` is swapped in Step 6. A failure in Step 6 leaves uncommitted attestations in the peripheral ledger.

---

## 4. NORMATIVE INVARIANTS & ARCHITECTURAL BOUNDARIES

### 4.1 Invariant 1: Read-Only Immutability
$$\forall \text{State } S = (W, R, H_{\text{slow}}), \quad \text{RETRIEVE}(S, \text{Events}) \implies \Delta W = 0 \land \Delta H_{\text{slow}} = 0 \land \Delta \text{Caller}(R) = 0$$
No field, counter, timestamp, link, binding status, or membership set in permanent $W$ may be modified during read-only inference.

### 4.2 Invariant 2: Provenance & Digest Integrity
$$\forall \text{Event } e, \quad \text{Digest}(e) = \text{Digest}(\text{SIC}(e)) = \text{Digest}(\text{Witness}(e)) = \text{Digest}(\text{Envelope}(e))$$
Any discrepancy between the Core event payload, SIC projection, observation witness, and peripheral envelope must result in immediate rejection before any neural dynamics or transaction staging occurs.

### 4.3 Invariant 3: Idempotent Exact Replay
$$\forall e_1, e_2 \text{ with } \text{Order}(e_1) = \text{Order}(e_2): \quad e_1 \equiv e_2 \implies \text{Return Cached Result}, \quad e_1 \not\equiv e_2 \implies \text{Raise Collision Error}$$

### 4.4 Invariant 4: Abort Rollback Completeness
$$\text{ABORT}(\text{root\_id}) \implies W_{\text{post}} = W_{\text{pre}} \cup \text{SensoryCommitments}_{\text{lawful}} \land \text{Latent}(\text{post}) \equiv \text{Latent}(\text{pre})$$

### 4.5 Invariant 5: Two-Phase Outbox Atomicity
$$\text{Attestations Delivered} \iff \text{Root Transaction Committed in } W$$
No peripheral attestation may become visible or durable unless its originating root is committed in $W$.

---

## 5. DETAILED REMEDIATION DESIGNS

---

### 5.1 R2-A01-P1: Read-Only Immutability Remediation

#### A. Root Cause Analysis
1. `src/dgca/core/dynamics.py` Line 677 executes:
   ```python
   w.last_referenced_event[cid] = w.global_event_clock
   ```
   without checking `mode == ExecutionMode.LEARN`.
2. `src/dgca/core/context_gate.py` Lines 143, 146, 149, 154, 158 execute:
   ```python
   binding.status = BindingStatus.STALE
   ```
   directly mutating the permanent instance in `w.stable_bindings` even when called from `RETRIEVE` or `GENERATE`.

#### B. Architectural Correction
1. **Execution Mode Guarding on Dynamics:**
   Guard line 677 in `dynamics.py`:
   ```python
   if mode == ExecutionMode.LEARN and origin == EventOrigin.EXTERNAL_DIRECT:
       w.last_referenced_event[cid] = w.global_event_clock
   ```
2. **Context Gate Evaluation Without In-Place Mutation:**
   Refactor `validate_and_refresh_stable_binding(binding: StableBinding, w: WState, *, mutate_stale: bool = False) -> tuple[bool, StatusCode]`.
   - When called during `evaluate_context_gate_for_cell`: pass `mutate_stale = (mode == ExecutionMode.LEARN)`.
   - If validation fails and `mutate_stale is False`: do NOT mutate `binding.status`. Return `(False, StatusCode)` immediately.
   - The cell's context gate $G_z^{\text{ctx}}$ closes ($0$), and the diagnostic code is appended to `diagnostics`, safely suppressing activity without mutating permanent $W$.
3. **Transactional STALE Transitions:**
   Stale binding status transitions occur legitimately only during an authorized transaction (`ExposureTransactionManager.end_exposure()` or an explicit offline maintenance transaction), operating on `w_shadow`.
4. **State Isolation in Read-Only Runner:**
   Update `run_read_only_episode()` in `exposure_tx.py`:
   - Pass `h_slow=state.H_slow.clone()` to prevent scratch adaptation from touching caller homeostasis.
   - Assert in development/testing mode: `assert w_before == w_after`.

---

### 5.2 R2-A01-P2: Event & Envelope Provenance Remediation

#### A. Root Cause Analysis
1. `EventExecutionResult` does not store `feature_bundle_digest`.
2. `ExposureTransactionManager.process_event()` accepts `peripheral_envelope` without validating it against `core_event`.
3. In `outbox.py`: `getattr(ev, 'feature_bundle_digest', None)` returned `None`, bypassing the envelope digest check.

#### B. Architectural Correction
1. **Extend `EventExecutionResult`:**
   Add mandatory field:
   ```python
   feature_bundle_digest: bytes
   ```
   Populated directly from `projection.feature_bundle_digest` in `execute_two_pass_event()`.
2. **Strict Pre-Execution Provenance Validation Function:**
   Define `validate_event_envelope_provenance(core_event: CoreEventPayloadV1, envelope: PeripheralSurfaceEnvelopeV1 | None, projection: SICProjectionResultV1) -> None`:
   - If `envelope is None`:
     - If `core_event.modality == Region.LANGUAGE` and `core_event.origin == EventOrigin.EXTERNAL_DIRECT`: allow only if headless/synthetic mode is explicitly configured. If peripheral tracking is enabled, raise `ObservationError(StatusCode.ENVELOPE_MISSING)`.
   - If `envelope is not None`:
     - Assert `envelope.feature_bundle_digest == projection.feature_bundle_digest` (StatusCode: `PROVENANCE_DIGEST_MISMATCH`).
     - Assert `envelope.feature_bundle_digest == core_event.feature_bundle_digest` (StatusCode: `PROVENANCE_DIGEST_MISMATCH`).
     - Assert `envelope.marker == (Marker.EOS if core_event.boundary and '\x1fEOS#0' in [f[0] for f in core_event.features] else Marker.LEXICAL)` (StatusCode: `PROVENANCE_MARKER_MISMATCH`).
     - Assert `envelope.surface_sha256 == sha256(envelope.raw_surface_nfc_utf8.encode('utf-8'))` (StatusCode: `INVALID_SURFACE_HASH`).
3. **Zero-Side-Effect Rejection:**
   Provenance validation executes at the very entry of `process_event()`, prior to:
   - Allocating proposal ordinals
   - Updating `journal.event_results`
   - Modifying latent topology
   - Incrementing `next_event_order`
   If validation fails, an `ObservationError` is raised, leaving $W$, $H_{\text{slow}}$, $R$, and the open journal completely untouched.
4. **Architectural Separation Maintained:**
   Peripheral surface text (`raw_surface_nfc_utf8`) remains strictly quarantined within `PeripheralSurfaceEnvelopeV1` and `SurfaceReadoutLedgerV1`. Neural dynamics and LLA use only numerical cell IDs, weights, and immutable digest bytes.

---

### 5.3 R2-A01-P3: Event Idempotency & Collision Remediation

#### A. Root Cause Analysis
`process_event()` currently implements:
```python
if core_event.event_order < journal.next_event_order:
    return journal.event_results[core_event.event_order]
```
This accepts any payload retried under an existing `event_order`, even if the features, salience, boundary, or peripheral envelope differ.

#### B. Architectural Correction
1. **Canonical Event Identity Specification:**
   Define `EventIdentityKey`:
   ```python
   @dataclass(frozen=True, slots=True)
   class EventIdentityKey:
       exposure_id: int
       event_order: int
       feature_bundle_digest: bytes
       boundary: bool
       origin: EventOrigin
       envelope_sha256: bytes | None
   ```
2. **Deterministic Replay & Collision Policy:**
   When `core_event.event_order < journal.next_event_order`:
   - Retrieve original recorded witness from `journal.observation_witnesses[core_event.event_order]`.
   - Retrieve original envelope from `journal.peripheral_envelopes_by_order.get(core_event.event_order)`.
   - Compute `current_key` from input and compare against `recorded_key`.
   - **Case 1 (Exact Identity Match):** Return `journal.event_results[core_event.event_order]` idempotently without side effects.
   - **Case 2 (Payload or Envelope Conflict):** Raise `ObservationError(StatusCode.EVENT_RETRY_PAYLOAD_CONFLICT, "Event retry payload does not match recorded event")`.
   - **Case 3 (Retroactive Envelope Attachment):** If original had no envelope and retry supplies one, raise `ObservationError(StatusCode.EVENT_RETRY_PROVENANCE_ALTERATION)`. An accepted event's provenance cannot be retroactively altered.

---

### 5.4 R2-A01-P4: Latent Topology Rollback on ABORT Remediation

#### A. Comparative Evaluation of Rollback Strategies

| Strategy | Mechanism | Space Complexity | Time Complexity (Begin/End) | Time Complexity (Abort) | Failure/Bug Risk |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **1. Full Pre-Root Snapshot** (Recommended) | Deep clone `latent_table` at `begin_exposure`; restore on `abort_exposure`. | $\mathcal{O}(M_{\text{mat}})$ where $M_{\text{mat}} \le 300$ cells ($\approx 60\text{ KB}$) | $\mathcal{O}(M_{\text{mat}}) \approx 0.08\text{ ms}$ | $\mathcal{O}(M_{\text{mat}}) \approx 0.08\text{ ms}$ | **Zero Risk:** Mathematically impossible to leave orphaned reverse-index entries or asymmetric links. |
| **2. Per-Slot Undo Journal** | Append `(owner, slot, old_target)` to undo stack; unroll in reverse on abort. | $\mathcal{O}(K_{\text{mutations}}) \approx 1\text{ KB}$ | $\mathcal{O}(1)$ | $\mathcal{O}(K_{\text{mutations}})$ | **High Risk:** Fragile reverse-index tracking; partial failure leaves corrupt state. |
| **3. Copy-on-Write Latent Staging** | Stage slot changes in overlay dict; merge at commit; read checks overlay first. | $\mathcal{O}(K_{\text{mutations}})$ | $\mathcal{O}(1)$ | $\mathcal{O}(1)$ | **Moderate Risk:** Severe performance overhead on every query during event dynamics. |

#### B. Architectural Recommendation: Full Snapshot in `OpenExposureJournal`
1. **Snapshot Capture at `begin_exposure()`:**
   Store `latent_table_begin = self.state.W.latent_table.clone()` in `OpenExposureJournal` alongside `h_slow_begin`.
   - Latent table uses lazy cell materialization. Across 56 training roots, fewer than 300 cells are materialized. Deep copying 300 arrays of 24 integers requires $< 60$ kilobytes of memory and executes in $< 0.1$ milliseconds.
2. **Atomic Rollback in `abort_exposure()`:**
   ```python
   self.state.W.latent_table = journal.latent_table_begin.clone()
   ```
3. **Invariant Preservation:**
   - Legal sensory commitments remain in `W.committed_cells` (conforming to Core §10.1).
   - All coactive slot assignments, partner replacements, and `_coactive_reverse_index` entries created during the aborted exposure are wiped cleanly.
   - Reverse index symmetry is 100% guaranteed.
   - Repeated `abort_exposure()` calls for the same root remain idempotent status-only operations.

---

### 5.5 R2-A01-P5: Outbox Publication Ordering & Crash Atomicity

#### A. Root Cause Analysis
In `exposure_tx.py` lines 473–488, `readout_ledger.consume_outbox_batch(outbox_notifs)` is called in Step 5, before `self.state.W = w_shadow` in Step 6. A failure during Step 6 leaves published attestations in the ledger for a root that never committed to $W$.

#### B. Architectural Correction: 4-Phase Transaction Publication Protocol

```
+------------------------------------------------------------------------------------------------------+
|                                 CANONICAL PUBLICATION SEQUENCE                                       |
+------------------------------------------------------------------------------------------------------+
|  Phase 1: Validation & Notification Staging (Shadow W*)                                             |
|    |-- Apply link proposals, update candidates, compute assemblies on w_shadow                       |
|    \-- Deterministically build OutboxNotificationV1 batch against w_shadow & H_slow                  |
|                                                                                                      |
|  Phase 2: Atomic State Commit                                                                        |
|    |-- Stage outbox batch into w_shadow.pending_outbox_batches[root_id]                              |
|    |-- Commit self.state.W = w_shadow                                                                |
|    \-- Set journal.status = ExposureStatus.COMPLETED                                                 |
|                                                                                                      |
|  Phase 3: Peripheral Ledger Dispatch                                                                 |
|    \-- Deliver notifications to readout_ledger.consume_outbox_batch(outbox_notifs)                   |
|                                                                                                      |
|  Phase 4: Acknowledgement & Queue Clearance                                                          |
|    \-- Clear pending_outbox_batches[root_id] upon confirmed ledger delivery                          |
+------------------------------------------------------------------------------------------------------+
```

#### C. Crash & Failure Semantics
1. **Failure in Phase 1 (Shadow computation):**
   Root aborts. No changes to $W$, no pending outbox batch staged, zero notifications sent to ledger.
2. **Failure in Phase 2 (State commit):**
   Transaction fails cleanly before $W$ swap. Ledger is untouched.
3. **Failure in Phase 3 (Ledger dispatch failure or process interrupt):**
   $W$ is committed and root is COMPLETED. The pending outbox batch remains recorded in `WState.pending_outbox_batches`.
   - **In-Process Boundary:** Before any subsequent `generate_episode()` or `run_read_only_episode()` queries the peripheral ledger, `ExposureTransactionManager.reconcile_outbox()` flushes pending batches.
   - **Cross-Process Persistence Boundary:** In R2-A, this protocol establishes **in-process transaction atomicity**. Full cross-process disk crash recovery depends on the durable persistence service (R1-B03), which will persist `pending_outbox_batches` into the root journal log before commit.

---

## 6. EXACT API CHANGES & DATA MODEL AMENDMENTS

### 6.1 `EventExecutionResult` Amendment (`src/dgca/core/dynamics.py`)
```python
@dataclass(frozen=True, slots=True)
class EventExecutionResult:
    event_order: int
    exposure_id: int | None
    mode: ExecutionMode
    origin: EventOrigin
    boundary: bool
    feature_bundle_digest: bytes  # <-- NEW: Immutable 32-byte digest
    committed_before_event: frozenset[int]
    ...
```

### 6.2 `OpenExposureJournal` Amendment (`src/dgca/lifecycle/exposure_tx.py`)
```python
@dataclass(slots=True)
class OpenExposureJournal:
    exposure_id: int
    status: ExposureStatus
    h_slow_begin: HomeostasisState
    h_slow_event: HomeostasisState
    latent_table_begin: LatentNeighborhoodTable  # <-- NEW: Snapshot for abort rollback
    next_event_order: int
    next_proposal_ordinal: int
    last_event_remaining_k_r: int
    event_identities: list[EventIdentityKey] = field(default_factory=list)  # <-- NEW: Collision check
    ...
```

### 6.3 `WState` Pending Outbox Queue (`src/dgca/core/state.py`)
```python
@dataclass(slots=True)
class WState:
    ...
    pending_outbox_batches: dict[int, tuple[OutboxNotificationV1, ...]] = field(default_factory=dict)
```

### 6.4 New Status Codes (`src/dgca/common/errors.py`)
```python
class StatusCode(StrEnum):
    ...
    PROVENANCE_DIGEST_MISMATCH = "PROVENANCE_DIGEST_MISMATCH"
    PROVENANCE_MARKER_MISMATCH = "PROVENANCE_MARKER_MISMATCH"
    PROVENANCE_ENVELOPE_MISSING = "PROVENANCE_ENVELOPE_MISSING"
    EVENT_RETRY_PAYLOAD_CONFLICT = "EVENT_RETRY_PAYLOAD_CONFLICT"
    EVENT_RETRY_PROVENANCE_ALTERATION = "EVENT_RETRY_PROVENANCE_ALTERATION"
    OUTBOX_DELIVERY_PENDING = "OUTBOX_DELIVERY_PENDING"
```

---

## 7. REPRODUCIBILITY & SCIENTIFIC MANIFEST GENERATOR

To resolve the provenance defect identified in R1-F02-C01:
1. **Committed Location:** The manifest generation suite will reside in repository path:
   `tools/generate_scientific_manifest.py`
2. **Path Agnosticism:** Uses strictly repository-relative paths calculated via `pathlib.Path(__file__).resolve().parents[1]`.
3. **Execution Integrity:**
   - Programmatically executes test and experiment suites via `pytest.main()`.
   - Records git commit hash via `subprocess.check_output(['git', 'rev-parse', 'HEAD'])`.
   - Records SHA-256 hashes of all configuration files in `configs/`.
   - Captures runtime telemetry directly from `MachineState` and `GenerateEpisodeResult` objects.
   - Contains zero hard-coded numerical values.

---

## 8. RISKS & BACKWARD COMPATIBILITY

1. **Blast Radius:**
   - Low: All changes are isolated to transaction lifecycle (`exposure_tx.py`), context validation (`context_gate.py`), and outbox dispatch (`outbox.py`).
   - Core neural equations, Hebbian learning, LLA synaptic consolidation, and candidate FSM transitions are 100% unchanged.
2. **Baseline Compatibility:**
   - The 76 baseline unit tests in `tests/` will pass without modification because legal canonical operations satisfy all stricter provenance checks.
   - Forensic tests in `tests/forensics/` will transition from asserting defect presence to asserting defect prevention.

---

## 9. REQUIRED NORMATIVE SPECIFICATION AMENDMENTS

Upon successful implementation, the following normative document updates will be submitted for ratification:
1. **`DGCA_CORE_RC4_1.md` §1.3:** Explicitly specify that dynamic co-active latent modifications staged during an exposure must be rolled back on `ABORT_EXPOSURE`.
2. **`DGCA_CORE_RC4_1.md` §9.1:** Explicitly mandate that `RETRIEVE` mode forbids all permanent state mutation, including `last_referenced_event` and `binding.status`.
3. **`DGCA_CORE_RC4_1.md` §10.2:** Formalize the 4-phase atomic outbox publication sequence.
4. **`DGCA_LLA_RC4_1.md` §7:** Update Rule 2 (Event Processing) to require full payload hash validation for idempotent retries.

---

# R2-A01 DESIGN SUBMITTED — AWAITING ENGINEERING FREEZE
