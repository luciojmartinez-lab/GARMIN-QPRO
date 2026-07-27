"""Immutable schema definitions for Quattro Pro rows."""

from types import MappingProxyType
from typing import Final, Mapping

QPRO_COLUMNS: Final[tuple[str, ...]] = (
    "CODIGO",
    "RMED",
    "VMED",
    "VMED_M_S",
    "RMAX",
    "VMAX",
    "VMAX_M_S",
    "DISTANCIA",
    "PPME",
    "PPMAX",
    "MIN",
    "RITMO",
    "AER",
    "ANA",
    "CADM",
    "CADX",
    "ZAN",
    "TCS",
    "CARGA",
    "PTM",
    "PTX",
    "RVM",
    "OVM",
    "CARGA_AGUDA",
    "CARGA_CRONICA",
)

QPRO_COLUMN_COUNT: Final[int] = len(QPRO_COLUMNS)

QPRO_COLUMN_INDEX: Final[Mapping[str, int]] = MappingProxyType(
    {column: index for index, column in enumerate(QPRO_COLUMNS, start=1)}
)

TEXT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "PPME",
        "PPMAX",
        "MIN",
        "RITMO",
        "CADM",
        "CADX",
        "TCS",
        "CARGA",
        "PTM",
        "PTX",
        "RVM",
        "OVM",
        "CARGA_AGUDA",
        "CARGA_CRONICA",
    }
)
