from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from garmin_qpro.fit.models import DecodedFit
from garmin_qpro.fit.running_metrics import (
    RunningMetricsRaw,
    derive_moving_time_from_records,
    extract_running_metrics,
)
from garmin_qpro.input.sources import FitSource


def _source() -> FitSource:
    return FitSource("activity.fit", None, None, b"fit")


def _decoded(messages=None) -> DecodedFit:
    return DecodedFit(
        source=_source(),
        messages={} if messages is None else messages,
        errors=(),
        crc_checked=True,
    )


def _session(**overrides):
    values = {
        "message_index": 0,
        "total_timer_time": 100.5,
        "total_distance": 250.25,
        "enhanced_avg_speed": 2.5,
        "enhanced_max_speed": 5.5,
        "avg_heart_rate": 120,
        "max_heart_rate": 160,
        "total_training_effect": 2.3,
        "total_anaerobic_training_effect": 0.4,
        "avg_cadence": 80,
        "avg_fractional_cadence": 0.5,
        "max_cadence": 100,
        "max_fractional_cadence": 0.25,
        "avg_step_length": 900.0,
        "avg_stance_time": 300.0,
        "training_load_peak": 12.75,
        "avg_power": 210,
        "max_power": 500,
        "avg_vertical_ratio": 8.4,
        "avg_vertical_oscillation": 70.2,
    }
    values.update(overrides)
    return values


def _records(*speeds: float):
    start = datetime(2026, 7, 6, tzinfo=timezone.utc)
    return [
        {"timestamp": start + timedelta(seconds=index), "enhanced_speed": speed}
        for index, speed in enumerate(speeds)
    ]


def test_extracts_complete_session_metrics() -> None:
    metrics = extract_running_metrics(
        _decoded(
            {
                "session": [_session(total_moving_time=88.0)],
                "record": _records(0.0, 1.0),
            }
        ),
        qpro_key="ENT",
    )

    assert metrics == RunningMetricsRaw(
        timer_time_s=100.5,
        moving_time_s=88.0,
        distance_m=250.25,
        avg_speed_mps=2.5,
        max_speed_mps=5.5,
        avg_hr_bpm=120,
        max_hr_bpm=160,
        aerobic_te=2.3,
        anaerobic_te=0.4,
        avg_cadence_raw=80.5,
        max_cadence_raw=100.25,
        avg_step_length_mm=900.0,
        avg_stance_time_ms=300.0,
        exercise_load=12.75,
        avg_power_w=210,
        max_power_w=500,
        avg_vertical_ratio_pct=8.4,
        avg_vertical_oscillation_mm=70.2,
        acute_load=None,
        chronic_load=None,
        source_scope="session",
        warmup_lap_count=0,
        requires_manual_review=False,
    )


def test_optional_fields_remain_none() -> None:
    metrics = extract_running_metrics(
        _decoded({"session": [{"message_index": 0}]}),
        qpro_key="ENT",
    )

    assert metrics.timer_time_s is None
    assert metrics.distance_m is None
    assert metrics.avg_cadence_raw is None
    assert metrics.exercise_load is None
    assert metrics.acute_load is None
    assert metrics.chronic_load is None


def test_fractional_cadence_is_optional() -> None:
    metrics = extract_running_metrics(
        _decoded(
            {
                "session": [
                    _session(
                        avg_cadence=81,
                        avg_fractional_cadence=None,
                        max_cadence=102,
                        max_fractional_cadence=None,
                    )
                ]
            }
        ),
        qpro_key="ENT",
    )

    assert metrics.avg_cadence_raw == 81.0
    assert metrics.max_cadence_raw == 102.0


def test_moving_time_is_derived_from_records() -> None:
    metrics = extract_running_metrics(
        _decoded(
            {
                "session": [_session()],
                "record": _records(0.0, 0.31, 1.0, 0.3, 0.4),
            }
        ),
        qpro_key="ENT",
    )

    assert metrics.moving_time_s == 3.0


