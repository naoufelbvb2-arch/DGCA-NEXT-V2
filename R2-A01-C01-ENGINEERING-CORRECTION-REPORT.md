# DGCA NEXT V2 — R2-A01-C01 ENGINEERING CORRECTION REPORT
## Independent Scientific Verification & Design Remediation Addendum

**Document Version:** 1.0.0  
**Audit Stage:** Design Correction & Ratification (R2-A01-C01)  
**Author:** Principal AI Systems Architect & Independent Scientific Software Verification Engineer  
**Baseline Commit:** `31721fd1ba7559b72d9fe11f037ea0c0d1e91ed2` (`main`)  
**Base Submitted Commit:** `26cce2b066a907d888ba46a34dce487ce573be9b`  
**Current Branch:** `design/r2-a01-c01-contract-corrections`  
**Final Status:** **`R2-A01-C01 DESIGN CORRECTED — AWAITING FINAL FREEZE REVIEW`**  

---

## 1. EXECUTIVE SUMMARY

Following review by the Lead Engineer of the R2-A01 remediation design package, eight specific technical, structural, and architectural inconsistencies were identified. This report documents the comprehensive resolution of every identified issue across all design artifacts.

### Strict Verification Invariant:
> **Zero production code was modified during this assignment.**  
> All work performed on branch `design/r2-a01-c01-contract-corrections` is strictly documentation, test specification, and architectural contract correction.

---

## 2. DETAILED BREAKDOWN OF CORRECTIONS APPLIED

---

### C01: Canonical EOS Provenance & Marker Specification

#### 1. Issue & Previous Defect
The previous design document incorrectly identified EOS events using the predicate `core_event.boundary and '\x1fEOS#0' in features` and referenced a non-existent `Marker.LEXICAL` enum member.

#### 2. Root Cause Analysis
In `src/dgca/encoder/envelope.py`:
- Line 16-20 defines:
  ```python
  class Marker(IntEnum):
      NONE = 0x00
      EOS = 0x01
  ```
  There is NO `Marker.LEXICAL`. Ordinary lexical tokens use `Marker.NONE`.
- Line 160 explicitly specifies:
  `Note: boundary is always False for EOS (cannot be event 0 alone)`.
Using `boundary=True` as an EOS discriminator directly contradicted normative Encoder §1.3.

#### 3. Corrected Design
EOS identity is derived strictly from the canonical reserved feature bundle:
$$\text{Features}(e) \equiv EOS\_CANONICAL\_FEATURES = ((\texttt{"\textbackslash x1fEOS\#0"}, \texttt{"1.000000"}), (\texttt{"\textbackslash x1fEOS\#1"}, \texttt{"0.900000"}), (\texttt{"\textbackslash x1fEOS\#2"}, \texttt{"0.800000"}))$$
Before neural execution, seven mandatory checks are performed:
1. Canonical feature bundle equality.
2. Projection digest equality.
3. Envelope digest equality.
4. Envelope canonical feature copy equality.
5. Marker consistency (`Marker.EOS` if EOS bundle, `Marker.NONE` otherwise).
6. Surface SHA-256 verification.
7. Canonical EOS surface (`"<EOS>"`) and feature consistency with `boundary=False`.

#### 4. Affected Documents
- `R2-A01-REMEDIATION-DESIGN-CONTRACT.md`: Sections §4.2, §5.2.
- `R2-A01-TEST-ACCEPTANCE-MATRIX.md`: Test cases `P2-01`, `P2-02`, `P2-04`, `P2-06`.

---

### C02: Outbox State Ownership & Separation of Concerns

#### 1. Issue & Previous Defect
The previous design proposed adding `pending_outbox_batches: dict[int, tuple[OutboxNotificationV1, ...]]` to `WState` and treated `WState` as a dataclass.

#### 2. Architectural Violations
1. `WState` in `src/dgca/core/state.py` is a regular Python class with `__init__`, NOT a dataclass.
2. Storing `OutboxNotificationV1` and peripheral envelopes in `WState` contaminates the pure neural graph state with peripheral text strings and raw surfaces.
3. Importing `OutboxNotificationV1` in `state.py` creates a circular import risk because `outbox.py` already imports `state.py`.

#### 3. Corrected Design
- `WState` remains 100% pure neural state (zero peripheral imports, zero raw surface texts).
- Pending outbox batches are owned exclusively by `ExposureTransactionManager`:
  ```python
  self._pending_outbox_by_root: dict[int, tuple[OutboxNotificationV1, ...]] = {}
  ```
- Eliminates circular imports entirely and keeps `WState.clone()` completely isolated.

#### 4. Affected Documents
- `R2-A01-REMEDIATION-DESIGN-CONTRACT.md`: Section §5.5, §6.3.
- `R2-A01-IMPLEMENTATION-PLAN.md`: Patch 4.

