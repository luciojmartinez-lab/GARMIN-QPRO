"""Adapt raw force metrics to the approved Quattro Pro force template."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from garmin_qpro.fit.force_metrics import ForceMetricsRaw

from .row import InvalidForceKeyError, QProRow, build_force_row
from .rows import QProFamily, family_for_key


def _finite_number(value: Any, field_name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float, Decimal))
    ):
        raise TypeError(f"{field_name} must be a number")
    parsed = float(value)
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        raise ValueError(f"{field_name} must be finite")
    return parsed


def _optional_non_negative_number(
    value: Any,
    field_name: str,
) -> float | None:
    if value is None:
        return None
    parsed = _finite_number(value, field_name)
    if parsed < 0:
        raise ValueError(f"{field_name} must not be negative")
    return parsed


def _optional_non_negative_integer(
    value: Any,
    field_name: str,
) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")
    return value


def _validate_metrics(metrics: ForceMetricsRaw) -> None:
    _optional_non_negative_number(metrics.timer_time_s, "timer_time_s")
    _optional_non_negative_number(metrics.elapsed_time_s, "elapsed_time_s")
    _optional_non_negative_integer(metrics.avg_hr_bpm, "avg_hr_bpm")
    _optional_non_negative_integer(metrics.max_hr_bpm, "max_hr_bpm")
    _optional_non_negative_number(metrics.aerobic_te, "aerobic_te")
    _optional_non_negative_number(metrics.anaerobic_te, "anaerobic_te")
    _optional_non_negative_number(metrics.exercise_load, "exercise_load")


def build_force_metrics_row(
    key: str,
    row_number: object | ForceMetricsRaw | None = None,
    metrics: ForceMetricsRaw | None = None,
) -> QProRow:
    """Build a force row; the former row_number argument is ignored."""

    family = family_for_key(key)
    if family is not QProFamily.FORCE:
        raise InvalidForceKeyError(key)
    if metrics is None and isinstance(row_number, ForceMetricsRaw):
        metrics = row_number
    if not isinstance(metrics, ForceMetricsRaw):
        raise TypeError("metrics must be a ForceMetricsRaw")
    _validate_metrics(metrics)

    minutes = (
        metrics.timer_time_s / 60
        if metrics.timer_time_s is not None
        else None
    )
    return build_force_row(
        key,
        ppme=metrics.avg_hr_bpm,
        ppmax=metrics.max_hr_bpm,
        minutes=minutes,
        aer=metrics.aerobic_te,
        ana=metrics.anaerobic_te,
        exercise_load=metrics.exercise_load,
    )
