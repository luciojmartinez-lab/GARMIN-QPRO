"""FIT decoding and activity metadata through the official Garmin SDK."""

from .activity_metadata import (
    ActivityContext,
    ActivityMetadata,
    extract_activity_metadata,
    resolve_decoded_activity,
)
from .decoder import InvalidFitError, decode_fit
from .models import DecodedFit

__all__ = [
    "ActivityContext",
    "ActivityMetadata",
    "DecodedFit",
    "InvalidFitError",
    "decode_fit",
    "extract_activity_metadata",
    "resolve_decoded_activity",
]
