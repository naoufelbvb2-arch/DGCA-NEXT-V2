"""Lexical and punctuation stream segmentation into discrete temporal events.

Normative references:
- DGCA-DCR-ENCODER-SPEC §1.2 (Lexical vs punctuation segmentation rules)
- DGCA-DCR-ENCODER-SPEC §1.3 (Canonical EOS lexical event representation)
"""

from __future__ import annotations

from dataclasses import dataclass

from dgca.common.errors import EmptyLexicalExposureError
from dgca.encoder.normalizer import ALLOWED_WHITESPACE_CHARS, normalize_and_strip_exposure_text

# Encoder §1.2 rule 2: Internal punctuation delimiters (detached as L=1 tokens, marker=NONE)
INTERNAL_PUNCTUATION_DELIMITERS: frozenset[str] = frozenset(
    {
        ",",
        "\u060c",  # Arabic comma ،
        ";",
        "\u061b",  # Arabic semicolon ؛
        ":",
    }
)

# Encoder §1.2 rule 3: Terminal sentence delimiters (detach and emit canonical EOS event)
TERMINAL_SENTENCE_DELIMITERS: frozenset[str] = frozenset(
    {
        ".",
        "!",
        "?",
        "\u061f",  # Arabic question mark ؟
    }
)

EOS_RAW_SURFACE: str = "<EOS>"


@dataclass(frozen=True, slots=True)
class SegmentedEventToken:
    """A single segmented event token produced by Layer 1 stream segmentation."""

    event_order: int
    surface: str
    is_eos: bool
    boundary: bool


def segment_exposure_text(
    raw_input: str | bytes,
    *,
    append_eos: bool = True,
) -> tuple[SegmentedEventToken, ...]:
    """Segment a raw UTF-8 exposure string into ordered lexical, punctuation, and EOS events.

    Args:
        raw_input: Raw UTF-8 text string or bytes.
        append_eos: If True (LAB DEFAULT), appends a canonical EOS event at the end
            if one was not already emitted by terminal punctuation.

    Returns:
        Tuple of SegmentedEventToken with contiguous event_order 0..n-1.
    """
    text = normalize_and_strip_exposure_text(raw_input)

    raw_items: list[tuple[str, bool]] = []  # (surface, is_eos)
    n = len(text)
    i = 0

    while i < n:
        ch = text[i]

        # 1. Whitespace delimiter run: collapse and advance
        if ch in ALLOWED_WHITESPACE_CHARS:
            while i < n and text[i] in ALLOWED_WHITESPACE_CHARS:
                i += 1
            continue

        # 2. Internal punctuation delimiter: single character event (L=1, is_eos=False)
        if ch in INTERNAL_PUNCTUATION_DELIMITERS:
            raw_items.append((ch, False))
            i += 1
            continue

        # 3. Terminal sentence delimiter run: consecutive '.', '!', '?', '؟' -> single EOS
        if ch in TERMINAL_SENTENCE_DELIMITERS:
            while i < n and text[i] in TERMINAL_SENTENCE_DELIMITERS:
                i += 1
            # Emit EOS (collapse if immediately preceded by an EOS event)
            if not raw_items or not raw_items[-1][1]:
                raw_items.append((EOS_RAW_SURFACE, True))
            continue

        # 4. Contiguous lexical token run
        start = i
        while (
            i < n
            and text[i] not in ALLOWED_WHITESPACE_CHARS
            and text[i] not in INTERNAL_PUNCTUATION_DELIMITERS
            and text[i] not in TERMINAL_SENTENCE_DELIMITERS
        ):
            i += 1
        token_surface = text[start:i]
        raw_items.append((token_surface, False))

    # Encoder §1.3: EOS cannot be event 0 alone; a bare EOS exposure is rejected
    if not raw_items or raw_items[0][1]:
        raise EmptyLexicalExposureError(
            "Exposure must begin with a non-EOS lexical token; bare EOS exposure is forbidden"
        )

    # Encoder §1.2 rule 3: append canonical EOS if append_eos=True and not already ended with EOS
    if append_eos and not raw_items[-1][1]:
        raw_items.append((EOS_RAW_SURFACE, True))

    events: list[SegmentedEventToken] = []
    for idx, (surface, is_eos) in enumerate(raw_items):
        events.append(
            SegmentedEventToken(
                event_order=idx,
                surface=surface,
                is_eos=is_eos,
                boundary=(idx == 0),
            )
        )

    return tuple(events)
