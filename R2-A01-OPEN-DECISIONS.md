# DGCA NEXT V2 — R2-A01 OPEN DECISIONS (RATIFIED CONTRACT)
## Architectural Decisions & Lead Engineer Final Ratification Record

**Document Version:** 1.2.0  
**Audit Stage:** R2-A01-C02 Final Freeze Closeout  
**Author:** Principal Systems Architect & Independent Contract Verification Engineer  
**Baseline Commit:** `31721fd1ba7559b72d9fe11f037ea0c0d1e91ed2`  
**Latest Design Commit:** `941288753d1ccdc4da874322690b40eff4829ca4`  
**Current Branch:** `design/r2-a01-c02-final-freeze-closeout`  
**Status:** **RATIFIED DECISIONS FULLY INCORPORATED — FREEZE CANDIDATE**  

---

## 1. PURPOSE & MANDATE

This document records the final, ratified architectural decisions and binding contractual conditions issued by the Lead Engineer for stage R2-A01.

In accordance with the R2-A01-C02 mandate:
> **The architectural design phase is closed. No further architectural reopening is permitted.**  
> All conditions specified herein are binding technical invariants incorporated into the final freeze contract.

---

## 2. RATIFIED DECISION MATRIX & BINDING CONDITIONS

| Decision ID | Focus Area | Proposed Alternative | Lead Engineer Disposition | Final Binding Contractual Conditions |
| :---: | :--- | :---: | :---: | :--- |
| **D1** | Contextual Binding Validation | **1A** | **APPROVED CONDITIONALLY** | 1. Read-only contextual validation (`RETRIEVE`, `GENERATE`) is 100% non-mutating on permanent $W$.<br>2. During `LEARN` event dynamics, invalid bindings close gates ($G_z^{\text{ctx}}=0$) without mutating permanent $W$ in-place.<br>3. Permanent `STALE` transitions occur strictly through legally committed shadow-state transactions (`w_shadow`) at `END_EXPOSURE`.<br>4. An aborted root retains zero unauthorized `STALE` transitions. |
| **D2** | Digest in `EventExecutionResult` | **2A** | **APPROVED CONDITIONALLY** | 1. Add `feature_bundle_digest: bytes` as an immutable 32-byte field.<br>2. Populated directly from canonical SIC projection.<br>3. Outbox verification asserts strict equality against peripheral envelope digest; silent fallback is permanently eliminated. |
| **D3** | Peripheral Envelope Enforcement | **3B** | **APPROVED CONDITIONALLY** | 1. Default `allow_headless_events = False` (strict provenance mandatory for external language events).<br>2. Headless mode explicitly configured for low-level synthetic tests only.<br>3. Headless events produce zero peripheral outbox attestations.<br>4. Retroactive envelope attachment to headless events is strictly rejected.<br>5. Explicit migration policy provided for baseline tests. |
| **D4** | Event Retry Retroactive Attachment | **4A** | **APPROVED UNCONDITIONALLY** | 1. Exact identical event retry is idempotent.<br>2. Any retry attempting retroactive envelope attachment or payload modification is rejected with `EVENT_RETRY_PROVENANCE_ALTERATION` or `EVENT_RETRY_PAYLOAD_CONFLICT`.<br>3. Zero side-effects on rejected retries. |
| **D5** | Latent Rollback Mechanism | **5A** | **APPROVED CONDITIONALLY** | 1. Pre-exposure snapshot in `OpenExposureJournal` is approved as the mechanism.<br>2. All unsupported universal claims (<300 cells, <60 KB, <0.1 ms under all workloads, zero risk) are removed.<br>3. Asymptotic scaling $\mathcal{O}(M_{\text{mat}} \times 24 + \|R_{\text{coactive}}\|)$ formally specified.<br>4. Verified via benchmark suite `BENCH-R2-A01-P4`. |
| **D6** | Outbox Reconciliation Policy | **6A** | **REJECTED (Revised Policy Adopted)** | **Final Policy:**<br>1. `run_read_only_episode()` does NOT invoke mutating `reconcile_outbox()`.<br>2. `generate_episode()` does NOT mutate peripheral ledger during active generation session.<br>3. Outbox reconciliation is an explicit transactional operation outside neural read-only execution.<br>4. Generation halts safely with `GEN_STOP_READOUT_UNAVAILABLE` if required attestations are unreconciled.<br>5. Pure neural `READ_ONLY_EPISODE` remains 100% independent of peripheral delivery. |
| **D7** | Manifest Generator Location | **7A** | **APPROVED UNCONDITIONALLY** | 1. Committed path: `tools/generate_scientific_manifest.py`.<br>2. Purely repository-relative paths.<br>3. Telemetry derived programmatically from actual execution (no hardcoded numbers).<br>4. Capture Git commit SHA and config hashes.<br>5. Historical forensic reports preserved unchanged. |

---

## 3. CONTRACTUAL INTEGRATION DETAILS

### 3.1 Decision 1: Transactional Binding STALE Transitions (Conditioned 1A)
- In `execute_two_pass_event()` (across all modes: `LEARN`, `RETRIEVE`, `GENERATE`): `validate_and_refresh_stable_binding(..., mutate_stale=False)` is used. If validation fails, $G_z^{\text{ctx}}$ evaluates to $0$ (closed gate), and the diagnostic code is appended to `r.context_diagnostics`. Permanent $W$ remains untouched.
- In `end_exposure()`: During candidate and assembly maintenance on `w_shadow`, corrupted active bindings are transitioned to `BindingStatus.STALE` on `w_shadow`.
- When `state.W = w_shadow` commits, legitimate STALE transitions become permanent atomically.
- If `abort_exposure()` is called, `w_shadow` is discarded, and zero STALE transitions persist in $W$.

### 3.2 Decision 6: Revised Outbox Reconciliation & Generation Policy
- **Strict Read-Only Purity:** `run_read_only_episode()` and `generate_episode()` are strictly read-only on both `MachineState` and `SurfaceReadoutLedgerV1`. They never invoke mutating reconciliation.
- **Explicit Transactional Reconciliation:** `ExposureTransactionManager.reconcile_outbox(ledger)` must be invoked explicitly prior to generation.
- **Readout Safety:** If an un-reconciled assembly wins next-event selection, `ledger.resolve_readout()` returns `StatusCode.READOUT_UNAVAILABLE`. `generate_episode()` cleanly halts with `StatusCode.GEN_STOP_READOUT_UNAVAILABLE` without corrupting state.
- **Neural Invariance:** Read-only temporal drive computation ($P_T$) is strictly neural and does not require peripheral reconciliation.

---

# RATIFIED DECISIONS FULLY INCORPORATED — FREEZE CANDIDATE