---

### C03: Transactional STALE Binding Transitions

#### 1. Issue & Previous Defect
The previous design proposed `mutate_stale = (mode == ExecutionMode.LEARN)` in `context_gate.py`. This would mutate `state.W.stable_bindings[z].status = STALE` during event processing in an OPEN root. If the root later aborted, the STALE transition would survive rollback.

#### 2. Corrected Design
1. During runtime event dynamics (`execute_two_pass_event()` across ALL modes: `LEARN`, `RETRIEVE`, `GENERATE`): `validate_and_refresh_stable_binding()` is strictly non-mutating (`mutate_stale=False`). If validation fails, gate closes ($G_z^{\text{ctx}}=0$) and diagnostic is recorded. Permanent $W$ is NOT mutated.
2. Permanent STALE transitions occur strictly at `end_exposure()` on `w_shadow`.
3. If the root commits, `self.state.W = w_shadow` persists the legitimate STALE transition.
4. If the root aborts, `w_shadow` is discarded, and zero STALE transitions persist in $W$.

#### 4. Affected Documents
- `R2-A01-REMEDIATION-DESIGN-CONTRACT.md`: Section §5.1.
- `R2-A01-TEST-ACCEPTANCE-MATRIX.md`: Test cases `P1-02`, `P1-04`.
- `R2-A01-OPEN-DECISIONS.md`: Section §3.1 (Decision 1).

---

### C04: Outbox Reconciliation Policy & Pure Read-Only Guarantee

#### 1. Issue & Previous Defect
Alternative 6A proposed that `run_read_only_episode()` and `generate_episode()` automatically invoke `reconcile_outbox()`. This violated the read-only contract by mutating the peripheral ledger during an inference pass.

#### 2. Corrected Design
1. **D6 6A is formally rejected.**
2. `run_read_only_episode()` and `generate_episode()` are strictly non-mutating on both neural state and peripheral ledger. They NEVER invoke mutating reconciliation.
3. Explicit transaction API: `tx.reconcile_outbox(ledger)`.
4. If an assembly winning readout in `generate_episode()` has pending unreconciled attestations, `ledger.resolve_readout()` returns `StatusCode.READOUT_UNAVAILABLE`. `generate_episode()` cleanly halts with `StatusCode.GEN_STOP_STALE_ASSEMBLY` without mutating state.
5. Pure neural temporal drive computation ($P_T$) in `run_read_only_episode()` remains 100% independent of peripheral ledger delivery.

#### 3. Affected Documents
- `R2-A01-REMEDIATION-DESIGN-CONTRACT.md`: Section §5.5.
- `R2-A01-OPEN-DECISIONS.md`: Section §3.2 (Decision 6).
- `R2-A01-IMPLEMENTATION-PLAN.md`: Patch 4.

---

### C05: Regression Constants, Reference Owners & Test Count Accounting

#### 1. Constants Verified Directly Against Production Source
- $\theta_{\text{read}} = 0.08$ (`src/dgca/core/readout.py:32`, `THETA_READ`)
- $M_{\text{read}} = 0.04$ (`src/dgca/core/readout.py:33`, `M_READ`)
- $\theta_{\text{OB}} = 0.40$ (`src/dgca/core/assembly.py:44`, `THETA_OB`)
- $\rho_{\text{core}} = 0.70$ (`src/dgca/core/assembly.py:42`, `RHO_CORE`)
- $K_R = 12$ (`src/dgca/core/dynamics.py:50`, `K_R_PER_EVENT`)

#### 2. Cold-Start Reference Owner Correction
- $z=8321$: Complete Contextual Owner for Branch $AB$ / Cat (`القط يشرب حليب`).
- $z=8320$: Complete Contextual Owner for Branch $DB$ / Eagle (`النسر يشرب ماء`).
*(Inverted mapping in previous text corrected).*

#### 3. Test Accounting & Premature Label Removal
- In `R2-A01-TEST-ACCEPTANCE-MATRIX.md`, test cases were previously miscounted as 22 (actual 21 rows). The matrix now defines **exactly 25 distinct, numbered acceptance test cases** (`P1-01..P1-04`, `P2-01..P2-08`, `P3-01..P3-04`, `P4-01..P4-05`, `P5-01..P5-04`).
- All premature `RATIFIED` labels have been removed and replaced with `DESIGN CORRECTED — PENDING FINAL FREEZE REVIEW`.

---

### C06: Full Event Identity Key & ObservationError Signature

#### 1. Issue & Previous Defect
The previous `EventIdentityKey` checked only a partial subset of fields, and proposed calls to `ObservationError` used an incorrect argument order (`ObservationError(StatusCode, message)`).

