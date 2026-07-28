"""Build Quattro Pro rows for running-family activities."""

from __future__ import annotations

from dataclasses import fields
from decimal import Decimal
from typing import Any

from garmin_qpro.fit.running_metrics import RunningMetricsRaw

from .formatter import (
    empty_or_formatted,
    format_decimal,
    format_text_decimal,
    format_text_integer,
    format_text_pace,
)
from .formulas import build_vmax_ms_formula, build_vmed_ms_formula
from .row import QProRow
from .rows import QProFamily, family_for_key
from .schema import QPRO_COLUMNS


class InvalidRunningKeyError(ValueError):
    """Raised when a known key does not belong to the running family."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"Quattro Pro key is not a running key: {key!r}")


def _normalize_running_key(key: str) -> str:
    family = family_for_key(key)
    if family is not QProFamily.RUNNING:
        raise InvalidRunningKeyError(key)
    return key.strip().upper()


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float, Decimal)) and not isinstance(
        value,
        bool,
    )


def _finite_float(value: Any, field_name: str) -> float:
    if not _is_number(value):
        raise TypeError(f"{field_name} must be a number")
    parsed = float(value)
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        raise ValueError(f"{field_name} must be finite")
    return parsed


def _optional_non_negative(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    parsed = _finite_float(value, field_name)
    if parsed < 0:
        raise ValueError(f"{field_name} must not be negative")
    return parsed


def _validate_metrics(metrics: RunningMetricsRaw) -> None:
    for field in fields(RunningMetricsRaw):
        if field.name in {
            "source_scope",
            "warmup_lap_count",
            "requires_manual_review",
        }:
            continue
        _optional_non_negative(getattr(metrics, field.name), field.name)


def _positive_pair(first: float | None, second: float | None) -> bool:
    return first is not None and second is not None and first > 0 and second > 0


def _running_speed_kmh(metrics: RunningMetricsRaw) -> float | None:
    distance = _optional_non_negative(metrics.distance_m, "distance_m")
    moving_time = _optional_non_negative(metrics.moving_time_s, "moving_time_s")
    if not _positive_pair(distance, moving_time):
        return None
    return (distance / moving_time) * 3.6


def _pace_seconds_per_km(metrics: RunningMetricsRaw) -> float | None:
    distance = _optional_non_negative(metrics.distance_m, "distance_m")
    moving_time = _optional_non_negative(metrics.moving_time_s, "moving_time_s")
    if not _positive_pair(distance, moving_time):
        return None
    return moving_time / (distance / 1000)


def _cadence_spm(cadence_raw: float | None) -> float | None:
    cadence = _optional_non_negative(cadence_raw, "cadence_raw")
    if cadence is None:
        return None
    if cadence <= 120:
        return cadence * 2
    return cadence


def _rounded_text_integer(value: float | None) -> str:
    return empty_or_formatted(value, format_text_integer)


def build_running_row(
    key: str,
    row_number: int,
    metrics: RunningMetricsRaw,
) -> QProRow:
    """Build a 23-column Quattro Pro row from raw running metrics."""

    normalized_key = _normalize_running_key(key)
    if not isinstance(metrics, RunningMetricsRaw):
        raise TypeError("metrics must be a RunningMetricsRaw")
    _validate_metrics(metrics)

    vmed_kmh = _running_speed_kmh(metrics)
    pace_seconds = _pace_seconds_per_km(metrics)
    moving_minutes = (
        metrics.moving_time_s / 60 if metrics.moving_time_s is not None else None
    )

    values = {
        "CODIGO": normalized_key,
        "RMED": "",
        "VMED": empty_or_formatted(
            vmed_kmh,
            lambda value: format_decimal(value, 2),
        ),
        "VMED_M_S": build_vmed_ms_formula(row_number),
        "RMAX": "",
        "VMAX": empty_or_formatted(
            metrics.max_speed_mps,
            lambda value: format_decimal(value * 3.6, 2),
        ),
        "VMAX_M_S": build_vmax_ms_formula(row_number),
        "DISTANCIA": empty_or_formatted(
            metrics.distance_m,
            lambda value: format_decimal(value / 1000, 2),
        ),
        "PPME": _rounded_text_integer(metrics.avg_hr_bpm),
        "PPMAX": _rounded_text_integer(metrics.max_hr_bpm),
        "MIN": _rounded_text_integer(moving_minutes),
        "RITMO": empty_or_formatted(pace_seconds, format_text_pace),
        "AER": empty_or_formatted(
            metrics.aerobic_te,
            lambda value: format_decimal(value, 1),
        ),
        "ANA": empty_or_formatted(
            metrics.anaerobic_te,
            lambda value: format_decimal(value, 1),
        ),
        "CADM": _rounded_text_integer(_cadence_spm(metrics.avg_cadence_raw)),
        "CADX": _rounded_text_integer(_cadence_spm(metrics.max_cadence_raw)),
        "ZAN": empty_or_formatted(
            metrics.avg_step_length_mm,
            lambda value: format_decimal(value / 1000, 2),
        ),
        "TCS": _rounded_text_integer(metrics.avg_stance_time_ms),
        "CARGA": _rounded_text_integer(metrics.exercise_load),
        "PTM": _rounded_text_integer(metrics.avg_power_w),
        "PTX": _rounded_text_integer(metrics.max_power_w),
        "RVM": empty_or_formatted(
            metrics.avg_vertical_ratio_pct,
            lambda value: format_text_decimal(value, 1, width=2),
        ),
        "OVM": empty_or_formatted(
            metrics.avg_vertical_oscillation_mm,
            lambda value: format_text_decimal(value / 10, 1, width=2),
        ),
    }
    return QProRow(values[column] for column in QPRO_COLUMNS)
