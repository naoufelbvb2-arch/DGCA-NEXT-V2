# DGCA NEXT V2 — R2-A01-P1-C01 CORRECTION REPORT

**Document ID:** DGCA-R2-A01-P1-C01-REPORT  
**Role:** Principal Python Systems Engineer & Independent Scientific Verification Engineer  
**Baseline Git Commit:** `31721fd1ba7559b72d9fe11f037ea0c0d1e91ed2` (`main`)  
**Starting Implementation Git SHA:** `a5e8173ba7bf2f940dd8bbd924ce6a600d710e0c`  
**Target Branch:** `fix/r2-a01-p1-provenance-identity`  
**Status:** `R2-A01-P1-C01 CORRECTED — AWAITING FINAL ACCEPTANCE`  
**Date:** October 28, 2026  

---

## 1. Executive Summary

This report documents the resolution of the three narrowly scoped boundary defects identified during the independent review of DGCA NEXT V2 R2-A01 Patch 1 at commit `a5e8173ba7bf2f940dd8bbd924ce6a600d710e0c`.

In strict adherence to the mandate:
- **No architectural reopening or rewrite occurred.**
- **Patches 2 through 5 remain completely untouched.**
- **Neural dynamics, LLA equations, Assembly lifecycle, and readout scoring remain strictly unmutated.**
- **Full repository test suite passed with 116/116 tests passing (100% PASS, 0 FAILURES, 0 ERRORS).**

---

## 2. Exact Defects Corrected

### 2.1 Correction C01 — Language Modality Validation
- **Defect Identified:** `validate_event_envelope_provenance()` reconstructed lexical features correctly from raw surface strings but failed to assert that `core_event.modality` matched `Region.LANGUAGE` when accompanied by a language peripheral envelope (`PeripheralSurfaceEnvelopeV1`). This could permit a malicious or malformed event to project language surface features into `Region.VISION` or `Region.AUDIO`.
- **Implementation Correction:**
  In `src/dgca/lifecycle/exposure_tx.py`, inside `validate_event_envelope_provenance()`:
  ```python
  # Modality validation for language peripheral envelope (Correction C01)
  if core_event.modality != Region.LANGUAGE:
      raise ObservationError(
          f"Language peripheral envelope requires Region.LANGUAGE, got {core_event.modality}",
          code=StatusCode.INVALID_OBSERVATION,
      )
  ```
  Ensures that any language envelope paired with non-LANGUAGE modality is trapped and rejected before neural execution, preserving the extensible design for future modality-specific envelopes without altering SIC hashing or region salts.

### 2.2 Correction C02 — Headless EOS Structural Boundary
- **Defect Identified:** The early-return in `validate_event_envelope_provenance()` under `allow_headless_events=True` bypassed canonical EOS rules, permitting a canonical EOS event at `event_order == 0` in headless testing mode.
- **Implementation Correction:**
  Introduced a structural neural event precheck evaluated prior to the headless early-return:
  ```python
  # Structural neural event precheck (independent of peripheral envelope - Correction C02)
  is_canonical_eos_features = (
      core_event.features == EOS_CANONICAL_FEATURES
      or any(feat[0].startswith("\x1fEOS") for feat in core_event.features)
  )
  if is_canonical_eos_features:
      if core_event.event_order == 0:
          raise ObservationError(
              "Canonical EOS event cannot be event_order 0 alone (empty exposure)",
              code=StatusCode.EMPTY_LEXICAL_EXPOSURE,
          )
      if core_event.boundary:
          raise ObservationError(
              "Canonical EOS event cannot have boundary=True",
              code=StatusCode.PROVENANCE_MARKER_MISMATCH,
          )
  ```
  - Rejects canonical EOS event 0 under `allow_headless_events=True` with `EMPTY_LEXICAL_EXPOSURE` and zero state mutation.
  - Preserves legal headless lexical events and legal canonical headless EOS events at `event_order > 0`.
  - Ensures headless events produce zero peripheral attestations.

