from pathlib import Path

import pytest

from garmin_qpro.conversion import convert_decoded_activity
from garmin_qpro.fit.models import DecodedFit
from garmin_qpro.garmin import (
    GarminActivityDownload,
    GarminActivitySummary,
    GarminAuthenticationError,
)
from garmin_qpro.input import FitSource
from garmin_qpro.mcp_server import TOKEN_REFRESH_COMMAND
from garmin_qpro.mcp_server import service as service_module
from garmin_qpro.mcp_server.service import GarminQProMcpService


class FakeReader:
    def __init__(self, *, activities=(), downloads=None):
        self.activities = tuple(activities)
        self.downloads = downloads or {}
        self.list_calls = []
        self.download_calls = []

    def list_activities(self, *, start=0, limit=20):
        self.list_calls.append((start, limit))
        return self.activities

    def download_original_activity(self, activity_id):
        self.download_calls.append(activity_id)
        return self.downloads[activity_id]


def _source(
    name: str,
    *,
    data: bytes | None = None,
    member: str | None = None,
) -> FitSource:
    return FitSource(
        source_name=name,
        container_name="garmin-1.zip",
        member_path=member or name,
        data=data if data is not None else name.encode("ascii"),
    )


def _download(activity_id: str, *sources: FitSource):
    return GarminActivityDownload(
        activity_id=activity_id,
        container_name=f"garmin-{activity_id}.zip",
        archive_sha256=activity_id.zfill(64),
        archive_size=100 + len(sources),
        sources=sources,
    )


def _running_decoded(
    source: FitSource,
    *,
    workout_name: str | None = "EB1 - Carrera - 1",
    profile: str = "Carrera",
    cal: bool = False,
) -> DecodedFit:
    messages = {
        "session": [
            {
                "message_index": 0,
                "sport_profile_name": profile,
                "sport": "running",
                "sub_sport": "generic",
                "total_timer_time": 100.0,
                "total_moving_time": 80.0,
                "total_distance": 200.0,
                "enhanced_avg_speed": 2.0,
                "enhanced_max_speed": 4.0,
                "avg_heart_rate": 100,
                "max_heart_rate": 120,
                "total_training_effect": 0.5,
                "total_anaerobic_training_effect": 0.0,
                "avg_cadence": 60,
                "max_cadence": 80,
                "avg_step_length": 700.0,
                "avg_stance_time": 300.0,
                "training_load_peak": 5.0,
                "avg_power": 100,
                "max_power": 200,
                "avg_vertical_ratio": 10.0,
                "avg_vertical_oscillation": 70.0,
            }
        ]
    }
    if workout_name is not None:
        messages["workout"] = [{"wkt_name": workout_name}]
    if cal:
        messages["lap"] = [
            {
                "intensity": "warmup",
                "total_timer_time": 10.0,
                "avg_cadence": 70,
                "max_cadence": 80,
                "avg_step_length": 750.0,
                "avg_stance_time": 250.0,
                "avg_power": 150,
                "max_power": 250,
                "avg_vertical_ratio": 9.0,
                "avg_vertical_oscillation": 65.0,
            }
        ]
    return DecodedFit(
        source=source,
        messages=messages,
        errors=(),
        crc_checked=True,
    )


def _force_decoded(
    source: FitSource,
    *,
    workout_name: str | None = "EB9 - Salto de altura - Competic",
) -> DecodedFit:
    messages = {
        "session": [
            {
                "message_index": 0,
                "sport_profile_name": "Fuerza",
                "sport": "training",
                "sub_sport": "strength_training",
                "total_timer_time": 1663.291,
                "total_elapsed_time": 1701.977,
                "avg_heart_rate": 121,
                "max_heart_rate": 146,
                "total_training_effect": 3.0,
                "total_anaerobic_training_effect": 2.3,
                "training_load_peak": 93.91545104980469,
            }
        ]
    }
    if workout_name is not None:
        messages["workout"] = [{"wkt_name": workout_name}]
    return DecodedFit(
        source=source,
        messages=messages,
        errors=(),
        crc_checked=True,
    )


def test_service_does_not_connect_during_construction() -> None:
    calls = []

    GarminQProMcpService(reader_factory=lambda path: calls.append(path))

    assert calls == []


def test_reader_is_created_lazily_and_reused() -> None:
    reader = FakeReader()
    calls = []

    def factory(path):
        calls.append(path)
        return reader

    service = GarminQProMcpService(
        token_store=Path("tokens"),
        reader_factory=factory,
    )
    service.list_garmin_activities()
    service.list_garmin_activities()

    assert calls == [Path("tokens")]
    assert reader.list_calls == [(0, 10), (0, 10)]


