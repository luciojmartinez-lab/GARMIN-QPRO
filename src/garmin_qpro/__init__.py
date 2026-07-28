"""GARMIN-QPRO package."""

from .batch import (
    BatchConversionFailure,
    BatchConversionResult,
    convert_input_directory,
    convert_input_paths,
    discover_input_paths,
)
from .conversion import (
    ActivityConversionResult,
    ActivityRequiresChoiceError,
    MultipleFitSourcesError,
    convert_decoded_activity,
    convert_fit_source,
    convert_input_path,
)
from .garmin import (
    GarminActivityDownload,
    GarminActivitySummary,
    GarminAuthenticationError,
    GarminConnectReader,
    GarminConnectionError,
    GarminIntegrationUnavailableError,
    GarminResponseError,
    connect_garmin,
)
from .input import load_zip_fit_sources_bytes

__all__ = [
    "ActivityConversionResult",
    "ActivityRequiresChoiceError",
    "BatchConversionFailure",
    "BatchConversionResult",
    "GarminActivityDownload",
    "GarminActivitySummary",
    "GarminAuthenticationError",
    "GarminConnectReader",
    "GarminConnectionError",
    "GarminIntegrationUnavailableError",
    "GarminResponseError",
    "MultipleFitSourcesError",
    "connect_garmin",
    "convert_decoded_activity",
    "convert_fit_source",
    "convert_input_directory",
    "convert_input_path",
    "convert_input_paths",
    "discover_input_paths",
    "load_zip_fit_sources_bytes",
]
