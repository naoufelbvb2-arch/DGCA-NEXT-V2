# DGCA NEXT V2 — R2-A01 REMEDIATION DESIGN CONTRACT (FINAL TECHNICAL CONTRACT)
## Transaction Integrity, Provenance & State Atomicity Architecture

**Document Version:** 1.2.1  
**Audit Stage:** Final Technical Addendum (R2-A01-ADDENDUM)  
**Author:** Independent Systems Contract Verification Engineer  
**Status:** **R2-A01 FINAL ADDENDUM SUBMITTED — AWAITING FREEZE DECISION**  
**Repository Baseline Commit:** `31721fd1ba7559b72d9fe11f037ea0c0d1e91ed2` (`main`)  
**Base Submitted Commit:** `8a5d299eed294bd98f34bcf5604d2d5b3c3c9ce8`  
**Current Branch:** `design/r2-a01-final-technical-addendum`  

---

## 1. EXECUTIVE SUMMARY & FREEZE MANDATE

This contract specifies the final, implementable architectural remediation design for the transaction integrity, state immutability, event provenance, and outbox atomicity defects confirmed during forensic investigations R1-F01, R1-F02, and R1-F02-C01.

This version incorporates the final technical clarifications from `R2-A01-FINAL-TECHNICAL-ADDENDUM.md`:
1. Mechanical derivation of canonical feature bundles from normalized raw surface strings (`decompose_lexical_token()`), eliminating semantic-payload substitution attacks while keeping raw text strictly outside neural ranking.
2. A single atomically-swapped publication state reference (`TransactionPublicationView`) replacing multi-statement assignments, with explicit fault injection semantics.
3. Rigorous distinction of ledger failure semantics (`READOUT_UNKNOWN` vs `READOUT_UNAVAILABLE`) and generator safe stop mapping.
4. Non-mutating virtual latent neighbor lookup (`get_slots_read_only()`) guaranteeing that read-only queries never write to permanent $W$.
5. Test execution portability across platforms without shell glob dependencies.

### Governing Invariants:
- **Zero Production Modification:** No production source code has been or will be modified under this assignment.
- **Preservation of Normative Mechanics:** All biological learning equations, local credit assignment, Hebbian dynamics, and candidate selection rules remain byte-for-byte untouched.
- **Strict Scope Boundary:** Assemblies (`FORM`, `GROW`, `MERGE`, `SPLIT`) and readout scoring (`READOUT_V1`) remain frozen for subsequent R2 phases.

---

## 2. NORMATIVE SOURCES & BASELINE

This design strictly adheres to the authoritative normative specifications:
1. `DGCA_CORE_RC4_1.md`: Sections §1.3 (Latent Neighborhoods), §1.4 (Synapse Architecture), §5.1 (Contextual Gates), §9.1 (Read-Only Episodes), §9.2 (Normative Readout Thresholds), §9.3 (Generation Stop Codes), §9.4 (Peripheral Outbox & Surface Resolution), §10.1 (Exposure Lifecycle & Journaling), §10.2 (Atomic Publication Order).
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

## 3. REMEDIATION ARCHITECTURE & CONTRACT SPECIFICATIONS

---

### 3.1 P1 & C03: Read-Only Immutability & Transactional STALE Transitions

#### A. Invariant
$$\forall \text{State } S = (W, R, H_{\text{slow}}), \quad \text{RETRIEVE}(S, \text{Events}) \implies \Delta W = 0 \land \Delta H_{\text{slow}} = 0 \land \Delta \text{Caller}(R) = 0$$

#### B. Implementation Contracts
1. **Mode Guard on Cell Activity Clock:**
   In `src/dgca/core/dynamics.py` Line 677:
   ```python
   if mode == ExecutionMode.LEARN and origin == EventOrigin.EXTERNAL_DIRECT:
       w.last_referenced_event[cid] = w.global_event_clock
   ```
2. **Non-Mutating Context Gate Validation:**
   In `src/dgca/core/context_gate.py`:
   ```python
   def validate_and_refresh_stable_binding(
       binding: StableBinding,
       w: WState,
       *,
       mutate_stale: bool = False,
   ) -> tuple[bool, StatusCode]:
   ```
   - In `execute_two_pass_event()` (across ALL modes: `LEARN`, `RETRIEVE`, `GENERATE`): always invoked with `mutate_stale = False`.
   - If validation fails, return `(False, StatusCode)`. Gate $G_z^{\text{ctx}}$ closes ($0$), diagnostic is recorded in `r.context_diagnostics`. **Zero mutations are written to `binding.status` during runtime event processing.**
