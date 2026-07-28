"""Extract FIT activity metadata and resolve it to Quattro Pro context."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from garmin_qpro.fit.models import DecodedFit
from garmin_qpro.mapping.activity_resolution import (
    ActivityResolution,
    resolve_activity,
)


@dataclass(frozen=True, slots=True)
class ActivityMetadata:
    """FIT metadata used to identify a Garmin activity safely."""

    workout_name: str | None
    workout_name_field: str | None
    sport_profile_name: str | None
    sport: str | None
    sub_sport: str | None


@dataclass(frozen=True, slots=True)
class ActivityContext:
    """Activity metadata plus its controlled Quattro Pro resolution."""

    metadata: ActivityMetadata
    resolution: ActivityResolution


def _clean_text(value: Any) -> str | None:
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace").replace("\x00", "")
    elif isinstance(value, str):
        text = value.replace("\x00", "")
    elif isinstance(value, (list, tuple)):
        for item in value:
            text = _clean_text(item)
            if text is not None:
                return text
        return None
    else:
        return None

    stripped = text.strip()
    return stripped or None


def _find_message_field(
    decoded: DecodedFit,
    message_type: str,
    field_name: str,
) -> str | None:
    wanted = field_name.casefold()
    for message in decoded.get_messages(message_type):
        if not isinstance(message, Mapping):
            continue
        for key, value in message.items():
            if str(key).casefold() != wanted:
                continue
            text = _clean_text(value)
            if text is not None:
                return text
    return None


def _normalized_comparison(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.strip().split()).casefold()


def _session_name_is_generic(
    session_name: str,
    *,
    sport_profile_name: str | None,
    sport: str | None,
    sub_sport: str | None,
) -> bool:
    normalized_name = _normalized_comparison(session_name)
    generic_values = {
        _normalized_comparison(value)
        for value in (sport_profile_name, sport, sub_sport)
        if value is not None
    }
    return normalized_name in generic_values


def _find_workout_name(
    decoded: DecodedFit,
    *,
    sport_profile_name: str | None,
    sport: str | None,
    sub_sport: str | None,
) -> tuple[str, str] | None:
    ordered_locations = (
        ("workout", "workout_name", "workout.workout_name"),
        ("workout", "wkt_name", "workout.workout_name"),
        ("workout", "name", "workout.name"),
        ("activity", "activity_name", "activity.activity_name"),
        ("activity", "name", "activity.name"),
        ("activity", "title", "activity.title"),
        ("session", "activity_name", "session.activity_name"),
        ("session", "name", "session.name"),
    )

    for message_type, field_name, logical_field in ordered_locations:
        value = _find_message_field(decoded, message_type, field_name)
        if value is None:
            continue
        if message_type == "session" and field_name == "name":
            if _session_name_is_generic(
                value,
                sport_profile_name=sport_profile_name,
                sport=sport,
                sub_sport=sub_sport,
            ):
                continue
        return value, logical_field
    return None


def extract_activity_metadata(decoded: DecodedFit) -> ActivityMetadata:
    """Extract explicit FIT metadata without inferring missing names."""

    if not isinstance(decoded, DecodedFit):
        raise TypeError("decoded must be a DecodedFit")

    sport_profile_name = _find_message_field(
        decoded,
        "session",
        "sport_profile_name",
    )
    sport = _find_message_field(decoded, "session", "sport")
    sub_sport = _find_message_field(decoded, "session", "sub_sport")
    workout_name = _find_workout_name(
        decoded,
        sport_profile_name=sport_profile_name,
        sport=sport,
        sub_sport=sub_sport,
    )

    return ActivityMetadata(
        workout_name=workout_name[0] if workout_name is not None else None,
        workout_name_field=workout_name[1] if workout_name is not None else None,
        sport_profile_name=sport_profile_name,
        sport=sport,
        sub_sport=sub_sport,
    )


def resolve_decoded_activity(
    decoded: DecodedFit,
    *,
    explicit_qpro_key: str | None = None,
) -> ActivityContext:
    """Resolve a decoded FIT activity through the approved cascade."""

    metadata = extract_activity_metadata(decoded)
    resolution = resolve_activity(
        workout_name=metadata.workout_name,
        sport_profile_name=metadata.sport_profile_name,
        explicit_qpro_key=explicit_qpro_key,
    )
    return ActivityContext(metadata=metadata, resolution=resolution)
