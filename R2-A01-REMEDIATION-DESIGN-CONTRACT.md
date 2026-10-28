# DGCA NEXT V2 — R2-A01 REMEDIATION DESIGN CONTRACT (FINAL FREEZE CANDIDATE)
## Transaction Integrity, Provenance & State Atomicity Architecture

**Document Version:** 1.2.0  
**Audit Stage:** Final Engineering Freeze Closeout (R2-A01-C02)  
**Author:** Principal Systems Architect & Independent Contract Verification Engineer  
**Status:** **R2-A01-C02 FREEZE CANDIDATE — READY FOR LEAD ENGINEER RATIFICATION**  
**Repository Baseline Commit:** `31721fd1ba7559b72d9fe11f037ea0c0d1e91ed2` (`main`)  
**Base Submitted Commit:** `941288753d1ccdc4da874322690b40eff4829ca4`  
**Current Branch:** `design/r2-a01-c02-final-freeze-closeout`  

---

## 1. EXECUTIVE SUMMARY & FREEZE MANDATE

This contract specifies the final, implementable architectural remediation design for the transaction integrity, state immutability, event provenance, and outbox atomicity defects confirmed during forensic investigations R1-F01, R1-F02, and R1-F02-C01.

This closeout incorporates all final contractual corrections mandated in review R2-A01-C02, including:
1. Complete canonical envelope identity within `EventIdentityKey` and pre-replay provenance re-validation.
2. Formal separation between private transaction pending outbox queues and pure neural read-only generation.
3. A single, indivisible in-process atomic commit boundary with explicit interruption semantics.
4. Rigorous analytical decomposition of latent snapshot memory and benchmark requirements.
5. Exact 4-state lifecycle semantics for pre-commit failures and sensory preservation.

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
   - If the root commits, `self.state.W = w_shadow` persists the legitimate STALE transitions atomically.
   - If the root aborts, `w_shadow` is discarded. Permanent $W$ retains zero unauthorized STALE transitions.
4. **Scratch Homeostasis Isolation:**
   In `run_read_only_episode()`:
   - Instantiate scratch state with `h_slow=state.H_slow.clone()`.
   - Caller homeostasis is strictly protected.

---

### 3.2 P2, C01 & F01: Event/Envelope Provenance & Exact EOS Identity

#### A. The Seven Mandatory Pre-Execution Provenance Checks
Prior to neural execution, proposal staging, or journal modification, `process_event()` invokes `validate_event_envelope_provenance(core_event, envelope, projection)`:
1. **Check 1 (Feature Bundle Identity):**
   Compare `core_event.features` against `EOS_CANONICAL_FEATURES` ($((\texttt{"\textbackslash x1fEOS\#0"}, \texttt{"1.000000"}), (\texttt{"\textbackslash x1fEOS\#1"}, \texttt{"0.900000"}), (\texttt{"\textbackslash x1fEOS\#2"}, \texttt{"0.800000"}))$).
   - If matching: event is canonical EOS.
   - If not matching: features must NOT contain reserved byte `\x1f`.
2. **Check 2 (Projection Digest Equality):**
   `projection.feature_bundle_digest == core_event.feature_bundle_digest`.
3. **Check 3 (Envelope Digest Equality):**
   `envelope.feature_bundle_digest == core_event.feature_bundle_digest`.
4. **Check 4 (Canonical Feature Copy Integrity):**
   `envelope.canonical_features_copy == core_event.features`.
5. **Check 5 (Marker Consistency):**
   - Canonical EOS: `envelope.marker == Marker.EOS` ($0\text{x}01$).
   - Lexical event: `envelope.marker == Marker.NONE` ($0\text{x}00$).
6. **Check 6 (Surface SHA-256 Verification):**
   `envelope.surface_sha256 == hashlib.sha256(envelope.raw_surface_nfc_utf8.encode('utf-8')).digest()`.
7. **Check 7 (EOS Surface & Boundary Consistency):**
   If `envelope.marker == Marker.EOS`:
   - `envelope.raw_surface_nfc_utf8 == "<EOS>"`.
   - `core_event.boundary == False` (cannot be event_order 0 alone; raises `ObservationError(code=StatusCode.EMPTY_LEXICAL_EXPOSURE)` if violated).

