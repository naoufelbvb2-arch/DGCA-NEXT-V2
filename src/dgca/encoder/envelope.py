"""Dual Envelope Protocol: Core Neural Payload vs Peripheral Readout Envelope.

Normative references:
- DGCA-DCR-ENCODER-SPEC §4 (Dual Envelope Protocol: Core Input vs Peripheral Readout Ledger)
- DGCA-DCR-ENCODER-SPEC §4.1 (Closed-loop feedback during GENERATE_EPISODE)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum, StrEnum

from dgca.common.errors import DGCAError, StatusCode
from dgca.common.hashing import Region, sha256_bytes
from dgca.common.numeric import DEFAULT_SALIENCE_STR, format_support_millionths
from dgca.encoder.decomposer import (
    decompose_eos_event,
    decompose_lexical_token,
    finalize_feature_bundle,
)
from dgca.encoder.segmenter import EOS_RAW_SURFACE, segment_exposure_text


class EventOrigin(StrEnum):
    """Canonical event origin tags (Core §6.1, Encoder §4)."""

    EXTERNAL_DIRECT = "EXTERNAL_DIRECT"
    READ_ONLY_OBSERVED = "READ_ONLY_OBSERVED"
    INTERNAL_SELECTED = "INTERNAL_SELECTED"


class Marker(IntEnum):
    """Peripheral surface marker byte (Encoder §1.3, §4)."""

    NONE = 0x00
    EOS = 0x01


@dataclass(frozen=True, slots=True)
class CoreEventPayloadV1:
    """Core Neural Payload passed to Core EVENT / READ_ONLY / GENERATE prompt.

    Contains zero raw_surface or semantic strings — only mechanical features and digests.
    """

    exposure_id: int | None
    event_order: int
    modality: Region
    origin: EventOrigin
    boundary: bool
    salience: str
    features: tuple[tuple[str, str], ...]
    feature_bundle_digest: bytes


@dataclass(frozen=True, slots=True)
class PeripheralSurfaceEnvelopeV1:
    """Peripheral Readout Envelope held in I/O shell; NEVER read by Core/LLA ranking."""

    raw_surface_nfc_utf8: str
    surface_sha256: bytes
    feature_bundle_digest: bytes
    canonical_features_copy: tuple[tuple[str, str], ...]
    marker: Marker

    @property
    def surface_utf8_nfc(self) -> str:
        """Canonical alias for raw_surface_nfc_utf8 (Core §9.4)."""
        return self.raw_surface_nfc_utf8


@dataclass(frozen=True, slots=True)
class EncodedEventEnvelopeV1:
    """Dual segregated envelope produced by the stateless Encoder for a single event."""

    core_event: CoreEventPayloadV1
    peripheral_surface: PeripheralSurfaceEnvelopeV1


def build_event_envelope(
    raw_surface_nfc: str,
    raw_features: Sequence[tuple[str, str]],
    *,
    marker: Marker = Marker.NONE,
    exposure_id: int | None = None,
    event_order: int = 0,
    origin: EventOrigin = EventOrigin.EXTERNAL_DIRECT,
    boundary: bool = False,
    salience: str = DEFAULT_SALIENCE_STR,
) -> EncodedEventEnvelopeV1:
    """Construct a segregated EncodedEventEnvelopeV1 from extracted features and surface."""
    allow_ctrl = marker == Marker.EOS
    canonical_str, _, salience_u, bundle_digest = finalize_feature_bundle(
        raw_features,
        salience=salience,
        allow_reserved_control=allow_ctrl,
    )
    normalized_salience_str = format_support_millionths(salience_u)
    surface_hash = sha256_bytes(raw_surface_nfc.encode("utf-8"))

    core_event = CoreEventPayloadV1(
        exposure_id=exposure_id,
        event_order=event_order,
        modality=Region.LANGUAGE,
        origin=origin,
        boundary=boundary,
        salience=normalized_salience_str,
        features=canonical_str,
        feature_bundle_digest=bundle_digest,
    )
    peripheral_surface = PeripheralSurfaceEnvelopeV1(
        raw_surface_nfc_utf8=raw_surface_nfc,
        surface_sha256=surface_hash,
        feature_bundle_digest=bundle_digest,
        canonical_features_copy=canonical_str,
        marker=marker,
    )
    return EncodedEventEnvelopeV1(
        core_event=core_event,
        peripheral_surface=peripheral_surface,
    )


def encode_lexical_token_event(
    raw_token: str | bytes,
    *,
    exposure_id: int | None = None,
    event_order: int = 0,
    origin: EventOrigin = EventOrigin.EXTERNAL_DIRECT,
    boundary: bool = True,
    salience: str = DEFAULT_SALIENCE_STR,
) -> EncodedEventEnvelopeV1:
    """Encode a single non-EOS lexical or internal-punctuation token into a dual envelope."""
    features = decompose_lexical_token(raw_token)
    # Extract normalized token w from F0 ("^" + w + "$")
    f0_candidates = [f for f, s in features if s == "1.000000" and f.startswith("^") and f.endswith("$")]
    raw_surface_nfc = f0_candidates[0][1:-1]
    return build_event_envelope(
        raw_surface_nfc=raw_surface_nfc,
        raw_features=features,
        marker=Marker.NONE,
        exposure_id=exposure_id,
        event_order=event_order,
        origin=origin,
        boundary=boundary,
        salience=salience,
    )


def encode_eos_event(
    *,
    exposure_id: int | None = None,
    event_order: int = 1,
    origin: EventOrigin = EventOrigin.EXTERNAL_DIRECT,
    salience: str = DEFAULT_SALIENCE_STR,
) -> EncodedEventEnvelopeV1:
    """Encode a canonical terminal EOS event (Encoder §1.3).

    Note: boundary is always False for EOS (cannot be event 0 alone).
    """
    if event_order <= 0:
        raise DGCAError(
            StatusCode.EMPTY_LEXICAL_EXPOSURE,
            "Canonical EOS event cannot be event_order 0 alone",
        )
    features = decompose_eos_event()
    return build_event_envelope(
        raw_surface_nfc=EOS_RAW_SURFACE,
        raw_features=features,
        marker=Marker.EOS,
        exposure_id=exposure_id,
        event_order=event_order,
        origin=origin,
        boundary=False,
        salience=salience,
    )


def encode_exposure(
    raw_text: str | bytes,
    *,
    exposure_id: int | None = None,
    origin: EventOrigin = EventOrigin.EXTERNAL_DIRECT,
    append_eos: bool = True,
    salience: str = DEFAULT_SALIENCE_STR,
) -> tuple[EncodedEventEnvelopeV1, ...]:
    """Segment and encode a complete natural-language text exposure into ordered dual envelopes.

    Implements Encoder §1, §2, and §4 end-to-end.
    """
    segmented_tokens = segment_exposure_text(raw_text, append_eos=append_eos)
    envelopes: list[EncodedEventEnvelopeV1] = []

    for token in segmented_tokens:
        if token.is_eos:
            env = encode_eos_event(
                exposure_id=exposure_id,
                event_order=token.event_order,
                origin=origin,
                salience=salience,
            )
        else:
            env = encode_lexical_token_event(
                token.surface,
                exposure_id=exposure_id,
                event_order=token.event_order,
                origin=origin,
                boundary=token.boundary,
                salience=salience,
            )
        envelopes.append(env)

    return tuple(envelopes)


def reinject_attested_bundle(
    peripheral_surface: PeripheralSurfaceEnvelopeV1,
    *,
    event_order: int,
    exposure_id: int | None = None,
    salience: str = DEFAULT_SALIENCE_STR,
) -> CoreEventPayloadV1:
    """Wrap an attested peripheral ledger record's canonical_features_copy into an INTERNAL_SELECTED Core event.

    Implements Encoder §4.1 step 3 and test gate ENC-T09 without re-running text segmentation.
    """
    if peripheral_surface.marker == Marker.EOS:
        raise DGCAError(
            StatusCode.GEN_STOP_EOS,
            "Cannot re-inject EOS peripheral surface as an internal lexical event",
        )
    _, _, salience_u, digest = finalize_feature_bundle(
        peripheral_surface.canonical_features_copy,
        salience=salience,
        allow_reserved_control=False,
    )
    if salience == DEFAULT_SALIENCE_STR and digest != peripheral_surface.feature_bundle_digest:
        raise DGCAError(
            StatusCode.INVALID_OBSERVATION,
            "Peripheral surface feature_bundle_digest mismatch on re-injection",
        )
    return CoreEventPayloadV1(
        exposure_id=exposure_id,
        event_order=event_order,
        modality=Region.LANGUAGE,
        origin=EventOrigin.INTERNAL_SELECTED,
        boundary=False,
        salience=format_support_millionths(salience_u),
        features=peripheral_surface.canonical_features_copy,
        feature_bundle_digest=digest,
    )
