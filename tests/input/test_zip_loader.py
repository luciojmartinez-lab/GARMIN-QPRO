from hashlib import sha256
from zipfile import ZipFile

import pytest

from garmin_qpro.input.sources import load_fit_sources
from garmin_qpro.input.zip_loader import (
    InvalidZipError,
    NoFitFilesError,
    UnsafeZipPathError,
)


def _write_zip(path, members: dict[str, bytes]) -> None:
    with ZipFile(path, mode="w") as archive:
        for member_path, data in members.items():
            archive.writestr(member_path, data)


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
