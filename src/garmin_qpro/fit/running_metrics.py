"""Extract raw running metrics from decoded FIT messages."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from math import isclose
from typing import Any, Literal

from garmin_qpro.fit.models import DecodedFit
from garmin_qpro.fit.speed_filter import (
    SOFT_SPEED_FILTER_KEYS,
    filter_soft_activity_max_speed,
)

SOURCE_SESSION: Literal["session"] = "session"
SOURCE_CAL_WARMUP_LAPS: Literal["cal_warmup_laps"] = "cal_warmup_laps"
MOVING_SPEED_THRESHOLD_MPS = 0.3
MAX_RECORD_SAMPLE_GAP_S = 2.0
CAM_MAX_AVERAGE_SPEED_MPS = 5.0
CAM_SPEED_REL_TOLERANCE = 0.05
CAM_SPEED_ABS_TOLERANCE_MPS = 0.05
CAM_ELAPSED_TOLERANCE_S = 2.0


class UnreliableCamTimeError(ValueError):
    """Raised when a CAM activity has no trustworthy session duration."""

    def __init__(self, reason: str) -> None:
        self.qpro_key = "CAM"
        self.reason = reason
        super().__init__(f"CAM activity has no reliable session time: {reason}")


@dataclass(frozen=True, slots=True)
class RunningMetricsRaw:
    """Raw FIT values for a running-like activity, before QPro formatting."""

    timer_time_s: float | None
    moving_time_s: float | None
    distance_m: float | None
    avg_speed_mps: float | None
    max_speed_mps: float | None
    avg_hr_bpm: int | None
    max_hr_bpm: int | None
    aerobic_te: float | None
    anaerobic_te: float | None
    avg_cadence_raw: float | None
    max_cadence_raw: float | None
    avg_step_length_mm: float | None
    avg_stance_time_ms: float | None
    exercise_load: float | None
    avg_power_w: int | float | None
    max_power_w: int | None
    avg_vertical_ratio_pct: float | None
    avg_vertical_oscillation_mm: float | None
    source_scope: Literal["session", "cal_warmup_laps"]
    warmup_lap_count: int = 0
    requires_manual_review: bool = False


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float, Decimal)) and not isinstance(
        value,
        bool,
    )


def _float_value(value: Any) -> float | None:
    if not _is_number(value):
        return None
    parsed = float(value)
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def _int_value(value: Any) -> int | None:
    parsed = _float_value(value)
    if parsed is None:
        return None
    return int(parsed)


def _positive_float_value(value: Any) -> float | None:
    parsed = _float_value(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def _combined_number(
    message: Mapping[Any, Any],
    whole_field: str,
    fractional_field: str,
) -> float | None:
    whole = _float_value(message.get(whole_field))
    fraction = _float_value(message.get(fractional_field))
    if whole is None:
        return None
    return whole + (fraction or 0.0)


def _valid_messages(messages: Iterable[Any]) -> tuple[Mapping[Any, Any], ...]:
    return tuple(message for message in messages if isinstance(message, Mapping))


def _message_index(message: Mapping[Any, Any], fallback: int) -> tuple[int, int]:
    index = _float_value(message.get("message_index"))
    if index is None:
        return (1, fallback)
    return (0, int(index))


def _select_session(decoded: DecodedFit) -> Mapping[Any, Any] | None:
    """Select a session deterministically: lowest message_index, then FIT order."""

    sessions = _valid_messages(decoded.get_messages("session"))
    if not sessions:
        return None
    indexed = sorted(
        enumerate(sessions),
        key=lambda item: _message_index(item[1], item[0]),
    )
    return indexed[0][1]


def _timestamp_seconds_delta(first: Any, second: Any) -> float | None:
    try:
        if isinstance(first, datetime) and isinstance(second, datetime):
            return (second - first).total_seconds()
        if _is_number(first) and _is_number(second):
            return float(second) - float(first)
    except (OverflowError, TypeError, ValueError):
        return None
    return None


def derive_moving_time_from_records(
    records: Iterable[Any],
    *,
    speed_field: str = "enhanced_speed",
    speed_threshold_mps: float = MOVING_SPEED_THRESHOLD_MPS,
    max_sample_gap_s: float = MAX_RECORD_SAMPLE_GAP_S,
) -> float | None:
    """Derive moving time from 1 Hz records whose speed exceeds the threshold."""

    threshold = _float_value(speed_threshold_mps)
    max_gap = _float_value(max_sample_gap_s)
    if threshold is None or max_gap is None or max_gap <= 0:
        raise ValueError("speed threshold and max gap must be valid numbers")

    samples: list[tuple[Any, float]] = []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        timestamp = record.get("timestamp")
        speed = _float_value(record.get(speed_field))
        if timestamp is None or speed is None:
            continue
        samples.append((timestamp, speed))

    if len(samples) < 2:
        return None

    try:
        samples.sort(key=lambda item: item[0])
    except TypeError:
        return None

    moving_seconds = 0.0
    valid_neighbor_seen = False
    for index, (timestamp, speed) in enumerate(samples):
        previous_gap = (
            _timestamp_seconds_delta(samples[index - 1][0], timestamp)
            if index > 0
            else None
        )
        next_gap = (
            _timestamp_seconds_delta(timestamp, samples[index + 1][0])
            if index < len(samples) - 1
            else None
        )
        has_valid_neighbor = any(
            gap is not None and 0 < gap <= max_gap
            for gap in (previous_gap, next_gap)
        )
        if not has_valid_neighbor:
            continue
        valid_neighbor_seen = True
        if speed > threshold:
            moving_seconds += 1.0

    return moving_seconds if valid_neighbor_seen else None


def _cam_activity_time(
    session: Mapping[Any, Any] | None,
) -> float:
    if session is None:
        raise UnreliableCamTimeError("session message is missing")

    timer_time = _positive_float_value(session.get("total_timer_time"))
    if timer_time is None:
        raise UnreliableCamTimeError(
            "session.total_timer_time is missing or invalid"
        )

    distance = _positive_float_value(session.get("total_distance"))
    if distance is None:
        raise UnreliableCamTimeError(
            "session.total_distance is missing or invalid"
        )

    calculated_speed = distance / timer_time
    if calculated_speed > CAM_MAX_AVERAGE_SPEED_MPS:
        raise UnreliableCamTimeError(
            "session time and distance imply an implausible walking speed"
        )

    elapsed_raw = session.get("total_elapsed_time")
    elapsed_time = (
        _positive_float_value(elapsed_raw)
        if elapsed_raw is not None
        else None
    )
    if elapsed_raw is not None and elapsed_time is None:
        raise UnreliableCamTimeError(
            "session.total_elapsed_time is invalid"
        )
    if (
        elapsed_time is not None
        and timer_time > elapsed_time + CAM_ELAPSED_TOLERANCE_S
    ):
        raise UnreliableCamTimeError(
            "session.total_timer_time exceeds total_elapsed_time"
        )

    average_speed_raw = session.get("enhanced_avg_speed")
    if average_speed_raw is None:
        average_speed_raw = session.get("avg_speed")
    average_speed = (
        _positive_float_value(average_speed_raw)
        if average_speed_raw is not None
        else None
    )
    if average_speed_raw is not None and average_speed is None:
        raise UnreliableCamTimeError(
            "session average speed is invalid"
        )
    if average_speed is not None and not isclose(
        calculated_speed,
        average_speed,
        rel_tol=CAM_SPEED_REL_TOLERANCE,
        abs_tol=CAM_SPEED_ABS_TOLERANCE_MPS,
    ):
        raise UnreliableCamTimeError(
            "session time, distance, and average speed are inconsistent"
        )
    if average_speed is None and elapsed_time is None:
        raise UnreliableCamTimeError(
            "session time lacks an independent consistency check"
        )

    return timer_time


def _weighted_average(
    messages: Iterable[Mapping[Any, Any]],
    value_field: str,
    *,
    fractional_field: str | None = None,
) -> float | None:
    numerator = 0.0
    denominator = 0.0
    for message in messages:
        duration = _float_value(message.get("total_timer_time"))
        if duration is None or duration <= 0:
            continue
        if fractional_field is None:
            value = _float_value(message.get(value_field))
        else:
            value = _combined_number(message, value_field, fractional_field)
        if value is None:
            continue
        numerator += value * duration
        denominator += duration
    if denominator <= 0:
        return None
    return numerator / denominator


def _max_value(
    messages: Iterable[Mapping[Any, Any]],
    value_field: str,
    *,
    fractional_field: str | None = None,
) -> float | None:
    values: list[float] = []
    for message in messages:
        if fractional_field is None:
            value = _float_value(message.get(value_field))
        else:
            value = _combined_number(message, value_field, fractional_field)
        if value is not None:
            values.append(value)
    return max(values) if values else None


def _warmup_laps(decoded: DecodedFit) -> tuple[Mapping[Any, Any], ...]:
    return tuple(
        lap
        for lap in _valid_messages(decoded.get_messages("lap"))
        if lap.get("intensity") == "warmup"
    )


def _session_metrics(
    session: Mapping[Any, Any] | None,
    moving_time_s: float | None,
    *,
    source_scope: Literal["session", "cal_warmup_laps"],
    warmup_lap_count: int = 0,
    requires_manual_review: bool = False,
) -> RunningMetricsRaw:
    if session is None:
        return RunningMetricsRaw(
            timer_time_s=None,
            moving_time_s=moving_time_s,
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
            source_scope=source_scope,
            warmup_lap_count=warmup_lap_count,
            requires_manual_review=requires_manual_review,
        )

    return RunningMetricsRaw(
        timer_time_s=_float_value(session.get("total_timer_time")),
        moving_time_s=moving_time_s,
        distance_m=_float_value(session.get("total_distance")),
        avg_speed_mps=_float_value(session.get("enhanced_avg_speed")),
        max_speed_mps=_float_value(session.get("enhanced_max_speed")),
        avg_hr_bpm=_int_value(session.get("avg_heart_rate")),
        max_hr_bpm=_int_value(session.get("max_heart_rate")),
        aerobic_te=_float_value(session.get("total_training_effect")),
        anaerobic_te=_float_value(
            session.get("total_anaerobic_training_effect")
        ),
        avg_cadence_raw=_combined_number(
            session,
            "avg_cadence",
            "avg_fractional_cadence",
        ),
        max_cadence_raw=_combined_number(
            session,
            "max_cadence",
            "max_fractional_cadence",
        ),
        avg_step_length_mm=_float_value(session.get("avg_step_length")),
        avg_stance_time_ms=_float_value(session.get("avg_stance_time")),
        exercise_load=_float_value(session.get("training_load_peak")),
        avg_power_w=_int_value(session.get("avg_power")),
        max_power_w=_int_value(session.get("max_power")),
        avg_vertical_ratio_pct=_float_value(session.get("avg_vertical_ratio")),
        avg_vertical_oscillation_mm=_float_value(
            session.get("avg_vertical_oscillation")
        ),
        source_scope=source_scope,
        warmup_lap_count=warmup_lap_count,
        requires_manual_review=requires_manual_review,
    )


def _apply_cal_warmup_metrics(
    metrics: RunningMetricsRaw,
    warmups: tuple[Mapping[Any, Any], ...],
) -> RunningMetricsRaw:
    warmup_count = len(warmups)
    requires_review = metrics.requires_manual_review or warmup_count == 0
    return RunningMetricsRaw(
        timer_time_s=metrics.timer_time_s,
        moving_time_s=metrics.moving_time_s,
        distance_m=metrics.distance_m,
        avg_speed_mps=metrics.avg_speed_mps,
        max_speed_mps=metrics.max_speed_mps,
        avg_hr_bpm=metrics.avg_hr_bpm,
        max_hr_bpm=metrics.max_hr_bpm,
        aerobic_te=metrics.aerobic_te,
        anaerobic_te=metrics.anaerobic_te,
        avg_cadence_raw=_weighted_average(
            warmups,
            "avg_cadence",
            fractional_field="avg_fractional_cadence",
        ),
        max_cadence_raw=_max_value(
            warmups,
            "max_cadence",
            fractional_field="max_fractional_cadence",
        ),
        avg_step_length_mm=_weighted_average(warmups, "avg_step_length"),
        avg_stance_time_ms=_weighted_average(warmups, "avg_stance_time"),
        exercise_load=metrics.exercise_load,
        avg_power_w=_weighted_average(warmups, "avg_power"),
        max_power_w=(
            int(max_power)
            if (max_power := _max_value(warmups, "max_power")) is not None
            else None
        ),
        avg_vertical_ratio_pct=_weighted_average(
            warmups,
            "avg_vertical_ratio",
        ),
        avg_vertical_oscillation_mm=_weighted_average(
            warmups,
            "avg_vertical_oscillation",
        ),
        source_scope=SOURCE_CAL_WARMUP_LAPS,
        warmup_lap_count=warmup_count,
        requires_manual_review=requires_review,
    )


def extract_running_metrics(
    decoded: DecodedFit,
    *,
    qpro_key: str,
) -> RunningMetricsRaw:
    """Extract raw running metrics for a resolved QPro key."""

    if not isinstance(decoded, DecodedFit):
        raise TypeError("decoded must be a DecodedFit")
    if not isinstance(qpro_key, str):
        raise TypeError("qpro_key must be a string")
    normalized_key = qpro_key.strip().upper()
    if not normalized_key:
        raise ValueError("qpro_key cannot be empty")

    session = _select_session(decoded)
    if normalized_key == "CAM":
        moving_time_s = _cam_activity_time(session)
    else:
        session_moving_time = (
            _positive_float_value(session.get("total_moving_time"))
            if session is not None
            else None
        )
        moving_time_s = (
            session_moving_time
            if session_moving_time is not None
            else derive_moving_time_from_records(
                decoded.get_messages("record")
            )
        )

    source_scope = (
        SOURCE_CAL_WARMUP_LAPS
        if normalized_key == "CAL"
        else SOURCE_SESSION
    )
    metrics = _session_metrics(
        session,
        moving_time_s,
        source_scope=source_scope,
    )
    if normalized_key in SOFT_SPEED_FILTER_KEYS:
        speed_result = filter_soft_activity_max_speed(
            decoded.get_messages("record"),
            original_max_speed_mps=metrics.max_speed_mps,
            average_speed_mps=metrics.avg_speed_mps,
        )
        metrics = replace(
            metrics,
            max_speed_mps=speed_result.max_speed_mps,
            requires_manual_review=(
                metrics.requires_manual_review
                or speed_result.requires_manual_review
            ),
        )
    if normalized_key != "CAL":
        return metrics

    return _apply_cal_warmup_metrics(metrics, _warmup_laps(decoded))