#### B. Populating `EventExecutionResult.feature_bundle_digest` (D2)
Add `feature_bundle_digest: bytes` to `EventExecutionResult`. In `execute_two_pass_event()`, assign directly from `projection.feature_bundle_digest`. In `outbox.py:104`, assert `ev.feature_bundle_digest == envelope.feature_bundle_digest`.

---

### 3.3 P3 & F01: Exact Event Identity Key & Replay Validation

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

#### B. Replay & Collision Evaluation Protocol
When `core_event.event_order < journal.next_event_order`:
1. **Mandatory Full Provenance Validation:** Incoming event and envelope MUST undergo complete structural validation `validate_event_envelope_provenance()` first.
2. **Identity Comparison:** Construct `current_key` and compare against `journal.event_identities[core_event.event_order]`.
3. **Rejection Semantics:**
   - If core payload fields differ: raise `ObservationError("Payload conflict on retry", code=StatusCode.EVENT_RETRY_PAYLOAD_CONFLICT)`.
   - If envelope digest, marker, features copy, or raw surface differ: raise `ObservationError("Envelope conflict on retry", code=StatusCode.EVENT_RETRY_PAYLOAD_CONFLICT)`.
   - If original was headless and retry attaches envelope: raise `ObservationError("Cannot retroactively attach envelope", code=StatusCode.EVENT_RETRY_PROVENANCE_ALTERATION)`.
4. **Idempotent Return:** If and only if `current_key == recorded_key`, return `journal.event_results[core_event.event_order]`. Zero mutations occur.

---

### 3.4 P4, C07 & F04: Latent Topology Rollback & Scaling Benchmark

#### A. Rollback Mechanism
In `OpenExposureJournal`, store `latent_table_begin = self.state.W.latent_table.clone()`.
On `abort_exposure()`:
```python
self.state.W.latent_table = journal.latent_table_begin.clone()
```

#### B. Memory Overhead & Scaling Decomposition
1. **Asymptotic Complexity:**
   $$\text{Time} = \Theta(M_{\text{mat}} + |R_{\text{coactive}}| + P_{\text{pins}} + W_{\text{logs}})$$
   $$\text{Memory} = \Theta(M_{\text{mat}} \times 24 \times 8\text{ bytes} + |R_{\text{coactive}}| + P_{\text{pins}} + W_{\text{logs}})$$
2. **Theoretical Minimum Payload:**
   - Raw slot integers: $M_{\text{mat}} \times 24 \times 2\text{ bytes} = 48 \times M_{\text{mat}}\text{ bytes}$ ($14.4\text{ KB}$ for 300 cells; $589.8\text{ KB}$ for 12,288 cells).
3. **Python 64-bit Object Overhead:**
   - List header + pointers: $\approx 440\text{ bytes/cell}$. Dict entry: $\approx 64\text{ bytes/cell}$. Total per cell: $\approx 504\text{ bytes}$.
   - Dict of sets (`_coactive_reverse_index`): $\approx 216\text{ bytes/set} + 8\text{ bytes/entry}$.
   - Estimated overhead for 56-root curriculum ($M_{\text{mat}} \approx 250..300$): $\approx 200..350\text{ KB}$.
   - Full materialization stress ($M_{\text{mat}} = 12{,}288$, 6 links/cell): $\approx 8..15\text{ MB}$.
4. **Benchmark Verification Requirement (`BENCH-R2-A01-P4`):**
   No fixed latency or memory guarantees are asserted prior to execution. Patch 3 requires execution of `BENCH-R2-A01-P4` to measure actual memory usage and latency on the target Python 3.14 environment across small, medium, and high-occupancy loads, verifying zero leakage over 1,000 abort/commit cycles.

---

### 3.5 P5, C02, C04, C08, F02, F03, F05: Coherent In-Process Commit & Outbox Architecture

#### A. State Ownership Separation (C02 & F02)
- **Neural `WState`:** Pure neural state. Regular class. Zero peripheral envelope/notification storage.
- **Transaction Manager:** Owns `self._pending_outbox_by_root: dict[int, tuple[OutboxNotificationV1, ...]]`.
- **Orchestration Readiness API:**
  - `tx.has_pending_outbox() -> bool`
  - `tx.pending_outbox_count() -> int`
  - `tx.assert_outbox_ready() -> None` (raises `ObservationError(code=StatusCode.OUTBOX_DELIVERY_PENDING)`)
- **Explicit External Reconciliation:**
  `tx.reconcile_outbox(ledger: SurfaceReadoutLedgerV1 | None = None) -> tuple[int, list[StatusCode]]` executes outside read-only generation.
