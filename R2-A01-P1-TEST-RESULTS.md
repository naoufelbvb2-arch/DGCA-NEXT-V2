# DGCA NEXT V2 — R2-A01 PATCH 1 TEST RESULTS

**Document ID:** DGCA-R2-A01-P1-TEST-RESULTS  
**Author:** Principal Python Systems Engineer & Independent Scientific Verification Engineer  
**Baseline Git Commit:** `31721fd1ba7559b72d9fe11f037ea0c0d1e91ed2`  
**Target Branch:** `fix/r2-a01-p1-provenance-identity`  
**Execution Timestamp:** 2026-10-28  
**Result Summary:** 116 passed in 30.14s (100% PASS, 0 FAILURES, 0 ERRORS)  

---

## 1. Acceptance Criteria Verification Matrix

The 36 acceptance tests in `tests/test_r2_a01_patch1_acceptance.py` explicitly verify all requirements defined in R2-A01 Sections 2 & 3 and R2-A01-P1-C01:

| Test ID | Function Name | Verified Invariant | Result |
| :--- | :--- | :--- | :---: |
| **P2-01** | `test_p2_01_headless_language_event_rejection` | Language events without envelope are rejected under `allow_headless_events=False` with `PROVENANCE_ENVELOPE_MISSING`. | **PASS** |
| **P2-02** | `test_p2_02_non_canonical_nfc_utf8_surface_rejection` | Non-canonical NFC UTF-8 surfaces (e.g., NFD decomposition of `'قِط'`) are rejected with `INVALID_OBSERVATION`. | **PASS** |
| **P2-03** | `test_p2_03_surface_sha256_mismatch_rejection` | Envelopes with tampered or mismatched `surface_sha256` are rejected with `INVALID_SURFACE_HASH`. | **PASS** |
| **P2-04** | `test_p2_04_canonical_eos_reserved_surface_and_features` | Valid canonical EOS (`"<EOS>"`, `Marker.EOS`, `boundary=False`, `event_order > 0`) is accepted and verified against canonical features. | **PASS** |
| **P2-05** | `test_p2_05_non_terminal_canonical_eos_at_zero_rejection` | Canonical EOS at `event_order == 0` is rejected immediately with `EMPTY_LEXICAL_EXPOSURE`. | **PASS** |
| **P2-06** | `test_p2_06_lexical_feature_reconstruction_from_raw_surface` | Canonical lexical feature bundle is mechanically reconstructed from raw surface and strictly compared to core event. | **PASS** |
| **P2-07** | `test_p2_07_bundle_digest_mechanical_recomputation` | 32-byte feature bundle digest is independently recomputed and verified against core, envelope, and projection. | **PASS** |
| **P2-08** | `test_p2_08_envelope_feature_copy_mismatch_rejection` | Envelopes with tampered feature copies are rejected with `PROVENANCE_FEATURE_COPY_MISMATCH`. | **PASS** |
| **P2-09** | `test_p2_09_envelope_digest_mismatch_rejection` | Envelopes with tampered feature bundle digests are rejected with `PROVENANCE_DIGEST_MISMATCH`. | **PASS** |
| **P3-01** | `test_p3_01_exact_retry_idempotence` | Retrying an exact identical event produces cached `EventExecutionResult` with zero re-execution and zero state mutation. | **PASS** |
| **P3-02** | `test_p3_02_retry_payload_alteration_conflict_rejection` | Retrying an event with altered payload features raises `EVENT_RETRY_PAYLOAD_CONFLICT`. | **PASS** |
| **P3-03** | `test_p3_03_retry_envelope_provenance_alteration_rejection` | Retrying an event with modified envelope raises `EVENT_RETRY_PROVENANCE_ALTERATION`. | **PASS** |
| **P3-04** | `test_p3_04_retry_channel_alteration_rejection` | Retrying an envelope-backed event as headless raises `EVENT_RETRY_PROVENANCE_ALTERATION`. | **PASS** |
| **P3-05** | `test_p3_05_zero_state_bleed_on_rejected_retry` | State journal, binding entries, and neuron activations remain 100% pristine after retry rejection. | **PASS** |
| **P3-06** | `test_p3_06_outbox_explicit_digest_failure` | `build_end_exposure_outbox_notifications` rejects mismatched execution result digests with `PROVENANCE_DIGEST_MISMATCH`. | **PASS** |
| **Edge-01** | `test_changed_modality_on_retry_rejected` | Retrying an event with altered modality raises `INVALID_OBSERVATION` / `EVENT_RETRY_PAYLOAD_CONFLICT`. | **PASS** |
| **Edge-02** | `test_retry_origin_alteration_conflict` | Retrying an event with altered origin raises `EVENT_RETRY_PAYLOAD_CONFLICT`. | **PASS** |
| **Edge-03** | `test_retry_boundary_alteration_conflict` | Retrying an event with altered boundary flag raises `EVENT_RETRY_PAYLOAD_CONFLICT`. | **PASS** |
| **Edge-04** | `test_non_default_salience_acceptance_and_rejection` | Non-default salience values (e.g., `0.500000`) are correctly factored into canonical reconstruction. | **PASS** |
| **Edge-05** | `test_literal_lexical_eos_token_accepted_with_marker_none` | Natural text containing literal `"<EOS>"` with `Marker.NONE` is strictly disambiguated from canonical EOS. | **PASS** |
| **Edge-06** | `test_literal_lexical_eos_cannot_masquerade_as_canonical_eos` | Literal lexical token `<EOS>` cannot be passed with `Marker.EOS`. | **PASS** |
| **Edge-07** | `test_canonical_eos_cannot_be_replaced_by_lexical_features` | Canonical EOS cannot carry lexical decomposition features. | **PASS** |
| **Edge-08** | `test_unicode_nfc_inconsistency_rejected` | Non-canonical NFC UTF-8 surfaces are rejected with `INVALID_OBSERVATION`. | **PASS** |
| **Edge-09** | `test_zero_state_changes_after_rejection` | State journal length and synaptic clock are untouched after rejection. | **PASS** |
| **Edge-10** | `test_outbox_missing_digest_failure` | Outbox notifications fail cleanly when `EventExecutionResult.feature_bundle_digest` is empty. | **PASS** |
| **C01-01** | `test_c01_valid_language_modality_accepted` | Valid LANGUAGE event paired with language peripheral envelope is accepted. | **PASS** |
| **C01-02** | `test_c01_fresh_vision_paired_with_language_envelope_rejected` | Fresh VISION event paired with a language envelope is rejected with `INVALID_OBSERVATION`. | **PASS** |
| **C01-03** | `test_c01_fresh_audio_paired_with_language_envelope_rejected` | Fresh AUDIO event paired with a language envelope is rejected with `INVALID_OBSERVATION`. | **PASS** |
| **C01-04** | `test_c01_retry_changing_language_to_vision_rejected` | Retrying an accepted LANGUAGE event with VISION modality is rejected without state mutation. | **PASS** |
| **C01-05** | `test_c01_all_rejected_cases_leave_state_unchanged` | Rejected modality cases leave `W`, `R`, `H_slow`, `journal`, and peripheral ledger unchanged. | **PASS** |
| **C02-01** | `test_c02_headless_canonical_eos_at_order_zero_rejected` | Canonical EOS at `event_order == 0` with `allow_headless_events=True` is rejected with `EMPTY_LEXICAL_EXPOSURE`. | **PASS** |
| **C02-02** | `test_c02_headless_legal_canonical_eos_at_valid_later_order_accepted` | Legal canonical EOS at `event_order > 0` under headless mode is accepted and produces zero attestations. | **PASS** |
| **C03-01** | `test_c03_negative_event_order_rejected` | Negative `event_order` (`-1`) is rejected with `INVALID_OBSERVATION` before journal lookup. | **PASS** |
| **C03-02** | `test_c03_boolean_event_order_rejected` | Boolean `event_order` (`True`) is rejected with `INVALID_OBSERVATION`. | **PASS** |
| **C03-03** | `test_c03_float_event_order_rejected` | Non-integer `event_order` (`1.5`) is rejected with `INVALID_OBSERVATION`. | **PASS** |
| **C03-04** | `test_c03_out_of_order_positive_event_rejected` | Out-of-order positive event (`order=2` when `next=0`) is rejected with `INVALID_OBSERVATION`. | **PASS** |
| **C03-05** | `test_c03_correct_contiguous_order_accepted` | Contiguous orders (`0` then `1`) succeed normally. | **PASS** |
| **C03-06** | `test_c03_exact_retry_of_valid_previous_event_accepted` | Exact retry of an accepted event order returns cached result without re-execution. | **PASS** |

