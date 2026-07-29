from datetime import datetime, timedelta, timezone

import pytest

from garmin_qpro.fit.speed_filter import (
    SOFT_SPEED_FILTER_KEYS,
    filter_soft_activity_max_speed,
)


def _records(
    speeds: list[float],
    *,
    gaps: list[float] | None = None,
    interval_rates: list[float] | None = None,
):
    if gaps is None:
        gaps = [5.0] * (len(speeds) - 1)
    if interval_rates is None:
        interval_rates = [1.0] * (len(speeds) - 1)
    assert len(gaps) == len(speeds) - 1
    assert len(interval_rates) == len(speeds) - 1

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    elapsed = 0.0
    distance = 0.0
    records = [
        {
            "timestamp": start,
            "enhanced_speed": speeds[0],
            "distance": distance,
        }
    ]
    for index, gap in enumerate(gaps):
        elapsed += gap
        distance += interval_rates[index] * gap
        records.append(
            {
                "timestamp": start + timedelta(seconds=elapsed),
                "enhanced_speed": speeds[index + 1],
                "distance": distance,
            }
        )
    return records


def test_authorized_key_set_is_exact() -> None:
    assert SOFT_SPEED_FILTER_KEYS == {
        "AQG",
        "CAM",
        "CAL",
        "CLP",
        "FIN",
        "FPN",
        "MOV",
        "PLY",
    }


def test_isolated_peak_is_discarded_for_a_record_backed_maximum() -> None:
    records = _records([1.0, 5.0, 1.1, 1.0, 1.0])

    result = filter_soft_activity_max_speed(
        records,
        original_max_speed_mps=5.0,
        average_speed_mps=1.0,
    )

    assert result.max_speed_mps == 1.1
    assert result.max_speed_mps in {
        record["enhanced_speed"] for record in records
    }
    assert result.discarded_speeds_mps == (5.0,)
    assert result.requires_manual_review is False


def test_sustained_high_speed_with_spatial_continuity_is_kept() -> None:
    records = _records(
        [1.0, 5.0, 5.2, 5.1, 1.0],
        interval_rates=[5.0, 5.2, 5.1, 1.0],
    )

    result = filter_soft_activity_max_speed(
        records,
        original_max_speed_mps=5.2,
        average_speed_mps=1.0,
    )

    assert result.max_speed_mps == 5.2
    assert result.discarded_speeds_mps == ()
    assert result.requires_manual_review is False


def test_summary_maximum_absent_from_records_uses_record_maximum_first() -> None:
    records = _records([1.0, 5.0, 1.1, 1.0, 1.0])

    result = filter_soft_activity_max_speed(
        records,
        original_max_speed_mps=9.0,
        average_speed_mps=1.0,
    )

    assert result.max_speed_mps == 1.1
    assert result.discarded_speeds_mps == (5.0,)
    assert result.requires_manual_review is False


def test_unconfirmed_summary_does_not_replace_sustained_record_maximum() -> None:
    records = _records(
        [1.0, 5.0, 5.2, 5.1, 1.0],
        interval_rates=[5.0, 5.2, 5.1, 1.0],
    )

    result = filter_soft_activity_max_speed(
        records,
        original_max_speed_mps=9.0,
        average_speed_mps=1.0,
    )

    assert result.max_speed_mps == 5.2
    assert result.discarded_speeds_mps == ()
    assert result.requires_manual_review is False


def test_irregular_smart_recording_gaps_are_supported() -> None:
    records = _records(
        [1.0, 5.0, 1.1, 1.0, 1.0],
        gaps=[7.0, 9.0, 5.0, 10.0],
    )

    result = filter_soft_activity_max_speed(
        records,
        original_max_speed_mps=5.0,
        average_speed_mps=1.0,
    )

    assert result.max_speed_mps == 1.1
    assert result.requires_manual_review is False


def test_maximum_without_sufficient_neighbors_is_kept_for_review() -> None:
    records = _records([5.0, 1.0])

    result = filter_soft_activity_max_speed(
        records,
        original_max_speed_mps=5.0,
        average_speed_mps=1.0,
    )

    assert result.max_speed_mps == 5.0
    assert result.discarded_speeds_mps == ()
    assert result.requires_manual_review is True


def test_unconfirmed_summary_with_insufficient_records_is_kept_for_review() -> None:
    records = _records([1.0, 5.0])

    result = filter_soft_activity_max_speed(
        records,
        original_max_speed_mps=9.0,
        average_speed_mps=1.0,
    )

    assert result.max_speed_mps == 9.0
    assert result.discarded_speeds_mps == ()
    assert result.requires_manual_review is True


@pytest.mark.parametrize(
    ("original_max", "average_speed"),
    [(None, 1.0), (5.0, None), (5.0, 0.0)],
)
def test_missing_summary_evidence_preserves_original_for_review(
    original_max,
    average_speed,
) -> None:
    result = filter_soft_activity_max_speed(
        (),
        original_max_speed_mps=original_max,
        average_speed_mps=average_speed,
    )

    assert result.max_speed_mps == original_max
    assert result.requires_manual_review is True


def test_non_suspicious_record_backed_maximum_is_kept() -> None:
    result = filter_soft_activity_max_speed(
        _records([1.0, 2.5, 5.0], interval_rates=[2.5, 5.0]),
        original_max_speed_mps=5.0,
        average_speed_mps=2.0,
    )

    assert result.max_speed_mps == 5.0
    assert result.requires_manual_review is False
