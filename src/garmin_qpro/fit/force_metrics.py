"""Extract raw force metrics from decoded FIT session messages."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from garmin_qpro.fit.models import DecodedFit


@dataclass(frozen=True, slots=True)
class ForceMetricsRaw:
    """Raw FIT values used by the approved Quattro Pro force template."""

    timer_time_s: float | None
    elapsed_time_s: float | None
    avg_hr_bpm: int | None
    max_hr_bpm: int | None
    aerobic_te: float | None
    anaerobic_te: float | None
    exercise_load: float | None


def _finite_number(value: Any) -> float | None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float, Decimal))
    ):
        return None
    parsed = float(value)
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def _non_negative_float(value: Any) -> float | None:
    parsed = _finite_number(value)
    if parsed is None or parsed < 0:
        return None
    return parsed


def _non_negative_int(value: Any) -> int | None:
    parsed = _non_negative_float(value)
    if parsed is None:
        return None
    return int(parsed)


def _numeric_message_index(message: Mapping[Any, Any]) -> float | None:
    return _finite_number(message.get("message_index"))


def _select_session(decoded: DecodedFit) -> Mapping[Any, Any] | None:
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
        if (index := _numeric_message_index(session)) is not None
    )
    if indexed_sessions:
        return min(
            indexed_sessions,
            key=lambda item: (item[2], item[0]),
        )[1]
    return sessions[0]


def extract_force_metrics(decoded: DecodedFit) -> ForceMetricsRaw:
    """Extract only confirmed force metrics from one deterministic session."""

    if not isinstance(decoded, DecodedFit):
        raise TypeError("decoded must be a DecodedFit")

    session = _select_session(decoded)
    if session is None:
        return ForceMetricsRaw(
            timer_time_s=None,
            elapsed_time_s=None,
            avg_hr_bpm=None,
            max_hr_bpm=None,
            aerobic_te=None,
            anaerobic_te=None,
            exercise_load=None,
        )

    return ForceMetricsRaw(
        timer_time_s=_non_negative_float(session.get("total_timer_time")),
        elapsed_time_s=_non_negative_float(
            session.get("total_elapsed_time")
        ),
        avg_hr_bpm=_non_negative_int(session.get("avg_heart_rate")),
        max_hr_bpm=_non_negative_int(session.get("max_heart_rate")),
        aerobic_te=_non_negative_float(
            session.get("total_training_effect")
        ),
        anaerobic_te=_non_negative_float(
            session.get("total_anaerobic_training_effect")
        ),
        exercise_load=_non_negative_float(
            session.get("training_load_peak")
        ),
    )
