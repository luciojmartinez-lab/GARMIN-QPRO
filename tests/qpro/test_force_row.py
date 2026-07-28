from dataclasses import replace
from math import inf, nan

import pytest

from garmin_qpro.fit.force_metrics import ForceMetricsRaw
from garmin_qpro.fit.running_metrics import RunningMetricsRaw
from garmin_qpro.qpro.force_row import build_force_metrics_row
from garmin_qpro.qpro.formulas import (
    build_vmax_ms_formula,
    build_vmed_ms_formula,
)
from garmin_qpro.qpro.row import (
    InvalidForceKeyError,
    QProRow,
    build_force_row,
)
from garmin_qpro.qpro.rows import UnknownQProKeyError
from garmin_qpro.qpro.running_row import build_running_row
from garmin_qpro.qpro.schema import QPRO_COLUMNS
from garmin_qpro.qpro.tsv import row_to_tsv


def _metrics(**overrides) -> ForceMetricsRaw:
    values = {
        "timer_time_s": 1663.291,
        "elapsed_time_s": 1701.977,
        "avg_hr_bpm": 121,
        "max_hr_bpm": 146,
        "aerobic_te": 3.0,
        "anaerobic_te": 2.3,
        "exercise_load": 93.91545104980469,
    }
    values.update(overrides)
    return ForceMetricsRaw(**values)


def _empty_metrics() -> ForceMetricsRaw:
    return ForceMetricsRaw(
        timer_time_s=None,
        elapsed_time_s=None,
        avg_hr_bpm=None,
        max_hr_bpm=None,
        aerobic_te=None,
        anaerobic_te=None,
        exercise_load=None,
    )


def test_builds_exact_force_values_from_raw_metrics() -> None:
    row = build_force_metrics_row(" cmf ", 36, _metrics())

    assert row.get("CODIGO") == "CMF"
    assert row.get("PPME") == "'121"
    assert row.get("PPMAX") == "'146"
    assert row.get("MIN") == "'028"
    assert row.get("AER") == "3,0"
    assert row.get("ANA") == "2,3"
    assert row.get("CARGA") == "'094"


def test_timer_time_is_used_for_minutes_without_elapsed_fallback() -> None:
    row = build_force_metrics_row(
        "PES",
        61,
        _metrics(timer_time_s=None, elapsed_time_s=3600),
    )

    assert row.get("MIN") == ""


def test_half_up_rounding_is_used_for_minutes_and_exercise_load() -> None:
    row = build_force_metrics_row(
        "PES",
        61,
        _metrics(timer_time_s=90.0, exercise_load=78.5),
    )

    assert row.get("MIN") == "'002"
    assert row.get("CARGA") == "'079"


def test_missing_exercise_load_keeps_existing_neutral_value() -> None:
    row = build_force_metrics_row(
        "PES",
        61,
        _empty_metrics(),
    )

    assert row.get("CARGA") == "'000"


@pytest.mark.parametrize("key", ["PES", "CMF", "MOF"])
def test_only_force_family_keys_are_accepted(key: str) -> None:
    assert build_force_metrics_row(key, 36, _empty_metrics()).get(
        "CODIGO"
    ) == key


@pytest.mark.parametrize("key", ["CMP", "ENT", "CAL"])
def test_running_keys_are_rejected(key: str) -> None:
    with pytest.raises(InvalidForceKeyError):
        build_force_metrics_row(key, 36, _empty_metrics())


def test_unknown_key_is_rejected() -> None:
    with pytest.raises(UnknownQProKeyError):
        build_force_metrics_row("UNKNOWN", 36, _empty_metrics())


def test_metrics_type_is_required() -> None:
    with pytest.raises(TypeError):
        build_force_metrics_row("CMF", 36, object())  # type: ignore[arg-type]


@pytest.mark.parametrize("row_number", [True, 0, -1, 1.5, "36"])
def test_row_number_must_be_a_positive_integer(row_number) -> None:
    with pytest.raises((TypeError, ValueError)):
        build_force_metrics_row("CMF", row_number, _empty_metrics())


@pytest.mark.parametrize("invalid", [True, "1", nan, inf, -inf, -1])
def test_invalid_numeric_metrics_are_rejected(invalid) -> None:
    with pytest.raises((TypeError, ValueError)):
        build_force_metrics_row(
            "CMF",
            36,
            replace(_metrics(), exercise_load=invalid),
        )


def test_invalid_heart_rate_type_is_rejected() -> None:
    with pytest.raises(TypeError):
        build_force_metrics_row(
            "CMF",
            36,
            replace(_metrics(), avg_hr_bpm=121.5),
        )


def test_formulas_use_the_explicit_row_number() -> None:
    row = build_force_metrics_row("CMF", 36, _metrics())

    assert row.get("VMED_M_S") == build_vmed_ms_formula(36)
    assert row.get("VMAX_M_S") == build_vmax_ms_formula(36)


def test_row_and_tsv_keep_exact_schema_shape() -> None:
    row = build_force_metrics_row("CMF", 36, _metrics())
    tsv = row_to_tsv(row)

    assert isinstance(row, QProRow)
    assert tuple(row.as_mapping()) == QPRO_COLUMNS
    assert len(row.as_tuple()) == 23
    assert tsv.count("\t") == 22
    assert len(tsv.split("\t")) == 23
    assert tsv.split("\t")[-1] == row.get("OVM")


def test_empty_adapter_preserves_existing_force_template() -> None:
    assert build_force_metrics_row(
        "PES",
        61,
        _empty_metrics(),
    ) == build_force_row("PES", 61)


def test_running_builder_output_remains_independent() -> None:
    metrics = RunningMetricsRaw(
        timer_time_s=None,
        moving_time_s=None,
        distance_m=None,
        avg_speed_mps=None,
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
        source_scope="session",
    )

    row = build_running_row("ENT", 23, metrics)

    assert row.get("CODIGO") == "ENT"
    assert len(row.as_tuple()) == 23