3. **Transactional STALE Transitions in `w_shadow`:**
   - Permanent `STALE` transitions occur strictly at `end_exposure()` during candidate and assembly maintenance passes operating on `w_shadow`.
   - When `self._publication_view` commits, legitimate STALE transitions become permanent atomically.
   - If the root aborts, `w_shadow` is discarded. Permanent $W$ retains zero unauthorized STALE transitions.
4. **Scratch Homeostasis Isolation:**
   In `run_read_only_episode()`:
   - Instantiate scratch state with `h_slow=state.H_slow.clone()`.
   - Caller homeostasis is strictly protected.

---

### 3.2 P2, C01, F01 & Addendum: Surface-to-Feature Mechanical Provenance

#### A. Mechanical Reconstruction & 5-Step Provenance Validation
Prior to neural execution, proposal staging, or journal modification, `process_event()` invokes `validate_event_envelope_provenance(core_event, envelope, projection)`:
1. **Headless Check:**
   If `envelope is None`:
   - If `not allow_headless_events`: raise `ObservationError(code=StatusCode.PROVENANCE_ENVELOPE_MISSING)`.
   - If `allow_headless_events`: return immediately (low-level synthetic test path).
2. **Surface SHA-256 Integrity:**
   `envelope.surface_sha256 == hashlib.sha256(envelope.raw_surface_nfc_utf8.encode('utf-8')).digest()`.
   If false: raise `ObservationError(code=StatusCode.INVALID_SURFACE_HASH)`.
3. **Marker & Reserved Surface Validation:**
   - If `envelope.marker == Marker.EOS`:
     - Assert `envelope.raw_surface_nfc_utf8 == "<EOS>"`.
     - Assert `core_event.boundary == False`.
     - Assert `core_event.event_order > 0` (solitary EOS raises `ObservationError(code=StatusCode.EMPTY_LEXICAL_EXPOSURE)`).
     - Expected features = `EOS_CANONICAL_FEATURES`.
   - If `envelope.marker == Marker.NONE`:
     - Assert `envelope.raw_surface_nfc_utf8 != "<EOS>"` and `"\x1f"` not in raw surface.
     - **Mechanical Derivation:** `expected_features = decompose_lexical_token(envelope.raw_surface_nfc_utf8)` (using frozen Encoder §2.2 rules).
   - If unrecognized marker: raise `ObservationError(code=StatusCode.PROVENANCE_MARKER_MISMATCH)`.
4. **Exact Feature Equality:**
   - Assert `core_event.features == expected_features` (raises `PROVENANCE_FEATURE_COPY_MISMATCH`).
   - Assert `envelope.canonical_features_copy == expected_features` (raises `PROVENANCE_FEATURE_COPY_MISMATCH`).
5. **Bundle Digest Equality:**
   `expected_digest = compute_feature_bundle_digest(expected_features)`
   - Assert `projection.feature_bundle_digest == expected_digest`.
   - Assert `core_event.feature_bundle_digest == expected_digest`.
   - Assert `envelope.feature_bundle_digest == expected_digest` (raises `PROVENANCE_DIGEST_MISMATCH`).

#### B. Insulation of Neural Ranking and LLA
No raw text strings ever enter neural ranking, activation calculation, or LLA wiring. Reconstruction is strictly a cryptographic provenance check. Downstream execution operates entirely on orthogonal sub-token feature tuples.

---

### 3.3 P3, F01 & Addendum: Exact Event Identity Key & Replay Precedence

#### A. Comprehensive Canonical Identity Structures
```python
@dataclass(frozen=True, slots=True)
class CanonicalEnvelopeIdentity:
    """Immutable identity record for a peripheral surface envelope (Core §9.4, Encoder §4)."""
    raw_surface_nfc_utf8: str
    surface_sha256: bytes
    feature_bundle_digest: bytes
    canonical_features_copy: tuple[tuple[str, str], ...]
    marker: Marker

@dataclass(frozen=True, slots=True)
class EventIdentityKey:
    """Comprehensive canonical identity covering both Core neural payload and peripheral envelope."""
    exposure_id: int | None
    event_order: int
    origin: EventOrigin
    boundary: bool
    salience: str
    features: tuple[tuple[str, str], ...]
    feature_bundle_digest: bytes
    observation_scope: ObservationScope
    envelope_identity: CanonicalEnvelopeIdentity | None
```

