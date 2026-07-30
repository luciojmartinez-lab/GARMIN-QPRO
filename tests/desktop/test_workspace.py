from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from garmin_qpro.desktop.workspace import (
    DesktopWorkspace,
    OriginalSourceRequiredError,
    RemoteActivityStatus,
)
from garmin_qpro.fit.activity_metadata import ActivityContext, ActivityMetadata
from garmin_qpro.garmin.models import (
    GarminActivityDownload,
    GarminActivitySummary,
)
from garmin_qpro.history import (
    ConversionDraft,
    HistoryRepository,
    HistoryStatus,
)
from garmin_qpro.input import FitSource
from garmin_qpro.mapping.activity_resolution import ActivityResolution


def _source(name: str = "activity.fit") -> FitSource:
    return FitSource(
        source_name=name,
        container_name="activity.zip",
        member_path=name,
        data=b"fit-data",
    )


def _summary(activity_id: str, name: str = "Carrera") -> GarminActivitySummary:
    return GarminActivitySummary(
        activity_id=activity_id,
        name=name,
        activity_type="running",
        start_time_local="2026-07-30T08:00:00",
        duration_s=60.0,
        elapsed_duration_s=60.0,
        distance_m=100.0,
    )


def _download(activity_id: str) -> GarminActivityDownload:
    source = _source(f"{activity_id}.fit")
    return GarminActivityDownload(
        activity_id=activity_id,
        container_name=f"garmin-{activity_id}.zip",
        archive_sha256="b" * 64,
        archive_size=100,
        sources=(source,),
    )


def _context(key: str | None = "ENT") -> ActivityContext:
    return ActivityContext(
        metadata=ActivityMetadata(
            workout_name="EB1 - Carrera - 1" if key else None,
            workout_name_field="workout.workout_name" if key else None,
            sport_profile_name="Carrera",
            sport="running",
            sub_sport="generic",
        ),
        resolution=ActivityResolution(
            workout_name="EB1 - Carrera - 1" if key else None,
            sport_profile_name="Carrera",
            qpro_key=key,
            resolution_source="workout_name" if key else None,
            requires_user_choice=key is None,
        ),
    )


def _tsv(key: str = "ENT") -> str:
    return "\t".join((key, *("0" for _ in range(22))))


def _result(source: FitSource, key: str = "ENT") -> object:
    return SimpleNamespace(
        source_name=source.source_name,
        sha256=source.sha256,
        activity_context=_context(key),
        metrics=SimpleNamespace(
            review_reasons=(),
            trim_reasons=(),
        ),
        decoder_errors=(),
        tsv=_tsv(key),
    )


class FakeReader:
    def __init__(self, summaries, *, failures=()) -> None:
        self.summaries = tuple(summaries)
        self.failures = set(failures)
        self.download_calls: list[str] = []

    def list_activities(self, *, start: int, limit: int):
        return self.summaries[:limit]

    def download_original_activity(self, activity_id: str):
        self.download_calls.append(activity_id)
        if activity_id in self.failures:
            raise ConnectionError("private-token")
        return _download(activity_id)


class FakeGarminSession:
    def __init__(self, reader: FakeReader, *, connected: bool = True) -> None:
        self.reader = reader
        self.connected = connected
        self.email = "user@example.com" if connected else None

    def restore(self) -> bool:
        return self.connected

    def connect(self, **kwargs):
        self.connected = True

    def disconnect(self):
        self.connected = False


def _workspace(tmp_path, reader: FakeReader) -> DesktopWorkspace:
    return DesktopWorkspace(
        history=HistoryRepository(tmp_path / "history.db"),
        garmin=FakeGarminSession(reader),
    )


def test_refresh_skips_converted_garmin_activities(monkeypatch, tmp_path) -> None:
    reader = FakeReader((_summary("1"), _summary("2")))
    workspace = _workspace(tmp_path, reader)
    workspace.history.save(
        ConversionDraft(
            garmin_activity_id="1",
            source_sha256="a" * 64,
            activity_datetime=None,
            workout_name="Old",
            profile_name="Carrera",
            qpro_key="ENT",
            tsv=_tsv(),
            source_type="garmin",
        )
    )
    monkeypatch.setattr(
        workspace,
        "_inspect_remote",
        lambda summary, download: SimpleNamespace(activity_id=summary.activity_id),
    )

    activities = workspace.refresh_remote_activities()

    assert tuple(item.activity_id for item in activities) == ("2",)
    assert reader.download_calls == ["2"]


def test_partial_download_error_does_not_hide_other_activities(
    monkeypatch,
    tmp_path,
) -> None:
    reader = FakeReader((_summary("1"), _summary("2")), failures=("1",))
    workspace = _workspace(tmp_path, reader)
    monkeypatch.setattr(
        workspace,
        "_inspect_remote",
        lambda summary, download: SimpleNamespace(
            activity_id=summary.activity_id,
            status=RemoteActivityStatus.READY,
        ),
    )

    activities = workspace.refresh_remote_activities()

    assert activities[0].status is RemoteActivityStatus.ERROR
    assert activities[1].status is RemoteActivityStatus.READY
    assert "private-token" not in activities[0].warning


