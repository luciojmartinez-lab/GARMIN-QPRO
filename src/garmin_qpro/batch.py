"""Batch conversion of FIT and ZIP inputs without filesystem output."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from garmin_qpro.conversion import (
    ActivityConversionResult,
    ActivityRequiresChoiceError,
    convert_decoded_activity,
)
from garmin_qpro.fit.activity_metadata import resolve_decoded_activity
from garmin_qpro.fit.decoder import decode_fit
from garmin_qpro.input.sources import FitSource, load_fit_sources
from garmin_qpro.qpro.rows import family_for_key

BatchFailureStage = Literal[
    "load",
    "decode",
    "resolve",
    "row_number",
    "convert",
]

_ALLOWED_STAGES = frozenset(
    {"load", "decode", "resolve", "row_number", "convert"}
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


class _MissingRowNumberError(LookupError):
    pass


def _validate_verify_crc(verify_crc: bool) -> None:
    if not isinstance(verify_crc, bool):
        raise TypeError("verify_crc must be a boolean")


def _normalize_row_numbers(
    row_numbers: Mapping[str, int],
) -> Mapping[str, int]:
    if not isinstance(row_numbers, Mapping):
        raise TypeError("row_numbers must be a mapping")

    normalized: dict[str, int] = {}
    for key, row_number in row_numbers.items():
        if not isinstance(key, str):
            raise TypeError("row_numbers keys must be strings")
        normalized_key = key.strip().upper()
        family_for_key(normalized_key)
        if normalized_key in normalized:
            raise ValueError(
                f"Duplicate QPro key after normalization: {normalized_key}"
            )
        if isinstance(row_number, bool) or not isinstance(row_number, int):
            raise TypeError("row numbers must be integers")
        if row_number <= 0:
            raise ValueError("row numbers must be positive")
        normalized[normalized_key] = row_number
    return MappingProxyType(normalized)


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
    row_numbers: Mapping[str, int],
    verify_crc: bool = True,
) -> BatchConversionResult:
    """Convert all FIT sources while isolating per-path and per-source failures."""

    _validate_verify_crc(verify_crc)
    normalized_rows = _normalize_row_numbers(row_numbers)
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
            row_number = normalized_rows.get(qpro_key)
            if row_number is None:
                error = _MissingRowNumberError(
                    f"No row number configured for QPro key {qpro_key}"
                )
                failures.append(
                    _failure(
                        input_path=input_path,
                        source=source,
                        qpro_key=qpro_key,
                        stage="row_number",
                        error=error,
                    )
                )
                continue

            try:
                result = convert_decoded_activity(
                    decoded,
                    row_number=row_number,
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
    row_numbers: Mapping[str, int],
    verify_crc: bool = True,
) -> BatchConversionResult:
    """Discover immediate inputs and delegate to batch conversion."""

    return convert_input_paths(
        discover_input_paths(directory),
        row_numbers=row_numbers,
        verify_crc=verify_crc,
    )
