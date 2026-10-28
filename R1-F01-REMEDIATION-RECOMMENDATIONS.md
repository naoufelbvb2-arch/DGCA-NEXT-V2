# DGCA NEXT V2 — R1-F01 Remediation Recommendations

**Status:** PROPOSED FOR FUTURE REMEDIATION (READ-ONLY AUDIT PHASE — NO CODE MODIFICATIONS APPLIED)  
**Author:** Independent Forensic Auditor & Scientific Verification Engineer  
**Baseline Commit:** `31721fd1ba7559b72d9fe11f037ea0c0d1e91ed2`  
**Audit Branch:** `audit/r1-f01-forensic-verification`

---

## 1. Overview and Engineering Scope

During forensic investigation `R1-F01`, eleven critical findings were investigated across the neural, transaction, assembly, and peripheral layers of DGCA V2. Ten findings were experimentally confirmed as concrete architecture or contractual defects, and cross-process persistence was confirmed to be entirely missing.

In strict compliance with the forensic mandate, **no repairs have been applied to the codebase**. This document details the exact root causes, affected normative invariants, minimal corrections, alternative approaches, regression hazards, and specification amendments required prior to entering the implementation repair phase.

---

## 2. Structural and Transactional Defects

### 2.1 R1-B01: Read-Only W Immutability Violation during RETRIEVE

- **Root Cause:**
  1. In `src/dgca/core/dynamics.py` line 678, `w.last_referenced_event[cid] = w.global_event_clock` executes unconditionally for all activated committed cells, even when `mode == ExecutionMode.RETRIEVE` or `origin == EventOrigin.READ_ONLY_OBSERVED`.
  2. In `src/dgca/core/context_gate.py` lines 143–200, `validate_and_refresh_stable_binding` mutates `binding.status = BindingStatus.STALE` in-place on the shared `w.stable_bindings[z]` dictionary during read-only context evaluation.
- **Affected Invariant:**
  - `DGCA_CORE_RC4_1.md §9.1`: Standalone `READ_ONLY_EPISODE` and `RETRIEVE` must be strictly side-effect-free with respect to permanent state `W`.
- **Minimal Correction:**
  1. In `src/dgca/core/dynamics.py`: Guard line 678 with `if mode == ExecutionMode.LEARN: w.last_referenced_event[cid] = w.global_event_clock`.
  2. In `src/dgca/core/context_gate.py`: Add parameter `mutate_on_stale: bool = True`. During `mode == ExecutionMode.RETRIEVE`, pass `mutate_on_stale=False` so that invalid bindings return `(False, StatusCode.STALE_CONTEXT_BINDING)` without writing to `binding.status`.
- **Alternative Corrections:**
  - Pass a read-only snapshot or deep proxy of `W` into `run_read_only_episode`. (Higher memory overhead per inference call).
- **Risks to Existing Learned Knowledge:** None. Preserves W immutability.
- **Specification Amendment:** None required; brings code into alignment with `Core §9.1`.
- **Required Regression Tests:** `tests/forensics/test_f01_01_read_only_w_immutability.py`.
- **Scientific Behavior Change:** Zero impact on genuine learning; prevents silent degradation of W during diagnostic querying.

---

### 2.2 R1-B02: Outbox Publication Ordering and Atomicity Inversion

- **Root Cause:**
  In `src/dgca/lifecycle/exposure_tx.py` lines 481–487, `self.readout_ledger.consume_outbox_batch(outbox_notifs)` is invoked BEFORE `self.state.W = w_shadow` (Step 6) and before `journal.status = ExposureStatus.COMPLETED`. If an exception occurs during notification consumption or before Step 6, peripheral attestations are retained in `readout_ledger` while `W` remains uncommitted or is subsequently aborted.
- **Affected Invariant:**
  - `DGCA_CORE_RC4_1.md §9.4` & `§10.2`: Peripheral ledger attestations must never precede or survive an uncommitted/aborted external root.
- **Minimal Correction:**
  Move peripheral ledger consumption to immediately AFTER `self.state.W = w_shadow` and `journal.status = ExposureStatus.COMPLETED`. Wrap outbox delivery in a transactional staging buffer in `readout_ledger` that commits only upon receipt of a final `commit_root_attestations(exposure_id)` handshake.
- **Alternative Corrections:**
  - Implement two-phase commit (2PC) between `ExposureTransactionManager` and `SurfaceReadoutLedgerV1`.
