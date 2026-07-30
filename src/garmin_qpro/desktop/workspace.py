"""Application orchestration for Garmin, manual imports and local history."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from pathlib import Path

from garmin_qpro.conversion import ActivityConversionResult, convert_fit_source
from garmin_qpro.fit.activity_metadata import resolve_decoded_activity
from garmin_qpro.fit.decoder import decode_fit
from garmin_qpro.garmin import (
    GarminActivityDownload,
    GarminActivitySummary,
    GarminDesktopSession,
)
from garmin_qpro.history import (
    CONVERTER_VERSION,
    ConversionDraft,
    ConversionRecord,
    DuplicateConversionError,
    HistoryFilters,
    HistoryRepository,
    HistoryStatus,
)

from .controller import DesktopActivityController, DesktopActivityView


class RemoteActivityStatus(str, Enum):
    READY = "ready"
    NEEDS_KEY = "needs_key"
    ERROR = "error"
    CONVERTED = "converted"


@dataclass(frozen=True, slots=True)
class RemoteActivityView:
    activity_id: str
    activity_datetime: str | None
    name: str
    activity_type: str | None
    workout_name: str | None
    profile_name: str | None
    qpro_key: str | None
    resolution_source: str | None
    status: RemoteActivityStatus
    warning: str
    requires_manual_review: bool
    tsv: str | None = None


@dataclass(slots=True)
class _RemoteActivityRecord:
    summary: GarminActivitySummary
    view: RemoteActivityView
    download: GarminActivityDownload | None = field(default=None, repr=False)


class OriginalSourceRequiredError(ValueError):
    pass


class DesktopWorkspace:
    """Keep UI concerns out of Garmin, history and conversion layers."""

    def __init__(
        self,
        *,
        history: HistoryRepository | None = None,
        garmin: GarminDesktopSession | None = None,
        importer: DesktopActivityController | None = None,
    ) -> None:
        self.history = history or HistoryRepository()
        self.garmin = garmin or GarminDesktopSession()
        self.importer = importer or DesktopActivityController()
        self._remote: dict[str, _RemoteActivityRecord] = {}
        self.last_sync: str | None = None

    @property
    def connected(self) -> bool:
        return self.garmin.connected

    @property
    def garmin_email(self) -> str | None:
        return self.garmin.email

    @property
    def remote_activities(self) -> tuple[RemoteActivityView, ...]:
        return tuple(record.view for record in self._remote.values())

    def restore_garmin(self) -> bool:
        return self.garmin.restore()

    def connect_garmin(self, **kwargs: object) -> None:
        self.garmin.connect(**kwargs)

    def disconnect_garmin(self) -> None:
        self.garmin.disconnect()
        self._remote.clear()
        self.last_sync = None

    def refresh_remote_activities(self, *, limit: int = 20) -> tuple[RemoteActivityView, ...]:
        summaries = self.garmin.reader.list_activities(start=0, limit=limit)
        refreshed: dict[str, _RemoteActivityRecord] = {}
        for summary in summaries:
            if self.history.has_garmin_activity(summary.activity_id):
                continue
            try:
                download = self.garmin.reader.download_original_activity(
                    summary.activity_id
                )
                view = self._inspect_remote(summary, download)
            except Exception as exc:
                download = None
                view = RemoteActivityView(
                    activity_id=summary.activity_id,
                    activity_datetime=summary.start_time_local,
                    name=summary.name,
                    activity_type=summary.activity_type,
                    workout_name=None,
                    profile_name=None,
                    qpro_key=None,
                    resolution_source=None,
                    status=RemoteActivityStatus.ERROR,
                    warning=self._safe_error(exc),
                    requires_manual_review=True,
                )
            refreshed[summary.activity_id] = _RemoteActivityRecord(
                summary=summary,
                view=view,
                download=download,
            )
        self._remote = refreshed
        self.last_sync = datetime.now().isoformat(timespec="seconds")
        return self.remote_activities

    def set_remote_key(self, activity_id: str, key: str) -> RemoteActivityView:
        record = self._remote[activity_id]
        normalized = key.strip().upper()
        view = RemoteActivityView(
            activity_id=record.view.activity_id,
            activity_datetime=record.view.activity_datetime,
            name=record.view.name,
            activity_type=record.view.activity_type,
            workout_name=record.view.workout_name,
            profile_name=record.view.profile_name,
            qpro_key=normalized,
            resolution_source="explicit_qpro_key",
            status=RemoteActivityStatus.READY,
            warning=record.view.warning,
            requires_manual_review=record.view.requires_manual_review,
        )
        record.view = view
        return view

    def convert_remote(
        self,
        activity_ids: tuple[str, ...],
    ) -> tuple[RemoteActivityView, ...]:
        converted: list[RemoteActivityView] = []
        for activity_id in activity_ids:
            record = self._remote[activity_id]
            if record.download is None:
                continue
            key = (
                record.view.qpro_key
                if record.view.resolution_source == "explicit_qpro_key"
                else None
            )
            try:
                if len(record.download.sources) != 1:
                    raise ValueError("Garmin activity contains multiple FIT sources")
                result = convert_fit_source(
                    record.download.sources[0],
                    explicit_qpro_key=key,
                )
                self._save_result(
                    result,
                    garmin_activity_id=activity_id,
                    activity_datetime=record.summary.start_time_local,
                    source_type="garmin",
                    manual_key=key is not None,
                )
                new_view = self._remote_view_from_result(record, result)
                record.view = new_view
                converted.append(new_view)
            except DuplicateConversionError as exc:
                existing = self.history.get(exc.existing_id)
                record.view = replace(
                    record.view,
                    status=RemoteActivityStatus.CONVERTED,
                    warning="Ya estaba guardada en el historial.",
                    tsv=existing.tsv,
                )
                converted.append(record.view)
            except Exception as exc:
                record.view = RemoteActivityView(
                    activity_id=record.view.activity_id,
                    activity_datetime=record.view.activity_datetime,
                    name=record.view.name,
                    activity_type=record.view.activity_type,
                    workout_name=record.view.workout_name,
                    profile_name=record.view.profile_name,
                    qpro_key=record.view.qpro_key,
                    resolution_source=record.view.resolution_source,
                    status=RemoteActivityStatus.ERROR,
                    warning=self._safe_error(exc),
                    requires_manual_review=True,
                )
        return tuple(converted)

    def import_paths(self, paths: tuple[Path, ...]) -> tuple[DesktopActivityView, ...]:
        views = self.importer.process_paths(paths)
        for view in views:
            self._save_import_if_ready(view.item_id)
        return views

    def apply_import_key(self, item_id: int, key: str) -> DesktopActivityView:
        view = self.importer.apply_manual_key(item_id, key)
        self._save_import_if_ready(item_id)
        return view

    def history_items(
        self,
        filters: HistoryFilters | None = None,
    ) -> tuple[ConversionRecord, ...]:
        return self.history.list(filters)

    def set_history_status(
        self,
        record_id: int,
        status: HistoryStatus,
    ) -> ConversionRecord:
        return self.history.update_status(record_id, status)

    def delete_history(self, record_id: int) -> None:
        self.history.delete(record_id)

    def reconvert_history(
        self,
        record_id: int,
        *,
        explicit_qpro_key: str | None = None,
        manual_path: Path | None = None,
    ) -> ConversionRecord:
        record = self.history.get(record_id)
        if record.garmin_activity_id:
            download = self.garmin.reader.download_original_activity(
                record.garmin_activity_id
            )
            if len(download.sources) != 1:
                raise ValueError("Garmin activity contains multiple FIT sources")
            source = download.sources[0]
        elif manual_path is not None:
            from garmin_qpro.input import load_fit_sources

            sources = load_fit_sources(manual_path)
            if len(sources) != 1:
                raise ValueError("Manual input must contain exactly one FIT")
            source = sources[0]
        else:
            raise OriginalSourceRequiredError(
                "Selecciona de nuevo el FIT o ZIP original para reconvertir."
            )
        result = convert_fit_source(
            source,
            explicit_qpro_key=explicit_qpro_key,
        )
        warnings = self._result_warnings(result)
        return self.history.replace_conversion(
            record_id,
            qpro_key=result.activity_context.resolution.qpro_key or record.qpro_key,
            tsv=result.tsv,
            warnings=warnings,
            manual_key=explicit_qpro_key is not None,
            converter_version=CONVERTER_VERSION,
            resolution_source=result.activity_context.resolution.resolution_source,
        )

    def _inspect_remote(
        self,
        summary: GarminActivitySummary,
        download: GarminActivityDownload,
    ) -> RemoteActivityView:
        if len(download.sources) != 1:
            raise ValueError("Garmin activity contains multiple FIT sources")
        decoded = decode_fit(download.sources[0])
        context = resolve_decoded_activity(decoded)
        needs_key = (
            context.resolution.qpro_key is None
            or context.resolution.requires_user_choice
        )
        return RemoteActivityView(
            activity_id=summary.activity_id,
            activity_datetime=summary.start_time_local,
            name=summary.name,
            activity_type=summary.activity_type,
            workout_name=context.metadata.workout_name,
            profile_name=context.metadata.sport_profile_name,
            qpro_key=context.resolution.qpro_key,
            resolution_source=context.resolution.resolution_source,
            status=(
                RemoteActivityStatus.NEEDS_KEY
                if needs_key
                else RemoteActivityStatus.READY
            ),
            warning=(
                "Selecciona una clave QPro."
                if needs_key
                else (
                    f"El decodificador informo de {len(decoded.errors)} incidencia(s)."
                    if decoded.errors
                    else ""
                )
            ),
            requires_manual_review=needs_key or bool(decoded.errors),
        )

    def _remote_view_from_result(
        self,
        record: _RemoteActivityRecord,
        result: ActivityConversionResult,
    ) -> RemoteActivityView:
        warnings = self._result_warnings(result)
        return RemoteActivityView(
            activity_id=record.summary.activity_id,
            activity_datetime=record.summary.start_time_local,
            name=record.summary.name,
            activity_type=record.summary.activity_type,
            workout_name=result.activity_context.metadata.workout_name,
            profile_name=result.activity_context.metadata.sport_profile_name,
            qpro_key=result.activity_context.resolution.qpro_key,
            resolution_source=result.activity_context.resolution.resolution_source,
            status=RemoteActivityStatus.CONVERTED,
            warning="; ".join(warnings),
            requires_manual_review=bool(warnings),
            tsv=result.tsv,
        )

    def _save_import_if_ready(self, item_id: int) -> None:
        result = self.importer.get_result(item_id)
        path = self.importer.get_input_path(item_id)
        if result is None or path is None:
            return
        source_type = "zip" if path.suffix.casefold() == ".zip" else "fit"
        try:
            self._save_result(
                result,
                garmin_activity_id=None,
                activity_datetime=None,
                source_type=source_type,
                manual_key=(
                    result.activity_context.resolution.resolution_source
                    == "explicit_qpro_key"
                ),
            )
        except DuplicateConversionError:
            pass

    def _save_result(
        self,
        result: ActivityConversionResult,
        *,
        garmin_activity_id: str | None,
        activity_datetime: str | None,
        source_type: str,
        manual_key: bool,
    ) -> ConversionRecord:
        context = result.activity_context
        key = context.resolution.qpro_key
        if key is None:
            raise ValueError("Converted result has no QPro key")
        warnings = self._result_warnings(result)
        return self.history.save(
            ConversionDraft(
                garmin_activity_id=garmin_activity_id,
                source_sha256=result.sha256,
                activity_datetime=activity_datetime,
                workout_name=context.metadata.workout_name,
                profile_name=context.metadata.sport_profile_name,
                qpro_key=key,
                tsv=result.tsv,
                source_type=source_type,
                source_name=result.source_name,
                warnings=warnings,
                manual_key=manual_key,
                status=(
                    HistoryStatus.PENDING
                    if warnings
                    else HistoryStatus.CONVERTED
                ),
                resolution_source=context.resolution.resolution_source,
            )
        )

    @staticmethod
    def _result_warnings(result: ActivityConversionResult) -> tuple[str, ...]:
        warnings = list(getattr(result.metrics, "review_reasons", ()))
        warnings.extend(getattr(result.metrics, "trim_reasons", ()))
        if result.decoder_errors:
            warnings.append(
                f"decoder_error_count:{len(result.decoder_errors)}"
            )
        return tuple(dict.fromkeys(warnings))

    @staticmethod
    def _safe_error(error: Exception) -> str:
        if isinstance(error, (TypeError, ValueError)):
            text = str(error).strip()
            if text:
                return text
        return "No se pudo completar la operacion."
