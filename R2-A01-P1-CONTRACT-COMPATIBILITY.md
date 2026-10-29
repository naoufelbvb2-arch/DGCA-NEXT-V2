# DGCA NEXT V2 — R2-A01 PATCH 1 CONTRACT COMPATIBILITY

**Document ID:** DGCA-R2-A01-P1-COMPATIBILITY  
**Author:** Principal Python Systems Engineer & Independent Scientific Verification Engineer  
**Baseline Git Commit:** `31721fd1ba7559b72d9fe11f037ea0c0d1e91ed2`  
**Target Branch:** `fix/r2-a01-p1-provenance-identity`  
**Status:** COMPLETE & RATIFIED  

---

## 1. Purpose

During the transition from the preliminary conceptual design specification of R2-A01 to real-world code implementation in DGCA NEXT V2, several architectural contracts required precise reconciliation with the actual production code interfaces.

This document details all technical design reconciliations made in Patch 1, confirming their compliance with the normative specifications (`DGCA_CORE_RC4_1.md`, `DGCA_LLA_RC4_1.md`, and `dgca_v2_dynamic_core_reconstruction_encoder_specification.md`).

---

## 2. Technical Contract Reconciliations

### 2.1 Feature Bundle Digest & Finalization Signature
- **Preliminary Specification Concept**:
  The R2-A01 draft referenced a theoretical function `canonical_feature_bundle_digest(raw_features)` or `Encoder.canonicalize()`.
- **Actual Production Interface**:
  Defined in `dgca.encoder.decomposer`, the frozen canonicalization and digest generation engine is:
  ```python
  def finalize_feature_bundle(
      features: Sequence[tuple[str | bytes, str]],
      *,
      salience: str = DEFAULT_SALIENCE_STR,
      allow_reserved_control: bool = False,
  ) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[bytes, int], ...], int, bytes]:
  ```
  Returns:
  ```python
  (
      canonical_features_str: tuple of (feature_str_nfc, support_str_6),
      canonical_features_bytes: tuple of (feature_utf8_bytes, support_u32),
      salience_u32: int,
      feature_bundle_digest: bytes32,
  )
  ```
- **Patch 1 Alignment**:
  `validate_event_envelope_provenance` directly invokes `finalize_feature_bundle` using `salience=core_event.salience` and `allow_reserved_control=is_eos`. This guarantees exact bitwise parity between the reconstructed bundle digest and the projection digest produced by `SICProjectionResult`.

### 2.2 SIC Projection Result Type Identity
- **Preliminary Specification Concept**:
  The conceptual design referred to generic `ProjectionResult`.
- **Actual Production Interface**:
  The core projection engine `project_core_event_v1()` returns `SICProjectionResult` (defined in `dgca.core.sic_v1`).
- **Patch 1 Alignment**:
  `validate_event_envelope_provenance` explicitly types the parameter as `projection: SICProjectionResult`, ensuring full type safety and direct access to `projection.feature_bundle_digest`.

### 2.3 Strict Separation: Literal Lexical `<EOS>` vs Canonical Special EOS
- **Preliminary Specification Ambiguity**:
  The draft noted that `<EOS>` was a reserved surface string, but did not clearly distinguish between natural text containing `<EOS>` as a literal token versus a terminal exposure control event.
- **Production Normative Reality**:
  1. **Canonical Special EOS**:
     - `raw_surface_nfc_utf8 == "<EOS>"`
     - `marker == Marker.EOS`
     - `boundary == False`
     - `event_order > 0`
     - Features: `EOS_CANONICAL_FEATURES` (`\x1fEOS#0`, `\x1fEOS#1`, `\x1fEOS#2`).
  2. **Literal Lexical Token `<EOS>`**:
     - `marker == Marker.NONE`
     - Contains ordinary character tokens decomposed into n-grams (`^<EOS>$`, `^<E`, `OS>$`, `~EOS`).
- **Patch 1 Alignment**:
  Patch 1 explicitly separates these two pathways. If `marker == Marker.NONE`, the surface is decomposed via `decompose_lexical_token()`. If `marker == Marker.EOS`, the canonical special token features are enforced. Attempting to disguise a lexical decomposition under `Marker.EOS` is rejected with `PROVENANCE_FEATURE_COPY_MISMATCH`.

