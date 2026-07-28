import pytest

from garmin_qpro.qpro.schema import (
    QPRO_COLUMN_COUNT,
    QPRO_COLUMN_INDEX,
    QPRO_COLUMNS,
    TEXT_FIELDS,
)

EXPECTED_COLUMNS = (
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
)

EXPECTED_TEXT_FIELDS = frozenset(
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
    }
)


def test_qpro_columns_have_exact_count_and_order() -> None:
    assert QPRO_COLUMN_COUNT == 23
    assert len(QPRO_COLUMNS) == 23
    assert QPRO_COLUMNS == EXPECTED_COLUMNS


def test_ovm_is_the_last_column() -> None:
    assert QPRO_COLUMNS[-1] == "OVM"
    assert QPRO_COLUMN_INDEX["OVM"] == 23


def test_column_indexes_are_human_one_based() -> None:
    assert dict(QPRO_COLUMN_INDEX) == {
        column: index for index, column in enumerate(EXPECTED_COLUMNS, start=1)
    }


def test_schema_collections_are_immutable() -> None:
    assert isinstance(QPRO_COLUMNS, tuple)
    assert isinstance(TEXT_FIELDS, frozenset)
    with pytest.raises(TypeError):
        QPRO_COLUMN_INDEX["CODIGO"] = 99  # type: ignore[index]


def test_text_fields_are_exact() -> None:
    assert TEXT_FIELDS == EXPECTED_TEXT_FIELDS