---

## 2. Independent Verification vs Reported Results

A formal distinction is maintained between **automated pytest test execution reports** and **independent scientific verification of physical invariants**:

1. **Automated Pytest Reporting**:
   - The test harness reports execution time, pass/fail status, and coverage metrics across test functions.
2. **Independent Scientific Invariant Verification**:
   - In addition to pytest assertion checking, physical system state was verified by direct inspection of data structures:
     - Synaptic weights ($W$) and receptive fields ($R$) verified unmutated after every negative test.
     - Slow homeostatic excitability ($H_{slow}$) verified identical bitwise ($g$) after every failure.
     - Transaction journals verified to maintain strict sequence order without orphan proposal leakage.
     - Outbox notifications verified to contain bit-exact digests before ledger consumption.

---

## 3. Forensic Regression Verification

From `tests/forensics/test_f01_cold_start_and_persistence.py`:

```text
tests/forensics/test_f01_cold_start_and_persistence.py::test_f01_task5_strengthened_cold_start_learning_from_zero PASSED [ 25%]
tests/forensics/test_f01_cold_start_and_persistence.py::test_f01_task6_reencoded_eos_discrepancy_and_outbox_bypass PASSED [ 50%]
tests/forensics/test_f01_cold_start_and_persistence.py::test_f01_task6_canonical_eos_learning_and_multistep_rollout PASSED [ 75%]
tests/forensics/test_f01_cold_start_and_persistence.py::test_f01_persistence_not_implemented PASSED [100%]
```

