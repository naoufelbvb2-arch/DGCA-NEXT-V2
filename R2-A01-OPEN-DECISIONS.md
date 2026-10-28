# DGCA NEXT V2 — R2-A01 OPEN DECISIONS (RATIFIED CONTRACT)
## Architectural Decisions & Lead Engineer Final Ratification Record

**Document Version:** 1.2.1  
**Audit Stage:** Final Technical Addendum (R2-A01-ADDENDUM)  
**Author:** Independent Systems Contract Verification Engineer  
**Baseline Commit:** `31721fd1ba7559b72d9fe11f037ea0c0d1e91ed2`  
**Latest Design Commit:** `8a5d299eed294bd98f34bcf5604d2d5b3c3c9ce8`  
**Current Branch:** `design/r2-a01-final-technical-addendum`  
**Status:** **R2-A01 FINAL ADDENDUM SUBMITTED — AWAITING FREEZE DECISION**  

---

## 1. PURPOSE & MANDATE

This document records the final, ratified architectural decisions, binding contractual conditions, and technical addendum alignments issued for stage R2-A01.

In accordance with the Lead Engineer mandate:
> **The architectural design phase is closed. No further architectural reopening is permitted.**  
> All conditions specified herein and in `R2-A01-FINAL-TECHNICAL-ADDENDUM.md` are binding technical invariants incorporated into the final freeze evaluation.

---

## 2. RATIFIED DECISION MATRIX & BINDING CONDITIONS

| Decision ID | Focus Area | Proposed Alternative | Lead Engineer Disposition | Final Binding Contractual Conditions |
| :---: | :--- | :---: | :---: | :--- |
| **D1** | Contextual Binding Validation | **1A** | **APPROVED CONDITIONALLY** | 1. Read-only contextual validation (`RETRIEVE`, `GENERATE`) is 100% non-mutating on permanent $W$.<br>2. During `LEARN` event dynamics, invalid bindings close gates ($G_z^{\text{ctx}}=0$) without mutating permanent $W$ in-place.<br>3. Permanent `STALE` transitions occur strictly through legally committed shadow-state transactions (`w_shadow`) at `END_EXPOSURE`.<br>4. An aborted root retains zero unauthorized `STALE` transitions. |
| **D2** | Digest in `EventExecutionResult` | **2A** | **APPROVED CONDITIONALLY** | 1. Add `feature_bundle_digest: bytes` as an immutable 32-byte field.<br>2. Populated directly from canonical SIC projection.<br>3. Outbox verification asserts strict equality against peripheral envelope digest; silent fallback is permanently eliminated. |
| **D3** | Peripheral Envelope Enforcement | **3B** | **APPROVED CONDITIONALLY** | 1. Default `allow_headless_events = False` (strict provenance mandatory for external language events).<br>2. Headless mode explicitly configured for low-level synthetic tests only.<br>3. Headless events produce zero peripheral outbox attestations.<br>4. Retroactive envelope attachment to headless events is strictly rejected.<br>5. Explicit migration policy provided for baseline tests. |
| **D4** | Event Retry Retroactive Attachment | **4A** | **APPROVED UNCONDITIONALLY** | 1. Exact identical event retry is idempotent.<br>2. Any retry attempting retroactive envelope attachment or payload modification is rejected with `EVENT_RETRY_PROVENANCE_ALTERATION` or `EVENT_RETRY_PAYLOAD_CONFLICT`.<br>3. Zero side-effects on rejected retries. |
| **D5** | Latent Rollback Mechanism | **5A** | **APPROVED CONDITIONALLY** | 1. Pre-exposure snapshot in `OpenExposureJournal` is approved as the mechanism.<br>2. All unsupported universal claims (<300 cells, <60 KB, <0.1 ms under all workloads, zero risk) are removed.<br>3. Asymptotic scaling $\mathcal{O}(M_{\text{mat}} \times 24 + \|R_{\text{coactive}}\|)$ formally specified.<br>4. Verified via benchmark suite `BENCH-R2-A01-P4`. |
| **D6** | Outbox Reconciliation Policy | **6A** | **REJECTED (Revised Policy Adopted)** | **Final Policy:**<br>1. `run_read_only_episode()` does NOT invoke mutating `reconcile_outbox()`.<br>2. `generate_episode()` does NOT mutate peripheral ledger during active generation session.<br>3. Outbox reconciliation is an explicit transactional operation outside neural read-only execution.<br>4. Generation halts safely with `GEN_STOP_READOUT_UNKNOWN` if row is missing/unattested, or `GEN_STOP_READOUT_UNAVAILABLE` if ledger is disabled.<br>5. Pure neural `READ_ONLY_EPISODE` remains 100% independent of peripheral delivery. |
| **D7** | Manifest Generator Location | **7A** | **APPROVED UNCONDITIONALLY** | 1. Committed path: `tools/generate_scientific_manifest.py`.<br>2. Purely repository-relative paths.<br>3. Telemetry derived programmatically from actual execution (no hardcoded numbers).<br>4. Capture Git commit SHA and config hashes.<br>5. Historical forensic reports preserved unchanged. |

