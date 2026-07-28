from math import inf, nan

import pytest

from garmin_qpro.qpro.formulas import (
    build_vmax_ms_formula,
    build_vmed_ms_formula,
)
from garmin_qpro.qpro.row import (
    InvalidForceKeyError,
    QProRow,
    UnknownQProColumnError,
    build_force_row,
)
from garmin_qpro.qpro.rows import UnknownQProKeyError
from garmin_qpro.qpro.schema import QPRO_COLUMNS


def test_qpro_row_preserves_exact_column_count_and_order() -> None:
    values = tuple(f"value-{index}" for index in range(23))
    row = QProRow(values)

    assert len(row.as_tuple()) == 23
    assert row.as_tuple() == values
    assert tuple(row.as_mapping()) == QPRO_COLUMNS
    assert tuple(row.as_mapping().values()) == values
    assert row.get("CARGA") == values[18]


def test_qpro_row_normalizes_output_to_strings_and_empty_cells() -> None:
    row = QProRow([None, 1, 2.5, *("" for _ in range(20))])

    assert row.as_tuple()[:3] == ("", "1", "2.5")
    assert all(isinstance(value, str) for value in row.as_tuple())


@pytest.mark.parametrize("count", [0, 22, 24])
def test_qpro_row_rejects_invalid_value_count(count: int) -> None:
    with pytest.raises(ValueError, match="exactly 23 values"):
        QProRow([""] * count)


def test_qpro_row_rejects_unknown_column() -> None:
    row = QProRow([""] * 23)
    with pytest.raises(UnknownQProColumnError):
        row.get("UNKNOWN")


def test_qpro_row_is_immutable() -> None:
    row = QProRow([""] * 23)
    with pytest.raises(AttributeError):
        row._values = ("changed",) * 23  # type: ignore[misc]


@pytest.mark.parametrize("key", ["PES", " cmf "])
def test_force_keys_are_accepted_and_normalized(key: str) -> None:
    row = build_force_row(key, 61)
    assert row.get("CODIGO") == key.strip().upper()


@pytest.mark.parametrize("key", ["CMP", "CAL"])
def test_running_keys_are_rejected_by_force_template(key: str) -> None:
    with pytest.raises(InvalidForceKeyError):
        build_force_row(key, 23)


@pytest.mark.parametrize("key", ["COM", "UNKNOWN"])
def test_unknown_keys_are_rejected_by_force_template(key: str) -> None:
    with pytest.raises(UnknownQProKeyError):
        build_force_row(key, 23)


def test_force_formulas_use_the_received_row_number() -> None:
    row = build_force_row("PES", 61)
    assert row.get("VMED_M_S") == build_vmed_ms_formula(61)
    assert row.get("VMAX_M_S") == build_vmax_ms_formula(61)
    assert "61" in row.get("VMED_M_S")
    assert "61" in row.get("VMAX_M_S")


def test_pes_without_optional_metrics_has_exact_neutral_values() -> None:
    row = build_force_row("PES", 61)
    assert row.as_tuple() == (
        "PES",
        "",
        "",
        build_vmed_ms_formula(61),
        "",
        "",
        build_vmax_ms_formula(61),
        "0,00",
        "",
        "",
        "",
        "'00,00",
        "",
        "",
        "'000",
        "'000",
        "0,00",
        "'000",
        "'000",
        "'000",
        "'000",
        "'000",
        "'000",
    )


def test_force_row_uses_real_exercise_load() -> None:
    row = build_force_row(
        "CMF",
        36,
        exercise_load=133,
    )
    assert row.get("CARGA") == "'133"


def test_force_row_uses_neutral_load_only_for_missing_exercise_load() -> None:
    row = build_force_row("PES", 61)
    assert row.get("CARGA") == "'000"


def test_force_row_formats_optional_real_metrics() -> None:
    row = build_force_row(
        "PES",
        61,
        ppme=98,
        ppmax=133,
        minutes=44,
        aer=1.1,
        ana=0,
    )
    assert row.get("PPME") == "'098"
    assert row.get("PPMAX") == "'133"
    assert row.get("MIN") == "'044"
    assert row.get("AER") == "1,1"
    assert row.get("ANA") == "0,0"


@pytest.mark.parametrize("row_number", [True, 0, -1, 1.5, "23"])
def test_force_row_rejects_invalid_rows(row_number) -> None:
    with pytest.raises((TypeError, ValueError)):
        build_force_row("PES", row_number)


@pytest.mark.parametrize("value", [True, nan, inf, -inf])
def test_force_row_rejects_invalid_metrics(value) -> None:
    with pytest.raises((TypeError, ValueError)):
        build_force_row("PES", 61, exercise_load=value)