#### B. Replay & Collision Evaluation Protocol (Error Precedence)
When `core_event.event_order < journal.next_event_order`:
1. **Precedence 1 (Structural Validation):** Execute `validate_event_envelope_provenance()`. Any corrupted or tampered envelope fails fast here.
2. **Precedence 2 (Provenance Alteration):** If existing event was headless and retry attaches an envelope (or vice versa), raise `ObservationError(code=StatusCode.EVENT_RETRY_PROVENANCE_ALTERATION)`.
3. **Precedence 3 (Core Payload Conflict):** If core features, boundary, or salience differ from recorded identity, raise `ObservationError(code=StatusCode.EVENT_RETRY_PAYLOAD_CONFLICT)`.
4. **Precedence 4 (Envelope Identity Conflict):** If envelope raw surface, marker, digest, or feature copy differ from recorded identity, raise `ObservationError(code=StatusCode.EVENT_RETRY_PAYLOAD_CONFLICT)`.
5. **Precedence 5 (Idempotent Return):** If and only if `current_key == recorded_key`, return cached `journal.event_results[core_event.event_order]`. Zero mutations occur.

---

### 3.4 P4, C07, F04 & Addendum: Latent Topology Rollback & Read Immutability

#### A. Rollback Mechanism
In `OpenExposureJournal`, store `latent_table_begin = self.state.W.latent_table.clone()`.
On `abort_exposure()`:
```python
self.state.W.latent_table = journal.latent_table_begin.clone()
```

#### B. Latent Read Immutability (Non-Mutating Virtual Lookup)
In `LatentNeighborhoodTable`, calling `_ensure_cell_materialized(c)` on unmaterialized cells writes to `_slots_by_cell`, causing $\Delta W \ne 0$ during read-only inference.
- Implement `get_slots_read_only(cell_id)`: for any unmaterialized cell, compute local and topographic neighbors virtually on the fly and return without writing to `self._slots_by_cell`.
- In `ExecutionMode.RETRIEVE` and `ExecutionMode.GENERATE`, all latent queries route through read-only virtual lookups.
- Invariant: $\text{set}(W_{\text{pre}}.\text{latent\_table.\_slots\_by\_cell.keys()}) == \text{set}(W_{\text{post}}.\text{latent\_table.\_slots\_by\_cell.keys()})$.

#### C. Memory Overhead & Benchmark Requirement (`BENCH-R2-A01-P4`)
- Asymptotic: $\Theta(M_{\text{mat}} + |R_{\text{coactive}}| + P_{\text{pins}} + W_{\text{logs}})$.
- Benchmark: Execute `benchmarks/bench_r2_a01_p4_latent_scaling.py` across small, medium, and high-occupancy loads to verify 0 bytes net memory leakage across 1,000 abort/commit cycles.

---

### 3.5 P5, C02, C04, C08, F02, F03, F05 & Addendum: Atomic State Publication

#### A. State Ownership Separation & Ledger Status Semantics
- **Neural `WState`:** Pure neural state. Regular class. Zero peripheral envelope/notification storage.
- **Transaction Manager:** Owns `self._publication_view: TransactionPublicationView`.
- **Orchestration Readiness API:**
  - `tx.has_pending_outbox() -> bool`
  - `tx.pending_outbox_count() -> int`
  - `tx.assert_outbox_ready() -> None` (raises `ObservationError(code=StatusCode.OUTBOX_DELIVERY_PENDING)`)
- **Explicit External Reconciliation:**
  `tx.reconcile_outbox(ledger: SurfaceReadoutLedgerV1 | None = None)` executes strictly outside read-only generation.
- **Ledger Status Taxonomy in Generation:**
  - If candidate row is missing or unattested: `ledger.resolve_readout()` returns `StatusCode.READOUT_UNKNOWN`, mapped by generator to `StatusCode.GEN_STOP_READOUT_UNKNOWN`.
  - If ledger is administratively unavailable (`available=False`): `ledger.resolve_readout()` returns `StatusCode.READOUT_UNAVAILABLE`, mapped to `StatusCode.GEN_STOP_READOUT_UNAVAILABLE`.
  - Read-only generation performs zero mutations on `SurfaceReadoutLedgerV1`.