- **Risks to Existing Learned Knowledge:** Low. Ensures strict causal consistency.
- **Specification Amendment:** Explicitly document the publication sequence in `Core §10.2 Step 6`.
- **Required Regression Tests:** `tests/forensics/test_f01_02_outbox_atomicity.py`.
- **Scientific Behavior Change:** Prevents phantom peripheral surface attestations from aborted roots.

---

### 2.3 R1-B03: Missing Durable Cross-Process Persistence

- **Root Cause:**
  `src/dgca/common/serialization.py` only implements primitive IEEE-754 binary64 and record envelope packers. No serialization schemas or disk persistence routines exist for `WState`, `HSlowState`, `RState`, `Synapse`, `StableBinding`, `Assembly`, or `SurfaceReadoutLedgerV1`.
- **Affected Invariant:**
  - `DGCA_CORE_RC4_1.md §3.1` & `§10`: Durable survival across process restarts.
- **Minimal Correction:**
  Implement canonical big-endian binary or JSON-backed schema serialization for all persistent dataclasses (`WState`, `HSlowState`, `Assembly`, `StableBinding`, `SurfaceReadoutLedgerV1`), along with atomic file swapping (`write to .tmp + os.replace`).
- **Alternative Corrections:**
  - SQLite/RocksDB relational or key-value persistent storage engine.
- **Risks to Existing Learned Knowledge:** None; enables checkpoints to be safely loaded from disk.
- **Specification Amendment:** Add formal serialization record tags (`RECORD_W_STATE = 0x10`, etc.) to `Core §3.1`.
- **Required Regression Tests:** Full process restart, state reload, and continuation verification.
- **Scientific Behavior Change:** None on algorithmic logic; provides real-world crash recovery.

---

### 2.4 R1-H04: Event Retry Collision within OPEN Exposure

- **Root Cause:**
  In `src/dgca/lifecycle/exposure_tx.py` lines 282–283:
  ```python
  if core_event.event_order < journal.next_event_order:
      return journal.event_results[core_event.event_order]
  ```
  The check only compares `event_order` without verifying whether the re-submitted event has an identical `feature_bundle_digest`, `features`, or matching peripheral envelope.
- **Affected Invariant:**
  - `DGCA_CORE_RC4_1.md §10.1`: Retry idempotency must enforce exact equivalence; conflicting events at the same ordinal must raise an error.
- **Minimal Correction:**
  Compare the projection `projection.feature_bundle_digest` and peripheral envelope digest against the recorded witness in `journal.observation_witnesses[core_event.event_order]`. If digests do not match, raise `ObservationError(StatusCode.EVENT_PAYLOAD_CONFLICT)`.
- **Alternative Corrections:**
  - Disallow any in-root retries and require root abort on retry mismatch.
- **Risks to Existing Learned Knowledge:** None.
- **Specification Amendment:** Formally define event-retry idempotency in `Core §10.1`.
- **Required Regression Tests:** `tests/forensics/test_f01_03_event_retry_collision.py`.
- **Scientific Behavior Change:** Rejects corrupted or conflicting retry streams.

---

### 2.5 R1-H05: Latent Topology Mutations Surviving ABORT_EXPOSURE

- **Root Cause:**
  In `src/dgca/lifecycle/exposure_tx.py` lines 326–331, `_update_coactive_latent_neighborhoods_for_event` mutates `self.state.W.latent_table` in-place during `process_event`. When `abort_exposure` is executed (lines 376–387), it restores `H_slow = journal.h_slow_begin.clone()` and resets `R`, but does NOT roll back `W.latent_table` or its reverse index.
- **Affected Invariant:**
  - `DGCA_CORE_RC4_1.md §10.1`: While committed sensory cells legally persist, uncommitted structural staging and learning effects must be discarded upon `ABORT`.
- **Minimal Correction:**
  Capture a lightweight rollback journal for `W.latent_table` at `begin_exposure`, or record newly allocated/recycled coactive slots in `open_journal._latent_mutations`, and revert them during `abort_exposure`.
- **Alternative Corrections:**
  - Clone `W.latent_table` at `begin_exposure` and restore on `ABORT`.
- **Risks to Existing Learned Knowledge:** Low. Ensures aborted exposures leave no structural contamination.
- **Specification Amendment:** Clarify in `Core §10.1` that coactive latent slots allocated during an aborted root must be reclaimed.
- **Required Regression Tests:** `tests/forensics/test_f01_04_abort_latent_topology.py`.
- **Scientific Behavior Change:** Prevents speculative coactivity graph inflation from failed/aborted sequences.

---

## 3. Assembly and Readout Defects

