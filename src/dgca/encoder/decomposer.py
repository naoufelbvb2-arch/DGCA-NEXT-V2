"""Deterministic 4-Feature Orthographic Decomposition and Canonical Bundle Finalization.

Normative references:
- DGCA-DCR-ENCODER-SPEC §1.3 (Canonical EOS lexical event representation)
- DGCA-DCR-ENCODER-SPEC §2.2 (Decomposition algorithm for a normalized lexical token w)
- DGCA-DCR-ENCODER-SPEC §2.3 (Canonical sorting and bundle finalization)
"""

from __future__ import annotations

from collections.abc import Sequence

from dgca.common.errors import (
    EmptyExposureInputError,
    InvalidEncoderInputError,
    StatusCode,
    TokenTooLongError,
)
from dgca.common.hashing import compute_feature_bundle_digest
from dgca.common.numeric import (
    DEFAULT_SALIENCE_STR,
    format_support_millionths,
    noisy_or_millionths,
    parse_support_millionths,
)
from dgca.encoder.normalizer import ALLOWED_WHITESPACE_CHARS, validate_strict_utf8_and_nfc

ENCODER_VERSION: str = "DGCA-ENC-V1"
MAX_FEATURES_PER_EVENT: int = 4
MIN_FEATURES_PER_EVENT: int = 3
MAX_TOKEN_UTF8_BYTES: int = 64

SUPPORT_TIER_0: str = "1.000000"
SUPPORT_TIER_1: str = "0.900000"
SUPPORT_TIER_2: str = "0.800000"
SUPPORT_TIER_3: str = "0.750000"

EOS_CANONICAL_FEATURES: tuple[tuple[str, str], ...] = (
    ("\x1fEOS#0", SUPPORT_TIER_0),
    ("\x1fEOS#1", SUPPORT_TIER_1),
    ("\x1fEOS#2", SUPPORT_TIER_2),
)


def decompose_lexical_token(raw_token: str | bytes) -> tuple[tuple[str, str], ...]:
    """Decompose a single normalized lexical or internal-punctuation token w into 3 or 4 features.

    Returns:
        Tuple of (feature_text_NFC_UTF8, support_decimal_6) sorted by ascending unsigned UTF-8 bytes.
    """
    w = validate_strict_utf8_and_nfc(raw_token, allow_reserved_control=False)
    if not w:
        raise EmptyExposureInputError("Lexical token cannot be empty")
    for ch in w:
        if ch in ALLOWED_WHITESPACE_CHARS:
            raise InvalidEncoderInputError(
                f"Lexical token must not contain whitespace: {w!r}"
            )

    w_utf8 = w.encode("utf-8")
    if len(w_utf8) > MAX_TOKEN_UTF8_BYTES:
        raise TokenTooLongError(
            f"Token UTF-8 byte length {len(w_utf8)} exceeds MAX_TOKEN_UTF8_BYTES ({MAX_TOKEN_UTF8_BYTES})"
        )

    length = len(w)
    if length == 1:
        # Encoder §2.2 special handling for L = 1
        candidates = [
            (f"^{w}$", SUPPORT_TIER_0),
            (f"^1:{w}", SUPPORT_TIER_1),
            (f"1$:{w}", SUPPORT_TIER_2),
        ]
    elif length == 2:
        # Encoder §2.2 special handling for L = 2
        candidates = [
            (f"^{w}$", SUPPORT_TIER_0),
            (f"^{w}", SUPPORT_TIER_1),
            (f"{w}$", SUPPORT_TIER_2),
        ]
    else:
        # Encoder §2.2 standard 4-tier extraction for L >= 3
        m = (length - 3) // 2
        medial_trigram = w[m : m + 3]
        candidates = [
            (f"^{w}$", SUPPORT_TIER_0),
            (f"^{w[:2]}", SUPPORT_TIER_1),
            (f"{w[-2:]}$", SUPPORT_TIER_2),
            (f"~{medial_trigram}", SUPPORT_TIER_3),
        ]

    # Sort strictly in ascending unsigned UTF-8 byte order
    candidates.sort(key=lambda pair: pair[0].encode("utf-8"))
    return tuple(candidates)


def decompose_eos_event() -> tuple[tuple[str, str], ...]:
    """Return the canonical sorted 3-feature bundle for an EOS event (Encoder §1.3)."""
    return EOS_CANONICAL_FEATURES


def finalize_feature_bundle(
    features: Sequence[tuple[str | bytes, str]],
    *,
    salience: str = DEFAULT_SALIENCE_STR,
    allow_reserved_control: bool = False,
) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[bytes, int], ...], int, bytes]:
    """Normalize, deduplicate (via exact decimal Noisy-OR), sort, and hash a feature bundle.

    Returns:
        (
            canonical_features_str: tuple of (feature_str_nfc, support_str_6),
            canonical_features_bytes: tuple of (feature_utf8_bytes, support_u32),
            salience_u32: int,
            feature_bundle_digest: bytes32
        )
    """
    salience_u = parse_support_millionths(
        salience, error_code=StatusCode.INVALID_ENCODER_INPUT
    )
    if not features:
        raise InvalidEncoderInputError("Feature bundle must contain at least one feature")

    grouped: dict[bytes, tuple[str, list[int]]] = {}
    for raw_feat, support_str in features:
        nfc_feat = validate_strict_utf8_and_nfc(
            raw_feat, allow_reserved_control=allow_reserved_control
        )
        feat_bytes = nfc_feat.encode("utf-8")
        if not feat_bytes or len(feat_bytes) > 4096:
            raise InvalidEncoderInputError(
                f"Normalized feature byte length {len(feat_bytes)} outside [1, 4096]"
            )
        u = parse_support_millionths(
            support_str, error_code=StatusCode.INVALID_ENCODER_INPUT
        )
        if feat_bytes not in grouped:
            grouped[feat_bytes] = (nfc_feat, [u])
        else:
            grouped[feat_bytes][1].append(u)

    # Sort unique features by unsigned UTF-8 byte order
    sorted_keys = sorted(grouped.keys())
    canonical_str: list[tuple[str, str]] = []
    canonical_bytes: list[tuple[bytes, int]] = []

    for feat_bytes in sorted_keys:
        nfc_feat, u_list = grouped[feat_bytes]
        merged_u = u_list[0] if len(u_list) == 1 else noisy_or_millionths(u_list)
        canonical_str.append((nfc_feat, format_support_millionths(merged_u)))
        canonical_bytes.append((feat_bytes, merged_u))

    digest = compute_feature_bundle_digest(salience_u, canonical_bytes)
    return tuple(canonical_str), tuple(canonical_bytes), salience_u, digest
