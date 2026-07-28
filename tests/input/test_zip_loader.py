from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile

import pytest

from garmin_qpro.input.sources import load_fit_sources
from garmin_qpro.input.zip_loader import (
    InvalidZipError,
    NoFitFilesError,
    UnsafeZipPathError,
    load_zip_fit_sources_bytes,
)


def _write_zip(path, members: dict[str, bytes]) -> None:
    with ZipFile(path, mode="w") as archive:
        for member_path, data in members.items():
            archive.writestr(member_path, data)


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, mode="w") as archive:
        for member_path, data in members.items():
            archive.writestr(member_path, data)
    return buffer.getvalue()


def test_zip_with_one_fit_preserves_container_and_member_path(tmp_path) -> None:
    path = tmp_path / "export.ZIP"
    _write_zip(path, {"activity.fit": b"fit-data"})

    source = load_fit_sources(path)[0]

    assert source.source_name == "activity.fit"
    assert source.container_name == "export.ZIP"
    assert source.member_path == "activity.fit"
    assert source.data == b"fit-data"
    assert not (tmp_path / "activity.fit").exists()


def test_zip_loads_multiple_fit_files_in_subfolders(tmp_path) -> None:
    path = tmp_path / "export.zip"
    _write_zip(
        path,
        {
            "activities/second.fit": b"second",
            "first.fit": b"first",
        },
    )

    sources = load_fit_sources(path)

    assert tuple(source.member_path for source in sources) == (
        "activities/second.fit",
        "first.fit",
    )


def test_zip_order_is_deterministic_by_internal_path(tmp_path) -> None:
    path = tmp_path / "export.zip"
    _write_zip(
        path,
        {
            "z/last.fit": b"last",
            "a/first.fit": b"first",
            "m/middle.FIT": b"middle",
        },
    )

    sources = load_fit_sources(path)

    assert tuple(source.member_path for source in sources) == (
        "a/first.fit",
        "m/middle.FIT",
        "z/last.fit",
    )


def test_zip_ignores_non_fit_files_and_directories(tmp_path) -> None:
    path = tmp_path / "export.zip"
    with ZipFile(path, mode="w") as archive:
        archive.writestr("activities/", b"")
        archive.writestr("activities/activity.fit", b"fit")
        archive.writestr("notes/readme.txt", b"ignore")

    sources = load_fit_sources(path)

    assert tuple(source.member_path for source in sources) == (
        "activities/activity.fit",
    )


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "/absolute.fit",
        "../escape.fit",
        "folder/../../escape.fit",
        r"C:\absolute.fit",
    ],
)
def test_zip_rejects_unsafe_member_paths(tmp_path, unsafe_path: str) -> None:
    path = tmp_path / "unsafe.zip"
    _write_zip(path, {unsafe_path: b"unsafe"})

    with pytest.raises(UnsafeZipPathError):
        load_fit_sources(path)


def test_zip_rejects_unsafe_non_fit_member_paths(tmp_path) -> None:
    path = tmp_path / "unsafe.zip"
    _write_zip(
        path,
        {
            "activity.fit": b"fit",
            "../notes.txt": b"unsafe",
        },
    )

    with pytest.raises(UnsafeZipPathError):
        load_fit_sources(path)


@pytest.mark.parametrize(
    "members",
    [
        {},
        {"readme.txt": b"no fit here"},
    ],
)
def test_zip_without_fit_files_is_rejected(tmp_path, members) -> None:
    path = tmp_path / "empty.zip"
    _write_zip(path, members)

    with pytest.raises(NoFitFilesError):
        load_fit_sources(path)


def test_corrupt_zip_is_rejected(tmp_path) -> None:
    path = tmp_path / "corrupt.zip"
    path.write_bytes(b"not-a-valid-zip")

    with pytest.raises(InvalidZipError):
        load_fit_sources(path)


def test_duplicate_fit_content_is_preserved_with_matching_hashes(
    tmp_path,
) -> None:
    path = tmp_path / "duplicates.zip"
    data = b"duplicate-fit"
    _write_zip(path, {"one.fit": data, "two.fit": data})

    sources = load_fit_sources(path)

    assert len(sources) == 2
    assert sources[0].sha256 == sources[1].sha256 == sha256(data).hexdigest()


def test_zip_bytes_load_one_fit_without_writing_files(tmp_path) -> None:
    data = _zip_bytes({"folder/activity.fit": b"fit"})

    source = load_zip_fit_sources_bytes(
        data,
        container_name="garmin-123.zip",
    )[0]

    assert source.source_name == "activity.fit"
    assert source.container_name == "garmin-123.zip"
    assert source.member_path == "folder/activity.fit"
    assert source.data == b"fit"
    assert tuple(tmp_path.iterdir()) == ()


def test_zip_bytes_preserve_safe_order_and_uppercase_fit() -> None:
    data = _zip_bytes(
        {
            "z/last.FIT": b"last",
            "notes.txt": b"ignore",
            "a/first.fit": b"first",
        }
    )

    sources = load_zip_fit_sources_bytes(data, container_name="remote.zip")

    assert tuple(source.member_path for source in sources) == (
        "a/first.fit",
        "z/last.FIT",
    )


@pytest.mark.parametrize(
    "unsafe_path",
    ["/root.fit", "../escape.fit", r"C:\drive.fit"],
)
def test_zip_bytes_reject_unsafe_paths(unsafe_path: str) -> None:
    data = _zip_bytes({unsafe_path: b"fit"})

    with pytest.raises(UnsafeZipPathError):
        load_zip_fit_sources_bytes(data, container_name="remote.zip")


@pytest.mark.parametrize(
    "members",
    [{}, {"readme.txt": b"none"}],
)
def test_zip_bytes_without_fit_uses_existing_error(members) -> None:
    with pytest.raises(NoFitFilesError):
        load_zip_fit_sources_bytes(
            _zip_bytes(members),
            container_name="remote.zip",
        )


def test_corrupt_zip_bytes_use_existing_error() -> None:
    with pytest.raises(InvalidZipError):
        load_zip_fit_sources_bytes(
            b"not-a-zip",
            container_name="remote.zip",
        )


def test_file_and_bytes_loaders_apply_the_same_rules(tmp_path) -> None:
    data = _zip_bytes({"b.fit": b"b", "a.fit": b"a"})
    path = tmp_path / "same.zip"
    path.write_bytes(data)

    from_file = load_fit_sources(path)
    from_bytes = load_zip_fit_sources_bytes(
        data,
        container_name=path.name,
    )

    assert from_bytes == from_file


@pytest.mark.parametrize("invalid_data", [bytearray(b"zip"), "zip", None])
def test_zip_bytes_require_exact_bytes(invalid_data) -> None:
    with pytest.raises(TypeError):
        load_zip_fit_sources_bytes(
            invalid_data,
            container_name="remote.zip",
        )


@pytest.mark.parametrize("container_name", ["", "   "])
def test_zip_bytes_require_container_name(container_name: str) -> None:
    with pytest.raises(ValueError):
        load_zip_fit_sources_bytes(
            _zip_bytes({"one.fit": b"fit"}),
            container_name=container_name,
        )
