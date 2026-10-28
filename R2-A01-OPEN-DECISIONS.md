# DGCA NEXT V2 — R2-A01 OPEN DECISIONS (RATIFIED ADDENDUM)
## Architectural Decisions & Lead Engineer Ratification Record

**Document Version:** 1.1.0  
**Audit Stage:** R2-A01-C01 Contract Correction  
**Author:** Principal AI Systems Architect & Transaction Systems Engineer  
**Baseline Commit:** `31721fd1ba7559b72d9fe11f037ea0c0d1e91ed2`  
**Base Submitted Commit:** `26cce2b066a907d888ba46a34dce487ce573be9b`  
**Current Branch:** `design/r2-a01-c01-contract-corrections`  
**Status:** **RATIFIED DECISIONS DOCUMENTED — PENDING FINAL FREEZE REVIEW**  

---

## 1. PURPOSE & MANDATE

This document records the formal review outcomes and binding architectural conditions issued by the Lead Engineer for the seven design decisions proposed in stage R2-A01.

In accordance with the R2-A01-C01 mandate:
> **Conditional approval does NOT constitute unrestricted implementation authorization.**  
> All conditions specified herein are mandatory technical invariants that must be incorporated into the remediation design contract, test matrix, and implementation plan before engineering freeze.

---

## 2. RATIFIED DECISION MATRIX & BINDING CONDITIONS

| Decision ID | Focus Area | Proposed Alternative | Lead Engineer Disposition | Binding Mandatory Conditions |
| :---: | :--- | :---: | :---: | :--- |
| **D1** | Contextual Binding Validation | **1A** | **APPROVE CONDITIONALLY** | 1. Read-only contextual validation (`RETRIEVE`, `GENERATE`) must be 100% non-mutating on permanent $W$.<br>2. During `LEARN`, invalid bindings must close their gates safely without mutating permanent $W$ in-place.<br>3. Permanent `STALE` transitions must occur strictly through an authorized, legally committed shadow-state transaction (`w_shadow`) at `END_EXPOSURE`.<br>4. An aborted root must retain zero unauthorized `STALE` transitions. |
| **D2** | Digest in `EventExecutionResult` | **2A** | **APPROVE CONDITIONALLY** | 1. Add `feature_bundle_digest: bytes` as an immutable 32-byte field.<br>2. Must be populated directly from canonical SIC projection.<br>3. Outbox verification must strictly assert digest equality against peripheral envelopes; the silent `None` fallback is permanently eliminated. |
| **D3** | Peripheral Envelope Enforcement | **3B** | **APPROVE CONDITIONALLY** | 1. Default `allow_headless_events = False` (strict provenance mandatory for external language events).<br>2. Headless mode must be explicitly configured and auditable.<br>3. Headless events produce zero peripheral outbox attestations.<br>4. Retroactive envelope attachment to headless events is strictly rejected.<br>5. Explicit migration policy for existing baseline tests must be provided. |
| **D4** | Event Retry Retroactive Attachment | **4A** | **APPROVE UNCONDITIONALLY** | 1. Exact identical event retry is idempotent.<br>2. Any retry attempting retroactive envelope attachment or payload modification must be rejected with `EVENT_RETRY_PROVENANCE_ALTERATION` or `EVENT_RETRY_PAYLOAD_CONFLICT`.<br>3. Zero side-effects on rejected retries. |
| **D5** | Latent Rollback Mechanism | **5A** | **APPROVE CONDITIONALLY** | 1. Pre-exposure snapshot in `OpenExposureJournal` is approved as the mechanism.<br>2. Remove all unsupported universal claims (<300 cells, <60 KB, <0.1 ms under all workloads, zero risk).<br>3. Specify asymptotic scaling $\mathcal{O}(M_{\text{mat}} \times 24 + \|R_{\text{coactive}}\|)$.<br>4. Add benchmark suites for small, medium, high occupancy curricula, and repeated abort/commit loops. |
| **D6** | Outbox Reconciliation Policy | **6A** | **REJECTED AS SUBMITTED** | **New Ratified Policy Adopted:**<br>1. `run_read_only_episode()` must NOT invoke mutating `reconcile_outbox()`.<br>2. `generate_episode()` must NOT mutate peripheral ledger during active generation session.<br>3. Outbox reconciliation must be an explicit transactional operation outside neural read-only execution.<br>4. Generation fails safely with `READOUT_UNAVAILABLE` or `GEN_STOP_STALE_ASSEMBLY` if required attestations are unreconciled.<br>5. Pure neural `READ_ONLY_EPISODE` remains 100% independent of peripheral delivery. |
| **D7** | Manifest Generator Location | **7A** | **APPROVE UNCONDITIONALLY** | 1. Committed path: `tools/generate_scientific_manifest.py`.<br>2. Purely repository-relative paths.<br>3. Telemetry derived programmatically from actual execution (no hardcoded numbers).<br>4. Capture Git commit SHA and config hashes.<br>5. Historical forensic reports preserved unchanged. |

---

## 3. DETAILED ANALYSIS OF REVISED DECISIONS

### 3.1 Decision 1: Transactional Binding STALE Transitions (Conditioned 1A)
- **Problem with Previous Design:** Staging `mutate_stale = (mode == ExecutionMode.LEARN)` directly in `dynamics.py` would allow uncommitted events in an OPEN root to mutate `state.W.stable_bindings[z].status = STALE`. If that root later called `abort_exposure()`, the STALE transition would illegally survive rollback.
- **Ratified Architecture:**
  - In `execute_two_pass_event()` (regardless of mode): `validate_and_refresh_stable_binding(..., mutate_stale=False)` is used. If validation fails, $G_z^{\text{ctx}}$ evaluates to $0$ (closed gate), and the diagnostic code is appended to `r.context_diagnostics`. Permanent $W$ remains untouched.
  - In `end_exposure()`: During candidate and assembly maintenance on `w_shadow`, corrupted active bindings are transitioned to `BindingStatus.STALE` on `w_shadow`.
  - When `state.W = w_shadow` commits, legitimate STALE transitions become permanent atomically.
  - If `abort_exposure()` is called, `w_shadow` is discarded, and zero STALE transitions persist in $W$.

### 3.2 Decision 6: Revised Outbox Reconciliation & Generation Policy (Replacing Rejected 6A)
- **Problem with Previous Design 6A:** Previous 6A proposed that `run_read_only_episode()` and `generate_episode()` automatically invoke `reconcile_outbox()`. This violated the read-only contract by mutating the peripheral ledger during an inference pass.
- **Ratified Architecture:**
  1. **Strict Read-Only Purity:** `run_read_only_episode()` and `generate_episode()` are strictly read-only on both `MachineState` and `SurfaceReadoutLedgerV1`. They never invoke mutating reconciliation.
  2. **Explicit Transactional Reconciliation:** `ExposureTransactionManager.reconcile_pending_outbox(ledger)` or standalone `reconcile_outbox_batch(tx, ledger)` must be invoked explicitly prior to generation.
  3. **Readout Safety:** If an un-reconciled assembly wins next-event selection, `ledger.resolve_readout()` returns `StatusCode.READOUT_UNAVAILABLE` (or `READOUT_UNKNOWN`). `generate_episode()` cleanly halts with `StatusCode.GEN_STOP_NO_MATCH` or `StatusCode.GEN_STOP_STALE_ASSEMBLY` without corrupting state.
  4. **Neural Invariance:** Read-only temporal drive computation ($P_T$) is strictly neural and does not require peripheral reconciliation.

---

# RATIFIED DECISIONS RECORD COMPLETE — READY FOR SPECIFICATION FREEZE
