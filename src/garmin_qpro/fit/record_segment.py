"""Audit the effective record segment of an edited or trimmed FIT activity."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable

from garmin_qpro.fit.models import DecodedFit

BOUNDARY_TOLERANCE_S = 15.0
STALE_MAX_REL_DIFFERENCE = 0.25
STALE_MAX_ABS_DIFFERENCE_MPS = 0.5


@dataclass(frozen=True, slots=True)
class RecordSegmentAudit:
    """Record-backed bounds and maxima for the preserved activity segment."""

    records: tuple[Mapping[Any, Any], ...]
    is_trimmed: bool
    trim_reasons: tuple[str, ...]
    start_timestamp_s: float | None
    end_timestamp_s: float | None
    duration_s: float | None
    distance_m: float | None
    max_speed_mps: float | None
    min_heart_rate_bpm: int | None
    max_heart_rate_bpm: int | None
    min_cadence_raw: float | None
    max_cadence_raw: float | None
    min_power_w: float | None
    max_power_w: float | None


def _finite_float(value: Any) -> float | None:
    if (
        not isinstance(value, (int, float, Decimal))
        or isinstance(value, bool)
    ):
        return None
    parsed = float(value)
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def _timestamp_seconds(value: Any) -> float | None:
    if isinstance(value, datetime):
        try:
            return value.timestamp()
        except (OSError, OverflowError, ValueError):
            return None
    return _finite_float(value)


def _record_speed(record: Mapping[Any, Any]) -> float | None:
    speed = _finite_float(record.get("enhanced_speed"))
    if speed is None:
        speed = _finite_float(record.get("speed"))
    return speed if speed is not None and speed >= 0 else None


def _record_cadence(record: Mapping[Any, Any]) -> float | None:
    cadence = _finite_float(record.get("cadence"))
    if cadence is None or cadence < 0:
        return None
    fractional = _finite_float(record.get("fractional_cadence"))
    return cadence + (fractional or 0.0)


def _numeric_range(
    records: tuple[Mapping[Any, Any], ...],
    extractor: Callable[[Mapping[Any, Any]], float | None],
) -> tuple[float | None, float | None]:
    values = [
        value
        for record in records
        if (value := extractor(record)) is not None and value >= 0
    ]
    if not values:
        return None, None
    return min(values), max(values)


def _message_time(
    message: Mapping[Any, Any] | None,
    field: str,
) -> float | None:
    return (
        _timestamp_seconds(message.get(field))
        if message is not None
        else None
    )


def _valid_messages(
    decoded: DecodedFit,
    message_type: str,
) -> tuple[Mapping[Any, Any], ...]:
    return tuple(
        message
        for message in decoded.get_messages(message_type)
        if isinstance(message, Mapping)
    )


def _boundary_reasons(
    decoded: DecodedFit,
    *,
    record_start: float,
    record_end: float,
    session: Mapping[Any, Any] | None,
) -> list[str]:
    reasons: list[str] = []
    start_candidates = [
        ("session", _message_time(session, "start_time")),
        *(
            ("lap", _message_time(lap, "start_time"))
            for lap in _valid_messages(decoded, "lap")
        ),
    ]
    for source, boundary in start_candidates:
        if (
            boundary is not None
            and record_start - boundary > BOUNDARY_TOLERANCE_S
        ):
            reasons.append(f"record_start_after_{source}_start")

    end_candidates = [
        ("session", _message_time(session, "timestamp")),
        *(
            ("lap", _message_time(lap, "timestamp"))
            for lap in _valid_messages(decoded, "lap")
        ),
        *(
            ("activity", _message_time(activity, "timestamp"))
            for activity in _valid_messages(decoded, "activity")
        ),
    ]
    for source, boundary in end_candidates:
        if boundary is None:
            continue
        if boundary - record_end > BOUNDARY_TOLERANCE_S:
            reasons.append(f"record_end_before_{source}_end")
        elif record_end - boundary > BOUNDARY_TOLERANCE_S:
            reasons.append(f"{source}_end_before_record_end")

    timer_events = tuple(
        event
        for event in _valid_messages(decoded, "event")
        if event.get("event") == "timer"
    )
    start_events = [
        _message_time(event, "timestamp")
        for event in timer_events
        if event.get("event_type") == "start"
    ]
    stop_events = [
        _message_time(event, "timestamp")
        for event in timer_events
        if event.get("event_type") in {"stop", "stop_all"}
    ]
    valid_starts = [value for value in start_events if value is not None]
    valid_stops = [value for value in stop_events if value is not None]
    if (
        valid_starts
        and record_start - min(valid_starts) > BOUNDARY_TOLERANCE_S
    ):
        reasons.append("record_start_after_timer_start")
    if valid_stops:
        final_stop = max(valid_stops)
        if final_stop - record_end > BOUNDARY_TOLERANCE_S:
            reasons.append("record_end_before_timer_stop")
        elif record_end - final_stop > BOUNDARY_TOLERANCE_S:
            reasons.append("timer_stop_before_record_end")
    return reasons


def _summary_speed_is_outside_records(
    session: Mapping[Any, Any] | None,
    record_max_speed: float | None,
) -> bool:
    if session is None or record_max_speed is None:
        return False
    summary_max = _finite_float(session.get("enhanced_max_speed"))
    if summary_max is None:
        summary_max = _finite_float(session.get("max_speed"))
    if summary_max is None or summary_max <= record_max_speed:
        return False
    difference = summary_max - record_max_speed
    return difference > max(
        STALE_MAX_ABS_DIFFERENCE_MPS,
        record_max_speed * STALE_MAX_REL_DIFFERENCE,
    )


def audit_record_segment(
    decoded: DecodedFit,
    *,
    session: Mapping[Any, Any] | None,
) -> RecordSegmentAudit:
    """Identify the record-backed segment and strong evidence of trimming."""

    if not isinstance(decoded, DecodedFit):
        raise TypeError("decoded must be a DecodedFit")
    if session is not None and not isinstance(session, Mapping):
        raise TypeError("session must be a mapping or None")

    timed_records = []
    for order, record in enumerate(decoded.get_messages("record")):
        if not isinstance(record, Mapping):
            continue
        timestamp = _timestamp_seconds(record.get("timestamp"))
        if timestamp is None:
            continue
        timed_records.append((timestamp, order, record))
    timed_records.sort(key=lambda item: (item[0], item[1]))
    records = tuple(item[2] for item in timed_records)

    if not timed_records:
        return RecordSegmentAudit(
            records=(),
            is_trimmed=False,
            trim_reasons=(),
            start_timestamp_s=None,
            end_timestamp_s=None,
            duration_s=None,
            distance_m=None,
            max_speed_mps=None,
            min_heart_rate_bpm=None,
            max_heart_rate_bpm=None,
            min_cadence_raw=None,
            max_cadence_raw=None,
            min_power_w=None,
            max_power_w=None,
        )

    record_start = timed_records[0][0]
    record_end = timed_records[-1][0]
    first_distance = _finite_float(records[0].get("distance"))
    last_distance = _finite_float(records[-1].get("distance"))
    distance = (
        last_distance - first_distance
        if (
            first_distance is not None
            and last_distance is not None
            and last_distance >= first_distance
        )
        else None
    )

    _, max_speed = _numeric_range(records, _record_speed)
    min_hr, max_hr = _numeric_range(
        records,
        lambda record: _finite_float(record.get("heart_rate")),
    )
    min_cadence, max_cadence = _numeric_range(records, _record_cadence)
    min_power, max_power = _numeric_range(
        records,
        lambda record: _finite_float(record.get("power")),
    )

    boundary_reasons = _boundary_reasons(
        decoded,
        record_start=record_start,
        record_end=record_end,
        session=session,
    )
    reasons = list(boundary_reasons)
    if _summary_speed_is_outside_records(session, max_speed):
        reasons.append("summary_speed_max_outside_records")
    unique_reasons = tuple(dict.fromkeys(reasons))

    return RecordSegmentAudit(
        records=records,
        # A summary maximum absent from records is supporting evidence, but is
        # not enough by itself to declare an edit. A record/message boundary
        # mismatch provides the independent evidence required here.
        is_trimmed=bool(boundary_reasons),
        trim_reasons=unique_reasons,
        start_timestamp_s=record_start,
        end_timestamp_s=record_end,
        duration_s=record_end - record_start,
        distance_m=distance,
        max_speed_mps=max_speed,
        min_heart_rate_bpm=int(min_hr) if min_hr is not None else None,
        max_heart_rate_bpm=int(max_hr) if max_hr is not None else None,
        min_cadence_raw=min_cadence,
        max_cadence_raw=max_cadence,
        min_power_w=min_power,
        max_power_w=max_power,
    )
