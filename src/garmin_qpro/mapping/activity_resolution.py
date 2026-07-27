"""Resolve an activity using explicit, workout, then sport-profile evidence."""

from dataclasses import dataclass
from typing import Final

from garmin_qpro.qpro.rows import family_for_key

from .workout_names import resolve_workout_name

EXPLICIT_QPRO_KEY_SOURCE: Final[str] = "explicit_qpro_key"
WORKOUT_NAME_SOURCE: Final[str] = "workout_name"
SPORT_PROFILE_NAME_SOURCE: Final[str] = "sport_profile_name"

_RUNNING_PROFILES: Final[frozenset[str]] = frozenset(
    {
        "carrera",
        "running",
    }
)


@dataclass(frozen=True, slots=True)
class ActivityResolution:
    """Immutable result of the controlled activity-resolution cascade."""

    workout_name: str | None
    sport_profile_name: str | None
    qpro_key: str | None
    resolution_source: str | None
    requires_user_choice: bool


def _validate_optional_text(value: str | None, field_name: str) -> None:
    if value is not None and not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or None")


def _resolved(
    *,
    workout_name: str | None,
    sport_profile_name: str | None,
    qpro_key: str,
    resolution_source: str,
) -> ActivityResolution:
    normalized_key = qpro_key.strip().upper()
    family_for_key(normalized_key)
    return ActivityResolution(
        workout_name=workout_name,
        sport_profile_name=sport_profile_name,
        qpro_key=normalized_key,
        resolution_source=resolution_source,
        requires_user_choice=False,
    )


def resolve_activity(
    *,
    workout_name: str | None,
    sport_profile_name: str | None,
    explicit_qpro_key: str | None = None,
) -> ActivityResolution:
    """Resolve an activity without applying a general default key."""

    _validate_optional_text(workout_name, "workout_name")
    _validate_optional_text(sport_profile_name, "sport_profile_name")
    _validate_optional_text(explicit_qpro_key, "explicit_qpro_key")

    if explicit_qpro_key is not None:
        return _resolved(
            workout_name=workout_name,
            sport_profile_name=sport_profile_name,
            qpro_key=explicit_qpro_key,
            resolution_source=EXPLICIT_QPRO_KEY_SOURCE,
        )

    if workout_name is not None:
        workout_resolution = resolve_workout_name(workout_name)
        if workout_resolution.qpro_key is not None:
            return _resolved(
                workout_name=workout_name,
                sport_profile_name=sport_profile_name,
                qpro_key=workout_resolution.qpro_key,
                resolution_source=WORKOUT_NAME_SOURCE,
            )

    normalized_profile = (
        sport_profile_name.strip().casefold()
        if sport_profile_name is not None
        else ""
    )
    if normalized_profile in _RUNNING_PROFILES:
        return _resolved(
            workout_name=workout_name,
            sport_profile_name=sport_profile_name,
            qpro_key="ENT",
            resolution_source=SPORT_PROFILE_NAME_SOURCE,
        )

    return ActivityResolution(
        workout_name=workout_name,
        sport_profile_name=sport_profile_name,
        qpro_key=None,
        resolution_source=None,
        requires_user_choice=True,
    )