#### 2. Root Cause Analysis
In `src/dgca/common/errors.py`:
```python
class ObservationError(DGCAError):
    def __init__(self, message: str = "", code: StatusCode = StatusCode.INVALID_OBSERVATION) -> None:
        super().__init__(code, message)
```
`ObservationError` requires `(message: str = "", code: StatusCode = ...)`.

#### 3. Corrected Design
1. Comprehensive 12-attribute `EventIdentityKey`:
   - `exposure_id`, `event_order`, `origin`, `boundary`, `salience`, `features`, `feature_bundle_digest`, `observation_scope`, `has_envelope`, `envelope_surface_sha256`, `envelope_marker`, `envelope_features_copy`.
2. All constructor calls use explicit keyword arguments:
   `raise ObservationError(message="...", code=StatusCode.EVENT_RETRY_PAYLOAD_CONFLICT)`.

---

### C07: Latent Snapshot Scaling Complexity & Benchmark Specification

#### 1. Issue & Previous Defect
The previous draft made unsupported universal claims: `<300 cells under all workloads`, `<60 KB under all workloads`, `<0.1 ms`, and `mathematically zero implementation risk`.

#### 2. Corrected Design
- Formal asymptotic scaling specified:
  $$\text{Memory} = \mathcal{O}(M_{\text{mat}} \times 24 \times 8\text{ bytes} + |R_{\text{coactive}}| + P_{\text{pins}} + W_{\text{logs}})$$
  $$\text{Latency} = \mathcal{O}(M_{\text{mat}} + |R_{\text{coactive}}| + P_{\text{pins}} + W_{\text{logs}})$$
- Stress regime analysis: At full materialization ($M_{\text{mat}} = 12{,}288$), footprint scales to $\approx 2.5\text{ MB}$ and $\approx 2.5\text{ ms}$.
- Added formal benchmark requirement `BENCH-R2-A01-P4` across small, medium, high occupancy, and 1,000-cycle ABORT/COMMIT loops.

---

### C08: Commit Publication Boundary & Interruption Semantics

#### 1. Issue & Previous Defect
The previous design assumed consecutive Python assignments create crash-atomic transactions and lacked clear interruption handling.

#### 2. Corrected Design
1. Clearly partitioned phases:
   - Prepare (shadow state in memory)
   - Neural Commit Point (`self.state.W = w_shadow`, status `COMPLETED`, staged into `_pending_outbox_by_root`)
   - Peripheral Dispatch (`consume_outbox_batch`)
   - Acknowledgement (`del _pending_outbox_by_root[exposure_id]`)
2. In-process failure boundary: Delivery failure leaves root `COMPLETED`, never reverting to `OPEN` or `ABORTED`.
3. Clear persistence boundary: In-process atomicity is guaranteed; full cross-process durable recovery is explicitly acknowledged as dependent on R1-B03 (`DurablePersistenceService`).

---

## 3. BACKWARD COMPATIBILITY & HEADLESS MIGRATION MATRIX

| Test Category | Baseline Call Pattern | Migration Requirement | Auditable Behavior |
| :--- | :--- | :--- | :--- |
| **Production Pipeline** | `process_event(core_ev, peripheral_envelope=env)` | `allow_headless_events=False` (Default) | Strict 7-point provenance check; raises `PROVENANCE_ENVELOPE_MISSING` if envelope is None. |
| **Synthetic Baseline Tests** (`tests/test_phase*.py`) | `process_event(core_ev)` (no envelope) | Instantiate with `allow_headless_events=True` | Headless events accepted; produces zero outbox attestations; retroactive envelope attachment rejected. |

---

## 4. VERIFICATION STATUS SUMMARY

| Document | File Path | Status |
| :--- | :--- | :---: |
| Remediation Contract | [`R2-A01-REMEDIATION-DESIGN-CONTRACT.md`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/R2-A01-REMEDIATION-DESIGN-CONTRACT.md) | **CORRECTED** |
| Acceptance Matrix | [`R2-A01-TEST-ACCEPTANCE-MATRIX.md`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/R2-A01-TEST-ACCEPTANCE-MATRIX.md) | **CORRECTED (25 Cases)** |
| Implementation Plan | [`R2-A01-IMPLEMENTATION-PLAN.md`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/R2-A01-IMPLEMENTATION-PLAN.md) | **CORRECTED** |
| Ratified Decisions | [`R2-A01-OPEN-DECISIONS.md`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/R2-A01-OPEN-DECISIONS.md) | **CORRECTED** |
| Engineering Report | [`R2-A01-C01-ENGINEERING-CORRECTION-REPORT.md`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/R2-A01-C01-ENGINEERING-CORRECTION-REPORT.md) | **COMPLETE** |

---

# R2-A01-C01 DESIGN CORRECTED — AWAITING FINAL FREEZE REVIEW
