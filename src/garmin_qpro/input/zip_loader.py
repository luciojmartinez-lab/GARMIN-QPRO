"""Safe in-memory loading of FIT members from ZIP containers."""

from io import BytesIO
from pathlib import Path, PurePosixPath, PureWindowsPath
from zipfile import BadZipFile, LargeZipFile, ZipFile, ZipInfo

from .sources import FitSource


class NoFitFilesError(LookupError):
    """Raised when a ZIP container has no FIT file members."""


class InvalidZipError(ValueError):
    """Raised when a ZIP container cannot be parsed safely."""


class UnsafeZipPathError(ValueError):
    """Raised when a ZIP member uses an absolute or parent-relative path."""


def _safe_member_path(member_name: str) -> str:
    normalized = member_name.replace("\\", "/")
    posix_path = PurePosixPath(normalized)
    windows_path = PureWindowsPath(member_name)

    if (
        posix_path.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or ".." in posix_path.parts
    ):
        raise UnsafeZipPathError(
            f"Unsafe path in ZIP container: {member_name!r}"
        )
    return normalized


def _fit_members(archive: ZipFile) -> list[tuple[str, ZipInfo]]:
    members: list[tuple[str, ZipInfo]] = []
    for member in archive.infolist():
        safe_path = _safe_member_path(member.filename)
        if member.is_dir():
            continue
        if PurePosixPath(safe_path).suffix.casefold() != ".fit":
            continue
        members.append((safe_path, member))
    members.sort(key=lambda item: item[0])
    return members


def _load_archive_fit_sources(
    archive: ZipFile,
    *,
    container_name: str,
) -> tuple[FitSource, ...]:
    members = _fit_members(archive)
    if not members:
        raise NoFitFilesError(
            f"ZIP container has no FIT files: {container_name}"
        )

    return tuple(
        FitSource(
            source_name=PurePosixPath(safe_path).name,
            container_name=container_name,
            member_path=member.filename,
            data=archive.read(member),
        )
        for safe_path, member in members
    )


def load_zip_fit_sources(path: Path) -> tuple[FitSource, ...]:
    """Load safe FIT members in deterministic path order without extraction."""

    input_path = Path(path)
    try:
        with ZipFile(input_path, mode="r") as archive:
            return _load_archive_fit_sources(
                archive,
                container_name=input_path.name,
            )
    except (BadZipFile, LargeZipFile) as exc:
        raise InvalidZipError(
            f"Invalid ZIP container: {input_path.name}"
        ) from exc


def load_zip_fit_sources_bytes(
    data: bytes,
    *,
    container_name: str,
) -> tuple[FitSource, ...]:
    """Load safe FIT members directly from ZIP bytes without extraction."""

    if not isinstance(data, bytes):
        raise TypeError("ZIP data must be bytes")
    if not isinstance(container_name, str):
        raise TypeError("container_name must be a string")
    normalized_name = container_name.strip()
    if not normalized_name:
        raise ValueError("container_name cannot be empty")

    try:
        with ZipFile(BytesIO(data), mode="r") as archive:
            return _load_archive_fit_sources(
                archive,
                container_name=normalized_name,
            )
    except (BadZipFile, LargeZipFile) as exc:
        raise InvalidZipError(
            f"Invalid ZIP container: {normalized_name}"
        ) from exc