#### B. Single Atomically-Swapped Publication State Reference
```python
@dataclass(frozen=True, slots=True)
class TransactionPublicationView:
    """Single atomically-swapped publication state reference."""
    W: WState
    completed_roots: frozendict[int, EndExposureReport]
    pending_outbox_by_root: frozendict[int, tuple[OutboxNotificationV1, ...]]
    completed_roots_high_watermark: int
    active_exposure_id: int | None
```

In `end_exposure(exposure_id)`:
1. **Preparation Phase (Private Memory):**
   - Candidate settlements and assembly updates computed on `w_shadow`.
   - Outbox notifications built against `w_shadow` and `H_slow`.
   - Construct `new_view = TransactionPublicationView(...)`.
   *Failure here:* `self._publication_view` untouched, root remains `OPEN` (retryable or abortable), ledger untouched.
2. **The Atomic Publication Point:**
   ```python
   # Single reference pointer assignment: atomic under Python runtime
   self._publication_view = new_view
   self.open_journal = None
   ```
   At this single instant, all readers observe the new $W$, completed report, pending outbox batch, and closed active exposure simultaneously.
3. **Post-Commit Peripheral Dispatch Phase:**
   ```python
   if self.readout_ledger is not None and prepared.pending_notifications:
       try:
           self.readout_ledger.consume_outbox_batch(prepared.pending_notifications)
           # Update publication view with cleared pending queue for this root
       except Exception as exc:
           # Root remains COMPLETED. W remains committed. Batch remains in pending view.
           logger.warning("Peripheral dispatch deferred for root %d: %s", exposure_id, exc)
   ```

#### C. Pre-Commit Failure Semantics & Sensory Retention
1. **$S_{\text{pre-begin}}$:** State before root begins.
2. **$S_{\text{pre-end}}$:** Lawful sensory cells admitted during `process_event()` are in `state.W.committed_cells`.
3. **$S_{\text{post-failed-end}}$:** Failure during preparation before commit. Publication view unswapped. Lawful sensory commitments admitted during `process_event()` **remain** in `state.W.committed_cells`. Root is `OPEN` and **retryable** or **abortable**.
4. **$S_{\text{post-abort}}$:** Root aborted. Latent topology and `H_slow` restored. Sensory commitments admitted during `process_event()` **remain** (Core §10.1). High watermark updated. Root is not retryable.

#### D. Precise Durable Persistence Boundaries
In-process commit atomicity guarantees state consistency only within a single running process memory space. It explicitly **cannot** guarantee survivability against:
- Process crash, `SIGKILL`, or OS segfault.
- Host machine power failure.
- Cross-process ledger desynchronization.
- Restart rollforward without disk WAL.
These guarantees are formally designated as the boundary for future R1-B03 (`DurablePersistenceService`).

---

## 4. EXACT FAILURE INJECTION MATRIX (ADDENDUM ALIGNED)

| Failure Point | Timing | Observable $W$ | Observable Root Status | Completed Registry | Pending Outbox | Peripheral Ledger | Client Recovery Action | Linked Tests |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **FP-01** | During `w_shadow` candidate/assembly preparation | Unchanged ($S_{\text{pre-end}}$); sensory cells preserved | `OPEN` | Not present | Not present | 0 attestations | **Eligible to Retry or Abort:** Retry `end_exposure()` or call `abort_exposure()`. | `P5-02` |
| **FP-02** | During outbox batch staging against `w_shadow` | Unchanged ($S_{\text{pre-end}}$); sensory cells preserved | `OPEN` | Not present | Not present | 0 attestations | **Eligible to Retry or Abort:** Retry `end_exposure()` or call `abort_exposure()`. | `P5-02` |
| **FP-03** | During `consume_outbox_batch` (post-publication) | Committed (`w_shadow`) | `COMPLETED` | Present (`EndExposureReport`) | **Present** (`exposure_id` queued) | 0 attestations | **Ineligible to Retry Exposure:** Call `tx.reconcile_outbox(exposure_id, ledger)`. | `P5-03`, `P5-04`, `P5-05` |
| **FP-04** | Transient network or ledger error during `reconcile_outbox` | Committed (`w_shadow`) | `COMPLETED` | Present (`EndExposureReport`) | **Present** (`exposure_id` queued) | Partial / 0 attestations | **Idempotent Retry:** Redrive `tx.reconcile_outbox()`. | `P5-05` |

---

# R2-A01 FINAL ADDENDUM SUBMITTED — AWAITING FREEZE DECISION
