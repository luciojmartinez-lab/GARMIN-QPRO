"""Pure builders for Quattro Pro row formulas."""


def _validate_row_number(row_number: int) -> None:
    if isinstance(row_number, bool) or not isinstance(row_number, int):
        raise TypeError("row_number must be an integer")
    if row_number <= 0:
        raise ValueError("row_number must be positive")


def build_vmed_ms_formula(row_number: int) -> str:
    """Build the robust VMED M/S formula for a positive row number."""

    _validate_row_number(row_number)
    return (
        f'@SI(@ESERR(@SI(C{row_number}<>"";(C{row_number}*1000)/3600;'
        f'1000/(B{row_number}*60)));0;@SI(C{row_number}<>"";'
        f'(C{row_number}*1000)/3600;1000/(B{row_number}*60)))'
    )


def build_vmax_ms_formula(row_number: int) -> str:
    """Build the robust VMAX M/S formula for a positive row number."""

    _validate_row_number(row_number)
    return (
        f'@SI(@ESERR(@SI(F{row_number}<>"";(F{row_number}*1000)/3600;'
        f'1000/(E{row_number}*60)));0;@SI(F{row_number}<>"";'
        f'(F{row_number}*1000)/3600;1000/(E{row_number}*60)))'
    )
