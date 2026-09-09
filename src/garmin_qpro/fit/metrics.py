"""Extract neutral, unformatted metrics from decoded FIT messages."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Any

from .models import DecodedFit


MOVING_SPEED_THRESHOLD_MPS = 0.3


@dataclass(frozen=True, slots=True)
class FitMetrics:
    """Confirmed FIT metrics before any Quattro Pro formatting."""

    moving_time_s: float | None
    distance_m: float | None
    avg_heart_rate: float | None
    max_heart_rate: float | None
    aerobic_te: float | None
    anaerobic_te: float | None
    exercise_load: float | None


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if isfinite(parsed) else None


def _non_negative_number(value: Any) -> float | None:
    parsed = _finite_number(value)
    if parsed is None or parsed < 0:
        return None
    return parsed


def _positive_number(value: Any) -> float | None:
    parsed = _finite_number(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def _select_primary_session(
    decoded: DecodedFit,
) -> Mapping[Any, Any] | None:
    """Apply the project's existing deterministic session ordering."""

    sessions = tuple(
        message
        for message in decoded.get_messages("session")
        if isinstance(message, Mapping)
    )
    if not sessions:
        return None

    indexed_sessions = tuple(
        (order, session, index)
        for order, session in enumerate(sessions)
        if (index := _finite_number(session.get("message_index")))
        is not None
    )
    if indexed_sessions:
        return min(
            indexed_sessions,
            key=lambda item: (item[2], item[0]),
        )[1]
    return sessions[0]


def _timestamp_seconds(value: Any) -> float | None:
    if isinstance(value, datetime):
        try:
            parsed = value.timestamp()
        except (OSError, OverflowError, ValueError):
            return None
        return parsed if isfinite(parsed) else None
    return _finite_number(value)


def _record_speed(record: Mapping[Any, Any]) -> float | None:
    enhanced_speed = _non_negative_number(record.get("enhanced_speed"))
    if enhanced_speed is not None:
        return enhanced_speed
    return _non_negative_number(record.get("speed"))


def _derive_moving_time_from_records(decoded: DecodedFit) -> float | None:
    samples: list[tuple[float, int, float | None]] = []
    for order, record in enumerate(decoded.get_messages("record")):
        if not isinstance(record, Mapping):
            continue
        timestamp = _timestamp_seconds(record.get("timestamp"))
        if timestamp is None:
            continue
        samples.append((timestamp, order, _record_speed(record)))

    if len(samples) < 2:
        return None

    samples.sort(key=lambda sample: (sample[0], sample[1]))
    moving_time_s = 0.0
    valid_interval_seen = False
    for current, following in zip(samples, samples[1:], strict=False):
        interval_s = following[0] - current[0]
        if not isfinite(interval_s) or interval_s <= 0:
            continue
        valid_interval_seen = True
        speed = current[2]
        if speed is not None and speed > MOVING_SPEED_THRESHOLD_MPS:
            moving_time_s += interval_s

    return moving_time_s if valid_interval_seen else None


def extract_fit_metrics(decoded: DecodedFit) -> FitMetrics:
    """Extract confirmed session metrics without formatting or enrichment."""

    if not isinstance(decoded, DecodedFit):
        raise TypeError("decoded must be a DecodedFit")

    session = _select_primary_session(decoded)
    moving_time_s = (
        _positive_number(session.get("total_moving_time"))
        if session is not None
        else None
    )
    if moving_time_s is None:
        moving_time_s = _derive_moving_time_from_records(decoded)

    if session is None:
        return FitMetrics(
            moving_time_s=moving_time_s,
            distance_m=None,
            avg_heart_rate=None,
            max_heart_rate=None,
            aerobic_te=None,
            anaerobic_te=None,
            exercise_load=None,
        )

    return FitMetrics(
        moving_time_s=moving_time_s,
        distance_m=_non_negative_number(session.get("total_distance")),
        avg_heart_rate=_non_negative_number(
            session.get("avg_heart_rate")
        ),
        max_heart_rate=_non_negative_number(
            session.get("max_heart_rate")
        ),
        aerobic_te=_non_negative_number(
            session.get("total_training_effect")
        ),
        anaerobic_te=_non_negative_number(
            session.get("total_anaerobic_training_effect")
        ),
        exercise_load=_non_negative_number(
            session.get("training_load_peak")
        ),
    )
