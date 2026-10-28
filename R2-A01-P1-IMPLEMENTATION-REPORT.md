# DGCA NEXT V2 — R2-A01 PATCH 1 IMPLEMENTATION REPORT

**Document ID:** DGCA-R2-A01-P1-REPORT  
**Author:** Principal Python Systems Engineer & Independent Scientific Verification Engineer  
**Baseline Git Commit:** `31721fd1ba7559b72d9fe11f037ea0c0d1e91ed2` (`main`)  
**Target Branch:** `fix/r2-a01-p1-provenance-identity`  
**Status:** `R2-A01-P1 IMPLEMENTED — AWAITING INDEPENDENT REVIEW`  
**Date:** October 28, 2026  

---

## 1. Executive Summary

This report documents the complete implementation and verification of **PATCH 1 ONLY** (Surface Provenance & Exact Event Identity) of the DGCA NEXT V2 transaction remediation architecture (R2-A01).

### Scope and Authorization
In strict compliance with authorization constraints:
- **Only Patch 1 has been implemented.** Patches 2 through 5 remain untouched.
- No modifications have been made to:
  - LLA learning equations (hebbian plasticity, weight updates, decay).
  - Neural activation dynamics or competitive inhibition.
  - Assembly lifecycle (FORM, GROW, MERGE, SPLIT, latent-slot recruitment).
  - Readout scoring, candidate graduation, or generation thresholds.
  - Latent topology algorithms or spatial layout computation.
  - Transaction publication ordering or outbox reconciliation architecture.
- Baseline commit `31721fd1ba7559b72d9fe11f037ea0c0d1e91ed2` served as the direct ancestor. No forensic or design branches were merged into the implementation branch.

---

## 2. Implemented Code Changes

### 2.1 Error Hierarchy Extensions (`src/dgca/common/errors.py`)
Added authoritative status codes for surface provenance and event identity validation:
- `PROVENANCE_DIGEST_MISMATCH = 1010` — Raised when feature bundle digests do not match across envelope, core payload, or reconstructed surface features.
- `PROVENANCE_MARKER_MISMATCH = 1011` — Raised when envelope marker does not match payload boundary/type semantics or contains illegal control characters.
- `PROVENANCE_FEATURE_COPY_MISMATCH = 1012` — Raised when feature copies in envelope or core payload diverge from canonical features derived from raw surface.
- `PROVENANCE_ENVELOPE_MISSING = 1013` — Raised when a language event lacks an envelope under strict provenance (`allow_headless_events=False`).
- `INVALID_SURFACE_HASH = 1014` — Raised when `surface_sha256` does not match the actual SHA-256 of the UTF-8 raw surface bytes.
- `EVENT_RETRY_PAYLOAD_CONFLICT = 1015` — Raised when an event is retried with an altered core payload.
- `EVENT_RETRY_PROVENANCE_ALTERATION = 1016` — Raised when an event retry attempts to alter the peripheral provenance channel (e.g., retrying headless vs envelope-backed).

### 2.2 Neural Event Dynamics (`src/dgca/core/dynamics.py`)
- Extended `EventExecutionResult` with `feature_bundle_digest: bytes = b""`.
- Inside `execute_two_pass_event()`, captured `feature_bundle_digest` directly from `SICProjectionResult` and populated `EventExecutionResult.feature_bundle_digest`.
- Ensured zero modification to two-pass activation dynamics, synapse updates, or cell recruitment.

### 2.3 Peripheral Outbox Digest Verification (`src/dgca/peripheral/outbox.py`)
- Removed silent fallback `getattr(ev, "feature_bundle_digest", None)` which previously allowed unverified event results to bypass outbox validation.
- Enforced strict digest equality when a peripheral envelope is present:
  ```python
  if ev.feature_bundle_digest != envelope.feature_bundle_digest:
      raise ObservationError(
          f"EventExecutionResult digest does not match peripheral envelope digest",
          code=StatusCode.PROVENANCE_DIGEST_MISMATCH,
      )
  ```
- Guaranteed that outbox notifications cannot publish when feature digests diverge.

