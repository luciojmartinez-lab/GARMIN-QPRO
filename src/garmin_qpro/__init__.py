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

__all__ = [
    "ActivityConversionResult",
    "ActivityRequiresChoiceError",
    "BatchConversionFailure",
    "BatchConversionResult",
    "MultipleFitSourcesError",
    "convert_decoded_activity",
    "convert_fit_source",
    "convert_input_directory",
    "convert_input_path",
    "convert_input_paths",
    "discover_input_paths",
]
