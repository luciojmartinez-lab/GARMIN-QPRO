"""Conservative GPS speed-peak filtering for soft running-family activities."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from statistics import median
from typing import Any, Literal

SOFT_SPEED_FILTER_KEYS = frozenset(
    {"AQG", "CAM", "CAL", "CLP", "FIN", "FPN", "MOV", "PLY"}
)

SUSPICIOUS_MAX_TO_AVERAGE_RATIO = 3.0
HIGH_CLUSTER_RATIO = 0.75
MIN_SUSTAINED_SUPPORTED_SAMPLES = 3
MIN_CONTINUITY_GAP_S = 2.0
MAX_CONTINUITY_GAP_S = 30.0
CONTINUITY_GAP_MULTIPLIER = 3.0
SPEED_SUPPORT_REL_TOLERANCE = 0.35
SPEED_SUPPORT_ABS_TOLERANCE_MPS = 0.75
ORIGINAL_MAX_REL_TOLERANCE = 0.02
ORIGINAL_MAX_ABS_TOLERANCE_MPS = 0.05


@dataclass(frozen=True, slots=True)
class SpeedFilterResult:
    """A record-backed maximum and whether its selection needs review."""

    max_speed_mps: float | None
    requires_manual_review: bool
    discarded_speeds_mps: tuple[float, ...] = ()


@dataclass(frozen=True, slots=True)
class _SpeedSample:
    order: int
    timestamp_s: float
    speed_mps: float
    distance_m: float | None


def _finite_float(value: Any) -> float | None:
    if (
        not isinstance(value, (int, float, Decimal))
        or isinstance(value, bool)
    ):
        return None
    parsed = float(value)
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def _timestamp_seconds(value: Any) -> float | None:
    if isinstance(value, datetime):
        try:
            return value.timestamp()
        except (OSError, OverflowError, ValueError):
            return None
    return _finite_float(value)


def _record_samples(records: Iterable[Any]) -> tuple[_SpeedSample, ...]:
    samples: list[_SpeedSample] = []
    for order, record in enumerate(records):
        if not isinstance(record, Mapping):
            continue
        timestamp = _timestamp_seconds(record.get("timestamp"))
        speed = _finite_float(record.get("enhanced_speed"))
        if speed is None:
            speed = _finite_float(record.get("speed"))
        if timestamp is None or speed is None or speed < 0:
            continue
        distance = _finite_float(record.get("distance"))
        if distance is not None and distance < 0:
            distance = None
        samples.append(
            _SpeedSample(
                order=order,
                timestamp_s=timestamp,
                speed_mps=speed,
                distance_m=distance,
            )
        )
    return tuple(
        sorted(samples, key=lambda sample: (sample.timestamp_s, sample.order))
    )


def _continuity_gap(samples: tuple[_SpeedSample, ...]) -> float | None:
    gaps = [
        current.timestamp_s - previous.timestamp_s
        for previous, current in zip(samples, samples[1:])
        if current.timestamp_s > previous.timestamp_s
    ]
    if not gaps:
        return None
    return min(
        MAX_CONTINUITY_GAP_S,
        max(
            MIN_CONTINUITY_GAP_S,
            median(gaps) * CONTINUITY_GAP_MULTIPLIER,
        ),
    )


def _interval_rates(
    samples: tuple[_SpeedSample, ...],
    *,
    max_gap_s: float,
) -> tuple[float | None, ...]:
    rates: list[float | None] = []
    for previous, current in zip(samples, samples[1:]):
        gap = current.timestamp_s - previous.timestamp_s
        if (
            gap <= 0
            or gap > max_gap_s
            or previous.distance_m is None
            or current.distance_m is None
        ):
            rates.append(None)
            continue
        distance_delta = current.distance_m - previous.distance_m
        rates.append(
            distance_delta / gap if distance_delta >= 0 else None
        )
    return tuple(rates)


def _speeds_are_coherent(
    measured_speed: float,
    distance_rate: float,
) -> bool:
    tolerance = max(
        SPEED_SUPPORT_ABS_TOLERANCE_MPS,
        measured_speed * SPEED_SUPPORT_REL_TOLERANCE,
    )
    return abs(measured_speed - distance_rate) <= tolerance


def _sample_is_supported(
    position: int,
    samples: tuple[_SpeedSample, ...],
    interval_rates: tuple[float | None, ...],
) -> bool:
    neighboring_rates = []
    if position > 0:
        neighboring_rates.append(interval_rates[position - 1])
    if position < len(samples) - 1:
        neighboring_rates.append(interval_rates[position])
    return any(
        rate is not None
        and _speeds_are_coherent(samples[position].speed_mps, rate)
        for rate in neighboring_rates
    )


def _sample_has_spatial_discontinuity(
    position: int,
    samples: tuple[_SpeedSample, ...],
    interval_rates: tuple[float | None, ...],
) -> bool:
    if position == 0 or position == len(samples) - 1:
        return False
    before = interval_rates[position - 1]
    after = interval_rates[position]
    if before is None or after is None:
        return False
    speed = samples[position].speed_mps
    return not _speeds_are_coherent(
        speed,
        before,
    ) and not _speeds_are_coherent(speed, after)


def _cluster_for_candidate(
    position: int,
    samples: tuple[_SpeedSample, ...],
    *,
    max_gap_s: float,
) -> tuple[int, int]:
    threshold = samples[position].speed_mps * HIGH_CLUSTER_RATIO
    left = position
    while left > 0:
        gap = samples[left].timestamp_s - samples[left - 1].timestamp_s
        if gap > max_gap_s or samples[left - 1].speed_mps < threshold:
            break
        left -= 1
    right = position
    while right < len(samples) - 1:
        gap = samples[right + 1].timestamp_s - samples[right].timestamp_s
        if gap > max_gap_s or samples[right + 1].speed_mps < threshold:
            break
        right += 1
    return left, right


def _classify_candidate(
    position: int,
    samples: tuple[_SpeedSample, ...],
    interval_rates: tuple[float | None, ...],
    *,
    max_gap_s: float,
) -> tuple[Literal["valid", "invalid", "unknown"], tuple[int, ...]]:
    left, right = _cluster_for_candidate(
        position,
        samples,
        max_gap_s=max_gap_s,
    )
    cluster = tuple(range(left, right + 1))
    supported_count = sum(
        _sample_is_supported(index, samples, interval_rates)
        for index in cluster
    )
    if supported_count >= MIN_SUSTAINED_SUPPORTED_SAMPLES:
        return "valid", cluster

    threshold = samples[position].speed_mps * HIGH_CLUSTER_RATIO
    left_is_bounded = (
        left > 0
        and samples[left].timestamp_s - samples[left - 1].timestamp_s
        <= max_gap_s
        and samples[left - 1].speed_mps < threshold
    )
    right_is_bounded = (
        right < len(samples) - 1
        and samples[right + 1].timestamp_s - samples[right].timestamp_s
        <= max_gap_s
        and samples[right + 1].speed_mps < threshold
    )
    has_discontinuity = any(
        _sample_has_spatial_discontinuity(
            index,
            samples,
            interval_rates,
        )
        for index in cluster
    )
    if left_is_bounded and right_is_bounded and has_discontinuity:
        return "invalid", cluster
    return "unknown", cluster


def filter_soft_activity_max_speed(
    records: Iterable[Any],
    *,
    original_max_speed_mps: Any,
    average_speed_mps: Any,
) -> SpeedFilterResult:
    """Return a conservative record-backed maximum for a soft activity."""

    original_max = _finite_float(original_max_speed_mps)
    average_speed = _finite_float(average_speed_mps)
    if original_max is None or original_max < 0:
        return SpeedFilterResult(original_max, True)
    if average_speed is None or average_speed <= 0:
        return SpeedFilterResult(original_max, True)

    samples = _record_samples(records)
    max_gap = _continuity_gap(samples)
    if len(samples) < 3 or max_gap is None:
        return SpeedFilterResult(original_max, True)

    record_max = max(sample.speed_mps for sample in samples)
    summary_is_record_backed = (
        abs(record_max - original_max)
        <= max(
            ORIGINAL_MAX_ABS_TOLERANCE_MPS,
            original_max * ORIGINAL_MAX_REL_TOLERANCE,
        )
    )
    candidate_max = original_max if summary_is_record_backed else record_max
    if candidate_max <= average_speed * SUSPICIOUS_MAX_TO_AVERAGE_RATIO:
        return SpeedFilterResult(candidate_max, False)

    interval_rates = _interval_rates(samples, max_gap_s=max_gap)
    excluded: set[int] = set()
    discarded: list[float] = []
    ordered_positions = sorted(
        range(len(samples)),
        key=lambda index: (-samples[index].speed_mps, index),
    )
    for position in ordered_positions:
        if position in excluded:
            continue
        classification, cluster = _classify_candidate(
            position,
            samples,
            interval_rates,
            max_gap_s=max_gap,
        )
        if classification == "valid":
            return SpeedFilterResult(
                samples[position].speed_mps,
                False,
                tuple(discarded),
            )
        if classification == "invalid":
            excluded.update(cluster)
            discarded.extend(
                samples[index].speed_mps for index in cluster
            )
            continue
        fallback = (
            samples[position].speed_mps if discarded else original_max
        )
        return SpeedFilterResult(
            fallback,
            True,
            tuple(discarded),
        )

    return SpeedFilterResult(original_max, True, tuple(discarded))