def test_positive_total_moving_time_is_used_directly() -> None:
    metrics = extract_running_metrics(
        _decoded(
            {
                "session": [_session(total_moving_time=42.5)],
                "record": _records(1.0, 1.0, 1.0),
            }
        ),
        qpro_key="ENT",
    )

    assert metrics.moving_time_s == 42.5


@pytest.mark.parametrize(
    "invalid_moving_time",
    [0, -1, "42"],
)
def test_invalid_total_moving_time_falls_back_to_records(
    invalid_moving_time,
) -> None:
    metrics = extract_running_metrics(
        _decoded(
            {
                "session": [_session(total_moving_time=invalid_moving_time)],
                "record": _records(1.0, 0.0, 1.0),
            }
        ),
        qpro_key="ENT",
    )

    assert metrics.moving_time_s == 2.0


def test_invalid_total_moving_time_without_safe_records_returns_none() -> None:
    metrics = extract_running_metrics(
        _decoded(
            {
                "session": [_session(total_moving_time=0)],
                "record": [{"enhanced_speed": 1.0}],
            }
        ),
        qpro_key="ENT",
    )

    assert metrics.moving_time_s is None


def test_record_order_and_invalid_intervals_are_handled() -> None:
    start = datetime(2026, 7, 6, tzinfo=timezone.utc)
    records = [
        {"timestamp": start + timedelta(seconds=5), "enhanced_speed": 1.0},
        {"timestamp": start + timedelta(seconds=0), "enhanced_speed": 1.0},
        {"timestamp": start + timedelta(seconds=1), "enhanced_speed": 1.0},
        {"timestamp": start + timedelta(seconds=20), "enhanced_speed": 1.0},
        {"timestamp": start + timedelta(seconds=20), "enhanced_speed": 1.0},
    ]

    assert derive_moving_time_from_records(records) == 2.0


def test_moving_time_returns_none_when_records_are_not_safe() -> None:
    assert derive_moving_time_from_records([{"enhanced_speed": 1.0}]) is None
    assert derive_moving_time_from_records(
        [
            {"timestamp": "a", "enhanced_speed": 1.0},
            {"timestamp": "b", "enhanced_speed": 1.0},
        ]
    ) is None


def test_multiple_sessions_are_selected_by_message_index() -> None:
    metrics = extract_running_metrics(
        _decoded(
            {
                "session": [
                    _session(message_index=2, total_distance=200.0),
                    _session(message_index=0, total_distance=100.0),
                ]
            }
        ),
        qpro_key="ENT",
    )

    assert metrics.distance_m == 100.0


def test_cal_with_one_warmup_lap_uses_lap_special_metrics() -> None:
    metrics = extract_running_metrics(
        _decoded(
            {
                "session": [
                    _session(
                        avg_cadence=1,
                        max_cadence=2,
                        avg_step_length=3,
                        avg_stance_time=4,
                        avg_power=5,
                        max_power=6,
                        avg_vertical_ratio=7,
                        avg_vertical_oscillation=8,
                    )
                ],
                "lap": [
                    {
                        "intensity": "warmup",
                        "total_timer_time": 10.0,
                        "avg_cadence": 70,
                        "avg_fractional_cadence": 0.5,
                        "max_cadence": 90,
                        "max_fractional_cadence": 0.25,
                        "avg_step_length": 800.0,
                        "avg_stance_time": 320.0,
                        "avg_power": 150,
                        "max_power": 300,
                        "avg_vertical_ratio": 10.5,
                        "avg_vertical_oscillation": 75.0,
                    }
                ],
            }
        ),
        qpro_key="CAL",
    )

    assert metrics.source_scope == "cal_warmup_laps"
    assert metrics.warmup_lap_count == 1
    assert metrics.requires_manual_review is False
    assert metrics.avg_cadence_raw == 70.5
    assert metrics.max_cadence_raw == 90.25
    assert metrics.avg_step_length_mm == 800.0
    assert metrics.avg_stance_time_ms == 320.0
    assert metrics.avg_power_w == 150.0
    assert metrics.max_power_w == 300
    assert metrics.avg_vertical_ratio_pct == 10.5
    assert metrics.avg_vertical_oscillation_mm == 75.0