- **Generator Isolation:** `generate_episode()` never mutates the ledger. If winning assembly is not found in ledger, `ledger.resolve_readout()` returns `StatusCode.READOUT_UNAVAILABLE`, which generator maps to `StatusCode.GEN_STOP_READOUT_UNAVAILABLE`.

#### B. Coherent In-Process Commit Sequence (F03)
```python
@dataclass(frozen=True, slots=True)
class PreparedRootCommit:
    exposure_id: int
    w_shadow: WState
    end_report: EndExposureReport
    pending_notifications: tuple[OutboxNotificationV1, ...]
```
In `end_exposure(exposure_id)`:
1. **Preparation Phase (Private Memory):**
   - Candidate settlements and assembly updates computed on `w_shadow`.
   - Outbox notifications built against `w_shadow` and `H_slow`.
   - `PreparedRootCommit` created.
   *Failure here:* `self.state.W` untouched, root remains `OPEN` (retryable or abortable), ledger untouched.
2. **Synchronized In-Process Commit Boundary:**
   ```python
   # THE ATOMIC IN-PROCESS COMMIT POINT
   self.state.W = prepared.w_shadow
   self.completed_roots[exposure_id] = prepared.end_report
   self._pending_outbox_by_root[exposure_id] = prepared.pending_notifications
   journal.status = ExposureStatus.COMPLETED
   self.state.W.completed_roots_high_watermark = max(self.state.W.completed_roots_high_watermark, exposure_id)
   self.open_journal = None
   ```
3. **Post-Commit Peripheral Dispatch Phase:**
   ```python
   if self.readout_ledger is not None and prepared.pending_notifications:
       try:
           self.readout_ledger.consume_outbox_batch(prepared.pending_notifications)
           del self._pending_outbox_by_root[exposure_id]
       except Exception as exc:
           # Root remains COMPLETED. W remains committed.
           # Batch stays in _pending_outbox_by_root for later idempotent reconciliation.
           logger.warning("Peripheral dispatch deferred for root %d: %s", exposure_id, exc)
   ```

#### C. Pre-Commit Failure Semantics & Sensory Retention (F05)
1. **$S_{\text{pre-begin}}$:** State before root begins.
2. **$S_{\text{pre-end}}$:** Lawful sensory cells admitted during `process_event()` are in `state.W.committed_cells`.
3. **$S_{\text{post-failed-end}}$:** Failure during preparation before commit. `self.state.W` not swapped. Lawful sensory commitments admitted during `process_event()` **remain** in `state.W.committed_cells`. Root is `OPEN` and **retryable** or **abortable**.
4. **$S_{\text{post-abort}}$:** Root aborted. `latent_table` and `H_slow` restored. Sensory commitments admitted during `process_event()` **remain** (Core §10.1). High watermark updated. Root is not retryable.

---

## 4. EXACT FAILURE INJECTION MATRIX (F03)

| Failure Point | Timing | Observable $W$ | Observable Root Status | Completed Registry | Pending Outbox | Peripheral Ledger | Retry Eligibility |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **FP-01** | During `w_shadow` assembly updates (pre-commit) | Unchanged ($S_{\text{pre-end}}$); sensory cells preserved | `OPEN` | Not present | Not present | 0 attestations | **Eligible** (Retry `end_exposure` or call `abort_exposure`) |
| **FP-02** | During outbox batch staging (pre-commit) | Unchanged ($S_{\text{pre-end}}$); sensory cells preserved | `OPEN` | Not present | Not present | 0 attestations | **Eligible** (Retry `end_exposure` or call `abort_exposure`) |
| **FP-03** | During `consume_outbox_batch` (post-commit) | Committed (`w_shadow`) | `COMPLETED` | Present (`EndExposureReport`) | **Present** (`exposure_id` queued) | 0 attestations | **Ineligible** (Root committed; reconcile via `tx.reconcile_outbox()`) |
| **FP-04** | Partial notification delivery in ledger (post-commit) | Committed (`w_shadow`) | `COMPLETED` | Present (`EndExposureReport`) | **Present** (`exposure_id` queued) | Partial attestations | **Ineligible** (Root committed; redelivery is idempotent via unique keys) |

---

# R2-A01-C02 FREEZE CANDIDATE — READY FOR LEAD ENGINEER RATIFICATION
