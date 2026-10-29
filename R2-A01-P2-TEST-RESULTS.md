# DGCA NEXT V2 — R2-A01 PATCH 2 TEST RESULTS

## Comprehensive Verification Matrix: Read-Only Immutability & Transactional STALE

- **Engineering Role:** Principal Scientific Software Verification Engineer  
- **Test Session Date:** 2026-10-28  
- **Branch:** `fix/r2-a01-p2-read-only-immutability`  
- **Target SHA:** Working Tree on `fix/r2-a01-p2-read-only-immutability`  
- **Test Command:** `python -m pytest tests/ -q`  
- **Result:** **130 passed (100% pass rate, 0 failures, 0 errors)**  

---

## 1. Epistemological and Verification Classification

The test evidence in this report is strictly delineated across five epistemic levels:

1. **Source-Code Inspection:** Static verification that mutation statements are guarded by `mode == ExecutionMode.LEARN` or `mutate=True` (deferred to Step 5.1 of `end_exposure`).
2. **Automated Pytest Evidence:** 130 automated regression and acceptance tests passing across Python 3.14.4 on Windows.
3. **Deterministic Snapshot Comparison:** Deep dictionary-and-tuple structural comparison covering 100% of persistent state attributes across `WState`, `LatentNeighborhoodTable`, `HSlowState`, `RState`, `SurfaceReadoutLedgerV1`, and all 10 nested mutable dataclasses.
4. **Cryptographic SHA-256 Digest Verification:** Executable computation and assertion of SHA-256 digests generated via `canonical_state_digest()`, featuring strict enum priority over generic primitives.
5. **Empirical Verification Under Tested Conditions:** Validation on both a synthetic fixture network AND a genuine 56-alternating-root cold-start curriculum with canonical EOS and an attested peripheral ledger containing 15 assembly/generation groups and 398 outbox keys.

---

## 2. Acceptance Scenario Verification Matrix