def test_cal_with_multiple_warmup_laps_uses_weighted_averages_and_maxima() -> None:
    metrics = extract_running_metrics(
        _decoded(
            {
                "session": [_session()],
                "lap": [
                    {
                        "intensity": "warmup",
                        "total_timer_time": 10.0,
                        "avg_cadence": 60,
                        "avg_fractional_cadence": 0.5,
                        "max_cadence": 80,
                        "max_fractional_cadence": 0.0,
                        "avg_power": 100,
                        "max_power": 180,
                    },
                    {
                        "intensity": "warmup",
                        "total_timer_time": 30.0,
                        "avg_cadence": 70,
                        "avg_fractional_cadence": 0.25,
                        "max_cadence": 75,
                        "max_fractional_cadence": 0.5,
                        "avg_power": 200,
                        "max_power": 220,
                    },
                    {
                        "intensity": "recovery",
                        "total_timer_time": 100.0,
                        "avg_cadence": 5,
                        "max_cadence": 10,
                    },
                ],
            }
        ),
        qpro_key="CAL",
    )

    assert metrics.avg_cadence_raw == pytest.approx(67.8125)
    assert metrics.max_cadence_raw == 80.0
    assert metrics.avg_power_w == pytest.approx(175.0)
    assert metrics.max_power_w == 220
    assert metrics.warmup_lap_count == 2


def test_cal_weighting_uses_only_laps_with_metric_and_duration() -> None:
    metrics = extract_running_metrics(
        _decoded(
            {
                "session": [_session()],
                "lap": [
                    {
                        "intensity": "warmup",
                        "total_timer_time": 10.0,
                        "avg_step_length": 100.0,
                    },
                    {
                        "intensity": "warmup",
                        "total_timer_time": 30.0,
                    },
                    {
                        "intensity": "warmup",
                        "total_timer_time": 0.0,
                        "avg_step_length": 999.0,
                    },
                ],
            }
        ),
        qpro_key="CAL",
    )

    assert metrics.avg_step_length_mm == 100.0
    assert metrics.avg_cadence_raw is None


def test_cal_without_warmup_laps_needs_manual_review_and_keeps_specials_none() -> None:
    metrics = extract_running_metrics(
        _decoded(
            {
                "session": [
                    _session(
                        avg_cadence=80,
                        max_cadence=100,
                        avg_step_length=900,
                        avg_stance_time=300,
                        avg_power=200,
                        max_power=500,
                        avg_vertical_ratio=8,
                        avg_vertical_oscillation=70,
                    )
                ],
                "lap": [{"intensity": "recovery", "total_timer_time": 10.0}],
            }
        ),
        qpro_key="CAL",
    )

    assert metrics.requires_manual_review is True
    assert metrics.warmup_lap_count == 0
    assert metrics.avg_cadence_raw is None
    assert metrics.max_cadence_raw is None
    assert metrics.avg_step_length_mm is None
    assert metrics.avg_stance_time_ms is None
    assert metrics.avg_power_w is None
    assert metrics.max_power_w is None
    assert metrics.avg_vertical_ratio_pct is None
    assert metrics.avg_vertical_oscillation_mm is None


def test_model_is_immutable() -> None:
    metrics = extract_running_metrics(
        _decoded({"session": [_session()]}),
        qpro_key="ENT",
    )

    with pytest.raises((FrozenInstanceError, AttributeError)):
        metrics.distance_m = 1.0  # type: ignore[misc]


def test_input_types_are_validated() -> None:
    with pytest.raises(TypeError):
        extract_running_metrics(object(), qpro_key="ENT")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        extract_running_metrics(_decoded(), qpro_key=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        extract_running_metrics(_decoded(), qpro_key=" ")
    with pytest.raises(ValueError):
        derive_moving_time_from_records([], max_sample_gap_s=0)
