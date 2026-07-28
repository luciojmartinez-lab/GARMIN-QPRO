"""Transport-independent service for the local Garmin-QPRO MCP server."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import fields
from pathlib import Path
from typing import Any

from garmin_qpro.conversion import (
    ActivityConversionResult,
    ActivityRequiresChoiceError,
    convert_fit_source,
)
from garmin_qpro.fit.activity_metadata import (
    ActivityContext,
    resolve_decoded_activity,
)
from garmin_qpro.fit.decoder import decode_fit
from garmin_qpro.fit.force_metrics import ForceMetricsRaw
from garmin_qpro.fit.running_metrics import RunningMetricsRaw
from garmin_qpro.garmin import (
    DEFAULT_TOKEN_STORE,
    GarminActivityDownload,
    GarminActivitySummary,
    GarminAuthenticationError,
    GarminConnectReader,
    connect_garmin,
)
from garmin_qpro.garmin.models import normalize_activity_id
from garmin_qpro.input.sources import FitSource
from garmin_qpro.qpro.rows import family_for_key

TOKEN_REFRESH_COMMAND = (
    "python scripts\\garmin_connect_smoke.py --limit 10"
)
MAX_DOWNLOAD_CACHE_SIZE = 8

ReaderFactory = Callable[[Path], GarminConnectReader]


def _default_reader_factory(token_store: Path) -> GarminConnectReader:
    return connect_garmin(token_store=token_store)


def _validate_verify_crc(verify_crc: bool) -> bool:
    if not isinstance(verify_crc, bool):
        raise TypeError("verify_crc must be a boolean")
    return verify_crc


def _validate_row_number(row_number: int) -> int:
    if isinstance(row_number, bool) or not isinstance(row_number, int):
        raise TypeError("row_number must be an integer")
    if row_number <= 0:
        raise ValueError("row_number must be positive")
    return row_number


def _validate_list_page(start: int, limit: int) -> tuple[int, int]:
    if isinstance(start, bool) or not isinstance(start, int):
        raise TypeError("start must be an integer")
    if start < 0:
        raise ValueError("start must be non-negative")
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("limit must be an integer")
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    return start, limit


def _normalize_explicit_key(explicit_qpro_key: str | None) -> str | None:
    if explicit_qpro_key is None:
        return None
    if not isinstance(explicit_qpro_key, str):
        raise TypeError("explicit_qpro_key must be text or None")
    normalized = explicit_qpro_key.strip().upper()
    family_for_key(normalized)
    return normalized


def _summary_payload(summary: GarminActivitySummary) -> dict[str, Any]:
    return {
        "activity_id": summary.activity_id,
        "name": summary.name,
        "activity_type": summary.activity_type,
        "start_time_local": summary.start_time_local,
        "duration_s": summary.duration_s,
        "elapsed_duration_s": summary.elapsed_duration_s,
        "distance_m": summary.distance_m,
    }


def _context_payload(context: ActivityContext) -> dict[str, Any]:
    metadata = context.metadata
    resolution = context.resolution
    return {
        "workout_name": metadata.workout_name,
        "workout_name_field": metadata.workout_name_field,
        "sport_profile_name": metadata.sport_profile_name,
        "sport": metadata.sport,
        "sub_sport": metadata.sub_sport,
        "qpro_key": resolution.qpro_key,
        "resolution_source": resolution.resolution_source,
        "requires_user_choice": resolution.requires_user_choice,
    }


def _source_identity(source: FitSource) -> dict[str, Any]:
    return {
        "source_name": source.source_name,
        "container_name": source.container_name,
        "member_path": source.member_path,
        "sha256": source.sha256,
    }


def _metrics_payload(
    metrics: RunningMetricsRaw | ForceMetricsRaw,
) -> dict[str, Any]:
    return {
        field.name: getattr(metrics, field.name)
        for field in fields(metrics)
    }


def _success_payload(
    result: ActivityConversionResult,
) -> dict[str, Any]:
    metrics = result.metrics
    context = result.activity_context
    row_values = result.row.as_tuple()
    return {
        "source_name": result.source_name,
        "container_name": result.container_name,
        "member_path": result.member_path,
        "sha256": result.sha256,
        "qpro_key": context.resolution.qpro_key,
        "resolution_source": context.resolution.resolution_source,
        "workout_name": context.metadata.workout_name,
        "sport_profile_name": context.metadata.sport_profile_name,
        "metric_family": (
            "running"
            if isinstance(metrics, RunningMetricsRaw)
            else "force"
        ),
        "metrics": _metrics_payload(metrics),
        "row_values": row_values,
        "tsv": result.tsv,
        "column_count": len(row_values),
        "tab_count": result.tsv.count("\t"),
        "requires_manual_review": bool(
            getattr(metrics, "requires_manual_review", False)
        ),
    }


def _safe_failure_message(error: Exception) -> str:
    if isinstance(error, ActivityRequiresChoiceError):
        return "Activity requires a manual QPro key choice"
    if isinstance(error, (TypeError, ValueError)):
        return str(error)
    return "FIT conversion failed"


def _failure_payload(
    source: FitSource,
    error: Exception,
) -> dict[str, Any]:
    context = (
        error.activity_context
        if isinstance(error, ActivityRequiresChoiceError)
        else None
    )
    metadata = context.metadata if context is not None else None
    resolution = context.resolution if context is not None else None
    return {
        **_source_identity(source),
        "error_type": type(error).__name__,
        "message": _safe_failure_message(error),
        "requires_user_choice": bool(
            resolution is not None and resolution.requires_user_choice
        ),
        "workout_name": (
            metadata.workout_name if metadata is not None else None
        ),
        "sport_profile_name": (
            metadata.sport_profile_name if metadata is not None else None
        ),
        "qpro_key": (
            resolution.qpro_key if resolution is not None else None
        ),
    }


class GarminQProMcpService:
    """Lazy read-only Garmin service with an eight-entry in-memory LRU cache."""

    __slots__ = (
        "_cache",
        "_cache_limit",
        "_reader",
        "_reader_factory",
        "token_store",
    )

    def __init__(
        self,
        *,
        token_store: Path = DEFAULT_TOKEN_STORE,
        reader: GarminConnectReader | None = None,
        reader_factory: ReaderFactory | None = None,
        cache_limit: int = MAX_DOWNLOAD_CACHE_SIZE,
    ) -> None:
        if isinstance(cache_limit, bool) or not isinstance(cache_limit, int):
            raise TypeError("cache_limit must be an integer")
        if not 1 <= cache_limit <= MAX_DOWNLOAD_CACHE_SIZE:
            raise ValueError("cache_limit must be between 1 and 8")
        if reader is not None and reader_factory is not None:
            raise ValueError("reader and reader_factory are mutually exclusive")
        self.token_store = Path(token_store).expanduser()
        self._reader = reader
        self._reader_factory = reader_factory or _default_reader_factory
        self._cache_limit = cache_limit
        self._cache: OrderedDict[str, GarminActivityDownload] = OrderedDict()

    @property
    def cache_size(self) -> int:
        return len(self._cache)

    def _get_reader(self) -> GarminConnectReader:
        if self._reader is None:
            try:
                self._reader = self._reader_factory(self.token_store)
            except GarminAuthenticationError as exc:
                raise GarminAuthenticationError(
                    "Garmin tokens require local authentication; run "
                    f"{TOKEN_REFRESH_COMMAND}"
                ) from exc
        return self._reader

    def _get_download(self, activity_id: str) -> GarminActivityDownload:
        cached = self._cache.get(activity_id)
        if cached is not None:
            self._cache.move_to_end(activity_id)
            return cached
        download = self._get_reader().download_original_activity(activity_id)
        self._cache[activity_id] = download
        self._cache.move_to_end(activity_id)
        while len(self._cache) > self._cache_limit:
            self._cache.popitem(last=False)
        return download

    def list_garmin_activities(
        self,
        *,
        start: int = 0,
        limit: int = 10,
    ) -> dict[str, Any]:
        validated_start, validated_limit = _validate_list_page(start, limit)
        activities = self._get_reader().list_activities(
            start=validated_start,
            limit=validated_limit,
        )
        return {
            "activities": tuple(
                _summary_payload(activity) for activity in activities
            ),
            "count": len(activities),
            "start": validated_start,
            "limit": validated_limit,
        }

    def inspect_garmin_activity(
        self,
        *,
        activity_id: str | int,
        verify_crc: bool = True,
    ) -> dict[str, Any]:
        normalized_id = normalize_activity_id(activity_id)
        validated_crc = _validate_verify_crc(verify_crc)
        download = self._get_download(normalized_id)
        sources: list[dict[str, Any]] = []
        for source in download.sources:
            decoded = decode_fit(source, verify_crc=validated_crc)
            context = resolve_decoded_activity(decoded)
            sources.append(
                {
                    **_source_identity(source),
                    **_context_payload(context),
                    "crc_checked": decoded.crc_checked,
                    "decoder_error_count": len(decoded.errors),
                }
            )
        return {
            "activity_id": normalized_id,
            "container_name": download.container_name,
            "archive_sha256": download.archive_sha256,
            "archive_size": download.archive_size,
            "fit_count": len(download.sources),
            "sources": tuple(sources),
        }

    def convert_garmin_activity(
        self,
        *,
        activity_id: str | int,
        row_number: int,
        explicit_qpro_key: str | None = None,
        verify_crc: bool = True,
    ) -> dict[str, Any]:
        normalized_id = normalize_activity_id(activity_id)
        validated_row = _validate_row_number(row_number)
        normalized_key = _normalize_explicit_key(explicit_qpro_key)
        validated_crc = _validate_verify_crc(verify_crc)
        download = self._get_download(normalized_id)

        results: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        successful_tsv: list[str] = []
        for source in download.sources:
            try:
                result = convert_fit_source(
                    source,
                    row_number=validated_row,
                    explicit_qpro_key=normalized_key,
                    verify_crc=validated_crc,
                )
            except Exception as exc:
                failures.append(_failure_payload(source, exc))
                continue
            results.append(_success_payload(result))
            successful_tsv.append(result.tsv)

        return {
            "activity_id": normalized_id,
            "container_name": download.container_name,
            "archive_sha256": download.archive_sha256,
            "archive_size": download.archive_size,
            "success_count": len(results),
            "failure_count": len(failures),
            "results": tuple(results),
            "failures": tuple(failures),
            "tsv": "\n".join(successful_tsv),
        }
