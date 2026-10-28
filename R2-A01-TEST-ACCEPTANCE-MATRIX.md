# DGCA NEXT V2 — R2-A01 TEST ACCEPTANCE MATRIX
## Formal Verification & Acceptance Criteria for Transaction & State Remediation

**Document Version:** 1.0.0  
**Audit Stage:** Remediation Design Contract (R2-A01)  
**Author:** Scientific Software Verification Engineer & Transaction Systems Architect  
**Baseline Commit:** `31721fd1ba7559b72d9fe11f037ea0c0d1e91ed2`  
**Design Branch:** `design/r2-a01-transaction-provenance-contract`  
**Status:** **SUBMITTED FOR SPECIFICATION REVIEW**  

---

## 1. PURPOSE & PRINCIPLES

This document defines the exact, executable acceptance criteria for every test scenario covering the five remediation areas (P1 through P5) and the 12 cross-cutting scientific regression gates.

### Core Testing Invariants:
1. **Zero Silent Degradation:** An architectural repair must never silently compromise existing valid neural dynamics or empirical gates.
2. **Deterministic Rejection:** Any forbidden operation must fail fast with an explicit `StatusCode` and leave all machine states byte-for-byte identical to their pre-operation state.
3. **No Fixture Leaks:** Tests must operate on canonical machine instances and authentic mathematical representations.

---

## 2. ACCEPTANCE MATRIX TABLE