def test_authentication_error_names_local_refresh_command() -> None:
    def factory(path):
        raise GarminAuthenticationError("external details")

    service = GarminQProMcpService(reader_factory=factory)

    with pytest.raises(GarminAuthenticationError) as exc_info:
        service.list_garmin_activities()

    assert TOKEN_REFRESH_COMMAND in str(exc_info.value)
    assert "external details" not in str(exc_info.value)


def test_list_returns_only_authorized_summary_fields_in_order() -> None:
    first = GarminActivitySummary("2", "Two", "running", None, 2, 3, 4)
    second = GarminActivitySummary("1", "One", None, None, None, None, None)
    reader = FakeReader(activities=(first, second))
    service = GarminQProMcpService(reader=reader)

    payload = service.list_garmin_activities(start=5, limit=7)

    assert tuple(item["activity_id"] for item in payload["activities"]) == (
        "2",
        "1",
    )
    assert set(payload["activities"][0]) == {
        "activity_id",
        "name",
        "activity_type",
        "start_time_local",
        "duration_s",
        "elapsed_duration_s",
        "distance_m",
    }
    assert payload["count"] == 2
    assert payload["start"] == 5
    assert payload["limit"] == 7
    assert reader.download_calls == []


@pytest.mark.parametrize("start", [True, -1, 1.5, "0"])
def test_invalid_start_is_rejected_before_connection(start) -> None:
    calls = []
    service = GarminQProMcpService(
        reader_factory=lambda path: calls.append(path)
    )

    with pytest.raises((TypeError, ValueError)):
        service.list_garmin_activities(start=start)

    assert calls == []


@pytest.mark.parametrize("limit", [True, 0, -1, 51, 1.5, "10"])
def test_invalid_limit_is_rejected_before_connection(limit) -> None:
    calls = []
    service = GarminQProMcpService(
        reader_factory=lambda path: calls.append(path)
    )

    with pytest.raises((TypeError, ValueError)):
        service.list_garmin_activities(limit=limit)

    assert calls == []


@pytest.mark.parametrize("limit", [1, 50])
def test_list_accepts_limit_boundaries(limit: int) -> None:
    reader = FakeReader()
    service = GarminQProMcpService(reader=reader)

    payload = service.list_garmin_activities(limit=limit)

    assert payload["limit"] == limit
    assert reader.list_calls == [(0, limit)]


@pytest.mark.parametrize("activity_id", [True, "", "abc", 1.5, None])
def test_invalid_inspection_id_is_rejected_before_connection(activity_id) -> None:
    calls = []
    service = GarminQProMcpService(
        reader_factory=lambda path: calls.append(path)
    )

    with pytest.raises((TypeError, ValueError)):
        service.inspect_garmin_activity(activity_id=activity_id)

    assert calls == []


@pytest.mark.parametrize("verify_crc", [0, 1, "yes", None])
def test_invalid_inspection_crc_is_rejected_before_connection(
    verify_crc,
) -> None:
    calls = []
    service = GarminQProMcpService(
        reader_factory=lambda path: calls.append(path)
    )

    with pytest.raises(TypeError):
        service.inspect_garmin_activity(
            activity_id="1",
            verify_crc=verify_crc,
        )

    assert calls == []


def test_inspection_returns_only_safe_metadata_for_multiple_fits(
    monkeypatch,
) -> None:
    first = _source("first.fit")
    second = _source("second.fit")
    download = _download("1", first, second)
    reader = FakeReader(downloads={"1": download})
    decoded_by_source = {
        first.source_name: _running_decoded(first),
        second.source_name: _running_decoded(
            second,
            workout_name=None,
        ),
    }
    observed_crc = []

    def fake_decode(source, *, verify_crc=True):
        observed_crc.append((source.source_name, verify_crc))
        return decoded_by_source[source.source_name]

    monkeypatch.setattr(service_module, "decode_fit", fake_decode)
    payload = GarminQProMcpService(reader=reader).inspect_garmin_activity(
        activity_id="1",
        verify_crc=False,
    )

    assert payload["fit_count"] == 2
    assert tuple(item["source_name"] for item in payload["sources"]) == (
        "first.fit",
        "second.fit",
    )
    assert tuple(item["qpro_key"] for item in payload["sources"]) == (
        "ENT",
        "ENT",
    )
    assert observed_crc == [
        ("first.fit", False),
        ("second.fit", False),
    ]
    forbidden = {
        "data",
        "messages",
        "record",
        "latitude",
        "longitude",
        "decoded",
    }
    representation = repr(payload).casefold()
    assert all(term not in representation for term in forbidden)


