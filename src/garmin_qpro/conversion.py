"""Convert one decoded FIT activity into a Quattro Pro TSV row."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from garmin_qpro.fit.activity_metadata import (
    ActivityContext,
    resolve_decoded_activity,
)
from garmin_qpro.fit.decoder import decode_fit
from garmin_qpro.fit.force_metrics import (
    ForceMetricsRaw,
    extract_force_metrics,
)
from garmin_qpro.fit.models import DecodedFit
from garmin_qpro.fit.running_metrics import (
    RunningMetricsRaw,
    extract_running_metrics,
)
from garmin_qpro.input.sources import FitSource, load_fit_sources
from garmin_qpro.qpro.force_row import build_force_metrics_row
from garmin_qpro.qpro.row import QProRow
from garmin_qpro.qpro.rows import QProFamily, family_for_key
from garmin_qpro.qpro.running_row import build_running_row
from garmin_qpro.qpro.tsv import row_to_tsv


@dataclass(frozen=True, slots=True)
class ActivityConversionResult:
    """Complete result for one activity conversion."""

    source_name: str
    container_name: str | None
    member_path: str | None
    sha256: str
    activity_context: ActivityContext
    metrics: RunningMetricsRaw | ForceMetricsRaw
    row: QProRow
    tsv: str
    decoder_errors: tuple[object, ...]
    crc_checked: bool


class ActivityRequiresChoiceError(ValueError):
    """Raised when no safe QPro key can be selected automatically."""

    def __init__(
        self,
        *,
        source: FitSource,
        activity_context: ActivityContext,
        reason: str,
    ) -> None:
        self.source = source
        self.activity_context = activity_context
        self.qpro_key = activity_context.resolution.qpro_key
        self.reason = reason
        super().__init__(reason)


class MultipleFitSourcesError(ValueError):
    """Raised when an input path contains more than one FIT source."""

    def __init__(self, *, path: Path, sources: tuple[FitSource, ...]) -> None:
        self.path = Path(path)
        self.sources = sources
        source_names = tuple(source.source_name for source in sources)
        super().__init__(
            f"Expected exactly one FIT source in {self.path.name}; "
            f"found {len(sources)}: {source_names!r}"
        )


def convert_decoded_activity(
    decoded: DecodedFit,
    *,
    explicit_qpro_key: str | None = None,
    row_number: object | None = None,
) -> ActivityConversionResult:
    """Convert an activity; row_number is deprecated and ignored."""

    if not isinstance(decoded, DecodedFit):
        raise TypeError("decoded must be a DecodedFit")
    if explicit_qpro_key is not None and not isinstance(explicit_qpro_key, str):
        raise TypeError("explicit_qpro_key must be a string or None")

    activity_context = resolve_decoded_activity(
        decoded,
        explicit_qpro_key=explicit_qpro_key,
    )
    resolution = activity_context.resolution
    if resolution.qpro_key is None or resolution.requires_user_choice:
        raise ActivityRequiresChoiceError(
            source=decoded.source,
            activity_context=activity_context,
            reason="Activity requires a manual QPro key choice",
        )

    family = family_for_key(resolution.qpro_key)
    if family is QProFamily.RUNNING:
        metrics: RunningMetricsRaw | ForceMetricsRaw = (
            extract_running_metrics(
                decoded,
                qpro_key=resolution.qpro_key,
            )
        )
        row = build_running_row(resolution.qpro_key, metrics)
    else:
        metrics = extract_force_metrics(decoded)
        row = build_force_metrics_row(
            resolution.qpro_key,
            metrics,
        )

    tsv = row_to_tsv(row)
    return ActivityConversionResult(
        source_name=decoded.source.source_name,
        container_name=decoded.source.container_name,
        member_path=decoded.source.member_path,
        sha256=decoded.source.sha256,
        activity_context=activity_context,
        metrics=metrics,
        row=row,
        tsv=tsv,
        decoder_errors=decoded.errors,
        crc_checked=decoded.crc_checked,
    )


def convert_input_path(
    path: Path,
    *,
    explicit_qpro_key: str | None = None,
    verify_crc: bool = True,
    row_number: object | None = None,
) -> ActivityConversionResult:
    """Load and convert one FIT; row_number is deprecated and ignored."""

    if explicit_qpro_key is not None and not isinstance(explicit_qpro_key, str):
        raise TypeError("explicit_qpro_key must be a string or None")
    if not isinstance(verify_crc, bool):
        raise TypeError("verify_crc must be a boolean")

    input_path = Path(path)
    sources = load_fit_sources(input_path)
    if len(sources) != 1:
        raise MultipleFitSourcesError(path=input_path, sources=sources)

    return convert_fit_source(
        sources[0],
        explicit_qpro_key=explicit_qpro_key,
        verify_crc=verify_crc,
        row_number=row_number,
    )


def convert_fit_source(
    source: FitSource,
    *,
    explicit_qpro_key: str | None = None,
    verify_crc: bool = True,
    row_number: object | None = None,
) -> ActivityConversionResult:
    """Decode and convert one FIT; row_number is deprecated and ignored."""

    if not isinstance(source, FitSource):
        raise TypeError("source must be a FitSource")
    if explicit_qpro_key is not None and not isinstance(explicit_qpro_key, str):
        raise TypeError("explicit_qpro_key must be a string or None")
    if not isinstance(verify_crc, bool):
        raise TypeError("verify_crc must be a boolean")

    decoded = decode_fit(source, verify_crc=verify_crc)
    return convert_decoded_activity(
        decoded,
        explicit_qpro_key=explicit_qpro_key,
        row_number=row_number,
    )