### 2.4 Transaction Lifecycle & Provenance Engine (`src/dgca/lifecycle/exposure_tx.py`)
- **Canonical Envelope & Event Identity Keys**:
  - Implemented `CanonicalEnvelopeIdentity`: frozen dataclass capturing `raw_surface_nfc_utf8`, `surface_sha256`, `features_copy`, `feature_bundle_digest`, and `marker`.
  - Implemented `EventIdentityKey`: frozen dataclass capturing exact identity (`modality: Region`, `features`, `feature_bundle_digest`, `salience`, `boundary`, `origin`, `observation_scope`, `envelope_identity`).
- **Provenance Validation Engine (`validate_event_envelope_provenance`)**:
  - **Headless Mode Policy**: Rejects headless events unless `allow_headless_events=True`.
  - **Surface Integrity**: Rejects non-string surfaces, lone Unicode surrogates (`0xD800`–`0xDFFF`), and non-NFC normalized strings (`unicodedata.is_normalized("NFC")`). Verifies `surface_sha256 == sha256(raw_surface.encode("utf-8"))`.
  - **Canonical EOS Rules**: Fast empty-exposure rejection at `event_order == 0` (`EMPTY_LEXICAL_EXPOSURE`). Enforces `raw_surface == "<EOS>"`, `marker == Marker.EOS`, `boundary == False`, and `raw_expected_features = EOS_CANONICAL_FEATURES`.
  - **Lexical Surface Rules**: Enforces `marker == Marker.NONE` and absence of reserved control delimiter `\x1f`. Mechanically decomposes raw surface via `decompose_lexical_token()`.
  - **Mechanical Feature Reconstruction**: Calls `finalize_feature_bundle(raw_expected_features, salience=core_event.salience, allow_reserved_control=is_eos)`.
  - **5-Way Strict Parity Assertion**:
    1. `core_event.features == canonical_features`
    2. `envelope.features_copy == canonical_features`
    3. `core_event.feature_bundle_digest == expected_digest`
    4. `envelope.feature_bundle_digest == expected_digest`
    5. `projection.feature_bundle_digest == expected_digest`
- **Transaction Manager Idempotence & State Isolation (`process_event`)**:
  - Provenance validation runs before any core state modification.
  - On event retry (matching `event_order`):
    - Validates provenance.
    - Rejects provenance channel alterations (`EVENT_RETRY_PROVENANCE_ALTERATION`).
    - Compares new `EventIdentityKey` with accepted identity; rejects conflicts (`EVENT_RETRY_PAYLOAD_CONFLICT`).
    - If identical: returns cached `EventExecutionResult` with zero re-execution and zero state mutation.
  - Records accepted identity in `OpenExposureJournal.event_identities`.

### 2.5 Low-Level Synthetic Test Opt-in (`tests/test_phase3_lla_and_transactions.py` & `src/dgca/experiments/gates.py`)
- Default production mode requires full peripheral envelopes (`allow_headless_events=False`).
- Low-level synthetic unit tests in Phase 3 testing raw transaction abort/commit without surface envelopes were updated to explicitly pass `allow_headless_events=True`.

---

## 3. Regression & Acceptance Verification

| Test Suite | Tests Run | Passed | Failed | Duration | Status |
| :--- | :---: | :---: | :---: | :---: | :---: |
| Baseline Core & Phase 2–7 Suite | 76 | 76 | 0 | 17.5s | PASS |
| Forensic Regression Suite (`test_f01_cold_start_and_persistence.py`) | 4 | 4 | 0 | 39.1s | PASS |
| Patch 1 Acceptance Suite (`test_r2_a01_patch1_acceptance.py`) | 23 | 23 | 0 | 1.3s | PASS |
| **Total Full Test Suite** | **103** | **103** | **0** | **56.6s** | **100% PASS** |

---

## 4. Architectural Boundaries Maintained

- **Patches 2–5 Untouched**:
  - Patch 2 (Two-Phase Commit & Journal Atomicity): Not touched.
  - Patch 3 (Assembly Mutation Rollback & Topology Integrity): Not touched.
  - Patch 4 (Outbox Publication & Event Sequencing): Not touched.
  - Patch 5 (Persistence & Recovery Contract): Not touched.
- **Branch Cleanliness**:
  - The implementation was developed directly on branch `fix/r2-a01-p1-provenance-identity` branched from commit `31721fd1ba7559b72d9fe11f037ea0c0d1e91ed2`.
  - No merge commits from audit or design branches exist.

---

## 5. Review Gate Status

**Status:** `R2-A01-P1 IMPLEMENTED — AWAITING INDEPENDENT REVIEW`
