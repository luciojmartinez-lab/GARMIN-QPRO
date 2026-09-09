"""Orchestrate FIT conversion with date-matched Garmin training load."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Protocol

from garmin_qpro.conversion import MultipleFitSourcesError
from garmin_qpro.fit.activity_metadata import (
    ActivityMetadata,
    extract_activity_metadata,
)
from garmin_qpro.fit.decoder import decode_fit
from garmin_qpro.garmin_connect import (
    GarminPyTrainingLoadAdapter,
    HistoricalTrainingLoad,
)
from garmin_qpro.input.sources import FitSource, load_fit_sources

from .activity_to_qpro import (
    ActivityToQProResult,
    convert_decoded_activity_to_qpro,
)


class TrainingLoadProvider(Protocol):
    """Minimal external contract required by the orchestration service."""

    def get_for_date(self, day: date) -> HistoricalTrainingLoad:
        """Return Garmin's historical load for exactly ``day``."""


class ActivityDateUnavailableForGarminLoadError(ValueError):
    """Raised before Garmin is queried when a FIT has no reliable local date."""

    def __init__(
        self,
        *,
        source: FitSource,
        metadata: ActivityMetadata,
    ) -> None:
        self.source = source
        self.metadata = metadata
        super().__init__(
            "activity local date is unavailable; Garmin load was not queried"
        )


def convert_input_path_to_qpro_with_garmin_load(
    path: Path,
    *,
    adapter: TrainingLoadProvider | None = None,
    explicit_qpro_key: str | None = None,
    verify_crc: bool = True,
) -> ActivityToQProResult:
    """Convert one FIT/ZIP after querying its exact local-date Garmin load."""

    input_path = Path(path)
    sources = load_fit_sources(input_path)
    if len(sources) != 1:
        raise MultipleFitSourcesError(path=input_path, sources=sources)

    source = sources[0]
    decoded = decode_fit(source, verify_crc=verify_crc)
    metadata = extract_activity_metadata(decoded)
    if metadata.activity_date is None:
        raise ActivityDateUnavailableForGarminLoadError(
            source=source,
            metadata=metadata,
        )

    active_adapter = (
        adapter if adapter is not None else GarminPyTrainingLoadAdapter()
    )
    historical_training_load = active_adapter.get_for_date(
        metadata.activity_date
    )
    return convert_decoded_activity_to_qpro(
        decoded,
        historical_training_load=historical_training_load,
        explicit_qpro_key=explicit_qpro_key,
    )
