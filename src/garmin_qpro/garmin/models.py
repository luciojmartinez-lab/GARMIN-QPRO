"""Minimal immutable models for safe Garmin Connect reads."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from math import isfinite
from typing import Any

from garmin_qpro.input.sources import FitSource


def normalize_activity_id(value: str | int) -> str:
    """Return a non-empty ASCII numeric Garmin activity identifier."""

    if isinstance(value, bool):
        raise TypeError("activity_id cannot be boolean")
    if isinstance(value, int):
        normalized = str(value)
    elif isinstance(value, str):
        normalized = value.strip()
    else:
        raise TypeError("activity_id must be a string or integer")
    if not normalized or not normalized.isascii() or not normalized.isdecimal():
        raise ValueError("activity_id must be non-empty numeric text")
    return normalized


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be text or None")
    normalized = value.strip()
    return normalized or None


def _optional_number(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(
        value,
        (int, float, Decimal),
    ):
        raise TypeError(f"{field_name} must be numeric or None")
    parsed = float(value)
    if not isfinite(parsed) or parsed < 0:
        raise ValueError(f"{field_name} must be finite and non-negative")
    return parsed


@dataclass(frozen=True, slots=True)
class GarminActivitySummary:
    """Only the recent-activity fields required by GARMIN-QPRO."""

    activity_id: str
    name: str
    activity_type: str | None
    start_time_local: str | None
    duration_s: float | None
    elapsed_duration_s: float | None
    distance_m: float | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "activity_id",
            normalize_activity_id(self.activity_id),
        )
        if not isinstance(self.name, str):
            raise TypeError("name must be text")
        object.__setattr__(
            self,
            "activity_type",
            _optional_text(self.activity_type, "activity_type"),
        )
        object.__setattr__(
            self,
            "start_time_local",
            _optional_text(self.start_time_local, "start_time_local"),
        )
        object.__setattr__(
            self,
            "duration_s",
            _optional_number(self.duration_s, "duration_s"),
        )
        object.__setattr__(
            self,
            "elapsed_duration_s",
            _optional_number(
                self.elapsed_duration_s,
                "elapsed_duration_s",
            ),
        )
        object.__setattr__(
            self,
            "distance_m",
            _optional_number(self.distance_m, "distance_m"),
        )

    @classmethod
    def from_mapping(
        cls,
        activity: Mapping[str, Any],
    ) -> GarminActivitySummary:
        """Build a summary without retaining the remote response mapping."""

        if not isinstance(activity, Mapping):
            raise TypeError("activity must be a mapping")
        raw_name = activity.get("activityName")
        if raw_name is None:
            name = ""
        elif isinstance(raw_name, str):
            name = raw_name
        else:
            raise TypeError("activityName must be text or None")

        raw_type = activity.get("activityType")
        if raw_type is None:
            activity_type = None
        elif isinstance(raw_type, Mapping):
            activity_type = raw_type.get("typeKey")
        else:
            raise TypeError("activityType must be a mapping or None")

        return cls(
            activity_id=activity.get("activityId"),
            name=name,
            activity_type=activity_type,
            start_time_local=activity.get("startTimeLocal"),
            duration_s=activity.get("duration"),
            elapsed_duration_s=activity.get("elapsedDuration"),
            distance_m=activity.get("distance"),
        )


@dataclass(frozen=True, slots=True)
class GarminActivityDownload:
    """Identity and FIT sources from one original in-memory ZIP download."""

    activity_id: str
    container_name: str
    archive_sha256: str
    archive_size: int
    sources: tuple[FitSource, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "activity_id",
            normalize_activity_id(self.activity_id),
        )
        if not isinstance(self.container_name, str):
            raise TypeError("container_name must be text")
        normalized_container = self.container_name.strip()
        if not normalized_container:
            raise ValueError("container_name cannot be empty")
        object.__setattr__(self, "container_name", normalized_container)
        if not isinstance(self.archive_sha256, str):
            raise TypeError("archive_sha256 must be text")
        if isinstance(self.archive_size, bool) or not isinstance(
            self.archive_size,
            int,
        ):
            raise TypeError("archive_size must be an integer")
        if self.archive_size < 0:
            raise ValueError("archive_size cannot be negative")
        frozen_sources = tuple(self.sources)
        if not all(isinstance(source, FitSource) for source in frozen_sources):
            raise TypeError("sources must contain FitSource values")
        object.__setattr__(self, "sources", frozen_sources)
