"""Compose approved FIT conversion and optional training-load enrichment."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from garmin_qpro.conversion import (
    ActivityConversionResult,
    convert_decoded_activity,
    convert_input_path,
)
from garmin_qpro.fit.activity_metadata import ActivityContext
from garmin_qpro.fit.force_metrics import ForceMetricsRaw
from garmin_qpro.fit.models import DecodedFit
from garmin_qpro.fit.running_metrics import RunningMetricsRaw
from garmin_qpro.garmin_connect import HistoricalTrainingLoad
from garmin_qpro.qpro.row import QProRow
from garmin_qpro.qpro.rows import QProFamily, family_for_key
from garmin_qpro.qpro.training_load import (
    QProRowWithTrainingLoad,
    enrich_qpro_row_with_training_load,
)
from garmin_qpro.qpro.tsv import row_to_tsv


@dataclass(frozen=True, slots=True)
class ActivityToQProResult:
    """A resolved base conversion and its final 25-column QPro output."""

    qpro_key: str
    family: QProFamily
    activity_context: ActivityContext
    metrics: RunningMetricsRaw | ForceMetricsRaw
    base_row: QProRow
    final_row: QProRowWithTrainingLoad
    tsv: str


class HistoricalTrainingLoadDateError(ValueError):
    """Raised when training load cannot be tied to the activity's local date."""

    def __init__(
        self,
        *,
        activity_date: date | None,
        training_load_date: date,
        reason: str,
    ) -> None:
        self.activity_date = activity_date
        self.training_load_date = training_load_date
        self.reason = reason
        super().__init__(reason)


def _compose_final_result(
    conversion: ActivityConversionResult,
    historical_training_load: HistoricalTrainingLoad | None,
) -> ActivityToQProResult:
    resolution = conversion.activity_context.resolution
    qpro_key = resolution.qpro_key
    if qpro_key is None:
        raise ValueError("conversion did not resolve a QPro key")

    if historical_training_load is None:
        final_row = QProRowWithTrainingLoad(
            base_row=conversion.row,
            acute_load_cell="",
            chronic_load_cell="",
        )
    else:
        if not isinstance(historical_training_load, HistoricalTrainingLoad):
            raise TypeError(
                "historical_training_load must be a "
                "HistoricalTrainingLoad or None"
            )
        activity_date = conversion.activity_context.metadata.activity_date
        if activity_date is None:
            raise HistoricalTrainingLoadDateError(
                activity_date=None,
                training_load_date=historical_training_load.date,
                reason="activity local date is unavailable",
            )
        if historical_training_load.date != activity_date:
            raise HistoricalTrainingLoadDateError(
                activity_date=activity_date,
                training_load_date=historical_training_load.date,
                reason="training load date does not match activity date",
            )
        final_row = enrich_qpro_row_with_training_load(
            conversion.row,
            historical_training_load,
        )

    tsv = "\t".join(
        (
            row_to_tsv(conversion.row),
            final_row.acute_load_cell,
            final_row.chronic_load_cell,
        )
    )
    return ActivityToQProResult(
        qpro_key=qpro_key,
        family=family_for_key(qpro_key),
        activity_context=conversion.activity_context,
        metrics=conversion.metrics,
        base_row=conversion.row,
        final_row=final_row,
        tsv=tsv,
    )


def convert_decoded_activity_to_qpro(
    decoded: DecodedFit,
    *,
    historical_training_load: HistoricalTrainingLoad | None = None,
    explicit_qpro_key: str | None = None,
) -> ActivityToQProResult:
    """Convert one decoded FIT through the approved family-specific path."""

    conversion = convert_decoded_activity(
        decoded,
        explicit_qpro_key=explicit_qpro_key,
    )
    return _compose_final_result(conversion, historical_training_load)


def convert_input_path_to_qpro(
    path: Path,
    *,
    historical_training_load: HistoricalTrainingLoad | None = None,
    explicit_qpro_key: str | None = None,
    verify_crc: bool = True,
) -> ActivityToQProResult:
    """Load one FIT/ZIP and compose its final 25-column QPro output."""

    conversion = convert_input_path(
        path,
        explicit_qpro_key=explicit_qpro_key,
        verify_crc=verify_crc,
    )
    return _compose_final_result(conversion, historical_training_load)