### 2.3 Correction C03 — Event Order Validation
- **Defect Identified:** `event_order` was checked after mathematical projection and lacked strict type validation, potentially permitting boolean values (`isinstance(True, int)` is True in Python), negative integers, non-integers, or out-of-order positive values to trigger unhandled indexing errors or unintended negative indexing in the journal.
- **Implementation Correction:**
  In `ExposureTransactionManager.process_event()`, added strict upfront validation immediately following OPEN exposure verification:
  ```python
  # Validate event order (Correction C03)
  order = core_event.event_order
  if isinstance(order, bool) or not isinstance(order, int):
      raise ObservationError(
          f"event_order must be a genuine int, got {type(order).__name__} ({order!r})",
          code=StatusCode.INVALID_OBSERVATION,
      )
  if order < 0:
      raise ObservationError(
          f"event_order must be non-negative, got {order}",
          code=StatusCode.INVALID_OBSERVATION,
      )
  if order > journal.next_event_order:
      raise ObservationError(
          f"Out-of-order event_order {order}; expected {journal.next_event_order}",
          code=StatusCode.INVALID_OBSERVATION,
      )
  ```
  - Rejects `event_order=-1`, `event_order=True`, `event_order=1.5`, and out-of-order positive events with `INVALID_OBSERVATION` before projection or journal indexing.
  - Guarantees contiguous event sequences (`0`, `1`, ...).
  - Permits exact retry only for previously accepted valid orders (`0 <= order < journal.next_event_order`).

### 2.4 Documentation Corrections
- **Function Location & Signature:** Corrected all documentation to accurately state that `finalize_feature_bundle` is defined in `dgca.encoder.decomposer`, and documented its exact production signature:
  ```python
  def finalize_feature_bundle(
      features: Sequence[tuple[str | bytes, str]],
      *,
      salience: str = DEFAULT_SALIENCE_STR,
      allow_reserved_control: bool = False,
  ) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[bytes, int], ...], int, bytes]:
  ```
- **StatusCode Values:** Corrected documentation to reflect that `StatusCode` is a `StrEnum` where all members have string values matching their names (`"PROVENANCE_DIGEST_MISMATCH"`, etc.), not integers.
- **Forensic EOS Test Narrative:** Updated docstrings in `tests/forensics/test_f01_cold_start_and_persistence.py` to explicitly document that the historical outbox bypass is now trapped and rejected during `process_event()`.

---

## 3. Exact Changed Files

| File Path | Description of Changes |
| :--- | :--- |
| `src/dgca/lifecycle/exposure_tx.py` | Added structural canonical EOS precheck (C02), modality validation for language envelopes (C01), and strict upfront event order validation (C03). |
| `tests/test_r2_a01_patch1_acceptance.py` | Added test class `TestR2A01Patch1CorrectionsC01C02C03` containing 13 focused acceptance tests for C01, C02, and C03. Updated edge case assertions. Total tests: 36. |
| `tests/forensics/test_f01_cold_start_and_persistence.py` | Updated narrative docstrings to reflect that the historical outbox bypass is permanently closed. |
| `R2-A01-P1-IMPLEMENTATION-REPORT.md` | Corrected `StatusCode` member string values, updated test counts (116 tests), and updated review status. |
| `R2-A01-P1-CONTRACT-COMPATIBILITY.md` | Corrected `finalize_feature_bundle` location and signature; added sections 2.7–2.10 covering C01, C02, C03, and `StatusCode` string typing. |
| `R2-A01-P1-TEST-RESULTS.md` | Expanded acceptance matrix with 13 new tests (36 total acceptance tests); added verification distinction; logged 116-test run. |

---

## 4. Negative Test Evidence & State Isolation

The 13 newly implemented tests verify all negative cases and confirm strict zero state bleed:

1. **Fresh VISION paired with language envelope (`test_c01_fresh_vision_paired_with_language_envelope_rejected`)**:
   - Status code raised: `StatusCode.INVALID_OBSERVATION`
   - Next event order: 0 (unchanged)
   - Zero state mutation.
