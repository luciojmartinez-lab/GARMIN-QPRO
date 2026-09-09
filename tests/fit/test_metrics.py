from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta
from math import inf, nan

import pytest

from garmin_qpro.fit.metrics import FitMetrics, extract_fit_metrics
from garmin_qpro.fit.models import DecodedFit
from garmin_qpro.input.sources import FitSource


def _decoded(messages=None) -> DecodedFit:
    return DecodedFit(
        source=FitSource(
            source_name="activity.fit",
            container_name=None,
            member_path=None,
            data=b"fit",
        ),
        messages={} if messages is None else messages,
        errors=(),
        crc_checked=True,
    )


def _session(**overrides):
    values = {
        "message_index": 0,
        "total_moving_time": 88.5,
        "total_distance": 1234.5,
        "avg_heart_rate": 101,
        "max_heart_rate": 142,
        "total_training_effect": 2.3,
        "total_anaerobic_training_effect": 1.4,
        "training_load_peak": 46.99,
    }
    values.update(overrides)
    return values


def test_extracts_confirmed_session_metrics_without_formatting() -> None:
    metrics = extract_fit_metrics(_decoded({"session": [_session()]}))

    assert metrics == FitMetrics(
        moving_time_s=88.5,
        distance_m=1234.5,
        avg_heart_rate=101.0,
        max_heart_rate=142.0,
        aerobic_te=2.3,
        anaerobic_te=1.4,
        exercise_load=46.99,
    )


def test_valid_session_moving_time_takes_precedence_over_records() -> None:
    start = datetime(2026, 7, 6, 10, 0)
    metrics = extract_fit_metrics(
        _decoded(
            {
                "session": [_session(total_moving_time=42.25)],
                "record": [
                    {"timestamp": start, "enhanced_speed": 2.0},
                    {
                        "timestamp": start + timedelta(seconds=100),
                        "enhanced_speed": 2.0,
                    },
                ],
            }
        )
    )

    assert metrics.moving_time_s == 42.25


def test_moving_time_falls_back_to_ordered_record_intervals() -> None:
    start = datetime(2026, 7, 6, 10, 0)
    metrics = extract_fit_metrics(
        _decoded(
            {
                "session": [_session(total_moving_time=None)],
                "record": [
                    {
                        "timestamp": start + timedelta(seconds=5),
                        "enhanced_speed": 1.0,
                    },
                    {"timestamp": start, "enhanced_speed": 1.0},
                    {
                        "timestamp": start + timedelta(seconds=2),
                        "enhanced_speed": 0.0,
                    },
                    {
                        "timestamp": start + timedelta(seconds=8),
                        "enhanced_speed": 1.0,
                    },
                ],
            }
        )
    )

    assert metrics.moving_time_s == 5.0


def test_enhanced_speed_has_priority_and_speed_is_its_fallback() -> None:
    metrics = extract_fit_metrics(
        _decoded(
            {
                "session": [_session(total_moving_time=0)],
                "record": [
                    {"timestamp": 0, "enhanced_speed": 0.0, "speed": 2.0},
                    {"timestamp": 1, "speed": 2.0},
                    {"timestamp": 3, "enhanced_speed": 0.0, "speed": 2.0},
                ],
            }
        )
    )

    assert metrics.moving_time_s == 2.0


def test_invalid_and_non_increasing_timestamps_are_ignored() -> None:
    metrics = extract_fit_metrics(
        _decoded(
            {
                "record": [
                    {"timestamp": "invalid", "enhanced_speed": 1.0},
                    {"timestamp": 1, "enhanced_speed": 1.0},
                    {"timestamp": 1, "enhanced_speed": 1.0},
                    {"timestamp": 4, "enhanced_speed": 1.0},
                ]
            }
        )
    )

    assert metrics.moving_time_s == 3.0


def test_anaerobic_effect_absence_remains_none() -> None:
    metrics = extract_fit_metrics(
        _decoded(
            {
                "session": [
                    _session(total_anaerobic_training_effect=None)
                ]
            }
        )
    )

    assert metrics.anaerobic_te is None


def test_exercise_load_uses_only_training_load_peak() -> None:
    metrics = extract_fit_metrics(
        _decoded(
            {
                "session": [
                    _session(
                        training_load_peak=None,
                        total_calories=900,
                        avg_power=250,
                    )
                ],
                "set": [{"weight": 120, "repetitions": 10}],
            }
        )
    )

    assert metrics.exercise_load is None


def test_missing_session_and_records_return_empty_metrics() -> None:
    assert extract_fit_metrics(_decoded()) == FitMetrics(
        moving_time_s=None,
        distance_m=None,
        avg_heart_rate=None,
        max_heart_rate=None,
        aerobic_te=None,
        anaerobic_te=None,
        exercise_load=None,
    )


@pytest.mark.parametrize("invalid", [True, "1", nan, inf, -inf, -1])
def test_invalid_session_values_are_rejected(invalid) -> None:
    metrics = extract_fit_metrics(
        _decoded(
            {
                "session": [
                    _session(
                        total_moving_time=invalid,
                        total_distance=invalid,
                        avg_heart_rate=invalid,
                        max_heart_rate=invalid,
                        total_training_effect=invalid,
                        total_anaerobic_training_effect=invalid,
                        training_load_peak=invalid,
                    )
                ]
            }
        )
    )

    assert metrics == FitMetrics(None, None, None, None, None, None, None)


def test_primary_session_uses_existing_message_index_rule() -> None:
    metrics = extract_fit_metrics(
        _decoded(
            {
                "session": [
                    _session(message_index=3, total_distance=300),
                    _session(message_index=1, total_distance=100),
                    _session(message_index=None, total_distance=999),
                ]
            }
        )
    )

    assert metrics.distance_m == 100.0


def test_equal_indexes_preserve_original_fit_order() -> None:
    metrics = extract_fit_metrics(
        _decoded(
            {
                "session": [
                    _session(message_index=1, total_distance=111),
                    _session(message_index=1, total_distance=222),
                ]
            }
        )
    )

    assert metrics.distance_m == 111.0


def test_model_is_immutable() -> None:
    metrics = extract_fit_metrics(_decoded({"session": [_session()]}))

    with pytest.raises(FrozenInstanceError):
        metrics.distance_m = 1.0  # type: ignore[misc]


def test_rejects_non_decoded_fit_input() -> None:
    with pytest.raises(TypeError):
        extract_fit_metrics(object())  # type: ignore[arg-type]
