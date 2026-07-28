"""Pure value formatters for Quattro Pro cells."""

from collections.abc import Callable
from decimal import Decimal, ROUND_HALF_UP
from typing import TypeVar

T = TypeVar("T")


def _as_finite_decimal(value: int | float) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("value must be an integer or float")

    decimal_value = Decimal(str(value))
    if not decimal_value.is_finite():
        raise ValueError("value must be finite")
    return decimal_value


def _validate_non_negative_integer(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must not be negative")


def format_text_integer(value: int | float, width: int = 3) -> str:
    """Format a rounded integer as apostrophe-prefixed zero-padded text."""

    _validate_non_negative_integer(width, "width")
    if width == 0:
        raise ValueError("width must be positive")

    rounded = _as_finite_decimal(value).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    integer_value = int(rounded)
    return f"'{integer_value:0{width}d}"


def format_decimal(value: int | float, decimals: int) -> str:
    """Format a finite number with a decimal comma and no thousands separator."""

    _validate_non_negative_integer(decimals, "decimals")
    decimal_value = _as_finite_decimal(value)
    quantum = Decimal(1).scaleb(-decimals)
    rounded = decimal_value.quantize(quantum, rounding=ROUND_HALF_UP)
    return format(rounded, f".{decimals}f").replace(".", ",")


def format_text_decimal(
    value: int | float,
    decimals: int,
    width: int | None = None,
) -> str:
    """Format a decimal as apostrophe-prefixed text with optional zero padding."""

    formatted = format_decimal(value, decimals)
    if width is not None:
        _validate_non_negative_integer(width, "width")
        if width == 0:
            raise ValueError("width must be positive")

        sign = ""
        unsigned = formatted
        if formatted.startswith(("-", "+")):
            sign, unsigned = formatted[0], formatted[1:]

        integer_part, separator, fractional_part = unsigned.partition(",")
        formatted = (
            f"{sign}{integer_part.zfill(width)}"
            f"{separator}{fractional_part}"
        )

    return f"'{formatted}"


def format_text_pace(seconds_per_km: int | float) -> str:
    """Format pace seconds per kilometer as apostrophe-prefixed mm,ss text."""

    rounded_seconds = _as_finite_decimal(seconds_per_km).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    if rounded_seconds < 0:
        raise ValueError("seconds_per_km must not be negative")

    total_seconds = int(rounded_seconds)
    minutes, seconds = divmod(total_seconds, 60)
    return f"'{minutes:02d},{seconds:02d}"


def empty_or_formatted(
    value: T | None,
    formatter: Callable[[T], str],
) -> str:
    """Return an empty cell for missing data, otherwise apply the formatter."""

    if value is None:
        return ""
    return formatter(value)
