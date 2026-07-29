from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from garmin_qpro.fit.models import DecodedFit
from garmin_qpro.fit.record_segment import audit_record_segment
from garmin_qpro.input.sources import FitSource


def _decoded(messages) -> DecodedFit:
    return DecodedFit(
        source=FitSource("activity.fit", None, None, b"fit"),
        messages=messages,
        errors=(),
        crc_checked=True,
    )


def _records(start: datetime, offsets: tuple[int, ...]):
    return [
        {
            "timestamp": start + timedelta(seconds=offset),
            "distance": float(offset),
            "enhanced_speed": 1.0 + index,
            "heart_rate": 90 + index,
            "cadence": 60 + index,
            "fractional_cadence": 0.25,
            "power": 100 + index * 10,
        }
        for index, offset in enumerate(offsets)
    ]


def test_final_trim_is_detected_from_record_end_boundary() -> None:
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    session = {
        "start_time": start,
        "timestamp": start + timedelta(seconds=100),
        "enhanced_max_speed": 9.0,
    }

    audit = audit_record_segment(
        _decoded(
            {
                "session": [session],
                "record": _records(start, (0, 25, 50)),
            }
        ),
        session=session,
    )

    assert audit.is_trimmed is True
    assert "record_end_before_session_end" in audit.trim_reasons
    assert "summary_speed_max_outside_records" in audit.trim_reasons
    assert audit.duration_s == 50.0


def test_initial_trim_is_detected_from_record_start_boundary() -> None:
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    session = {
        "start_time": start,
        "timestamp": start + timedelta(seconds=100),
        "enhanced_max_speed": 3.0,
    }

    audit = audit_record_segment(
        _decoded(
            {
                "session": [session],
                "record": _records(start, (20, 60, 100)),
            }
        ),
        session=session,
    )

    assert audit.is_trimmed is True
    assert "record_start_after_session_start" in audit.trim_reasons
    assert audit.start_timestamp_s == pytest.approx(start.timestamp() + 20)


def test_absent_summary_max_is_recorded_but_not_enough_alone_for_trim() -> None:
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    session = {"enhanced_max_speed": 9.0}

    audit = audit_record_segment(
        _decoded(
            {
                "session": [session],
                "record": _records(start, (0, 1, 2)),
            }
        ),
        session=session,
    )

    assert audit.is_trimmed is False
    assert audit.trim_reasons == ("summary_speed_max_outside_records",)


def test_complete_activity_keeps_matching_summary_maximum() -> None:
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    session = {
        "start_time": start,
        "timestamp": start + timedelta(seconds=100),
        "enhanced_max_speed": 3.0,
    }

    audit = audit_record_segment(
        _decoded(
            {
                "session": [session],
                "record": _records(start, (0, 50, 100)),
            }
        ),
        session=session,
    )

    assert audit.is_trimmed is False
    assert audit.trim_reasons == ()
    assert audit.max_speed_mps == 3.0


def test_record_backed_maxima_are_audited_and_model_is_immutable() -> None:
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    session = {
        "start_time": start,
        "timestamp": start + timedelta(seconds=100),
    }
    audit = audit_record_segment(
        _decoded(
            {
                "session": [session],
                "record": _records(start, (20, 60, 100)),
            }
        ),
        session=session,
    )

    assert audit.max_heart_rate_bpm == 92
    assert audit.max_cadence_raw == 62.25
    assert audit.max_power_w == 120.0
    with pytest.raises((FrozenInstanceError, AttributeError)):
        audit.is_trimmed = False  # type: ignore[misc]


def test_non_decoded_input_is_rejected() -> None:
    with pytest.raises(TypeError):
        audit_record_segment(object(), session=None)  # type: ignore[arg-type]