### 3.1 R1-M01: Duplicate Identical Assemblies Blocked from Merging

- **Root Cause:**
  In `src/dgca/core/assembly.py` lines 538–548:
  ```python
  excl_a = sorted(set_a - set_b)
  excl_b = sorted(set_b - set_a)
  if not excl_a or not excl_b:
      between_strength = 0.0
  else:
      ...
  if between_strength < THETA_OB:
      return False
  ```
  When two Assemblies have identical member cells (`set_a == set_b`), `excl_a` and `excl_b` are empty sets. The code forces `between_strength = 0.0`, which is strictly below `THETA_OB = 0.50`. This causes `_try_merge_pair` to reject exact duplicates.
- **Affected Invariant:**
  - `DGCA_CORE_RC4_1.md §2.0 item 4`: MERGE is designed to collapse overlapping Assemblies when Jaccard $\ge 0.70$ and mutual support is strong.
- **Minimal Correction:**
  When `set_a == set_b` (or `not excl_a and not excl_b`), Jaccard is 1.0. Set `between_strength = 1.0` (or bypass the cross-support check, since mutual support is already verified by internal member guards). Merge the higher ID into the lower ID and archive the higher ID.
- **Alternative Corrections:**
  - Prevent FORM from creating an Assembly if an identical `frozenset(member_cells)` already exists in `w.assemblies`.
- **Risks to Existing Learned Knowledge:** Low. Collapses redundant duplicate Assemblies and eliminates tied `score_next` ambiguities.
- **Specification Amendment:** Clarify the duplicate merge condition in `Core §2.0 item 4`.
- **Required Regression Tests:** `tests/forensics/test_f01_05_assembly_forensics.py::test_f01_05_exact_duplicate_assemblies_cannot_merge`.
- **Scientific Behavior Change:** Eliminates artificial `GEN_STOP_AMBIGUOUS` stops caused by identical twins.

---

### 3.2 R1-M02: Contextual z-Cell Contamination of Lexical Assemblies

- **Root Cause:**
  In `src/dgca/core/assembly.py` lines 78–84, `is_eligible_assembly_member_cell` explicitly permits completed contextual cells ($z \in W.\text{stable\_bindings}$) to become Assembly members. During GROW, reciprocal local links between Anchor $C$ and $z$ cause $z$ to be absorbed into lexical Assemblies (e.g. $z_{AB} = 8321$ entering Assembly 1 for "يشرب"). When evaluated under a different context (e.g. DB), $z$ has $G_z^{\text{ctx}} = 0$, depressing the Assembly's activation and CoreCoverage.
- **Affected Invariant:**
  - `DGCA_CORE_RC4_1.md §2.0`: Assemblies are cohesive sensory/lexical microcolumn cliques; contextual cells represent conditional gating paths, not lexical token surfaces.
- **Minimal Correction:**
  In `is_eligible_assembly_member_cell`, reject any cell where `w.is_contextual_cell(cell_id)` or `cell_id in w.stable_bindings`. Only ordinary sensory/lexical cells in `Region.LANGUAGE` should be eligible for Assembly membership.
- **Alternative Corrections:**
  - Allow contextual cells in specialized "phrase-level" or "compound" Assemblies, but exclude them from lexical word Assemblies.
- **Risks to Existing Learned Knowledge:** Medium. Requires existing contaminated Assemblies to be cleaned or re-formed.
- **Specification Amendment:** Add explicit rule in `Core §2.0`: "Contextual cells $z$ cannot be members of lexical surface Assemblies."
- **Required Regression Tests:** `tests/forensics/test_f01_05_assembly_forensics.py::test_f01_06_contextual_z_cell_contamination`.
- **Scientific Behavior Change:** Prevents context-dependent crippling of shared lexical items (like "يشرب").

---

### 3.3 R1-M03: Readout Score Dilution and Indirect Causal Gain Exclusion

- **Root Cause:**
  In `src/dgca/core/readout.py`:
  1. Line 108: `eligibleNext_j = 1[P_j^T > 0 and gain_j > 0]` requires direct temporal drive $P_j^T > 0$. Any Assembly member that receives activation only via synchronous lateral connections ($P_j^S$) in Pass 2 has $P_j^T = 0$, zeroing out its causal contribution.
  2. Lines 186–193: `score_val = total_gain / float(len(members))`. As an Assembly grows from 3 cells to 6, 8, or 12 cells, the denominator increases, diluting `score_next` below $\theta_{\text{read}} = 0.08$ (as observed at Checkpoint 34 where score was 0.0661).
