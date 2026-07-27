import pytest

from garmin_qpro.qpro.formulas import (
    build_vmax_ms_formula,
    build_vmed_ms_formula,
)

EXPECTED_VMED_ROW_23 = (
    '@SI(@ESERR(@SI(C23<>"";(C23*1000)/3600;1000/(B23*60)));'
    '0;@SI(C23<>"";(C23*1000)/3600;1000/(B23*60)))'
)

EXPECTED_VMAX_ROW_23 = (
    '@SI(@ESERR(@SI(F23<>"";(F23*1000)/3600;1000/(E23*60)));'
    '0;@SI(F23<>"";(F23*1000)/3600;1000/(E23*60)))'
)


def test_vmed_formula_for_row_23_is_exact() -> None:
    assert build_vmed_ms_formula(23) == EXPECTED_VMED_ROW_23


def test_vmax_formula_for_row_23_is_exact() -> None:
    assert build_vmax_ms_formula(23) == EXPECTED_VMAX_ROW_23


@pytest.mark.parametrize("row_number", [True, False, 1.0, 23.5, "23", None])
@pytest.mark.parametrize(
    "builder", [build_vmed_ms_formula, build_vmax_ms_formula]
)
def test_non_integer_rows_are_rejected(builder, row_number) -> None:
    with pytest.raises(TypeError):
        builder(row_number)


@pytest.mark.parametrize("row_number", [0, -1, -23])
@pytest.mark.parametrize(
    "builder", [build_vmed_ms_formula, build_vmax_ms_formula]
)
def test_non_positive_rows_are_rejected(builder, row_number: int) -> None:
    with pytest.raises(ValueError):
        builder(row_number)
