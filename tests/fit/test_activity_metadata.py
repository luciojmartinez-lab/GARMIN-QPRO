from dataclasses import FrozenInstanceError

import pytest

from garmin_qpro.fit.activity_metadata import (
    ActivityContext,
    ActivityMetadata,
    extract_activity_metadata,
    resolve_decoded_activity,
)
from garmin_qpro.fit.models import DecodedFit
from garmin_qpro.input.sources import FitSource


def _source() -> FitSource:
    return FitSource("activity.fit", None, None, b"fit")


def _decoded(messages=None) -> DecodedFit:
    return DecodedFit(
        source=_source(),
        messages={} if messages is None else messages,
        errors=(),
        crc_checked=True,
    )


def test_wkt_name_tuple_detects_first_non_empty_text() -> None:
    metadata = extract_activity_metadata(
        _decoded(
            {
                "workout": [{"wkt_name": ("", b"\x00 EB0 - Cal. Estadio \x00")}],
                "session": [{"sport_profile_name": "Carrera"}],
            }
        )
    )

    assert metadata.workout_name == "EB0 - Cal. Estadio"
    assert metadata.workout_name_field == "workout.workout_name"


@pytest.mark.parametrize(
    ("workout_name", "qpro_key"),
    [
        ("EB1 - Carrera - 1", "ENT"),
        ("EB0 - Vuelta a la calma", "FIN"),
        ("EB0 - Cal. Estadio", "CAL"),
    ],
)
def test_known_workout_names_resolve_to_qpro_keys(
    workout_name: str,
    qpro_key: str,
) -> None:
    context = resolve_decoded_activity(
        _decoded(
            {
                "workout": [{"wkt_name": workout_name}],
                "session": [{"sport_profile_name": "Carrera"}],
            }
        )
    )

    assert context.metadata.workout_name == workout_name
    assert context.resolution.qpro_key == qpro_key
    assert context.resolution.resolution_source == "workout_name"


def test_running_profile_without_workout_resolves_ent() -> None:
    context = resolve_decoded_activity(
        _decoded({"session": [{"sport_profile_name": "Carrera"}]})
    )

    assert context.metadata.workout_name is None
    assert context.metadata.sport_profile_name == "Carrera"
    assert context.resolution.qpro_key == "ENT"
    assert context.resolution.resolution_source == "sport_profile_name"


def test_force_profile_without_plan_requires_manual_choice() -> None:
    context = resolve_decoded_activity(
        _decoded({"session": [{"sport_profile_name": "Entreno de fuerza"}]})
    )

    assert context.resolution.qpro_key is None
    assert context.resolution.requires_user_choice is True


def test_explicit_key_takes_precedence() -> None:
    context = resolve_decoded_activity(
        _decoded(
            {
                "workout": [{"wkt_name": "EB1 - Carrera - 1"}],
                "session": [{"sport_profile_name": "Carrera"}],
            }
        ),
        explicit_qpro_key="CMF",
    )

    assert context.resolution.qpro_key == "CMF"
    assert context.resolution.resolution_source == "explicit_qpro_key"


def test_sport_profile_name_is_not_used_as_workout_name() -> None:
    metadata = extract_activity_metadata(
        _decoded(
            {
                "session": [
                    {
                        "sport_profile_name": "Carrera",
                        "sport": "running",
                        "sub_sport": "generic",
                    }
                ]
            }
        )
    )

    assert metadata.workout_name is None
    assert metadata.workout_name_field is None
    assert metadata.sport_profile_name == "Carrera"
    assert metadata.sport == "running"
    assert metadata.sub_sport == "generic"


def test_session_name_matching_generic_profile_is_ignored() -> None:
    metadata = extract_activity_metadata(
        _decoded(
            {
                "session": [
                    {
                        "name": "Carrera",
                        "sport_profile_name": "Carrera",
                        "sport": "running",
                    }
                ]
            }
        )
    )

    assert metadata.workout_name is None


def test_session_name_that_is_not_generic_can_be_used() -> None:
    metadata = extract_activity_metadata(
        _decoded(
            {
                "session": [
                    {
                        "name": "Entrenamiento libre especial",
                        "sport_profile_name": "Carrera",
                        "sport": "running",
                    }
                ]
            }
        )
    )

    assert metadata.workout_name == "Entrenamiento libre especial"
    assert metadata.workout_name_field == "session.name"


def test_bytes_lists_and_tuples_are_cleaned() -> None:
    metadata = extract_activity_metadata(
        _decoded(
            {
                "activity": [
                    {
                        "activity_name": [
                            b"\x00",
                            b"  EB0 - Vuelta a la calma\x00",
                        ]
                    }
                ],
                "session": [
                    {
                        "sport_profile_name": (b"\x00 Carrera ",),
                        "sport": [b"running\x00"],
                        "sub_sport": ("", "generic"),
                    }
                ],
            }
        )
    )

    assert metadata.workout_name == "EB0 - Vuelta a la calma"
    assert metadata.workout_name_field == "activity.activity_name"
    assert metadata.sport_profile_name == "Carrera"
    assert metadata.sport == "running"
    assert metadata.sub_sport == "generic"


def test_empty_decoded_messages_do_not_fail() -> None:
    context = resolve_decoded_activity(_decoded())

    assert context.metadata == ActivityMetadata(None, None, None, None, None)
    assert context.resolution.qpro_key is None
    assert context.resolution.requires_user_choice is True


def test_models_are_immutable() -> None:
    context = resolve_decoded_activity(
        _decoded({"session": [{"sport_profile_name": "Carrera"}]})
    )

    assert isinstance(context.metadata, ActivityMetadata)
    assert isinstance(context, ActivityContext)
    with pytest.raises((FrozenInstanceError, AttributeError)):
        context.metadata.workout_name = "otro"  # type: ignore[misc]
    with pytest.raises((FrozenInstanceError, AttributeError)):
        context.resolution = context.resolution  # type: ignore[misc]


def test_decoded_type_is_required() -> None:
    with pytest.raises(TypeError):
        extract_activity_metadata(object())  # type: ignore[arg-type]
