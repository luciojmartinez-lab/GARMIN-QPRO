"""FIT decoding and activity metadata through the official Garmin SDK."""

from .activity_metadata import (
    ActivityContext,
    ActivityMetadata,
    extract_activity_metadata,
    resolve_decoded_activity,
)
from .decoder import InvalidFitError, decode_fit
from .force_metrics import ForceMetricsRaw, extract_force_metrics
from .models import DecodedFit
from .record_segment import RecordSegmentAudit, audit_record_segment
from .running_metrics import (
    RunningMetricsRaw,
    derive_moving_time_from_records,
    extract_running_metrics,
)

__all__ = [
    "ActivityContext",
    "ActivityMetadata",
    "DecodedFit",
    "ForceMetricsRaw",
    "InvalidFitError",
    "RecordSegmentAudit",
    "RunningMetricsRaw",
    "decode_fit",
    "audit_record_segment",
    "derive_moving_time_from_records",
    "extract_running_metrics",
    "extract_activity_metadata",
    "extract_force_metrics",
    "resolve_decoded_activity",
]
