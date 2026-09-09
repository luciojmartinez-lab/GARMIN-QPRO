"""Pure composition of QPro rows with historical Garmin training load."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Mapping

from garmin_qpro.garmin_connect import HistoricalTrainingLoad

from .formatter import empty_or_formatted, format_text_integer
from .row import QProRow, UnknownQProColumnError
from .schema import QPRO_COLUMNS


TRAINING_LOAD_COLUMNS: Final[tuple[str, str]] = (
    "CARGA_AGUDA",
    "CARGA_CRONICA",
)
QPRO_COLUMNS_WITH_TRAINING_LOAD: Final[tuple[str, ...]] = (
    *QPRO_COLUMNS,
    *TRAINING_LOAD_COLUMNS,
)
_COLUMN_INDEX: Final[Mapping[str, int]] = MappingProxyType(
    {
        column: index
        for index, column in enumerate(
            QPRO_COLUMNS_WITH_TRAINING_LOAD,
            start=1,
        )
    }
)


@dataclass(frozen=True, slots=True)
class QProRowWithTrainingLoad:
    """An existing QPro row followed by acute and chronic load cells."""

    base_row: QProRow
    acute_load_cell: str
    chronic_load_cell: str

    def __post_init__(self) -> None:
        if not isinstance(self.base_row, QProRow):
            raise TypeError("base_row must be a QProRow")
        for field_name in ("acute_load_cell", "chronic_load_cell"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be text")

    def get(self, column: str) -> str:
        """Return a cell by its exact enriched-schema column name."""

        try:
            human_index = _COLUMN_INDEX[column]
        except (KeyError, TypeError):
            raise UnknownQProColumnError(column) from None
        return self.as_tuple()[human_index - 1]

    def as_tuple(self) -> tuple[str, ...]:
        """Return the 25 cell values in Quattro Pro order."""

        return (
            *self.base_row.as_tuple(),
            self.acute_load_cell,
            self.chronic_load_cell,
        )

    def as_mapping(self) -> Mapping[str, str]:
        """Return an immutable mapping for all 25 columns."""

        return MappingProxyType(
            dict(
                zip(
                    QPRO_COLUMNS_WITH_TRAINING_LOAD,
                    self.as_tuple(),
                    strict=True,
                )
            )
        )


def enrich_qpro_row_with_training_load(
    row: QProRow,
    training_load: HistoricalTrainingLoad,
) -> QProRowWithTrainingLoad:
    """Append Garmin-reported acute and chronic load to a built QPro row."""

    if not isinstance(row, QProRow):
        raise TypeError("row must be a QProRow")
    if not isinstance(training_load, HistoricalTrainingLoad):
        raise TypeError("training_load must be a HistoricalTrainingLoad")

    return QProRowWithTrainingLoad(
        base_row=row,
        acute_load_cell=empty_or_formatted(
            training_load.acute_load,
            format_text_integer,
        ),
        chronic_load_cell=empty_or_formatted(
            training_load.chronic_load,
            format_text_integer,
        ),
    )