| Scenario ID | Test Name | Purpose / Invariant Tested | Result |
| :--- | :--- | :--- | :--- |
| **AUD-01** | `test_field_coverage_audit` | **Top-Level Field Coverage Audit:** Verifies 100% attribute coverage across `WState` (21 fields), `LatentNeighborhoodTable` (4 fields), `HSlowState` (4 fields), `RState` (19 fields), and `SurfaceReadoutLedgerV1` (4 fields). Asserts failure if any attribute in `vars()` is omitted. | **PASSED** |
| **AUD-02** | `test_nested_dataclass_coverage_audit` | **Nested Dataclass Coverage Audit (Correction V04 & Section 3):** Dynamically inspects `dataclasses.fields()` across 10 nested records (`Synapse` [13 fields], `ContextCandidateDescriptor` [8], `StableBinding` [6], `OwnerProfile` [7], `CompactWitnessProfile` [5], `ContrastEpisodeRecord` [7], `Assembly` [6], `ParentContextRef` [2], `WiringLogEntry` [4], `LedgerCandidateRow` [6]). Asserts failure if any declared field is omitted from snapshot coverage. | **PASSED** |
| **TYP-01** | `test_canonical_enum_and_primitive_type_separation` | **Canonical Digest Type Separation (Section 4):** Serializes `enum.Enum` BEFORE `int` and `str` in `canonical_state_digest()`. Asserts zero silent collapse across 12 distinct Python types (`None`, `bool`, `IntEnum`, `StrEnum`, `int`, `float`, `str`, `bytes`, `tuple`, `set`, `dict`). | **PASSED** |
| **ADV-01** | `test_synapse_mutation_sensitivity_adversarial` | **Synapse Mutation Sensitivity Adversarial Test (Correction V04):** Adversarially mutates all 6 previously omitted Synapse fields (`last_evidence_root`, `candidate_deadline`, `internally_supported`, `created_event_id`, `created_exposure_id`, `last_external_event_id`). Asserts that snapshot structural comparison AND SHA-256 state digest detect every single mutation. | **PASSED** |
| **P1-01** | `test_p1_01_complete_retrieve_immutability_gate` | **Complete State Snapshot & Cryptographic Digest (P1-01):** Deep snapshot equality AND bitwise SHA-256 digest equality ($W_{\text{after}} = W_{\text{before}}$, $H^{\text{slow}}_{\text{after}} = H^{\text{slow}}_{\text{before}}$, $R^{\text{caller}}_{\text{after}} = R^{\text{caller}}_{\text{before}}$) after active multi-event read-only episode. Verifies `last_referenced_event` and `_slots_by_cell` key sets are untouched. | **PASSED** |
| **P1-02** | `test_p1_02_stale_binding_read_only_isolation` | **Read-Only STALE Isolation (P1-02):** Gating closure on corrupted binding ($l_z > u_z$), diagnostic reporting (`INVALID_CONTEXT_THRESHOLD`), and non-mutating preservation of `status == BindingStatus.ACTIVE` on caller $W$. Verified via snapshot and SHA-256 digest equality. | **PASSED** |
| **P1-03** | `test_p1_03_homeostasis_scratch_isolation` | **Scratch Homeostasis Isolation (P1-03):** Strict isolation of $H^{\text{slow}}$ in scratch state. Verifies float equality before and after 5 consecutive read-only episodes, bit-identical output determinism, and SHA-256 hash preservation. | **PASSED** |
| **P1-04** | `test_p1_04_transactional_stale_transition_abort_vs_commit` | **Transactional STALE Settlement (P1-04):** Two-phase transactional settlement: Aborted learning exposure leaves invalid binding `ACTIVE` on caller $W$; committed exposure transitions invalid binding to `STALE` on shadow $W$ at Step 5.1 and publishes it to permanent $W$. | **PASSED** |
| **LAT-01** | `test_latent_lookup_on_unmaterialized_cell` | **Virtual Latent Lookups:** Verifies `get_slots_read_only` and `get_slots` return complete 24-slot tuples for uncommitted cells without inserting into `_slots_by_cell`. | **PASSED** |
| **LAT-02** | `test_virtual_vs_materialized_neighbor_equality` | **Virtual Topology Equivalence:** Verifies bit-for-bit equivalence between virtual on-the-fly neighbor computation and explicit `materialize_cell` output. | **PASSED** |
| **LAT-03** | `test_reverse_neighbors_and_eligibility_immutability` | **Bidirectional Eligibility Zero-Bleed:** Evaluates $D_{ij}$ eligibility and reverse neighbor queries without allocating entries for candidate sources. | **PASSED** |
| **GEN-01** | `test_generate_episode_caller_state_and_ledger_immutability` | **GENERATE Caller State Invariance:** Full bounded rollout with `generate_episode` leaves caller $W$, $H^{\text{slow}}$, $R$, and `SurfaceReadoutLedgerV1` completely untouched, confirmed by structural snapshot and SHA-256 digest. | **PASSED** |
| **CLK-01** | `test_learn_mode_updates_last_referenced_event_while_retrieve_does_not` | **Mode Discrimination:** `ExecutionMode.LEARN` advances `last_referenced_event`, whereas `ExecutionMode.RETRIEVE` preserves existing timestamps. | **PASSED** |
| **CUR-01** | `test_non_empty_ledger_genuine_56_root_curriculum_immutability` | **Non-Empty Ledger & Genuine Curriculum (Correction V02):** 56 alternating cold-start roots with canonical EOS. Ledger populated with 15 assembly/generation groups and 398 outbox keys. Verifies Cat rollout `("يشرب", "حليب")` halting at `GEN_STOP_EOS` and Eagle rollout `("يشرب", "ماء")` halting at `GEN_STOP_AMBIGUOUS`. Proves 100% $W$, $H^{\text{slow}}$, $R$, $L$ structural equality and SHA-256 digest equality, with zero outbox keys added and zero attestation roots altered. | **PASSED** |

---

## 3. Test Execution Log Breakdown

### 3.1 Patch 2 Dedicated Acceptance Suite (`tests/test_r2_a01_patch2_acceptance.py`)
```text
tests/test_r2_a01_patch2_acceptance.py::test_field_coverage_audit PASSED [  7%]
tests/test_r2_a01_patch2_acceptance.py::test_nested_dataclass_coverage_audit PASSED [ 14%]
tests/test_r2_a01_patch2_acceptance.py::test_canonical_enum_and_primitive_type_separation PASSED [ 21%]
tests/test_r2_a01_patch2_acceptance.py::test_synapse_mutation_sensitivity_adversarial PASSED [ 28%]
tests/test_r2_a01_patch2_acceptance.py::test_p1_01_complete_retrieve_immutability_gate PASSED [ 35%]
tests/test_r2_a01_patch2_acceptance.py::test_p1_02_stale_binding_read_only_isolation PASSED [ 42%]
tests/test_r2_a01_patch2_acceptance.py::test_p1_03_homeostasis_scratch_isolation PASSED [ 50%]
tests/test_r2_a01_patch2_acceptance.py::test_p1_04_transactional_stale_transition_abort_vs_commit PASSED [ 57%]
tests/test_r2_a01_patch2_acceptance.py::test_latent_lookup_on_unmaterialized_cell PASSED [ 64%]
tests/test_r2_a01_patch2_acceptance.py::test_virtual_vs_materialized_neighbor_equality PASSED [ 71%]
tests/test_r2_a01_patch2_acceptance.py::test_reverse_neighbors_and_eligibility_immutability PASSED [ 78%]
tests/test_r2_a01_patch2_acceptance.py::test_generate_episode_caller_state_and_ledger_immutability PASSED [ 85%]
tests/test_r2_a01_patch2_acceptance.py::test_learn_mode_updates_last_referenced_event_while_retrieve_does_not PASSED [ 92%]
tests/test_r2_a01_patch2_acceptance.py::test_non_empty_ledger_genuine_56_root_curriculum_immutability PASSED [100%]
============================= 14 passed in 20.20s =============================
```

