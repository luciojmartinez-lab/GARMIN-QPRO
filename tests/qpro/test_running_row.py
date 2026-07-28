from dataclasses import replace
from math import inf, nan

import pytest

from garmin_qpro.fit.running_metrics import RunningMetricsRaw
from garmin_qpro.qpro.formulas import (
    build_vmax_ms_formula,
    build_vmed_ms_formula,
)
from garmin_qpro.qpro.row import QProRow
from garmin_qpro.qpro.rows import UnknownQProKeyError
from garmin_qpro.qpro.running_row import (
    InvalidRunningKeyError,
    build_running_row,
)
from garmin_qpro.qpro.schema import QPRO_COLUMNS
from garmin_qpro.qpro.tsv import row_to_tsv


def _metrics(**overrides) -> RunningMetricsRaw:
    values = {
        "timer_time_s": 999.0,
        "moving_time_s": 652.0,
        "distance_m": 1056.38,
        "avg_speed_mps": 999.0,
        "max_speed_mps": 1.959,
        "avg_hr_bpm": 96,
        "max_hr_bpm": 115,
        "aerobic_te": 0.7,
        "anaerobic_te": 0.0,
        "avg_cadence_raw": 69.4998,
        "max_cadence_raw": 81.5,
        "avg_step_length_mm": 667.16,
        "avg_stance_time_ms": 338.64,
        "exercise_load": 7.756,
        "avg_power_w": 155.55,
        "max_power_w": 215,
        "avg_vertical_ratio_pct": 11.426,
        "avg_vertical_oscillation_mm": 76.069,
        "acute_load": None,
        "chronic_load": None,
        "source_scope": "session",
        "warmup_lap_count": 0,
        "requires_manual_review": False,
    }
    values.update(overrides)
    return RunningMetricsRaw(**values)


def test_running_row_preserves_exact_25_column_order() -> None:
    row = build_running_row("CAL", 18, _metrics())

    assert isinstance(row, QProRow)
    assert len(row.as_tuple()) == 25
    assert tuple(row.as_mapping()) == QPRO_COLUMNS


def test_running_key_is_normalized() -> None:
    row = build_running_row(" ent ", 23, _metrics())

    assert row.get("CODIGO") == "ENT"


@pytest.mark.parametrize("key", ["PES", "CMF"])
def test_force_keys_are_rejected(key: str) -> None:
    with pytest.raises(InvalidRunningKeyError):
        build_running_row(key, 23, _metrics())


@pytest.mark.parametrize("key", ["COM", "UNKNOWN"])
def test_unknown_keys_are_rejected(key: str) -> None:
    with pytest.raises(UnknownQProKeyError):
        build_running_row(key, 23, _metrics())


def test_formulas_use_received_row_number() -> None:
    row = build_running_row("ENT", 23, _metrics())

    assert row.get("VMED_M_S") == build_vmed_ms_formula(23)
    assert row.get("VMAX_M_S") == build_vmax_ms_formula(23)


def test_vmed_uses_distance_and_moving_time_not_average_speed() -> None:
    row = build_running_row(
        "ENT",
        23,
        _metrics(distance_m=1000, moving_time_s=500, avg_speed_mps=99),
    )

    assert row.get("VMED") == "7,20"


def test_vmed_is_empty_when_distance_or_moving_time_is_missing_or_zero() -> None:
    assert build_running_row(
        "ENT", 23, _metrics(distance_m=None)
    ).get("VMED") == ""
    assert build_running_row(
        "ENT", 23, _metrics(moving_time_s=0)
    ).get("VMED") == ""


def test_speed_distance_minutes_and_pace_are_formatted() -> None:
    row = build_running_row(
        "ENT",
        23,
        _metrics(
            moving_time_s=462,
            distance_m=545.58,
            max_speed_mps=4.693,
        ),
    )

    assert row.get("VMED") == "4,25"
    assert row.get("VMAX") == "16,89"
    assert row.get("DISTANCIA") == "0,55"
    assert row.get("MIN") == "'008"
    assert row.get("RITMO") == "'14,07"


def test_pace_carries_rounded_seconds() -> None:
    row = build_running_row(
        "ENT",
        23,
        _metrics(moving_time_s=60, distance_m=1001.67),
    )

    assert row.get("RITMO") == "'01,00"


