"""Batch conversion of FIT and ZIP inputs without filesystem output."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from garmin_qpro.conversion import (
    ActivityConversionResult,
    ActivityRequiresChoiceError,
    convert_decoded_activity,
)
from garmin_qpro.fit.activity_metadata import resolve_decoded_activity
from garmin_qpro.fit.decoder import decode_fit
from garmin_qpro.input.sources import FitSource, load_fit_sources
BatchFailureStage = Literal[
    "load",
    "decode",
    "resolve",
    "convert",
]

_ALLOWED_STAGES = frozenset(
    {"load", "decode", "resolve", "convert"}
)
_SUPPORTED_SUFFIXES = frozenset({".fit", ".zip"})


@dataclass(frozen=True, slots=True)
class BatchConversionFailure:
    """Safe details for one failed batch source."""

    input_path: Path
    source_name: str | None
    container_name: str | None
    member_path: str | None
    sha256: str | None
    qpro_key: str | None
    stage: BatchFailureStage
    error_type: str
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.input_path, Path):
            object.__setattr__(self, "input_path", Path(self.input_path))
        if self.stage not in _ALLOWED_STAGES:
            raise ValueError(f"Unknown batch failure stage: {self.stage!r}")


@dataclass(frozen=True, slots=True)
class BatchConversionResult:
    """Immutable successful conversions, failures, and combined TSV."""

    results: tuple[ActivityConversionResult, ...]
    failures: tuple[BatchConversionFailure, ...]
    tsv: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "results", tuple(self.results))
        object.__setattr__(self, "failures", tuple(self.failures))
        if not all(
            isinstance(result, ActivityConversionResult)
            for result in self.results
        ):
            raise TypeError("results must contain ActivityConversionResult")
        if not all(
            isinstance(failure, BatchConversionFailure)
            for failure in self.failures
        ):
            raise TypeError("failures must contain BatchConversionFailure")
        if not isinstance(self.tsv, str):
            raise TypeError("tsv must be a string")

    @property
    def success_count(self) -> int:
        return len(self.results)

    @property
    def failure_count(self) -> int:
        return len(self.failures)


def _validate_verify_crc(verify_crc: bool) -> None:
    if not isinstance(verify_crc, bool):
        raise TypeError("verify_crc must be a boolean")


def _normalize_paths(paths: Iterable[Path]) -> tuple[Path, ...]:
    if isinstance(paths, (str, bytes, Path)):
        raise TypeError("paths must be an iterable of paths")
    try:
        return tuple(Path(path) for path in paths)
    except TypeError as exc:
        raise TypeError("paths must be an iterable of paths") from exc


def _failure(
    *,
    input_path: Path,
    stage: BatchFailureStage,
    error: Exception,
    source: FitSource | None = None,
    qpro_key: str | None = None,
) -> BatchConversionFailure:
    return BatchConversionFailure(
        input_path=input_path,
        source_name=source.source_name if source is not None else None,
        container_name=source.container_name if source is not None else None,
        member_path=source.member_path if source is not None else None,
        sha256=source.sha256 if source is not None else None,
        qpro_key=qpro_key,
        stage=stage,
        error_type=type(error).__name__,
        message=str(error) or type(error).__name__,
    )


def convert_input_paths(
    paths: Iterable[Path],
    *,
    verify_crc: bool = True,
    row_numbers: object | None = None,
) -> BatchConversionResult:
    """Convert all sources; row_numbers is deprecated and ignored."""

    _validate_verify_crc(verify_crc)
    input_paths = _normalize_paths(paths)

    results: list[ActivityConversionResult] = []
    failures: list[BatchConversionFailure] = []

    for input_path in input_paths:
        try:
            sources = load_fit_sources(input_path)
        except Exception as exc:
            failures.append(
                _failure(
                    input_path=input_path,
                    stage="load",
                    error=exc,
                )
            )
            continue

        for source in sources:
            try:
                decoded = decode_fit(source, verify_crc=verify_crc)
            except Exception as exc:
                failures.append(
                    _failure(
                        input_path=input_path,
                        source=source,
                        stage="decode",
                        error=exc,
                    )
                )
                continue

            try:
                activity_context = resolve_decoded_activity(decoded)
            except Exception as exc:
                failures.append(
                    _failure(
                        input_path=input_path,
                        source=source,
                        stage="resolve",
                        error=exc,
                    )
                )
                continue

            resolution = activity_context.resolution
            if resolution.qpro_key is None or resolution.requires_user_choice:
                error = ActivityRequiresChoiceError(
                    source=source,
                    activity_context=activity_context,
                    reason="Activity requires a manual QPro key choice",
                )
                failures.append(
                    _failure(
                        input_path=input_path,
                        source=source,
                        stage="resolve",
                        error=error,
                    )
                )
                continue

            qpro_key = resolution.qpro_key

            try:
                result = convert_decoded_activity(
                    decoded,
                    row_number=None,
                )
            except Exception as exc:
                failures.append(
                    _failure(
                        input_path=input_path,
                        source=source,
                        qpro_key=qpro_key,
                        stage="convert",
                        error=exc,
                    )
                )
                continue
            results.append(result)

    frozen_results = tuple(results)
    return BatchConversionResult(
        results=frozen_results,
        failures=tuple(failures),
        tsv="\n".join(result.tsv for result in frozen_results),
    )


def discover_input_paths(directory: Path) -> tuple[Path, ...]:
    """Discover immediate FIT and ZIP files in deterministic name order."""

    directory_path = Path(directory)
    if not directory_path.exists():
        raise FileNotFoundError(directory_path)
    if not directory_path.is_dir():
        raise NotADirectoryError(directory_path)

    paths = tuple(
        path
        for path in directory_path.iterdir()
        if path.is_file() and path.suffix.casefold() in _SUPPORTED_SUFFIXES
    )
    return tuple(sorted(paths, key=lambda path: (path.name.casefold(), path.name)))


def convert_input_directory(
    directory: Path,
    *,
    verify_crc: bool = True,
    row_numbers: object | None = None,
) -> BatchConversionResult:
    """Convert a directory; row_numbers is deprecated and ignored."""

    return convert_input_paths(
        discover_input_paths(directory),
        verify_crc=verify_crc,
        row_numbers=row_numbers,
    )