def test_inspection_preserves_duplicate_hashes(monkeypatch) -> None:
    first = _source("a.fit", data=b"same")
    second = _source("b.fit", data=b"same")
    reader = FakeReader(downloads={"1": _download("1", first, second)})
    monkeypatch.setattr(
        service_module,
        "decode_fit",
        lambda source, verify_crc=True: _running_decoded(source),
    )

    payload = GarminQProMcpService(reader=reader).inspect_garmin_activity(
        activity_id="1"
    )

    assert len(payload["sources"]) == 2
    assert payload["sources"][0]["sha256"] == payload["sources"][1]["sha256"]


def test_unknown_force_requires_choice_during_inspection(monkeypatch) -> None:
    source = _source("force.fit")
    reader = FakeReader(downloads={"1": _download("1", source)})
    monkeypatch.setattr(
        service_module,
        "decode_fit",
        lambda fit_source, verify_crc=True: _force_decoded(
            fit_source,
            workout_name=None,
        ),
    )

    item = GarminQProMcpService(reader=reader).inspect_garmin_activity(
        activity_id="1"
    )["sources"][0]

    assert item["qpro_key"] is None
    assert item["requires_user_choice"] is True


def test_download_cache_is_reused_between_inspection_and_conversion(
    monkeypatch,
) -> None:
    source = _source("one.fit")
    reader = FakeReader(downloads={"1": _download("1", source)})
    decoded = _running_decoded(source)
    monkeypatch.setattr(
        service_module,
        "decode_fit",
        lambda fit_source, verify_crc=True: decoded,
    )
    monkeypatch.setattr(
        service_module,
        "convert_fit_source",
        lambda fit_source, **kwargs: convert_decoded_activity(
            decoded,
            row_number=kwargs["row_number"],
            explicit_qpro_key=kwargs["explicit_qpro_key"],
        ),
    )
    service = GarminQProMcpService(reader=reader)

    service.inspect_garmin_activity(activity_id="1")
    service.convert_garmin_activity(activity_id="1", row_number=23)

    assert reader.download_calls == ["1"]
    assert service.cache_size == 1


def test_force_refresh_replaces_cached_download_in_memory(monkeypatch) -> None:
    old_source = _source("old.fit")
    new_source = _source("new.fit")

    class RefreshingReader(FakeReader):
        def download_original_activity(self, activity_id):
            self.download_calls.append(activity_id)
            return (
                _download(activity_id, old_source)
                if len(self.download_calls) == 1
                else _download(activity_id, new_source)
            )

    reader = RefreshingReader()
    monkeypatch.setattr(
        service_module,
        "decode_fit",
        lambda fit_source, verify_crc=True: _running_decoded(fit_source),
    )
    service = GarminQProMcpService(reader=reader)

    first = service.inspect_garmin_activity(activity_id="1")
    refreshed = service.inspect_garmin_activity(
        activity_id="1",
        force_refresh=True,
    )
    cached = service.inspect_garmin_activity(activity_id="1")

    assert first["sources"][0]["source_name"] == "old.fit"
    assert refreshed["sources"][0]["source_name"] == "new.fit"
    assert cached["sources"][0]["source_name"] == "new.fit"
    assert reader.download_calls == ["1", "1"]
    assert service.cache_size == 1


@pytest.mark.parametrize("force_refresh", [0, 1, "yes", None])
def test_invalid_force_refresh_is_rejected_before_connection(
    force_refresh,
) -> None:
    calls = []
    service = GarminQProMcpService(
        reader_factory=lambda path: calls.append(path)
    )

    with pytest.raises(TypeError):
        service.inspect_garmin_activity(
            activity_id="1",
            force_refresh=force_refresh,
        )
    with pytest.raises(TypeError):
        service.convert_garmin_activity(
            activity_id="1",
            row_number=23,
            force_refresh=force_refresh,
        )

    assert calls == []


def test_lru_cache_never_exceeds_eight_and_evicts_oldest() -> None:
    downloads = {
        str(index): _download(str(index), _source(f"{index}.fit"))
        for index in range(1, 10)
    }
    reader = FakeReader(downloads=downloads)
    service = GarminQProMcpService(reader=reader)

    for index in range(1, 9):
        service._get_download(str(index))
    service._get_download("1")
    service._get_download("9")
    service._get_download("2")

    assert service.cache_size == 8
    assert reader.download_calls == [
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "8",
        "9",
        "2",
    ]


