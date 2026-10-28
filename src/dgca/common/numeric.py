"""Exact decimal millionths, Q6 quantization, and IEEE-754 binary64 numeric operations.

Normative references:
- DGCA_CORE_RC4_1.md §3.1 (FIFR-B04 — SIC-V1 byte-exact input and projection, Numeric contract)
- DGCA_CORE_RC4_1.md §5.1 (Q6 quantization)
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from fractions import Fraction
import math
import re

from dgca.common.errors import DGCAError, ObservationError, StatusCode

MILLION: int = 1_000_000
DEFAULT_SALIENCE_STR: str = "1.000000"
DEFAULT_SALIENCE_U: int = MILLION

# Core §3.1: support and salience MUST be finite decimal strings matching:
# 0 | 1 | 0.[0-9]{1,6} | 1.0{1,6}
_DECIMAL_SUPPORT_RE = re.compile(r"(?:0|1|0\.[0-9]{1,6}|1\.0{1,6})")


def parse_support_millionths(
    value_str: str,
    *,
    error_code: StatusCode = StatusCode.INVALID_OBSERVATION,
) -> int:
    """Validate a canonical support/salience string and convert to integer millionths u in [0, 1_000_000].

    Rejects exponents, plus/minus signs, NaN, Inf, negative zero, or >6 fractional digits.
    """
    if not isinstance(value_str, str) or not _DECIMAL_SUPPORT_RE.fullmatch(value_str):
        raise ObservationError(
            f"Invalid decimal support/salience string: {value_str!r}",
            code=error_code,
        )
    if value_str == "0":
        return 0
    if value_str == "1" or value_str.startswith("1."):
        return MILLION
    # Format is "0." followed by 1..6 digits
    frac_part = value_str[2:].ljust(6, "0")
    return int(frac_part, 10)


def format_support_millionths(u: int) -> str:
    """Format integer millionths u in [0, 1_000_000] into canonical 6-decimal string."""
    if not isinstance(u, int) or isinstance(u, bool) or u < 0 or u > MILLION:
        raise DGCAError(
            StatusCode.INVALID_NUMERIC_VALUE,
            f"Support millionths out of range [0, 1_000_000]: {u!r}",
        )
    if u == MILLION:
        return "1.000000"
    return f"0.{u:06d}"


def noisy_or_millionths(supports_u: Iterable[int]) -> int:
    """Combine integer millionth supports by exact decimal Noisy-OR and round half-even once.

    Formula: u* = roundTiesEven(1_000_000 * (1 - prod(1 - u_f / 1_000_000)))
    """
    complement_prod = Fraction(1, 1)
    has_any = False
    for u in supports_u:
        if not isinstance(u, int) or isinstance(u, bool) or u < 0 or u > MILLION:
            raise DGCAError(
                StatusCode.INVALID_NUMERIC_VALUE,
                f"Support millionths out of range [0, 1_000_000]: {u!r}",
            )
        has_any = True
        if u == 0:
            continue
        if u == MILLION:
            return MILLION
        complement_prod *= Fraction(MILLION - u, MILLION)

    if not has_any:
        return 0
    exact_noisy_or = Fraction(1, 1) - complement_prod
    # Python 3 round() on Fraction performs exact rational round-half-to-even
    return int(round(exact_noisy_or * MILLION))


def scale_by_salience_millionths(support_u: int, salience_u: int) -> int:
    """Multiply integer millionth support by salience using exact decimal arithmetic, rounded half-even once."""
    if (
        not isinstance(support_u, int)
        or isinstance(support_u, bool)
        or support_u < 0
        or support_u > MILLION
    ):
        raise DGCAError(
            StatusCode.INVALID_NUMERIC_VALUE,
            f"Support millionths out of range: {support_u!r}",
        )
    if (
        not isinstance(salience_u, int)
        or isinstance(salience_u, bool)
        or salience_u < 0
        or salience_u > MILLION
    ):
        raise DGCAError(
            StatusCode.INVALID_NUMERIC_VALUE,
            f"Salience millionths out of range: {salience_u!r}",
        )
    if support_u == 0 or salience_u == 0:
        return 0
    if salience_u == MILLION:
        return support_u
    exact_product = Fraction(support_u * salience_u, MILLION)
    return int(round(exact_product))


def millionths_to_binary64(u: int) -> float:
    """Convert integer millionths u in [0, 1_000_000] to IEEE-754 binary64 float."""
    if not isinstance(u, int) or isinstance(u, bool) or u < 0 or u > MILLION:
        raise DGCAError(
            StatusCode.INVALID_NUMERIC_VALUE,
            f"Millionths value out of range [0, 1_000_000]: {u!r}",
        )
    return float(u) / 1_000_000.0


def validate_finite_binary64(x: float) -> float:
    """Ensure x is a finite IEEE-754 binary64 float and normalize -0.0 to +0.0."""
    if not isinstance(x, (float, int)) or isinstance(x, bool):
        raise DGCAError(
            StatusCode.INVALID_NUMERIC_VALUE,
            f"Expected finite float, got {type(x).__name__}",
        )
    val = float(x)
    if math.isnan(val) or math.isinf(val):
        raise DGCAError(
            StatusCode.INVALID_NUMERIC_VALUE,
            f"Non-finite floating point value rejected: {x!r}",
        )
    if val == 0.0:
        return 0.0
    return val


def q6_from_binary64(x: float) -> int:
    """Compute Q6(x) = roundTiesEven(1,000,000 * exactBinary64(x)) per Core §3.1 and §5.1.

    Uses Fraction(float(x)) to obtain the exact rational value of the IEEE-754 binary64 float
    without converting to a shortest decimal representation first.
    """
    val = validate_finite_binary64(x)
    exact_rational = Fraction(val)
    return int(round(exact_rational * MILLION))


def clip_float64(x: float, low: float = 0.0, high: float = 1.0) -> float:
    """Clip a finite IEEE-754 binary64 float to [low, high], normalizing -0.0 to +0.0."""
    val = validate_finite_binary64(x)
    if val <= low:
        return 0.0 if low == 0.0 else float(low)
    if val >= high:
        return float(high)
    return val


def noisy_or_float64(values: Sequence[float]) -> float:
    """Compute NoisyOR(z1, ..., zk) = 1 - prod(1 - z_i) in exact sequential IEEE-754 binary64 order.

    All inputs must already be ordered canonically (e.g. by (source_cell_id, scope_order, link_key)).
    """
    prod_complement = 1.0
    for z in values:
        val = validate_finite_binary64(z)
        if val < 0.0 or val > 1.0:
            raise DGCAError(
                StatusCode.INVALID_NUMERIC_VALUE,
                f"NoisyOR input out of [0, 1] bounds: {val!r}",
            )
        prod_complement = prod_complement * (1.0 - val)
    res = 1.0 - prod_complement
    return 0.0 if res == 0.0 else res
