from dataclasses import FrozenInstanceError

import pytest

from garmin_qpro.garmin.models import (
    GarminActivityDownload,
    GarminActivitySummary,
    normalize_activity_id,
)
from garmin_qpro.input import FitSource


def _summary_mapping(**overrides):
    values = {
        "activityId": 123456,
        "activityName": "Morning Run",
        "activityType": {"typeKey": "running"},
        "startTimeLocal": "2026-07-28 08:00:00",
        "duration": 120.5,
        "elapsedDuration": 130,
        "distance": 400.25,
        "latitude": 41.0,
        "longitude": 2.0,
        "description": "private",
        "token": "secret",
    }
    values.update(overrides)
    return values


def test_summary_extracts_only_seven_expected_fields() -> None:
    summary = GarminActivitySummary.from_mapping(_summary_mapping())

    assert summary == GarminActivitySummary(
        activity_id="123456",
        name="Morning Run",
        activity_type="running",
        start_time_local="2026-07-28 08:00:00",
        duration_s=120.5,
        elapsed_duration_s=130.0,
        distance_m=400.25,
    )
    representation = repr(summary)
    assert "latitude" not in representation
    assert "longitude" not in representation
    assert "private" not in representation
    assert "secret" not in representation


def test_summary_optional_fields_can_be_missing() -> None:
    summary = GarminActivitySummary.from_mapping({"activityId": "99"})

    assert summary.name == ""
    assert summary.activity_type is None
    assert summary.start_time_local is None
    assert summary.duration_s is None
    assert summary.elapsed_duration_s is None
    assert summary.distance_m is None


def test_summary_is_immutable() -> None:
    summary = GarminActivitySummary.from_mapping(_summary_mapping())

    with pytest.raises(FrozenInstanceError):
        summary.name = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("value", "expected"),
    [(123, "123"), (" 456 ", "456"), ("0", "0")],
)
def test_activity_id_normalization(value, expected: str) -> None:
    assert normalize_activity_id(value) == expected


@pytest.mark.parametrize("value", ["", "  ", "12a", "-1", "1.5"])
def test_invalid_activity_id_text_is_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_activity_id(value)


@pytest.mark.parametrize("value", [True, False, 1.0, None, object()])
def test_invalid_activity_id_types_are_rejected(value) -> None:
    with pytest.raises(TypeError):
        normalize_activity_id(value)


@pytest.mark.parametrize(
    "field_name",
    ["duration", "elapsedDuration", "distance"],
)
def test_summary_rejects_boolean_metrics(field_name: str) -> None:
    with pytest.raises(TypeError):
        GarminActivitySummary.from_mapping(
            _summary_mapping(**{field_name: True})
        )


def test_summary_rejects_non_mapping_activity_type() -> None:
    with pytest.raises(TypeError):
        GarminActivitySummary.from_mapping(
            _summary_mapping(activityType="running")
        )


def test_download_is_immutable_and_freezes_sources() -> None:
    source = FitSource("one.fit", "garmin-1.zip", "one.fit", b"fit")
    download = GarminActivityDownload(
        activity_id="1",
        container_name="garmin-1.zip",
        archive_sha256="abc",
        archive_size=10,
        sources=[source],  # type: ignore[arg-type]
    )

    assert download.sources == (source,)
    with pytest.raises(FrozenInstanceError):
        download.archive_size = 0  # type: ignore[misc]


def test_download_representation_has_no_archive_bytes() -> None:
    source = FitSource("one.fit", "garmin-1.zip", "one.fit", b"secret-fit")
    download = GarminActivityDownload(
        activity_id="1",
        container_name="garmin-1.zip",
        archive_sha256="abc",
        archive_size=10,
        sources=(source,),
    )

    assert "secret-fit" not in repr(download)


@pytest.mark.parametrize("archive_size", [True, -1, 1.5])
def test_download_rejects_invalid_archive_size(archive_size) -> None:
    expected = TypeError if archive_size is True or archive_size == 1.5 else ValueError
    with pytest.raises(expected):
        GarminActivityDownload(
            activity_id="1",
            container_name="garmin-1.zip",
            archive_sha256="abc",
            archive_size=archive_size,
            sources=(),
        )