@pytest.mark.parametrize("cache_limit", [True, 0, -1, 9, 1.5])
def test_invalid_cache_limit_is_rejected(cache_limit) -> None:
    with pytest.raises((TypeError, ValueError)):
        GarminQProMcpService(cache_limit=cache_limit)


def test_conversion_reuses_convert_fit_source_and_forwards_arguments(
    monkeypatch,
) -> None:
    source = _source("one.fit")
    reader = FakeReader(downloads={"1": _download("1", source)})
    decoded = _running_decoded(source)
    observed = []

    def fake_convert(
        fit_source,
        *,
        row_number,
        explicit_qpro_key=None,
        verify_crc=True,
    ):
        observed.append(
            (fit_source, row_number, explicit_qpro_key, verify_crc)
        )
        return convert_decoded_activity(
            decoded,
            row_number=row_number,
            explicit_qpro_key=explicit_qpro_key,
        )

    monkeypatch.setattr(service_module, "convert_fit_source", fake_convert)
    payload = GarminQProMcpService(reader=reader).convert_garmin_activity(
        activity_id="1",
        row_number=77,
        explicit_qpro_key=" ent ",
        verify_crc=False,
    )

    assert observed == [(source, 77, "ENT", False)]
    assert payload["success_count"] == 1
    assert payload["failure_count"] == 0
    result = payload["results"][0]
    assert result["qpro_key"] == "ENT"
    assert result["column_count"] == 23
    assert result["tab_count"] == 22
    assert len(result["row_values"]) == 23
    assert result["row_values"][-1] == result["tsv"].split("\t")[-1]
    assert not result["tsv"].endswith("\t")


def test_cal_conversion_preserves_warmup_rule(monkeypatch) -> None:
    source = _source("cal.fit")
    decoded = _running_decoded(
        source,
        workout_name="EB0 - Cal. Estadio",
        cal=True,
    )
    reader = FakeReader(downloads={"1": _download("1", source)})
    monkeypatch.setattr(
        service_module,
        "convert_fit_source",
        lambda fit_source, **kwargs: convert_decoded_activity(
            decoded,
            row_number=kwargs["row_number"],
        ),
    )

    result = GarminQProMcpService(reader=reader).convert_garmin_activity(
        activity_id="1",
        row_number=18,
    )["results"][0]

    assert result["qpro_key"] == "CAL"
    assert result["metrics"]["source_scope"] == "cal_warmup_laps"
    assert result["row_values"][14] == "'140"
    assert "C18" in result["row_values"][3]


def test_force_conversion_preserves_minutes_and_load(monkeypatch) -> None:
    source = _source("force.fit")
    decoded = _force_decoded(source)
    reader = FakeReader(downloads={"1": _download("1", source)})
    monkeypatch.setattr(
        service_module,
        "convert_fit_source",
        lambda fit_source, **kwargs: convert_decoded_activity(
            decoded,
            row_number=kwargs["row_number"],
            explicit_qpro_key=kwargs["explicit_qpro_key"],
        ),
    )

    result = GarminQProMcpService(reader=reader).convert_garmin_activity(
        activity_id="1",
        row_number=36,
        explicit_qpro_key="CMF",
    )["results"][0]

    assert result["metric_family"] == "force"
    assert result["row_values"][10] == "'028"
    assert result["row_values"][18] == "'094"
    assert "C36" in result["row_values"][3]


def test_manual_failure_keeps_identity_and_can_be_retried(
    monkeypatch,
) -> None:
    source = _source("force.fit")
    decoded = _force_decoded(source, workout_name=None)
    reader = FakeReader(downloads={"1": _download("1", source)})

    def fake_convert(fit_source, **kwargs):
        return convert_decoded_activity(
            decoded,
            row_number=kwargs["row_number"],
            explicit_qpro_key=kwargs["explicit_qpro_key"],
        )

    monkeypatch.setattr(service_module, "convert_fit_source", fake_convert)
    service = GarminQProMcpService(reader=reader)

    first = service.convert_garmin_activity(
        activity_id="1",
        row_number=36,
    )
    second = service.convert_garmin_activity(
        activity_id="1",
        row_number=36,
        explicit_qpro_key="CMF",
    )

    assert first["success_count"] == 0
    assert first["failure_count"] == 1
    failure = first["failures"][0]
    assert failure["source_name"] == "force.fit"
    assert failure["sha256"] == source.sha256
    assert failure["qpro_key"] is None
    assert failure["requires_user_choice"] is True
    assert second["success_count"] == 1
    assert reader.download_calls == ["1"]


