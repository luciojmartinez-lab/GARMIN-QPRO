import pytest

from garmin_qpro.qpro.formulas import (
    RELATIVE_SPEED_FORMULA,
    build_vmax_ms_formula,
    build_vmed_ms_formula,
)

EXPECTED_RELATIVE_FORMULA = (
    '@SI(@ESERR(@SI(c(-1)r(0)<>"";(c(-1)r(0)*1000)/3600;'
    '1000/(c(-2)r(0)*60)));0;@SI(c(-1)r(0)<>"";'
    '(c(-1)r(0)*1000)/3600;1000/(c(-2)r(0)*60)))'
)


def test_relative_formula_is_exact() -> None:
    assert RELATIVE_SPEED_FORMULA == EXPECTED_RELATIVE_FORMULA
    assert build_vmed_ms_formula() == EXPECTED_RELATIVE_FORMULA
    assert build_vmax_ms_formula() == EXPECTED_RELATIVE_FORMULA


@pytest.mark.parametrize(
    "deprecated_row",
    [None, 55, 60, True, 0, -1, 1.5, "obsolete"],
)
@pytest.mark.parametrize(
    "builder",
    [build_vmed_ms_formula, build_vmax_ms_formula],
)
def test_deprecated_row_argument_is_ignored(builder, deprecated_row) -> None:
    assert builder(deprecated_row) == EXPECTED_RELATIVE_FORMULA


def test_formula_contains_no_absolute_cell_reference() -> None:
    formula = build_vmed_ms_formula()

    for forbidden in ("C55", "B55", "F55", "E55", "C23", "F23"):
        assert forbidden not in formula
