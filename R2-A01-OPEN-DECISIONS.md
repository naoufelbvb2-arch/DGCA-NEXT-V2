# DGCA NEXT V2 — R2-A01 OPEN DECISIONS
## Architectural Trade-offs & Policy Questions Requiring Lead Engineer Ratification

**Document Version:** 1.0.0  
**Phase:** Remediation Specification (R2-A01)  
**Author:** Principal AI Systems Architect & Transaction Systems Engineer  
**Baseline Commit:** `31721fd1ba7559b72d9fe11f037ea0c0d1e91ed2`  
**Design Branch:** `design/r2-a01-transaction-provenance-contract`  
**Status:** **SUBMITTED FOR LEAD ENGINEER APPROVAL**  

---

## 1. PURPOSE

In strict accordance with the R2-A01 mandate, the verification engineer is prohibited from silently making decisions that alter normative semantics, error handling contracts, or system behavior. 

This document enumerates the seven critical design decisions requiring formal approval by the Lead Engineer prior to code implementation.

---

## 2. DECISION MATRIX

---

### DECISION 1: Contextual Binding State Transitions During Read-Only Inference

#### Background
When `evaluate_context_gate_for_cell()` validates a contextual `StableBinding` whose thresholds or links are corrupted, the current implementation mutates `binding.status = BindingStatus.STALE` in permanent `state.W` even during `ExecutionMode.RETRIEVE`.

#### Alternatives:
- **Alternative 1A (Recommended — Mode-Flagged Validation):**  
  Pass `mutate_stale: bool = (mode == ExecutionMode.LEARN)` to `validate_and_refresh_stable_binding()`. In `RETRIEVE` mode, if validation fails, return `(False, StatusCode)` to close the gate for the current event and record the diagnostic, but leave `binding.status` unchanged in permanent $W$. STALE transitions occur only during authorized learning or maintenance transactions.
  - *Pros:* Zero mutation of $W$ during retrieval; zero memory overhead; preserves `RETRIEVE => ΔW = 0`.
  - *Cons:* Corrupted binding remains labeled `ACTIVE` in permanent $W$ until a learning exposure or offline maintenance pass re-evaluates it.
- **Alternative 1B (Copy-on-Read / Deep Scratch):**  
  Deep-clone the entire `state.W` inside `run_read_only_episode()`.
  - *Pros:* Complete decoupling of scratch execution from caller state.
  - *Cons:* Unacceptable CPU and memory overhead on every read-only retrieval call.

#### Engineering Recommendation:
**Alternative 1A.**

---

### DECISION 2: Representation of Feature Bundle Digest in `EventExecutionResult`

#### Background
The peripheral outbox compares the event digest against the envelope digest. Currently, `EventExecutionResult` lacks the digest attribute, causing the comparison to evaluate `getattr(ev, 'feature_bundle_digest', None) is None` and silently bypass verification.

#### Alternatives:
- **Alternative 2A (Recommended — Direct 32-Byte Digest Field):**  
  Add `feature_bundle_digest: bytes` directly to `EventExecutionResult`.
  - *Pros:* Directly satisfies `outbox.py:103`; minimal memory (32 bytes per event); simple and explicit.
  - *Cons:* Minor schema addition to `EventExecutionResult`.
- **Alternative 2B (Reference to ObservationWitness):**  
  Add `witness: ObservationWitness` to `EventExecutionResult` and update `outbox.py` to inspect `ev.witness.feature_digest`.
  - *Pros:* Centralizes all observation metadata in the witness object.
  - *Cons:* Increases coupling between core dynamics and LLA witness structures.

#### Engineering Recommendation:
**Alternative 2A.**

---

### DECISION 3: Policy on Missing Peripheral Envelopes in `process_event()`

#### Background
Under `ExposureTransactionManager.process_event()`, `peripheral_envelope` is optional (`None`). However, external direct language observations must have peripheral provenance for outbox publication.

#### Alternatives:
- **Alternative 3A (Strict Enforcement):**  
  Require `peripheral_envelope is not None` whenever `core_event.origin == EventOrigin.EXTERNAL_DIRECT` and `core_event.modality == Region.LANGUAGE`. If `None`, raise `ObservationError(StatusCode.PROVENANCE_ENVELOPE_MISSING)`.
  - *Pros:* Eliminates un-attested language events; prevents silent omission of outbox notifications.
  - *Cons:* Breaks low-level synthetic tests that intentionally feed synthetic events without envelopes.
- **Alternative 3B (Recommended — Flagged Permissiveness):**  
  Default to strict enforcement; allow missing envelopes only when the transaction manager is explicitly instantiated with `allow_headless_events=True` (used exclusively in synthetic unit tests).
  - *Pros:* Enforces strict provenance in production while preserving unit test flexibility.
  - *Cons:* Requires one additional boolean configuration parameter on `ExposureTransactionManager`.

#### Engineering Recommendation:
**Alternative 3B.**

---

### DECISION 4: Event Retry with Retroactive Envelope Attachment

#### Background
If an event was previously accepted without an envelope (under headless mode), and a subsequent retry provides the same event payload but attaches a `PeripheralSurfaceEnvelopeV1`.