| Test ID | Area | Initial State | Operation | Injected Failure / Fault Condition | Expected State Transition | Forbidden State Transition | Exact Acceptance Condition | Required Evidence |
| :--- | :---: | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **P1-01** | `RETRIEVE` Immutability | Trained `MachineState` with committed cells & synapses; hash $H_0$ recorded. | `run_read_only_episode()` with legal canonical prompt events. | None. | Output `ReadOnlyEpisodeResult` returned; $R_{\text{caller}}$ unchanged. | $\Delta W \ne 0$, or $\Delta H_{\text{slow}} \ne 0$, or $R_{\text{caller}} \ne R_0$. | $\text{Hash}(W_{\text{post}}) == H_0$; $W.\text{last\_referenced\_event}$ unchanged for all cells. | Pre/post SHA-256 of serialized $W$ structures match exactly. |
| **P1-02** | Stale Binding Isolation | `MachineState` containing a corrupted `StableBinding` (e.g. invalid thresholds). | `run_read_only_episode()` evaluating cell $z$. | Corrupted binding evaluated by `evaluate_context_gate_for_cell()`. | Gate closes ($G_z^{\text{ctx}} = 0$); diagnostic `INVALID_CONTEXT_THRESHOLD` appended to result. | `binding.status` mutated to `STALE` in permanent $W$. | `binding.status == BindingStatus.ACTIVE` in $W$; result contains diagnostic code; $W$ hash unchanged. | Assertion `state.W.stable_bindings[z].status == BindingStatus.ACTIVE`. |
| **P1-03** | Homeostasis Isolation | `MachineState` with specific slow adaptation values $H_{\text{slow}}^0$. | `run_read_only_episode()` with repeated input sequence. | None. | Scratch evaluation completes; caller homeostasis untouched. | Any element of `state.H_slow` modified. | `state.H_slow == H_slow_0`. | Direct comparison of all threshold dictionaries and target arrays. |
| **P2-01** | Provenance Acceptance | Clean `ExposureTransactionManager` with OPEN root. | `process_event(core_ev, peripheral_envelope=matching_env)` | Canonical matching lexical event and envelope. | Event processed; witness and envelope recorded in journal. | Event rejected; or envelope discarded. | `res.event_order == 0`; `journal.event_results[0].feature_bundle_digest == envelope.feature_bundle_digest`. | Digest equality assertion; outbox receives notification. |
| **P2-02** | Canonical EOS Acceptance | Clean `ExposureTransactionManager` with OPEN root. | `process_event(core_ev, peripheral_envelope=eos_env)` | Canonical EOS event with `\x1fEOS#0..2` and `Marker.EOS`. | Event processed; recorded with `Marker.EOS`. | Event converted to lexical or rejected. | `res.feature_bundle_digest == eos_env.feature_bundle_digest`; envelope marker preserved. | Outbox notification contains `Marker.EOS`. |
| **P2-03** | Digest Mismatch Rejection | OPEN root in `ExposureTransactionManager`. | `process_event(core_ev, peripheral_envelope=mismatched_env)` | Envelope contains digest differing from CoreEvent / SIC projection. | Exception `ObservationError(PROVENANCE_DIGEST_MISMATCH)` raised. | Event accepted; journal advanced; partial $W$ change. | `next_event_order == 0`; `len(journal.event_results) == 0`; $W$ untouched. | Assert exception code; assert journal is empty. |
| **P2-04** | Marker Mismatch Rejection | OPEN root in `ExposureTransactionManager`. | `process_event(core_ev, peripheral_envelope=lexical_env_with_eos_marker)` | Envelope marker is `Marker.EOS` but CoreEvent has ordinary lexical features. | Exception `ObservationError(PROVENANCE_MARKER_MISMATCH)` raised. | Event accepted; or marker overwritten. | `next_event_order` unincremented; zero proposals staged. | Catch exception; verify root state unchanged. |
| **P2-05** | Surface Hash Rejection | OPEN root in `ExposureTransactionManager`. | `process_event(core_ev, peripheral_envelope=bad_hash_env)` | `surface_sha256 != sha256(raw_surface)`. | Exception `ObservationError(INVALID_SURFACE_HASH)` raised. | Corrupted envelope recorded in journal. | Pre-event machine state identical to post-rejection state. | Hash verification failure caught; zero side-effects. |
| **P2-06** | Outbox Verification | OPEN root in `ExposureTransactionManager`. | `end_exposure(root_id)` after processing canonical events. | None. | `build_end_exposure_outbox_notifications` verifies `ev.feature_bundle_digest == envelope.feature_bundle_digest`. | Outbox skips check or returns `None` for digest. | All published notifications have valid digests matching envelopes. | Notification digest assertion for every emitted notification. |
| **P3-01** | Exact Idempotent Replay | OPEN root with event 0 already processed. | Re-send identical `core_event` (order 0) with matching payload & envelope. | Duplicate network / process event delivery. | Returns cached `EventExecutionResult` without re-processing. | Re-execution; duplicate proposal staging; altered $H_{\text{slow}}$. | `len(journal.event_results) == 1`; `journal.next_proposal_ordinal` unchanged. | Identical return object identity; proposal count unchanged. |
| **P3-02** | Payload Conflict Rejection | OPEN root with event 0 processed. | Send event 0 with altered features or salience. | Malformed retry or conflicting event order. | Exception `ObservationError(EVENT_RETRY_PAYLOAD_CONFLICT)` raised. | Overwrites event 0; or silently returns cached result of different payload. | Cached event 0 preserved; journal unchanged; exception caught. | Verify original witness unchanged in journal. |
| **P3-03** | Provenance Alteration Rejection | OPEN root with event 0 processed without envelope. | Send event 0 with peripheral envelope attached. | Retry attempting retroactive provenance assignment. | Exception `ObservationError(EVENT_RETRY_PROVENANCE_ALTERATION)` raised. | Envelope attached retroactively to existing witness. | `journal.peripheral_envelopes_by_order` still has no entry for order 0. | Verify envelope dictionary remains empty. |
| **P4-01** | Abort Sensory Preservation | OPEN root where uncommitted sensory cells are admitted ($K_R$). | `abort_exposure(root_id)`. | Intentional exposure abortion. | Root status `ABORTED`; newly committed sensory cells remain in $W$. | Sensory cells erased from `W.committed_cells`. | Newly committed cells $\subset W.\text{committed\_cells}$; high watermark updated. | Cell commitment status verified in $W$. |
| **P4-02** | Abort Latent Slot Rollback | OPEN root where coactive slots are assigned / recycled; baseline slots $L_0$. | `abort_exposure(root_id)`. | Root aborted after 100+ coactive slot mutations. | `W.latent_table` restored to exact $L_0$ snapshot. | Coactive slot mutations survive in $W$. | For all cells $c$ and slots $s$, $L_{\text{post}}(c, s) == L_0(c, s)$. | Slot-by-slot equality assertion against baseline. |
| **P4-03** | Abort Reverse-Index Symmetry | OPEN root with coactive slot additions modifying reverse index $R_0$. | `abort_exposure(root_id)`. | Root aborted. | `_coactive_reverse_index` restored to exact $R_0$. | Orphaned reverse index entries remain in table. | `_coactive_reverse_index == R_0`. | Exact dictionary and set equality assertion. |
| **P4-04** | Duplicate Abort Safety | Root already in `aborted_roots`. | Call `abort_exposure(root_id)` again. | Duplicate client abort call. | Returns `ExposureStatus.ABORTED` safely without mutation. | Exception raised; or later roots overwritten. | Return value is `ABORTED`; machine state identical. | Idempotent return assertion. |
| **P4-05** | Multi-Root Rollback Integrity | Roots 1..2 completed; Root 3 aborts; Root 4 completes. | Sequential transactions. | Root 3 aborts midway. | Root 1, 2, and 4 states intact; Root 3 changes completely erased. | Root 3 latent links bleed into Root 4. | Latent table at Root 4 reflects only Roots 1, 2, and 4. | Forensic audit of latent partners across roots. |
| **P5-01** | Atomic Publication Success | Valid OPEN root with peripheral envelopes. | `end_exposure(root_id)`. | Normal execution. | $W$ committed; outbox batch delivered to ledger; pending queue cleared. | Ledger updated before $W$; or pending queue left full. | Root status `COMPLETED`; ledger has attestations; `pending_outbox_batches` is empty. | Ledger external count increased; pending queue empty. |
| **P5-02** | Pre-Commit Failure Isolation | Valid OPEN root with peripheral envelopes. | `end_exposure(root_id)`. | Injected exception during candidate or assembly finalization before $W$ swap. | Transaction aborted; $W$ not committed; zero attestations delivered to ledger. | Partial attestations leak into peripheral ledger. | Ledger has zero entries for `root_id`; $W$ unchanged. | Ledger query for `root_id` returns no attestations. |
| **P5-03** | Post-Commit Delivery Resilience | Valid OPEN root with peripheral envelopes. | `end_exposure(root_id)`. | Injected exception during `consume_outbox_batch()`. | $W$ committed; root `COMPLETED`; batch stored in `W.pending_outbox_batches`. | $W$ rolled back; or un-delivered notifications lost. | Root is `COMPLETED`; batch present in pending queue; reconcilable. | Assert `exposure_id in state.W.pending_outbox_batches`. |
| **P5-04** | Pending Batch Reconciliation | State with pending outbox batch from P5-03. | `reconcile_outbox()`. | Recovery call. | Pending batch delivered to ledger; queue cleared. | Batch dropped; or duplicate delivery error. | Ledger receives notifications; `pending_outbox_batches` cleared. | Ledger resolution succeeds after reconciliation. |

