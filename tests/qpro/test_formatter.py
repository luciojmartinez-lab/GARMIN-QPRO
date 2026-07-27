from functools import partial
from math import inf, nan

import pytest

from garmin_qpro.qpro.formatter import (
    empty_or_formatted,
    format_decimal,
    format_text_decimal,
    format_text_integer,
)


def test_text_integer_uses_apostrophe_and_zero_padding() -> None:
    assert format_text_integer(98) == "'098"
    assert format_text_integer(133) == "'133"


def test_decimal_formatters_use_decimal_comma() -> None:
    assert format_decimal(0, 2) == "0,00"
    assert format_decimal(12.345, 2) == "12,35"
    assert format_text_decimal(0, 2) == "'0,00"
    assert format_text_decimal(8.8, 1, width=2) == "'08,8"


def test_formatters_do_not_use_thousands_separators() -> None:
    assert format_text_integer(1234) == "'1234"
    assert format_decimal(1234.5, 2) == "1234,50"


def test_empty_or_formatted_preserves_missing_values() -> None:
    formatter = partial(format_decimal, decimals=2)
    assert empty_or_formatted(None, formatter) == ""
    assert empty_or_formatted(0, formatter) == "0,00"


@pytest.mark.parametrize(
    "formatter",
    [
        format_text_integer,
        partial(format_decimal, decimals=2),
        partial(format_text_decimal, decimals=2),
    ],
)
def test_boolean_values_are_rejected(formatter) -> None:
    with pytest.raises(TypeError):
        formatter(True)


@pytest.mark.parametrize("value", [nan, inf, -inf])
@pytest.mark.parametrize(
    "formatter",
    [
        format_text_integer,
        partial(format_decimal, decimals=2),
        partial(format_text_decimal, decimals=2),
    ],
)
def test_non_finite_values_are_rejected(formatter, value: float) -> None:
    with pytest.raises(ValueError):
        formatter(value)


@pytest.mark.parametrize(
    "formatter",
    [
        format_text_integer,
        partial(format_decimal, decimals=2),
        partial(format_text_decimal, decimals=2),
    ],
)
def test_none_is_not_implicitly_zero(formatter) -> None:
    with pytest.raises(TypeError):
        formatter(None)