- **Affected Invariant:**
  - `DGCA_CORE_RC4_1.md §9.2`: Readout score must measure the causal commitment of the candidate Assembly.
- **Minimal Correction:**
  1. Define eligibility as `eligibleNext_j = 1[(P_j^T > 0 or (P_j^S > 0 and A_j^FULL >= theta_active)) and gain_j > 0]`.
  2. Normalize the denominator by $\min(|G|, 3)$ or by the effective core clique size rather than total grown size $|G|$, or compute average gain over eligible members: `score_val = total_gain / float(max(1, elig_count)) * CoreCoverage(G)`.
- **Alternative Corrections:**
  - Recalibrate $\theta_{\text{read}}$ dynamically based on average Assembly size.
- **Risks to Existing Learned Knowledge:** Low to Medium. Readout scores will be higher and more resilient to Assembly growth.
- **Specification Amendment:** Amend formula in `Core §9.2`.
- **Required Regression Tests:** `tests/forensics/test_f01_05_assembly_forensics.py::test_f01_07_readout_score_dilution_and_indirect_gain_exclusion`.
- **Scientific Behavior Change:** Enables cold-start learning to successfully emit surfaces at earlier checkpoints (e.g. root 34 instead of waiting for root 56).

---

## 4. Scientific Protocol Gaps (Gates C, D, and E)

### 4.1 R1-H01: Insufficient Gate C Acceptance Criteria
- **Issue:** Gate C assertion checked `len(recruited_cells) >= 2` rather than verifying `len(state.W.stable_bindings) >= 2` and two distinct `COMPLETE` owner profiles.
- **Remediation:** Update Gate C assertion to explicitly check:
  `assert len(rep.graduated_context_cells) >= 2` and verify that both bindings have `status == BindingStatus.ACTIVE` with distinct $P$ and $Y$ footprints.

### 4.2 R1-H02: Fixture-Based Gate E Evidence Limitations
- **Issue:** Gate E was implemented using 100% pre-wired fixture networks and manual outbox injection, masking the fact that autonomous multi-step generation and native EOS learning were not yet functioning end-to-end.
- **Remediation:** Label Gate E as `Gate_E_Fixture_Mechanism` in test suites, and introduce a genuine `Gate_E_Autonomous_Learning_Suite` that trains an end-to-end multi-step sequence with naturally formed Assemblies and learned EOS markers.

### 4.3 R1-H03: Non-Equivalent Scientific Ablations in Gate D
- **Issue:** Gate D compared the Gate B fixture network against an unrelated toy network with arbitrary weights ($s = 0.45$), calculated headroom arithmetically (`max(0, 64-32)`), and tested Replay on an isolated object.
- **Remediation:** Run genuine matched ablation curricula on identical seeds:
  - Curriculum with DCR $z$-path enabled vs disabled.
  - Curriculum with candidate probe enabled vs disabled.
  - Measure actual empirical link saturation for $B_i = 64$ vs $32$ under long curricula.
  - Measure empirical interference with Replay enabled vs disabled.

---

## 5. Prioritized Remediation Roadmap

| Priority | Finding ID | Description | Impact | Target Module |
|---|---|---|---|---|
| **P0** | **R1-B01** | Fix read-only $W$ mutations (`last_referenced_event` and `binding.status`) | Transactional Integrity | `dynamics.py`, `context_gate.py` |
| **P0** | **R1-B02** | Correct outbox publication ordering ($W$ swap must precede ledger consume) | Causal Provenance | `exposure_tx.py` |
| **P1** | **R1-H04** | Enforce event retry payload conflict checks | Idempotency Contract | `exposure_tx.py` |
| **P1** | **R1-H05** | Roll back coactive latent slots and reverse index on `ABORT_EXPOSURE` | Transaction Isolation | `exposure_tx.py`, `latent_index.py` |
| **P1** | **R1-M01** | Allow exact duplicate Assemblies to merge (`between_strength = 1.0` when identical) | Generation Reliability | `assembly.py` |
| **P1** | **R1-M02** | Exclude contextual $z$ cells from lexical surface Assemblies | Assembly Purity | `assembly.py` |
| **P1** | **R1-M03** | Fix readout score dilution and include Pass 2 indirect causal gain | Generation Recall | `readout.py` |
| **P2** | **R1-B03** | Implement full cross-process disk persistence & checkpoint recovery | Operational Viability | `serialization.py` |
| **P2** | **R1-H01..03** | Update Gates C, D, and E to enforce strict non-fixture scientific benchmarks | Scientific Validity | `gates.py` |
