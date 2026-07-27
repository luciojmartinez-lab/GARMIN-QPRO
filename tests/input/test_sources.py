from hashlib import sha256

import pytest

from garmin_qpro.input.sources import (
    FitSource,
    UnsupportedInputError,
    load_fit_sources,
)


def test_load_individual_fit_source(tmp_path) -> None:
    path = tmp_path / "activity.fit"
    data = b"individual-fit-data"
    path.write_bytes(data)

    sources = load_fit_sources(path)

    assert len(sources) == 1
    assert sources[0].source_name == "activity.fit"
    assert sources[0].container_name is None
    assert sources[0].member_path is None
    assert sources[0].data == data


def test_load_individual_fit_accepts_uppercase_extension(tmp_path) -> None:
    path = tmp_path / "ACTIVITY.FIT"
    path.write_bytes(b"uppercase")

    source = load_fit_sources(path)[0]

    assert source.source_name == "ACTIVITY.FIT"


def test_fit_source_calculates_sha256_from_content() -> None:
    data = b"same-content"
    source = FitSource("activity.fit", None, None, data)

    assert source.sha256 == sha256(data).hexdigest()


def test_fit_source_requires_bytes() -> None:
    with pytest.raises(TypeError, match="must be bytes"):
        FitSource("activity.fit", None, None, bytearray(b"data"))


def test_fit_source_is_immutable() -> None:
    source = FitSource("activity.fit", None, None, b"data")

    with pytest.raises(AttributeError):
        source.source_name = "changed.fit"  # type: ignore[misc]


def test_missing_input_raises_file_not_found(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        load_fit_sources(tmp_path / "missing.fit")


def test_unsupported_extension_is_rejected(tmp_path) -> None:
    path = tmp_path / "activity.txt"
    path.write_text("not fit", encoding="utf-8")

    with pytest.raises(UnsupportedInputError):
        load_fit_sources(path)
