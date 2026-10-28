"""Unicode UTF-8 validation, NFC normalization, and control byte rejection.

Normative reference:
- DGCA-DCR-ENCODER-SPEC §1.1 (Unicode normalization and validation)
"""

from __future__ import annotations

import unicodedata

from dgca.common.errors import (
    EmptyExposureInputError,
    InvalidEncoderInputError,
    ReservedControlByteError,
)

# Allowed ASCII whitespace characters in caller-supplied natural text:
# U+0020 (space), U+0009 (\t), U+000A (\n), U+000D (\r)
ALLOWED_WHITESPACE_CHARS: frozenset[str] = frozenset({" ", "\t", "\n", "\r"})
ALLOWED_CONTROL_CODEPOINTS: frozenset[int] = frozenset({0x09, 0x0A, 0x0D})


def validate_strict_utf8_and_nfc(
    raw_input: str | bytes,
    *,
    allow_reserved_control: bool = False,
) -> str:
    """Validate strict UTF-8, reject lone surrogates and forbidden control bytes, and normalize to NFC.

    Args:
        raw_input: Caller-supplied str or bytes.
        allow_reserved_control: Only True for internal canonical EOS features (0x1F) or
            explicit raw pass-through mode if applicable. Even then, 0x00 is rejected.

    Returns:
        NFC-normalized Unicode string.
    """
    if isinstance(raw_input, bytes):
        try:
            text = raw_input.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise InvalidEncoderInputError(f"Invalid UTF-8 byte sequence: {exc}") from exc
    elif isinstance(raw_input, str):
        # Reject lone surrogates (U+D800..U+DFFF) which are invalid in strict UTF-8
        for ch in raw_input:
            cp = ord(ch)
            if 0xD800 <= cp <= 0xDFFF:
                raise InvalidEncoderInputError(
                    f"Lone Unicode surrogate U+{cp:04X} rejected"
                )
        text = raw_input
    else:
        raise InvalidEncoderInputError(
            f"Expected str or bytes input, got {type(raw_input).__name__}"
        )

    # Check control characters before and after NFC normalization
    _check_control_characters(text, allow_reserved_control=allow_reserved_control)
    nfc_text = unicodedata.normalize("NFC", text)
    _check_control_characters(nfc_text, allow_reserved_control=allow_reserved_control)
    return nfc_text


def _check_control_characters(text: str, *, allow_reserved_control: bool) -> None:
    """Enforce Encoder §1.1 rule 2: reject 0x00 and forbidden ASCII control bytes 0x01..0x1F."""
    for ch in text:
        cp = ord(ch)
        if cp == 0x00:
            raise ReservedControlByteError("NUL byte (0x00) is forbidden in encoder input")
        if 0x01 <= cp <= 0x1F and cp not in ALLOWED_CONTROL_CODEPOINTS:
            if allow_reserved_control and cp == 0x1F:
                continue
            raise ReservedControlByteError(
                f"Reserved ASCII control byte 0x{cp:02X} is forbidden in natural text input"
            )


def normalize_and_strip_exposure_text(raw_input: str | bytes) -> str:
    """Validate UTF-8, normalize to NFC, reject control bytes, and strip leading/trailing whitespace.

    Raises EmptyExposureInputError if the stripped string is empty.
    """
    nfc_text = validate_strict_utf8_and_nfc(raw_input, allow_reserved_control=False)
    stripped = nfc_text.strip(" \t\r\n")
    if not stripped:
        raise EmptyExposureInputError("Exposure input is empty after stripping whitespace")
    return stripped
