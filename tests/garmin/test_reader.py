from dataclasses import FrozenInstanceError
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

import garmin_qpro
from garmin_qpro.garmin import reader as reader_module
from garmin_qpro.garmin.errors import (
    GarminAuthenticationError,
    GarminConnectionError,
    GarminIntegrationUnavailableError,
    GarminResponseError,
)
from garmin_qpro.garmin.reader import (
    GarminConnectReader,
    _GarminBindings,
    connect_garmin,
)
from garmin_qpro.input import (
    InvalidZipError,
    NoFitFilesError,
    UnsafeZipPathError,
)


class ExternalAuthenticationError(Exception):
    pass


class ExternalConnectionError(Exception):
    pass


class ExternalRateLimitError(Exception):
    pass


class FakeGarminType:
    class ActivityDownloadFormat:
        ORIGINAL = object()


BINDINGS = _GarminBindings(
    Garmin=FakeGarminType,
    authentication_error=ExternalAuthenticationError,
    connection_error=ExternalConnectionError,
    too_many_requests_error=ExternalRateLimitError,
)
_UNSET = object()


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, mode="w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class FakeClient:
    def __init__(self, *, activities=_UNSET, archive=None, error=None):
        self.activities = [] if activities is _UNSET else activities
        self.archive = archive
        self.error = error
        self.calls = []

    def get_activities(self, start, limit):
        self.calls.append(("get_activities", start, limit))
        if self.error:
            raise self.error
        return self.activities

    def download_activity(self, activity_id, *, dl_fmt):
        self.calls.append(("download_activity", activity_id, dl_fmt))
        if self.error:
            raise self.error
        return self.archive


def _reader(client: FakeClient) -> GarminConnectReader:
    return GarminConnectReader(client, _bindings=BINDINGS)


def test_list_activities_preserves_order_and_calls_only_listing() -> None:
    activities = [
        {"activityId": 2, "activityName": "Second"},
        {"activityId": 1, "activityName": "First"},
    ]
    client = FakeClient(activities=activities)

    summaries = _reader(client).list_activities(start=3, limit=7)

    assert isinstance(summaries, tuple)
    assert tuple(item.activity_id for item in summaries) == ("2", "1")
    assert client.calls == [("get_activities", 3, 7)]


def test_list_discards_remote_mapping_and_coordinates() -> None:
    remote = {
        "activityId": 1,
        "activityName": "Run",
        "latitude": 41.0,
        "longitude": 2.0,
    }

    summary = _reader(FakeClient(activities=[remote])).list_activities()[0]
    remote["activityName"] = "Changed"

    assert summary.name == "Run"
    assert "latitude" not in repr(summary)
    assert "longitude" not in repr(summary)


@pytest.mark.parametrize("start", [True, -1, 1.5, "0"])
def test_list_rejects_invalid_start(start) -> None:
    with pytest.raises((TypeError, ValueError)):
        _reader(FakeClient()).list_activities(start=start)


@pytest.mark.parametrize("limit", [True, 0, -1, 1.5, "20"])
def test_list_rejects_invalid_limit(limit) -> None:
    with pytest.raises((TypeError, ValueError)):
        _reader(FakeClient()).list_activities(limit=limit)


@pytest.mark.parametrize("response", [{}, "activities", None])
def test_list_rejects_invalid_response_shape(response) -> None:
    with pytest.raises(GarminResponseError):
        _reader(FakeClient(activities=response)).list_activities()


def test_list_rejects_invalid_activity_without_exposing_json() -> None:
    with pytest.raises(GarminResponseError) as exc_info:
        _reader(
            FakeClient(
                activities=[
                    {
                        "activityId": "bad",
                        "password": "do-not-leak",
                    }
                ]
            )
        ).list_activities()

    assert "do-not-leak" not in str(exc_info.value)


def test_download_uses_original_and_returns_in_memory_metadata() -> None:
    archive = _zip_bytes({"folder/one.fit": b"fit-data"})
    client = FakeClient(archive=archive)

    result = _reader(client).download_original_activity(123)

    assert client.calls == [
        (
            "download_activity",
            "123",
            FakeGarminType.ActivityDownloadFormat.ORIGINAL,
        )
    ]
    assert result.activity_id == "123"
    assert result.container_name == "garmin-123.zip"
    assert result.archive_size == len(archive)
    assert result.archive_sha256 == sha256(archive).hexdigest()
    assert len(result.sources) == 1
    assert result.sources[0].container_name == "garmin-123.zip"


def test_download_multiple_fits_preserves_safe_order() -> None:
    archive = _zip_bytes({"z.FIT": b"z", "a.fit": b"a"})

    result = _reader(FakeClient(archive=archive)).download_original_activity("7")

    assert tuple(source.member_path for source in result.sources) == (
        "a.fit",
        "z.FIT",
    )


@pytest.mark.parametrize("archive", [None, b"", "zip", bytearray(b"zip")])
def test_download_rejects_empty_or_non_bytes(archive) -> None:
    with pytest.raises(GarminResponseError):
        _reader(FakeClient(archive=archive)).download_original_activity("7")


def test_download_preserves_no_fit_error() -> None:
    with pytest.raises(NoFitFilesError):
        _reader(FakeClient(archive=_zip_bytes({"readme.txt": b"x"}))).download_original_activity("7")