def test_partial_failure_does_not_stop_following_source(monkeypatch) -> None:
    bad = _source("bad.fit")
    good = _source("good.fit")
    reader = FakeReader(downloads={"1": _download("1", bad, good)})
    decoded = _running_decoded(good)

    def fake_convert(source, **kwargs):
        if source is bad:
            raise RuntimeError("password=must-not-leak")
        return convert_decoded_activity(
            decoded,
            row_number=kwargs["row_number"],
        )

    monkeypatch.setattr(service_module, "convert_fit_source", fake_convert)
    payload = GarminQProMcpService(reader=reader).convert_garmin_activity(
        activity_id="1",
        row_number=23,
    )

    assert payload["success_count"] == 1
    assert payload["failure_count"] == 1
    assert payload["failures"][0]["message"] == "FIT conversion failed"
    assert "must-not-leak" not in repr(payload)
    assert payload["tsv"] == payload["results"][0]["tsv"]
    assert not payload["tsv"].endswith("\n")


def test_conversion_preserves_duplicate_sources_and_combines_tsv_in_order(
    monkeypatch,
) -> None:
    first = _source("first.fit", data=b"same")
    second = _source("second.fit", data=b"same")
    reader = FakeReader(downloads={"1": _download("1", first, second)})

    def fake_convert(source, **kwargs):
        decoded = _running_decoded(source)
        return convert_decoded_activity(
            decoded,
            row_number=kwargs["row_number"],
        )

    monkeypatch.setattr(service_module, "convert_fit_source", fake_convert)
    payload = GarminQProMcpService(reader=reader).convert_garmin_activity(
        activity_id="1",
        row_number=23,
    )

    assert payload["success_count"] == 2
    assert tuple(item["source_name"] for item in payload["results"]) == (
        "first.fit",
        "second.fit",
    )
    assert payload["results"][0]["sha256"] == payload["results"][1]["sha256"]
    assert payload["tsv"] == "\n".join(
        item["tsv"] for item in payload["results"]
    )
    assert not payload["tsv"].endswith("\n")


def test_service_tools_do_not_write_activity_files(
    monkeypatch,
    tmp_path,
) -> None:
    source = _source("one.fit")
    reader = FakeReader(downloads={"1": _download("1", source)})
    decoded = _running_decoded(source)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        service_module,
        "decode_fit",
        lambda fit_source, verify_crc=True: decoded,
    )
    monkeypatch.setattr(
        service_module,
        "convert_fit_source",
        lambda fit_source, **kwargs: convert_decoded_activity(
            decoded,
            row_number=kwargs["row_number"],
        ),
    )
    service = GarminQProMcpService(reader=reader)

    service.list_garmin_activities()
    service.inspect_garmin_activity(activity_id="1")
    service.convert_garmin_activity(activity_id="1", row_number=23)

    assert tuple(tmp_path.iterdir()) == ()


@pytest.mark.parametrize("row_number", [True, 0, -1, 1.5, "23"])
def test_invalid_row_is_rejected_before_connection(row_number) -> None:
    calls = []
    service = GarminQProMcpService(
        reader_factory=lambda path: calls.append(path)
    )

    with pytest.raises((TypeError, ValueError)):
        service.convert_garmin_activity(
            activity_id="1",
            row_number=row_number,
        )

    assert calls == []


@pytest.mark.parametrize("key", [123, "", "UNKNOWN"])
def test_invalid_explicit_key_is_rejected_before_connection(key) -> None:
    calls = []
    service = GarminQProMcpService(
        reader_factory=lambda path: calls.append(path)
    )

    with pytest.raises((TypeError, ValueError)):
        service.convert_garmin_activity(
            activity_id="1",
            row_number=23,
            explicit_qpro_key=key,
        )

    assert calls == []


@pytest.mark.parametrize("verify_crc", [0, 1, "yes", None])
def test_invalid_conversion_crc_is_rejected_before_connection(
    verify_crc,
) -> None:
    calls = []
    service = GarminQProMcpService(
        reader_factory=lambda path: calls.append(path)
    )

    with pytest.raises(TypeError):
        service.convert_garmin_activity(
            activity_id="1",
            row_number=23,
            verify_crc=verify_crc,
        )

    assert calls == []