2. **Fresh AUDIO paired with language envelope (`test_c01_fresh_audio_paired_with_language_envelope_rejected`)**:
   - Status code raised: `StatusCode.INVALID_OBSERVATION`
   - Next event order: 0 (unchanged)
   - Zero state mutation.
3. **Retry changing LANGUAGE to VISION (`test_c01_retry_changing_language_to_vision_rejected`)**:
   - Status code raised: `StatusCode.INVALID_OBSERVATION` / `StatusCode.EVENT_RETRY_PAYLOAD_CONFLICT`
   - Next event order: 1 (unchanged)
   - Zero state mutation.
4. **Comprehensive State Invariance (`test_c01_all_rejected_cases_leave_state_unchanged`)**:
   - $W$ synaptic clock: 0 (identical)
   - $W$ committed cells: $\emptyset$ (identical)
   - $W$ synapses: 0 (identical)
   - $R$ step index: 0 (identical)
   - $R.A$ active activations: identical
   - $H_{slow}.g$ homeostatic gains: identical
   - Journal event results: 0 (identical)
   - Readout ledger candidates: 0 (identical)
5. **Headless Canonical EOS at Event 0 (`test_c02_headless_canonical_eos_at_order_zero_rejected`)**:
   - Status code raised: `StatusCode.EMPTY_LEXICAL_EXPOSURE`
   - Zero state mutation.
6. **Negative Event Order (`test_c03_negative_event_order_rejected`)**:
   - Input: `event_order = -1`
   - Status code raised: `StatusCode.INVALID_OBSERVATION`
7. **Boolean Event Order (`test_c03_boolean_event_order_rejected`)**:
   - Input: `event_order = True`
   - Status code raised: `StatusCode.INVALID_OBSERVATION`
8. **Float Event Order (`test_c03_float_event_order_rejected`)**:
   - Input: `event_order = 1.5`
   - Status code raised: `StatusCode.INVALID_OBSERVATION`
9. **Out-of-Order Positive Event (`test_c03_out_of_order_positive_event_rejected`)**:
   - Input: `event_order = 2` when next is `0`
   - Status code raised: `StatusCode.INVALID_OBSERVATION`

---

## 5. Full Pytest Results & Scientific Regression Evidence

### 5.1 Test Suite Summary
```text
============================= test session starts =============================
platform win32 -- Python 3.14.4, pytest-9.0.3, pluggy-1.6.0
rootdir: C:\Users\Laptop\Desktop\DGCA NEXT V2
configfile: pyproject.toml
plugins: anyio-4.13.0, hypothesis-6.165.2, asyncio-1.4.0
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

### 5.2 Scientific Invariants Preserved
- **Cat Branch Rollout**: Prompt `['القط']` generates `('يشرب', 'حليب')` followed by `GEN_STOP_EOS` through native neural selection of Assembly 2.
- **Eagle Branch Rollout**: Prompt `['النسر']` generates `('يشرب', 'ماء')` followed by `GEN_STOP_AMBIGUOUS` halting correctly at duplicate Assemblies 5 & 6 collision.
- **Cold-Start Learning from Zero**: Verifies 34 and 56 roots with distinct owners without fixtures.
- **Event Retry Idempotence**: Exact re-submission returns cached result with zero re-execution and zero state mutation.
- **Outbox Digest Verification**: End-exposure notifications assert exact digest match with peripheral envelopes before candidate tracking.

---

## 6. Remaining Scope Boundaries & Status

- **Patches 2 through 5**: Completely untouched.
- **Cross-process persistence**: Remains intentionally unimplemented per specification (`CROSS_PROCESS_PERSISTENCE_NOT_IMPLEMENTED`).
- **No merge to main**: All changes remain strictly contained on branch `fix/r2-a01-p1-provenance-identity`.

**Final Status:**  
`R2-A01-P1-C01 CORRECTED — AWAITING FINAL ACCEPTANCE`