def test_heart_rate_load_power_and_training_effect_are_formatted() -> None:
    row = build_running_row(
        "ENT",
        23,
        _metrics(
            avg_hr_bpm=96,
            max_hr_bpm=115,
            exercise_load=7.5,
            avg_power_w=155.5,
            max_power_w=215,
            aerobic_te=0.7,
            anaerobic_te=0,
        ),
    )

    assert row.get("PPME") == "'096"
    assert row.get("PPMAX") == "'115"
    assert row.get("CARGA") == "'008"
    assert row.get("PTM") == "'156"
    assert row.get("PTX") == "'215"
    assert row.get("AER") == "0,7"
    assert row.get("ANA") == "0,0"


@pytest.mark.parametrize(
    ("cadence_raw", "expected"),
    [
        (60, "'120"),
        (120, "'240"),
        (121, "'121"),
        (0, "'000"),
    ],
)
def test_cadence_raw_is_converted_to_steps_per_minute(
    cadence_raw: float,
    expected: str,
) -> None:
    row = build_running_row(
        "ENT",
        23,
        _metrics(avg_cadence_raw=cadence_raw),
    )

    assert row.get("CADM") == expected


def test_zan_tcs_rvm_and_ovm_are_formatted() -> None:
    row = build_running_row(
        "ENT",
        23,
        _metrics(
            avg_step_length_mm=667.16,
            avg_stance_time_ms=338.64,
            avg_vertical_ratio_pct=9.17,
            avg_vertical_oscillation_mm=76.069,
        ),
    )

    assert row.get("ZAN") == "0,67"
    assert row.get("TCS") == "'339"
    assert row.get("RVM") == "'09,2"
    assert row.get("OVM") == "'07,6"


def test_missing_metrics_are_empty_cells() -> None:
    metrics = _metrics(
        moving_time_s=None,
        distance_m=None,
        max_speed_mps=None,
        avg_hr_bpm=None,
        max_hr_bpm=None,
        aerobic_te=None,
        anaerobic_te=None,
        avg_cadence_raw=None,
        max_cadence_raw=None,
        avg_step_length_mm=None,
        avg_stance_time_ms=None,
        exercise_load=None,
        avg_power_w=None,
        max_power_w=None,
        avg_vertical_ratio_pct=None,
        avg_vertical_oscillation_mm=None,
    )
    row = build_running_row("ENT", 23, metrics)

    for column in (
        "VMED",
        "VMAX",
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
    ):
        assert row.get(column) == ""


def test_cal_manual_review_can_build_partial_row() -> None:
    row = build_running_row(
        "CAL",
        18,
        _metrics(
            requires_manual_review=True,
            avg_cadence_raw=None,
            max_cadence_raw=None,
            avg_step_length_mm=None,
            avg_stance_time_ms=None,
            avg_power_w=None,
            max_power_w=None,
            avg_vertical_ratio_pct=None,
            avg_vertical_oscillation_mm=None,
        ),
    )

    assert row.get("CODIGO") == "CAL"
    assert row.get("CADM") == ""
    assert row.get("PTM") == ""


def test_row_and_metrics_are_immutable_and_metrics_are_not_modified() -> None:
    metrics = _metrics()
    before = metrics
    row = build_running_row("ENT", 23, metrics)

    assert metrics == before
    with pytest.raises(AttributeError):
        row._values = ("x",) * 25  # type: ignore[misc]


@pytest.mark.parametrize("row_number", [True, 0, -1, 1.5, "23"])
def test_invalid_row_numbers_are_rejected(row_number) -> None:
    with pytest.raises((TypeError, ValueError)):
        build_running_row("ENT", row_number, _metrics())


def test_metrics_type_is_validated() -> None:
    with pytest.raises(TypeError):
        build_running_row("ENT", 23, object())  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [-1, True, nan, inf, -inf])
def test_invalid_numeric_metrics_are_rejected(value) -> None:
    metrics = replace(_metrics(), distance_m=value)

    with pytest.raises((TypeError, ValueError)):
        build_running_row("ENT", 23, metrics)


def test_tsv_serialization_has_25_columns_and_24_tabs() -> None:
    row = build_running_row("ENT", 23, _metrics())
    line = row_to_tsv(row)

    assert line.count("\t") == 24
    assert len(line.split("\t")) == 25