### 3.2 Patch 1 Regression Suite (`tests/test_r2_a01_patch1_acceptance.py`)
- Acceptance scenarios P2-01 through P2-09: **All PASSED**
- Acceptance scenarios P3-01 through P3-06: **All PASSED**
- Corrections C01, C02, C03 (Modality, Headless EOS order, Non-integer/out-of-order rejection): **All PASSED**
- Total: **33 passed**

### 3.3 Normative Program Milestones (Phase 7: Gate A through Gate E)
- `test_gate_a_unit_and_transaction_milestone`: **PASSED**
- `test_gate_b_isolated_mechanism_milestone`: **PASSED**
- `test_gate_c_learn_from_zero_and_rc4_1_subgate_milestone`: **PASSED**
- `test_gate_d_ablations_and_comparisons_milestone`: **PASSED**
- `test_gate_e_generalization_and_boundaries_milestone`: **PASSED**
- `test_full_empirical_suite_and_reproducible_manifest`: **PASSED**
- Total: **6 passed**

### 3.4 Forensic Curriculum Baselines (`tests/forensics/test_f01_cold_start_and_persistence.py`)
- Task 5 strengthened cold-start learning from zero: **PASSED**
- Task 6 canonical EOS learning and multi-step rollout: **PASSED**
- Cat branch termination (`GEN_STOP_EOS`): **PASSED**
- Eagle branch termination (`GEN_STOP_AMBIGUOUS`): **PASSED**
- Total: **4 passed**

---

## 4. Empirical Invariant Verification Details

### 4.1 Non-Empty Ledger Immutability (`CUR-01`)
The integration test `test_non_empty_ledger_genuine_56_root_curriculum_immutability` evaluated the system on an authentically populated state:
- **Curriculum:** 56 alternating exposures from cold start:
  - Odd roots: `"القط يشرب حليب"` with canonical EOS.
  - Even roots: `"النسر يشرب ماء"` with canonical EOS.
- **Ledger State:**
  - Distinct `(AssemblyID, generation)` groups: 15
  - Consumed outbox notifications: 398
  - Verified attested assemblies: 1, 2, 3, 4, 5, 6
- **Autonomous Rollout Outputs:**
  - Cat prompt (`['القط']`): Emitted `("يشرب", "حليب")`, halting with `GEN_STOP_EOS` via Assembly 2.
  - Eagle prompt (`['النسر']`): Emitted `("يشرب", "ماء")`, halting with `GEN_STOP_AMBIGUOUS` via Assemblies 5 & 6 collision.
- **State Invariance Results:**
  - Before Cat: $W_{\text{pre}}$, $H_{\text{pre}}$, $R_{\text{pre}}$, $L_{\text{pre}}$ captured and hashed.
  - After Cat: $W_{\text{post-cat}} == W_{\text{pre}}$ (100% match), SHA-256 match.
  - After Eagle: $W_{\text{post-eagle}} == W_{\text{pre-eagle}}$ (100% match), SHA-256 match.
  - Outbox key count before/after: exactly 398 (0 added, 0 removed).
  - Confirmed roots for all candidate rows: bit-for-bit identical before and after.

### 4.2 Latent Neighborhood Allocation Zero-Bleed
- Number of allocated cells in `_slots_by_cell` before read queries: equal to committed cells only.
- Number of allocated cells after forward, reverse, and eligibility queries: **identical**.
- Unmaterialized cell virtual lookup: returns complete 24-slot topology with fixed local and topographic vicinities while preserving `len(_slots_by_cell)` unchanged.

---

## 5. Certification & Freeze Readiness

All 130 tests pass across unit, integration, empirical milestones, forensics, and acceptance suites. Complete state snapshot coverage (all top-level and 10 nested dataclasses), deterministic SHA-256 cryptographic hashing with strict enum discrimination, adversarial mutation sensitivity, non-empty ledger immutability, and transactional STALE settlement are fully verified.
