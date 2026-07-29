"""Pure builders for row-independent Quattro Pro formulas."""

RELATIVE_SPEED_FORMULA = (
    '@SI(@ESERR(@SI(c(-1)r(0)<>"";(c(-1)r(0)*1000)/3600;'
    '1000/(c(-2)r(0)*60)));0;@SI(c(-1)r(0)<>"";'
    '(c(-1)r(0)*1000)/3600;1000/(c(-2)r(0)*60)))'
)


def build_vmed_ms_formula(
    row_number: object | None = None,
) -> str:
    """Return the relative VMED formula; row_number is deprecated and ignored."""

    return RELATIVE_SPEED_FORMULA


def build_vmax_ms_formula(
    row_number: object | None = None,
) -> str:
    """Return the relative VMAX formula; row_number is deprecated and ignored."""

    return RELATIVE_SPEED_FORMULA