#### Alternatives:
- **Alternative 4A (Recommended — Strict Immutability):**  
  Reject with `ObservationError(StatusCode.EVENT_RETRY_PROVENANCE_ALTERATION)`. An accepted event's provenance cannot be retroactively modified.
  - *Pros:* Strict append-only transaction semantics; prevents out-of-order attestation injections.
  - *Cons:* Client cannot "repair" a missing envelope on retry.
- **Alternative 4B (Permissive Attachment):**  
  Allow the retry to attach the envelope if the event digest matches.
  - *Pros:* Accommodates asynchronous envelope arrival.
  - *Cons:* Violates idempotent replay semantics and introduces state mutations during retries.

#### Engineering Recommendation:
**Alternative 4A.**

---

### DECISION 5: Latent Topology Rollback Implementation Strategy (P4)

#### Background
During an OPEN exposure, coactive latent slots in `state.W.latent_table` are mutated dynamically. `abort_exposure()` must restore the exact pre-exposure latent topology.

#### Alternatives:
- **Alternative 5A (Recommended — Pre-Exposure Snapshot in Journal):**  
  Capture `latent_table_begin = self.state.W.latent_table.clone()` in `OpenExposureJournal` at `begin_exposure()`; restore `self.state.W.latent_table = journal.latent_table_begin.clone()` at `abort_exposure()`.
  - *Complexity:* $\mathcal{O}(M_{\text{mat}})$ where $M_{\text{mat}} \le 300$ cells ($< 60\text{ KB}$, $< 0.1\text{ ms}$).
  - *Pros:* 100% bug-free mathematical guarantee; zero risk of reverse-index desynchronization.
  - *Cons:* Small deep-copy operation at beginning of each root.
- **Alternative 5B (Per-Slot Undo Log):**  
  Record `(owner, slot_idx, old_partner)` before every slot mutation; reverse on abort.
  - *Complexity:* $\mathcal{O}(K_{\text{mutations}})$.
  - *Pros:* Marginally smaller memory overhead.
  - *Cons:* High bug risk; complex reverse-index recalculations; fragile if rollback is interrupted.

#### Engineering Recommendation:
**Alternative 5A.**

---

### DECISION 6: Outbox Pending Delivery Failure Policy During Rollout

#### Background
If peripheral delivery fails after `state.W` has committed, the notifications remain in `WState.pending_outbox_batches`. How should subsequent `generate_episode()` calls behave?

#### Alternatives:
- **Alternative 6A (Recommended — Fail-Fast Reconciliation):**  
  `generate_episode()` and `run_read_only_episode()` automatically invoke `reconcile_outbox()`. If pending batches cannot be delivered (e.g. ledger locked or corrupted), raise `ObservationError(StatusCode.OUTBOX_DELIVERY_PENDING)`.
  - *Pros:* Prevents generating output from an un-reconciled peripheral state; guarantees ledger completeness.
  - *Cons:* Generation is blocked until peripheral delivery is restored.
- **Alternative 6B (Degraded Readout Mode):**  
  Allow generation to proceed; affected assemblies return `StatusCode.READOUT_UNAVAILABLE` when winning.
  - *Pros:* Partial generation possible.
  - *Cons:* Unpredictable generation failures; violates strict deterministic safety.

#### Engineering Recommendation:
**Alternative 6A.**

---

### DECISION 7: Canonical Location for the Deterministic Manifest Generator

#### Background
The scientific manifest generator was previously referenced via a scratch script. It must be committed to the repository for reproducible verification.

#### Alternatives:
- **Alternative 7A (Recommended — `tools/`):**  
  Commit as `tools/generate_scientific_manifest.py`.
  - *Pros:* Follows standard repository conventions for developer tooling and CI verification.
  - *Cons:* None.
- **Alternative 7B (`scripts/`):**  
  Commit as `scripts/generate_scientific_manifest.py`.
  - *Pros:* Also standard.
  - *Cons:* Less distinct from experimental curriculum runners.

#### Engineering Recommendation:
**Alternative 7A.**

---

## 3. SUMMARY OF RECOMMENDATIONS REQUIRING RATIFICATION

| Decision | Topic | Recommended Alternative | Status |
| :---: | :--- | :--- | :---: |
| **D1** | STALE Binding Transition in RETRIEVE | **1A:** Mode-flagged validation (no in-place mutation) | PENDING LEAD RATIFICATION |
| **D2** | Digest in `EventExecutionResult` | **2A:** Direct `feature_bundle_digest: bytes` field | PENDING LEAD RATIFICATION |
| **D3** | Missing Peripheral Envelope Policy | **3B:** Strict by default, `allow_headless` flag for tests | PENDING LEAD RATIFICATION |
| **D4** | Retroactive Envelope Attachment on Retry | **4A:** Strict rejection (`EVENT_RETRY_PROVENANCE_ALTERATION`) | PENDING LEAD RATIFICATION |
| **D5** | Latent Rollback Strategy | **5A:** Pre-exposure snapshot in `OpenExposureJournal` | PENDING LEAD RATIFICATION |
| **D6** | Outbox Pending Failure in Generation | **6A:** Fail-fast reconciliation preflight | PENDING LEAD RATIFICATION |
| **D7** | Manifest Generator Location | **7A:** `tools/generate_scientific_manifest.py` | PENDING LEAD RATIFICATION |

---

# AWAITING LEAD ENGINEER RATIFICATION PRIOR TO R2-A CODE EXECUTION