### 2.4 Event Modality Identity Typing
- **Preliminary Specification Concept**:
  `EventIdentityKey` referenced `modality` as a string or generic integer.
- **Actual Production Interface**:
  In DGCA NEXT V2, modality is strictly typed as `Region` (`Region.LANGUAGE = 2`).
- **Patch 1 Alignment**:
  `EventIdentityKey.modality` is typed as `Region`. Any change in modality on event retry is caught and rejected with `EVENT_RETRY_PAYLOAD_CONFLICT`.

### 2.5 Error Handling Precedence Hierarchy
- **Preliminary Specification Order**:
  Did not specify whether payload conflict or channel alteration should be evaluated before or after provenance validation.
- **Implemented Precedence in Patch 1**:
  To guarantee zero state bleed and fail-fast security, `process_event()` evaluates checks in the following order:
  1. **Provenance Validation (`validate_event_envelope_provenance`)**:
     Validates envelope integrity, NFC normalization, SHA-256 surface hash, and feature/digest derivation.
  2. **Retry Channel Alteration Check**:
     If an existing event at the same `event_order` had an envelope, retrying it without an envelope (or vice versa) raises `EVENT_RETRY_PROVENANCE_ALTERATION`.
  3. **Exact Payload Identity Comparison**:
     Compares the newly constructed `EventIdentityKey` with the accepted identity from `open_journal.event_identities`. If any field differs (modality, features, digest, salience, boundary, origin, scope), raises `EVENT_RETRY_PAYLOAD_CONFLICT`.
  4. **Exact Match Idempotent Fast Return**:
     If identity keys match exactly, returns the cached `EventExecutionResult` with zero re-execution and zero state mutation.

### 2.6 Headless Mode Policy & Test Isolation
- **Preliminary Specification**:
  Did not specify how lower-level unit tests testing synthetic transaction mechanics without language pipelines should function.
- **Patch 1 Policy**:
  - `allow_headless_events: bool = False` by default in `ExposureTransactionManager`. In production, language events must provide a valid peripheral envelope.
  - Low-level synthetic unit tests (`tests/test_phase3_lla_and_transactions.py` and `src/dgca/experiments/gates.py`) explicitly configure `ExposureTransactionManager(state, allow_headless_events=True)` to test transaction rollback and commit mechanics in isolation.

### 2.7 Language Modality Invariant for Peripheral Envelopes (Correction C01)
- For an external event carrying `PeripheralSurfaceEnvelopeV1`, `core_event.modality` must equal `Region.LANGUAGE`.
- Mismatched modalities (e.g. `Region.VISION`, `Region.AUDIO`) are rejected before neural execution with `ObservationError(code=StatusCode.INVALID_OBSERVATION)`.

### 2.8 Headless Canonical EOS Structural Precheck (Correction C02)
- Structural rules governing canonical EOS are evaluated independently of envelope presence.
- Even under `allow_headless_events=True` and `envelope=None`, canonical EOS at `event_order == 0` is strictly rejected with `ObservationError(code=StatusCode.EMPTY_LEXICAL_EXPOSURE)` with zero state mutation.
- Valid canonical headless EOS events at `event_order > 0` are accepted and produce zero peripheral attestations.

### 2.9 Event Order Invariants & Replay Boundary (Correction C03)
- `event_order` is validated before journal lookups: must be a genuine non-negative integer (`not isinstance(order, bool) and isinstance(order, int) and order >= 0`).
- Non-integers (e.g. floats, booleans) or negative orders are rejected with `ObservationError(code=StatusCode.INVALID_OBSERVATION)`.
- Out-of-order positive events (`order > journal.next_event_order`) fail immediately with `INVALID_OBSERVATION` without state mutation.
- Valid previously processed orders (`0 <= order < journal.next_event_order`) trigger exact retry comparison only.

### 2.10 Diagnostic Code Typing (`StatusCode`)
- All `StatusCode` members are typed as `StrEnum` with string values matching their identifier names (e.g., `StatusCode.PROVENANCE_DIGEST_MISMATCH == "PROVENANCE_DIGEST_MISMATCH"`), not numerical values.