def test_download_preserves_invalid_zip_error() -> None:
    with pytest.raises(InvalidZipError):
        _reader(FakeClient(archive=b"invalid")).download_original_activity("7")


def test_download_preserves_unsafe_zip_error() -> None:
    with pytest.raises(UnsafeZipPathError):
        _reader(FakeClient(archive=_zip_bytes({"../one.fit": b"x"}))).download_original_activity("7")


@pytest.mark.parametrize(
    ("external_error", "expected_error", "message"),
    [
        (
            ExternalAuthenticationError("password=secret"),
            GarminAuthenticationError,
            "authentication failed",
        ),
        (
            ExternalRateLimitError("token=secret"),
            GarminConnectionError,
            "rate limit exceeded",
        ),
        (
            ExternalConnectionError("cookie=secret"),
            GarminConnectionError,
            "activity listing failed",
        ),
    ],
)
def test_remote_errors_are_translated_safely(
    external_error,
    expected_error,
    message: str,
) -> None:
    with pytest.raises(expected_error) as exc_info:
        _reader(FakeClient(error=external_error)).list_activities()

    assert message in str(exc_info.value)
    assert "secret" not in str(exc_info.value)
    assert exc_info.value.__cause__ is external_error


def test_reader_has_no_remote_write_methods() -> None:
    public_methods = {
        name
        for name in dir(GarminConnectReader)
        if not name.startswith("_") and callable(getattr(GarminConnectReader, name))
    }

    assert public_methods == {
        "download_original_activity",
        "list_activities",
    }


def test_reader_representation_does_not_show_client_secrets() -> None:
    client = SimpleNamespace(password="secret", token="secret-token")
    result = GarminConnectReader(client, _bindings=BINDINGS)

    assert "secret" not in repr(result)


def test_missing_optional_dependency_has_clear_error(monkeypatch) -> None:
    monkeypatch.setattr(
        reader_module.importlib,
        "import_module",
        lambda name: (_ for _ in ()).throw(ImportError(name)),
    )

    with pytest.raises(GarminIntegrationUnavailableError, match="install"):
        reader_module._load_garmin_bindings()


def test_python_311_is_rejected_before_import(monkeypatch) -> None:
    monkeypatch.setattr(reader_module.sys, "version_info", (3, 11, 9))

    with pytest.raises(GarminIntegrationUnavailableError, match="3.12"):
        reader_module._load_garmin_bindings()


def test_main_package_import_does_not_load_optional_dependency(monkeypatch) -> None:
    monkeypatch.setattr(
        reader_module.importlib,
        "import_module",
        lambda name: (_ for _ in ()).throw(AssertionError(name)),
    )

    assert garmin_qpro.GarminConnectReader is GarminConnectReader


def test_connect_passes_token_store_and_mfa_without_retaining_password(
    monkeypatch,
    tmp_path,
) -> None:
    observed = {}

    class FakeGarmin:
        ActivityDownloadFormat = FakeGarminType.ActivityDownloadFormat

        def __init__(self, *, email=None, password=None, prompt_mfa=None):
            observed["email"] = email
            observed["password"] = password
            observed["prompt_mfa"] = prompt_mfa

        def login(self, *, tokenstore):
            observed["tokenstore"] = tokenstore

    bindings = _GarminBindings(
        Garmin=FakeGarmin,
        authentication_error=ExternalAuthenticationError,
        connection_error=ExternalConnectionError,
        too_many_requests_error=ExternalRateLimitError,
    )
    monkeypatch.setattr(reader_module, "_load_garmin_bindings", lambda: bindings)
    callback = lambda: "123456"
    token_store = tmp_path / "tokens"

    reader = connect_garmin(
        token_store=token_store,
        email="user@example.com",
        password="private-password",
        prompt_mfa=callback,
    )

    assert observed == {
        "email": "user@example.com",
        "password": "private-password",
        "prompt_mfa": callback,
        "tokenstore": str(token_store),
    }
    assert token_store.is_dir()
    assert "private-password" not in repr(reader)
    assert not hasattr(reader, "password")


def test_connect_translates_authentication_without_password_leak(
    monkeypatch,
    tmp_path,
) -> None:
    class FakeGarmin:
        def __init__(self, **kwargs):
            pass

        def login(self, *, tokenstore):
            raise ExternalAuthenticationError("private-password")

    monkeypatch.setattr(
        reader_module,
        "_load_garmin_bindings",
        lambda: _GarminBindings(
            Garmin=FakeGarmin,
            authentication_error=ExternalAuthenticationError,
            connection_error=ExternalConnectionError,
            too_many_requests_error=ExternalRateLimitError,
        ),
    )

    with pytest.raises(GarminAuthenticationError) as exc_info:
        connect_garmin(
            token_store=tmp_path / "tokens",
            password="private-password",
        )

    assert "private-password" not in str(exc_info.value)


def test_public_api_exports_garmin_components() -> None:
    expected = {
        "GarminActivitySummary",
        "GarminActivityDownload",
        "GarminConnectReader",
        "GarminIntegrationUnavailableError",
        "GarminAuthenticationError",
        "GarminConnectionError",
        "GarminResponseError",
        "connect_garmin",
        "load_zip_fit_sources_bytes",
    }

    assert expected <= set(garmin_qpro.__all__)
