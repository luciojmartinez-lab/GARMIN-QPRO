from dataclasses import FrozenInstanceError
from math import inf, nan

import pytest

from garmin_qpro.fit.force_metrics import (
    ForceMetricsRaw,
    extract_force_metrics,
)
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
        "total_timer_time": 1663.291,
        "total_elapsed_time": 1701.977,
        "avg_heart_rate": 121,
        "max_heart_rate": 146,
        "total_training_effect": 3.0,
        "total_anaerobic_training_effect": 2.3,
        "training_load_peak": 93.91545104980469,
    }
    values.update(overrides)
    return values


def test_extracts_all_confirmed_force_session_metrics() -> None:
    metrics = extract_force_metrics(
        _decoded({"session": [_session()]})
    )

    assert metrics == ForceMetricsRaw(
        timer_time_s=1663.291,
        elapsed_time_s=1701.977,
        avg_hr_bpm=121,
        max_hr_bpm=146,
        aerobic_te=3.0,
        anaerobic_te=2.3,
        exercise_load=93.91545104980469,
        acute_load=None,
        chronic_load=None,
    )


def test_session_with_lowest_numeric_message_index_is_selected() -> None:
    metrics = extract_force_metrics(
        _decoded(
            {
                "session": [
                    _session(message_index=3, avg_heart_rate=130),
                    _session(message_index=1, avg_heart_rate=110),
                    _session(avg_heart_rate=140, message_index=None),
                ]
            }
        )
    )

    assert metrics.avg_hr_bpm == 110


def test_equal_message_indexes_preserve_fit_order() -> None:
    metrics = extract_force_metrics(
        _decoded(
            {
                "session": [
                    _session(message_index=1, avg_heart_rate=101),
                    _session(message_index=1, avg_heart_rate=202),
                ]
            }
        )
    )

    assert metrics.avg_hr_bpm == 101


def test_sessions_without_numeric_indexes_use_original_order() -> None:
    metrics = extract_force_metrics(
        _decoded(
            {
                "session": [
                    _session(message_index=None, avg_heart_rate=111),
                    _session(message_index="2", avg_heart_rate=222),
                ]
            }
        )
    )

    assert metrics.avg_hr_bpm == 111


def test_missing_session_and_fields_remain_none() -> None:
    no_session = extract_force_metrics(_decoded())
    empty_session = extract_force_metrics(
        _decoded({"session": [{"message_index": 0}]})
    )

    assert no_session == empty_session
    assert all(
        value is None
        for value in (
            no_session.timer_time_s,
            no_session.elapsed_time_s,
            no_session.avg_hr_bpm,
            no_session.max_hr_bpm,
            no_session.aerobic_te,
            no_session.anaerobic_te,
            no_session.exercise_load,
            no_session.acute_load,
            no_session.chronic_load,
        )
    )


@pytest.mark.parametrize("invalid", [True, "1", nan, inf, -inf, -1])
def test_invalid_session_values_are_not_accepted(invalid) -> None:
    metrics = extract_force_metrics(
        _decoded(
            {
                "session": [
                    _session(
                        total_timer_time=invalid,
                        total_elapsed_time=invalid,
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

    assert metrics == ForceMetricsRaw(
        timer_time_s=None,
        elapsed_time_s=None,
        avg_hr_bpm=None,
        max_hr_bpm=None,
        aerobic_te=None,
        anaerobic_te=None,
        exercise_load=None,
        acute_load=None,
        chronic_load=None,
    )


def test_zero_is_preserved_for_valid_metrics() -> None:
    metrics = extract_force_metrics(
        _decoded(
            {
                "session": [
                    _session(
                        total_timer_time=0,
                        total_elapsed_time=0,
                        avg_heart_rate=0,
                        max_heart_rate=0,
                        total_training_effect=0,
                        total_anaerobic_training_effect=0,
                        training_load_peak=0,
                    )
                ]
            }
        )
    )

    assert metrics == ForceMetricsRaw(
        timer_time_s=0.0,
        elapsed_time_s=0.0,
        avg_hr_bpm=0,
        max_hr_bpm=0,
        aerobic_te=0.0,
        anaerobic_te=0.0,
        exercise_load=0.0,
        acute_load=None,
        chronic_load=None,
    )


def test_only_training_load_peak_can_supply_exercise_load() -> None:
    metrics = extract_force_metrics(
        _decoded(
            {
                "session": [
                    {
                        "message_index": 0,
                        "total_calories": 999,
                        "total_work": 123456,
                    }
                ],
                "set": [
                    {
                        "set_type": "active",
                        "weight": 93.91545104980469,
                        "repetitions": 10,
                    }
                ],
            }
        )
    )

    assert metrics.exercise_load is None
    assert metrics.acute_load is None
    assert metrics.chronic_load is None


def test_model_is_immutable() -> None:
    metrics = extract_force_metrics(_decoded({"session": [_session()]}))

    with pytest.raises((FrozenInstanceError, AttributeError)):
        metrics.exercise_load = 1.0  # type: ignore[misc]


def test_decoded_fit_is_required() -> None:
    with pytest.raises(TypeError):
        extract_force_metrics(object())  # type: ignore[arg-type]
