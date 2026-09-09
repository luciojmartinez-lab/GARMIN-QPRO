"""Isolated adapters for optional Garmin Connect data sources."""

from .training_load import (
    GarminPyQueryError,
    GarminPyResponseError,
    GarminPyTrainingLoadAdapter,
    GarminPyUnavailableError,
    HistoricalTrainingLoad,
    TrainingLoadAdapterError,
)

__all__ = [
    "GarminPyQueryError",
    "GarminPyResponseError",
    "GarminPyTrainingLoadAdapter",
    "GarminPyUnavailableError",
    "HistoricalTrainingLoad",
    "TrainingLoadAdapterError",
]
