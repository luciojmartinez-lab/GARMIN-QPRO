"""Immutable Quattro Pro rows and the force-family template."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .formatter import (
    empty_or_formatted,
    format_decimal,
    format_text_integer,
)
from .formulas import build_vmax_ms_formula, build_vmed_ms_formula
from .rows import QProFamily, family_for_key
from .schema import QPRO_COLUMN_COUNT, QPRO_COLUMN_INDEX, QPRO_COLUMNS


class UnknownQProColumnError(KeyError):
    """Raised when a row is queried with an unknown column name."""

    def __init__(self, column: object) -> None:
        self.column = column
        super().__init__(f"Unknown Quattro Pro column: {column!r}")


class InvalidForceKeyError(ValueError):
    """Raised when a known key does not belong to the force family."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"Quattro Pro key is not a force key: {key!r}")


@dataclass(frozen=True, slots=True, init=False)
class QProRow:
    """An immutable sequence of the 23 Quattro Pro cell values."""

    _values: tuple[str, ...]

    def __init__(self, values: Iterable[object]) -> None:
        normalized_values = tuple(
            "" if value is None else str(value) for value in values
        )
        if len(normalized_values) != QPRO_COLUMN_COUNT:
            raise ValueError(
                f"QProRow requires exactly {QPRO_COLUMN_COUNT} values; "
                f"received {len(normalized_values)}"
            )
        object.__setattr__(self, "_values", normalized_values)

    def get(self, column: str) -> str:
        """Return a cell by its exact schema column name."""

        try:
            human_index = QPRO_COLUMN_INDEX[column]
        except (KeyError, TypeError):
            raise UnknownQProColumnError(column) from None
        return self._values[human_index - 1]

    def as_tuple(self) -> tuple[str, ...]:
        """Return all cell values in QPRO_COLUMNS order."""

        return self._values

    def as_mapping(self) -> Mapping[str, str]:
        """Return an immutable column-to-value mapping in schema order."""

        return MappingProxyType(
            dict(zip(QPRO_COLUMNS, self._values, strict=True))
        )


def build_force_row(
    key: str,
    row_number: object | None = None,
    *,
    ppme: int | None = None,
    ppmax: int | None = None,
    minutes: int | None = None,
    aer: float | None = None,
    ana: float | None = None,
    exercise_load: int | float | None = None,
) -> QProRow:
    """Build the force template; row_number is deprecated and ignored."""

    if family_for_key(key) is not QProFamily.FORCE:
        raise InvalidForceKeyError(key)

    normalized_key = key.strip().upper()
    values = {
        "CODIGO": normalized_key,
        "RMED": "",
        "VMED": "",
        "VMED_M_S": build_vmed_ms_formula(),
        "RMAX": "",
        "VMAX": "",
        "VMAX_M_S": build_vmax_ms_formula(),
        "DISTANCIA": "0,00",
        "PPME": empty_or_formatted(ppme, format_text_integer),
        "PPMAX": empty_or_formatted(ppmax, format_text_integer),
        "MIN": empty_or_formatted(minutes, format_text_integer),
        "RITMO": "'00,00",
        "AER": empty_or_formatted(
            aer, lambda value: format_decimal(value, 1)
        ),
        "ANA": empty_or_formatted(
            ana, lambda value: format_decimal(value, 1)
        ),
        "CADM": "'000",
        "CADX": "'000",
        "ZAN": "0,00",
        "TCS": "'000",
        "CARGA": (
            "'000"
            if exercise_load is None
            else format_text_integer(exercise_load)
        ),
        "PTM": "'000",
        "PTX": "'000",
        "RVM": "'000",
        "OVM": "'000",
    }
    return QProRow(values[column] for column in QPRO_COLUMNS)
