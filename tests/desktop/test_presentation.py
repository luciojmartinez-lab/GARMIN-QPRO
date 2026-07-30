from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from garmin_qpro.desktop.presentation import (
    DashboardSummary,
    display_activity_name,
    format_activity_datetime,
    validate_clipboard_rows,
)


def _row(key: str = "ENT") -> str:
    return "\t".join((key,) + tuple(str(index) for index in range(1, 23)))


def test_activity_name_prefers_workout_then_profile_then_fallback() -> None:
    assert display_activity_name("Plan", "Carrera", "Archivo") == "Plan"
    assert display_activity_name(None, "Carrera", "Archivo") == "Carrera"
    assert display_activity_name(None, None, "Archivo") == "Archivo"
    assert display_activity_name(None, None, None) == "Actividad sin nombre"


def test_activity_datetime_is_compact_and_tolerates_unknown_text() -> None:
    assert format_activity_datetime("2026-07-30T17:45:00") == "30/07/2026 17:45"
    assert format_activity_datetime("sin fecha") == "sin fecha"
    assert format_activity_datetime(None) == ""


def test_clipboard_rows_keep_qpro_shape_and_order() -> None:
    first = _row("CAL")
    second = _row("ENT")
    result = validate_clipboard_rows((first, second))
    assert result == f"{first}\n{second}"
    assert result.splitlines()[0].split("\t")[0] == "CAL"
    assert result.splitlines()[1].split("\t")[0] == "ENT"


@pytest.mark.parametrize(
    "value",
    (
        "",
        "\t".join("x" for _ in range(22)),
        _row() + "\t",
        _row() + "\n",
    ),
)
def test_clipboard_rejects_rows_that_are_not_exactly_23_columns(
    value: str,
) -> None:
    with pytest.raises(ValueError):
        validate_clipboard_rows((value,))


def test_dashboard_summary_is_immutable() -> None:
    summary = DashboardSummary(1, 2, 3, 4)
    with pytest.raises(FrozenInstanceError):
        summary.new_activities = 5  # type: ignore[misc]