---

## 3. CROSS-CUTTING SCIENTIFIC REGRESSION GATES

Every candidate implementation of R2-A01 must successfully pass the following 12 gates without threshold relaxation or test modification:

1. **GATE-REG-01 (76-Test Production Baseline):** All 76 existing unit and integration tests in `tests/test_*.py` must pass with 0 failures.
2. **GATE-REG-02 (Cold-Start Dual Owners):** Roots 34 and 56 must graduate distinct complete owners $z=8320$ ($AB$) and $z=8321$ ($DB$) with active stable bindings.
3. **GATE-REG-03 (Next-Word Generation):** Prompt `['القط', 'يشرب']` must emit `"حليب"`; Prompt `['النسر', 'يشرب']` must emit `"ماء"`.
4. **GATE-REG-04 (Canonical EOS Learning):** Training with canonical EOS must form native Assemblies with `Marker.EOS`.
5. **GATE-REG-05 (Cat Branch Autonomous Rollout):** Prompt `['القط']` must autonomously emit `('يشرب', 'حليب')` and cleanly halt with `StatusCode.GEN_STOP_EOS`.
6. **GATE-REG-06 (Preservation of Eagle Collision):** Prompt `['النسر']` must emit `('يشرب', 'ماء')` and halt with `StatusCode.GEN_STOP_AMBIGUOUS` (preserving evidence of R1-M01 until R2-B).
7. **GATE-REG-07 (Exact Retrieval Immutability):** Hash of $W$ before and after 100 read-only episodes must be identical down to the byte.
8. **GATE-REG-08 (Provenance Rejection Zero-Bleed):** Rejecting a corrupted envelope must leave all open journal structures and machine state completely untouched.
9. **GATE-REG-09 (Outbox Atomicity Under Fault):** Outbox failure injection before commit must result in 0 attestations in the peripheral ledger.
10. **GATE-REG-10 (Latent Topology Abort Invariant):** 100% of latent slots and reverse index entries created during an aborted root must be restored.
11. **GATE-REG-11 (Deterministic Replay):** Exact duplicate event retries must return cached results in identical order.
12. **GATE-REG-12 (No Production Threshold Drift):** All constants ($\theta_{\text{read}}=0.08$, $\Delta_{\text{read}}=0.02$, $\theta_{\text{OB}}=0.40$, $K_R=12$, $\rho_{\text{core}}=0.70$) remain byte-for-byte unchanged.

---

# R2-A01 ACCEPTANCE MATRIX RATIFIED