---

## 3. TECHNICAL ADDENDUM CONTRACTUAL INTEGRATIONS

### 3.1 Decision 1: Transactional Binding STALE Transitions (Conditioned 1A)
- In `execute_two_pass_event()` (across all modes: `LEARN`, `RETRIEVE`, `GENERATE`): `validate_and_refresh_stable_binding(..., mutate_stale=False)` is used. If validation fails, $G_z^{\text{ctx}}$ evaluates to $0$ (closed gate), and the diagnostic code is appended to `r.context_diagnostics`. Permanent $W$ remains untouched.
- In `end_exposure()`: During candidate and assembly maintenance on `w_shadow`, corrupted active bindings are transitioned to `BindingStatus.STALE` on `w_shadow`.
- When `TransactionPublicationView` is atomically published, legitimate STALE transitions become permanent atomically.
- If `abort_exposure()` is called, `w_shadow` is discarded, and zero STALE transitions persist in $W$.

### 3.2 Decision 6: Revised Outbox Reconciliation & Generation Policy
- **Strict Read-Only Purity:** `run_read_only_episode()` and `generate_episode()` are strictly read-only on both `MachineState` and `SurfaceReadoutLedgerV1`. They never invoke mutating reconciliation.
- **Explicit Transactional Reconciliation:** `ExposureTransactionManager.reconcile_outbox(ledger)` must be invoked explicitly prior to generation.
- **Readout Safety:** If an un-attested assembly wins next-event selection, `ledger.resolve_readout()` returns `StatusCode.READOUT_UNKNOWN`, and generator halts with `StatusCode.GEN_STOP_READOUT_UNKNOWN`. If the ledger itself is disabled, it returns `StatusCode.READOUT_UNAVAILABLE` and halts with `StatusCode.GEN_STOP_READOUT_UNAVAILABLE`.
- **Neural Invariance:** Read-only temporal drive computation ($P_T$) is strictly neural and does not require peripheral reconciliation.

### 3.3 Addendum Clarifications (Technical Closeout)
1. **Mechanical Feature Reconstruction:** Canonical features are derived mechanically from `raw_surface_nfc_utf8` via `decompose_lexical_token()`, defeating surface-substitution attacks while keeping raw text strictly outside neural ranking.
2. **Single Atomic Commit Reference:** Multi-statement assignments are replaced by an atomic swap of `self._publication_view: TransactionPublicationView`, guaranteeing that no observer can see an inconsistent state.
3. **Latent Read Immutability:** `LatentNeighborhoodTable` provides `get_slots_read_only()` to prevent lazy materialization from writing to permanent $W$ during read-only inference.
4. **Glob-Free Execution:** All test execution mandates portable syntax without shell glob reliance.

---

# R2-A01 FINAL ADDENDUM SUBMITTED — AWAITING FREEZE DECISION