def test_refresh_detects_key_from_decoded_fit(monkeypatch, tmp_path) -> None:
    reader = FakeReader((_summary("1"),))
    workspace = _workspace(tmp_path, reader)
    monkeypatch.setattr(
        "garmin_qpro.desktop.workspace.decode_fit",
        lambda source: SimpleNamespace(errors=()),
    )
    monkeypatch.setattr(
        "garmin_qpro.desktop.workspace.resolve_decoded_activity",
        lambda decoded: _context("ENT"),
    )

    activity = workspace.refresh_remote_activities()[0]

    assert activity.qpro_key == "ENT"
    assert activity.resolution_source == "workout_name"
    assert activity.status is RemoteActivityStatus.READY


def test_remote_conversion_uses_engine_and_saves_history(
    monkeypatch,
    tmp_path,
) -> None:
    reader = FakeReader((_summary("1"),))
    workspace = _workspace(tmp_path, reader)
    monkeypatch.setattr(
        "garmin_qpro.desktop.workspace.decode_fit",
        lambda source: SimpleNamespace(errors=()),
    )
    monkeypatch.setattr(
        "garmin_qpro.desktop.workspace.resolve_decoded_activity",
        lambda decoded: _context("ENT"),
    )
    workspace.refresh_remote_activities()
    monkeypatch.setattr(
        "garmin_qpro.desktop.workspace.convert_fit_source",
        lambda source, explicit_qpro_key=None: _result(source),
    )

    converted = workspace.convert_remote(("1",))

    assert converted[0].status is RemoteActivityStatus.CONVERTED
    assert converted[0].tsv == _tsv()
    assert workspace.history.count() == 1
    assert workspace.history.list()[0].garmin_activity_id == "1"


def test_manual_remote_key_is_forwarded_to_engine(monkeypatch, tmp_path) -> None:
    reader = FakeReader((_summary("1"),))
    workspace = _workspace(tmp_path, reader)
    monkeypatch.setattr(
        "garmin_qpro.desktop.workspace.decode_fit",
        lambda source: SimpleNamespace(errors=()),
    )
    monkeypatch.setattr(
        "garmin_qpro.desktop.workspace.resolve_decoded_activity",
        lambda decoded: _context(None),
    )
    workspace.refresh_remote_activities()
    workspace.set_remote_key("1", "CMP")
    observed = {}

    def convert(source, explicit_qpro_key=None):
        observed["key"] = explicit_qpro_key
        return _result(source, "CMP")

    monkeypatch.setattr(
        "garmin_qpro.desktop.workspace.convert_fit_source",
        convert,
    )

    workspace.convert_remote(("1",))

    assert observed["key"] == "CMP"
    assert workspace.history.list()[0].manual_key is True


def test_history_remains_available_when_garmin_is_offline(tmp_path) -> None:
    reader = FakeReader(())
    workspace = _workspace(tmp_path, reader)
    workspace.history.save(
        ConversionDraft(
            garmin_activity_id=None,
            source_sha256="a" * 64,
            activity_datetime=None,
            workout_name="Local",
            profile_name=None,
            qpro_key="ENT",
            tsv=_tsv(),
            source_type="fit",
        )
    )
    reader.list_activities = lambda **kwargs: (_ for _ in ()).throw(
        ConnectionError("offline")
    )

    with pytest.raises(ConnectionError):
        workspace.refresh_remote_activities()

    assert len(workspace.history_items()) == 1


def test_manual_history_requires_original_source_for_reconversion(tmp_path) -> None:
    workspace = _workspace(tmp_path, FakeReader(()))
    saved = workspace.history.save(
        ConversionDraft(
            garmin_activity_id=None,
            source_sha256="a" * 64,
            activity_datetime=None,
            workout_name="Local",
            profile_name=None,
            qpro_key="ENT",
            tsv=_tsv(),
            source_type="fit",
        )
    )

    with pytest.raises(OriginalSourceRequiredError):
        workspace.reconvert_history(saved.id)


def test_status_changes_and_manual_delete_are_delegated(tmp_path) -> None:
    workspace = _workspace(tmp_path, FakeReader(()))
    saved = workspace.history.save(
        ConversionDraft(
            garmin_activity_id=None,
            source_sha256="a" * 64,
            activity_datetime=None,
            workout_name="Local",
            profile_name=None,
            qpro_key="ENT",
            tsv=_tsv(),
            source_type="fit",
        )
    )

    updated = workspace.set_history_status(saved.id, HistoryStatus.REVIEWED)
    workspace.delete_history(saved.id)

    assert updated.status is HistoryStatus.REVIEWED
    assert workspace.history.count() == 0
