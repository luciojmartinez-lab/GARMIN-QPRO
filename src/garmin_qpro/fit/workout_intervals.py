"""Select running laps linked to active Garmin workout steps."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType
from typing import Any

from garmin_qpro.fit.models import DecodedFit


@dataclass(frozen=True, slots=True)
class WorkoutIntervalSelection:
    """Immutable active-step indices and their linked running laps."""

    active_step_indices: tuple[int, ...]
    laps: tuple[Mapping[Any, Any], ...]

    @property
    def count(self) -> int:
        return len(self.laps)


def _message_index(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    if not isfinite(parsed) or parsed < 0 or not parsed.is_integer():
        return None
    return int(parsed)


def _normalized_intensity(message: Mapping[Any, Any]) -> str:
    intensity = message.get("intensity")
    return intensity.strip().casefold() if isinstance(intensity, str) else ""


def _ordered_messages(
    messages: tuple[object, ...],
) -> tuple[Mapping[Any, Any], ...]:
    valid = tuple(
        (order, message)
        for order, message in enumerate(messages)
        if isinstance(message, Mapping)
    )
    ordered = sorted(
        valid,
        key=lambda item: (
            _message_index(item[1].get("message_index")) is None,
            (
                _message_index(item[1].get("message_index"))
                if _message_index(item[1].get("message_index")) is not None
                else item[0]
            ),
            item[0],
        ),
    )
    return tuple(
        MappingProxyType(dict(message))
        for _, message in ordered
    )


def select_running_workout_intervals(
    decoded: DecodedFit,
    *,
    limit: int | None = None,
) -> WorkoutIntervalSelection:
    """Select active laps whose workout-step index points to an active step."""

    if not isinstance(decoded, DecodedFit):
        raise TypeError("decoded must be a DecodedFit")
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("limit must be an integer or None")
        if limit <= 0:
            raise ValueError("limit must be positive")

    steps = _ordered_messages(decoded.get_messages("workout_step"))
    active_step_indices = tuple(
        index
        for step in steps
        if _normalized_intensity(step) == "active"
        if (index := _message_index(step.get("message_index"))) is not None
    )
    active_step_set = frozenset(active_step_indices)

    selected = tuple(
        lap
        for lap in _ordered_messages(decoded.get_messages("lap"))
        if _normalized_intensity(lap) == "active"
        if _message_index(lap.get("wkt_step_index")) in active_step_set
    )
    if limit is not None:
        selected = selected[:limit]

    return WorkoutIntervalSelection(
        active_step_indices=active_step_indices,
        laps=selected,
    )
