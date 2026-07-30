"""Testable orchestration for the desktop application."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from garmin_qpro.conversion import (
    ActivityConversionResult,
    convert_decoded_activity,
)
from garmin_qpro.fit import DecodedFit, decode_fit
from garmin_qpro.fit.activity_metadata import (
    ActivityContext,
    resolve_decoded_activity,
)
from garmin_qpro.input import FitSource, load_fit_sources
from garmin_qpro.qpro.rows import QPRO_FAMILY_BY_KEY


class DesktopActivityStatus(str, Enum):
    """States shown for each activity in the desktop list."""

    CONVERTED = "converted"
    NEEDS_KEY = "needs_key"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class DesktopActivityView:
    """Public, privacy-conscious representation of a processed activity."""

    item_id: int
    input_name: str
    source_name: str | None
    workout_name: str | None
    sport_profile_name: str | None
    qpro_key: str | None
    resolution_source: str | None
    status: DesktopActivityStatus
    message: str
    warning: str
    requires_manual_review: bool
    tsv: str | None

    @property
    def can_copy(self) -> bool:
        return self.status is DesktopActivityStatus.CONVERTED and self.tsv is not None


@dataclass(slots=True)
class _DesktopActivityRecord:
    view: DesktopActivityView
    decoded: DecodedFit | None = field(default=None, repr=False)
    result: ActivityConversionResult | None = field(default=None, repr=False)
    input_path: Path | None = field(default=None, repr=False)


def parse_drop_paths(
    raw_data: str,
    splitlist: Callable[[str], Sequence[str]],
) -> tuple[Path, ...]:
    """Parse a Tk drop payload without making assumptions about spaces in paths."""

    if not isinstance(raw_data, str):
        raise TypeError("raw_data must be a string")
    return tuple(Path(value) for value in splitlist(raw_data) if value)


class DesktopActivityController:
    """Coordinate engine calls while keeping the UI free of conversion rules."""

    def __init__(self) -> None:
        self._records: list[_DesktopActivityRecord] = []
        self._next_item_id = 1

    @property
    def available_qpro_keys(self) -> tuple[str, ...]:
        return tuple(sorted(QPRO_FAMILY_BY_KEY))

    @property
    def items(self) -> tuple[DesktopActivityView, ...]:
        return tuple(record.view for record in self._records)

    def process_paths(
        self,
        paths: Iterable[Path | str],
        *,
        verify_crc: bool = True,
    ) -> tuple[DesktopActivityView, ...]:
        if not isinstance(verify_crc, bool):
            raise TypeError("verify_crc must be a bool")

        added: list[DesktopActivityView] = []
        for raw_path in paths:
            path = Path(raw_path)
            try:
                sources = load_fit_sources(path)
            except Exception as exc:
                added.append(self._append_failure(path.name, None, exc, input_path=path))
                continue

            for source in sources:
                try:
                    decoded = decode_fit(source, verify_crc=verify_crc)
                    context = resolve_decoded_activity(decoded)
                except Exception as exc:
                    added.append(
                        self._append_failure(
                            path.name,
                            source,
                            exc,
                            input_path=path,
                        )
                    )
                    continue

                if (
                    context.resolution.qpro_key is None
                    or context.resolution.requires_user_choice
                ):
                    added.append(
                        self._append_pending(
                            path.name,
                            decoded,
                            context,
                            input_path=path,
                        )
                    )
                    continue

                added.append(
                    self._append_converted(
                        path.name,
                        decoded,
                        context,
                        input_path=path,
                    )
                )
        return tuple(added)

    def apply_manual_key(self, item_id: int, key: str) -> DesktopActivityView:
        record = self._record_for_id(item_id)
        if (
            record.view.status is not DesktopActivityStatus.NEEDS_KEY
            or record.decoded is None
        ):
            raise ValueError("The selected activity does not require a key")

        result = convert_decoded_activity(
            record.decoded,
            explicit_qpro_key=key,
        )
        self._validate_result_tsv(result)
        new_view = self._view_from_result(
            item_id=item_id,
            input_name=record.view.input_name,
            result=result,
            context=result.activity_context,
        )
        record.view = new_view
        record.decoded = None
        record.result = result
        return new_view

    def get_item(self, item_id: int) -> DesktopActivityView:
        return self._record_for_id(item_id).view

    def get_result(self, item_id: int) -> ActivityConversionResult | None:
        return self._record_for_id(item_id).result

    def get_input_path(self, item_id: int) -> Path | None:
        return self._record_for_id(item_id).input_path

    def tsv_for_item(self, item_id: int) -> str:
        view = self.get_item(item_id)
        if not view.can_copy or view.tsv is None:
            raise ValueError("The selected activity has no valid TSV row")
        return view.tsv

    def all_tsv(self) -> str:
        return "\n".join(
            record.view.tsv
            for record in self._records
            if record.view.can_copy and record.view.tsv is not None
        )

    def clear(self) -> None:
        self._records.clear()
        self._next_item_id = 1

    def _append_converted(
        self,
        input_name: str,
        decoded: DecodedFit,
        context: ActivityContext,
        input_path: Path,
    ) -> DesktopActivityView:
        try:
            result = convert_decoded_activity(decoded)
            self._validate_result_tsv(result)
        except Exception as exc:
            return self._append_failure(
                input_name,
                decoded.source,
                exc,
                context=context,
                input_path=input_path,
            )

        view = self._view_from_result(
            item_id=self._take_item_id(),
            input_name=input_name,
            result=result,
            context=context,
        )
        self._records.append(
            _DesktopActivityRecord(
                view=view,
                result=result,
                input_path=input_path,
            )
        )
        return view

    def _append_pending(
        self,
        input_name: str,
        decoded: DecodedFit,
        context: ActivityContext,
        input_path: Path,
    ) -> DesktopActivityView:
        view = DesktopActivityView(
            item_id=self._take_item_id(),
            input_name=input_name,
            source_name=decoded.source.source_name,
            workout_name=context.metadata.workout_name,
            sport_profile_name=context.metadata.sport_profile_name,
            qpro_key=context.resolution.qpro_key,
            resolution_source=context.resolution.resolution_source,
            status=DesktopActivityStatus.NEEDS_KEY,
            message="Selecciona una clave QPro",
            warning="La actividad no se puede clasificar de forma automatica.",
            requires_manual_review=True,
            tsv=None,
        )
        self._records.append(
            _DesktopActivityRecord(
                view=view,
                decoded=decoded,
                input_path=input_path,
            )
        )
        return view

    def _append_failure(
        self,
        input_name: str,
        source: FitSource | None,
        error: Exception,
        *,
        context: ActivityContext | None = None,
        input_path: Path | None = None,
    ) -> DesktopActivityView:
        view = DesktopActivityView(
            item_id=self._take_item_id(),
            input_name=input_name,
            source_name=source.source_name if source is not None else None,
            workout_name=context.metadata.workout_name if context else None,
            sport_profile_name=(
                context.metadata.sport_profile_name if context else None
            ),
            qpro_key=context.resolution.qpro_key if context else None,
            resolution_source=(
                context.resolution.resolution_source if context else None
            ),
            status=DesktopActivityStatus.FAILED,
            message="No se pudo procesar",
            warning=self._safe_error_text(error),
            requires_manual_review=True,
            tsv=None,
        )
        self._records.append(
            _DesktopActivityRecord(view=view, input_path=input_path)
        )
        return view

    def _view_from_result(
        self,
        *,
        item_id: int,
        input_name: str,
        result: ActivityConversionResult,
        context: ActivityContext,
    ) -> DesktopActivityView:
        warnings = list(getattr(result.metrics, "review_reasons", ()))
        warnings.extend(getattr(result.metrics, "trim_reasons", ()))
        if result.decoder_errors:
            warnings.append(
                f"El decodificador informo de {len(result.decoder_errors)} incidencia(s)."
            )
        requires_review = bool(
            getattr(result.metrics, "requires_manual_review", False)
            or result.decoder_errors
        )
        if requires_review and not warnings:
            warnings.append("La actividad necesita revision manual.")

        return DesktopActivityView(
            item_id=item_id,
            input_name=input_name,
            source_name=result.source_name,
            workout_name=context.metadata.workout_name,
            sport_profile_name=context.metadata.sport_profile_name,
            qpro_key=context.resolution.qpro_key,
            resolution_source=context.resolution.resolution_source,
            status=DesktopActivityStatus.CONVERTED,
            message="Convertida; revisar" if requires_review else "Convertida",
            warning="; ".join(warnings),
            requires_manual_review=requires_review,
            tsv=result.tsv,
        )

    @staticmethod
    def _validate_result_tsv(result: ActivityConversionResult) -> None:
        tsv = result.tsv
        if (
            not isinstance(tsv, str)
            or tsv.count("\t") != 22
            or len(tsv.split("\t")) != 23
            or "\n" in tsv
            or "\r" in tsv
        ):
            raise ValueError("The converter did not produce a 23-column TSV row")

    def _record_for_id(self, item_id: int) -> _DesktopActivityRecord:
        if isinstance(item_id, bool) or not isinstance(item_id, int):
            raise TypeError("item_id must be an integer")
        for record in self._records:
            if record.view.item_id == item_id:
                return record
        raise KeyError(item_id)

    def _take_item_id(self) -> int:
        item_id = self._next_item_id
        self._next_item_id += 1
        return item_id

    @staticmethod
    def _safe_error_text(error: Exception) -> str:
        text = str(error).strip()
        return text or error.__class__.__name__
