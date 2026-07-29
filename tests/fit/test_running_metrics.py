from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timedelta, timezone

import pytest

from garmin_qpro.fit.models import DecodedFit
from garmin_qpro.fit.running_metrics import (
    RunningMetricsRaw,
    UnreliableCamTimeError,
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
        source_scope="session",
        warmup_lap_count=0,
        requires_manual_review=False,
    )


def test_model_contains_only_current_running_fields() -> None:
    assert tuple(field.name for field in fields(RunningMetricsRaw)) == (
        "timer_time_s",
        "moving_time_s",
        "distance_m",
        "avg_speed_mps",
        "max_speed_mps",
        "avg_hr_bpm",
        "max_hr_bpm",
        "aerobic_te",
        "anaerobic_te",
        "avg_cadence_raw",
        "max_cadence_raw",
        "avg_step_length_mm",
        "avg_stance_time_ms",
        "exercise_load",
        "avg_power_w",
        "max_power_w",
        "avg_vertical_ratio_pct",
        "avg_vertical_oscillation_mm",
        "source_scope",
        "warmup_lap_count",
        "requires_manual_review",
        "is_trimmed",
        "trim_reasons",
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


def test_cam_uses_valid_session_timer_instead_of_fragmented_records() -> None:
    session = _session(
        total_timer_time=5152.979,
        total_elapsed_time=5152.979,
        total_distance=3577.58,
        enhanced_avg_speed=0.694,
    )

    metrics = extract_running_metrics(
        _decoded(
            {
                "session": [session],
                "record": _records(*(1.0 for _ in range(147))),
            }
        ),
        qpro_key="CAM",
    )

    assert derive_moving_time_from_records(
        _records(*(1.0 for _ in range(147)))
    ) == 147.0
    assert metrics.timer_time_s == 5152.979
    assert metrics.moving_time_s == 5152.979
    assert metrics.distance_m == 3577.58


@pytest.mark.parametrize(
    "session",
    [
        _session(
            total_timer_time=None,
            total_elapsed_time=5152.979,
            total_distance=3577.58,
            enhanced_avg_speed=0.694,
        ),
        _session(
            total_timer_time=147.0,
            total_elapsed_time=5152.979,
            total_distance=3577.58,
            enhanced_avg_speed=0.694,
        ),
    ],
)
def test_cam_rejects_missing_or_incoherent_session_time(session) -> None:
    with pytest.raises(UnreliableCamTimeError):
        extract_running_metrics(
            _decoded({"session": [session]}),
            qpro_key="CAM",
        )


def _speed_filter_records(*, sustained: bool = False):
    start = datetime(2026, 7, 6, tzinfo=timezone.utc)
    if sustained:
        speeds = [1.0, 5.0, 5.2, 5.1, 1.0]
        distances = [0.0, 25.0, 51.0, 76.5, 81.5]
    else:
        speeds = [1.0, 5.0, 1.1, 1.0, 1.0]
        distances = [0.0, 5.0, 10.0, 15.0, 20.0]
    return [
        {
            "timestamp": start + timedelta(seconds=index * 5),
            "enhanced_speed": speed,
            "distance": distance,
        }
        for index, (speed, distance) in enumerate(zip(speeds, distances))
    ]


@pytest.mark.parametrize(
    "qpro_key",
    ["AQG", "CAM", "CAL", "CLP", "FIN", "FPN", "MOV", "PLY"],
)
def test_soft_activity_keys_filter_isolated_speed_peak(qpro_key: str) -> None:
    session = _session(
        total_timer_time=100.0,
        total_elapsed_time=100.0,
        total_moving_time=80.0,
        total_distance=100.0,
        enhanced_avg_speed=1.0,
        enhanced_max_speed=5.0,
    )
    messages = {
        "session": [session],
        "record": _speed_filter_records(),
    }
    if qpro_key == "CAL":
        messages["lap"] = [
            {
                "intensity": "warmup",
                "total_timer_time": 10.0,
                "avg_cadence": 70,
            }
        ]

    metrics = extract_running_metrics(
        _decoded(messages),
        qpro_key=qpro_key,
    )

    assert metrics.max_speed_mps == 1.1
    assert metrics.requires_manual_review is False


@pytest.mark.parametrize("qpro_key", ["ENT", "SER", "FLK"])
def test_fast_running_keys_do_not_filter_same_peak(qpro_key: str) -> None:
    metrics = extract_running_metrics(
        _decoded(
            {
                "session": [
                    _session(
                        total_moving_time=80.0,
                        enhanced_avg_speed=1.0,
                        enhanced_max_speed=5.0,
                    )
                ],
                "record": _speed_filter_records(),
            }
        ),
        qpro_key=qpro_key,
    )

    assert metrics.max_speed_mps == 5.0
    assert metrics.requires_manual_review is False


def test_soft_activity_keeps_sustained_high_speed() -> None:
    metrics = extract_running_metrics(
        _decoded(
            {
                "session": [
                    _session(
                        total_timer_time=100.0,
                        total_elapsed_time=100.0,
                        total_moving_time=80.0,
                        total_distance=100.0,
                        enhanced_avg_speed=1.0,
                        enhanced_max_speed=5.2,
                    )
                ],
                "record": _speed_filter_records(sustained=True),
            }
        ),
        qpro_key="CAM",
    )

    assert metrics.max_speed_mps == 5.2
    assert metrics.requires_manual_review is False


def _trimmed_messages(*, max_speed: float = 10.0):
    start = datetime(2026, 7, 6, tzinfo=timezone.utc)
    records = [
        {
            "timestamp": start + timedelta(seconds=index * 5),
            "enhanced_speed": speed,
            "distance": distance,
            "heart_rate": heart_rate,
            "cadence": cadence,
            "power": power,
        }
        for index, (
            speed,
            distance,
            heart_rate,
            cadence,
            power,
        ) in enumerate(
            [
                (1.0, 0.0, 90, 50, 100),
                (5.0, 5.0, 100, 60, 150),
                (1.1, 10.0, 110, 70, 200),
                (1.0, 15.0, 100, 60, 150),
                (1.0, 20.0, 90, 50, 100),
            ]
        )
    ]
    return {
        "session": [
            _session(
                start_time=start,
                timestamp=start + timedelta(seconds=100),
                total_timer_time=20.0,
                total_elapsed_time=20.0,
                total_moving_time=20.0,
                total_distance=20.0,
                enhanced_avg_speed=1.0,
                enhanced_max_speed=max_speed,
                avg_heart_rate=100,
                max_heart_rate=180,
                avg_cadence=60,
                avg_fractional_cadence=0.0,
                max_cadence=100,
                max_fractional_cadence=0.0,
                avg_power=150,
                max_power=500,
            )
        ],
        "record": records,
    }


def test_trimmed_soft_activity_uses_record_maxima_then_peak_filter() -> None:
    metrics = extract_running_metrics(
        _decoded(_trimmed_messages()),
        qpro_key="CAM",
    )

    assert metrics.is_trimmed is True
    assert "record_end_before_session_end" in metrics.trim_reasons
    assert metrics.max_speed_mps == 1.1
    assert metrics.max_hr_bpm == 110
    assert metrics.max_cadence_raw == 70.0
    assert metrics.max_power_w == 200
    assert metrics.avg_speed_mps == 1.0
    assert metrics.avg_hr_bpm == 100
    assert metrics.avg_cadence_raw == 60.0
    assert metrics.avg_power_w == 150
    assert metrics.requires_manual_review is True


def test_trimmed_fast_activity_uses_real_high_record_without_soft_filter() -> None:
    metrics = extract_running_metrics(
        _decoded(_trimmed_messages()),
        qpro_key="ENT",
    )

    assert metrics.is_trimmed is True
    assert metrics.max_speed_mps == 5.0
    assert metrics.moving_time_s is None
    assert metrics.requires_manual_review is True


def test_trimmed_incoherent_averages_are_not_preserved() -> None:
    messages = _trimmed_messages()
    messages["session"][0].update(
        enhanced_avg_speed=9.0,
        avg_heart_rate=200,
        avg_cadence=120,
        avg_power=900,
    )

    metrics = extract_running_metrics(
        _decoded(messages),
        qpro_key="ENT",
    )

    assert metrics.avg_speed_mps is None
    assert metrics.avg_hr_bpm is None
    assert metrics.avg_cadence_raw is None
    assert metrics.avg_power_w is None


def test_trimmed_activity_uses_record_segment_distance() -> None:
    messages = _trimmed_messages()
    messages["session"][0]["total_distance"] = 999.0

    metrics = extract_running_metrics(
        _decoded(messages),
        qpro_key="ENT",
    )

    assert metrics.distance_m == 20.0


def test_trimmed_cam_rejects_timer_beyond_preserved_record_segment() -> None:
    messages = _trimmed_messages()
    messages["session"][0].update(
        total_timer_time=100.0,
        total_elapsed_time=100.0,
        total_distance=20.0,
        enhanced_avg_speed=0.2,
    )

    with pytest.raises(
        UnreliableCamTimeError,
        match="preserved record segment",
    ):
        extract_running_metrics(
            _decoded(messages),
            qpro_key="CAM",
        )


def test_trimmed_cal_keeps_existing_warmup_special_rule() -> None:
    messages = _trimmed_messages()
    messages["lap"] = [
        {
            "intensity": "warmup",
            "total_timer_time": 10.0,
            "avg_cadence": 72,
            "max_cadence": 82,
            "avg_power": 175,
            "max_power": 225,
        }
    ]

    metrics = extract_running_metrics(
        _decoded(messages),
        qpro_key="CAL",
    )

    assert metrics.is_trimmed is True
    assert metrics.source_scope == "cal_warmup_laps"
    assert metrics.avg_cadence_raw == 72.0
    assert metrics.max_cadence_raw == 82.0
    assert metrics.avg_power_w == 175.0
    assert metrics.max_power_w == 225


def test_soft_activity_without_neighbors_keeps_maximum_for_review() -> None:
    start = datetime(2026, 7, 6, tzinfo=timezone.utc)
    metrics = extract_running_metrics(
        _decoded(
            {
                "session": [
                    _session(
                        total_timer_time=100.0,
                        total_elapsed_time=100.0,
                        total_moving_time=80.0,
                        total_distance=100.0,
                        enhanced_avg_speed=1.0,
                        enhanced_max_speed=5.0,
                    )
                ],
                "record": [
                    {
                        "timestamp": start,
                        "enhanced_speed": 5.0,
                        "distance": 0.0,
                    }
                ],
            }
        ),
        qpro_key="CAM",
    )

    assert metrics.max_speed_mps == 5.0
    assert metrics.requires_manual_review is True


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