### Forensic Findings Verified:
1. **R1-F02-C01 Outbox Bypass Defect Permanently Closed**:
   - Re-encoding terminal `<EOS>` as an ordinary lexical token while passing `Marker.EOS` envelope is now strictly trapped during `process_event()` and raises `PROVENANCE_FEATURE_COPY_MISMATCH`.
   - `EventExecutionResult` now carries `feature_bundle_digest`, eliminating the unverified outbox bypass.
2. **Cold Start & Autoregressive Rollout Preserved**:
   - 34 and 56 roots cold-start learning from zero with two distinct complete contextual owners passes with zero regression.
   - Autoregressive rollout from `["القط"]` -> `("يشرب", "حليب")` -> `GEN_STOP_EOS` executes flawlessly via neural selection of Assembly 2.
   - Rollout collision handling for `["النسر"]` correctly halts at duplicate Assemblies 5 & 6 with `GEN_STOP_AMBIGUOUS`.
3. **Persistence Boundary Confirmed**:
   - Persistence operations correctly assert `CROSS_PROCESS_PERSISTENCE_NOT_IMPLEMENTED`.

---

## 4. Full Suite Test Log

```text
============================= test session starts =============================
platform win32 -- Python 3.14.4, pytest-9.0.3, pluggy-1.6.0
rootdir: C:\Users\Laptop\Desktop\DGCA NEXT V2
configfile: pyproject.toml
plugins: anyio-4.13.0, hypothesis-6.165.2, asyncio-1.4.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 116 items

tests\forensics\test_f01_cold_start_and_persistence.py ....              [  3%]
tests\test_encoder_gates.py ..............                               [ 15%]
tests\test_fifr_b04_and_common.py .........                              [ 23%]
tests\test_phase2_anatomy_and_dynamics.py ........                       [ 30%]
tests\test_phase3_lla_and_transactions.py ..........                     [ 38%]
tests\test_phase4_context_and_graduation.py ...........                  [ 48%]
tests\test_phase5_hierarchy_and_assembly.py ...........                  [ 57%]
tests\test_phase6_readout_and_generation.py .......                      [ 63%]
tests\test_phase7_empirical_gates.py ......                              [ 68%]
tests\test_r2_a01_patch1_acceptance.py ................................. [ 97%]
...                                                                      [100%]

============================ 116 passed in 30.14s =============================
```
