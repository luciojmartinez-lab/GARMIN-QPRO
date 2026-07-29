from dataclasses import FrozenInstanceError

import pytest

from garmin_qpro.mapping import activity_resolution as resolution_module
from garmin_qpro.mapping.activity_resolution import (
    EXPLICIT_QPRO_KEY_SOURCE,
    SPORT_PROFILE_NAME_SOURCE,
    WORKOUT_NAME_SOURCE,
    ActivityResolution,
    resolve_activity,
)
from garmin_qpro.qpro.rows import UnknownQProKeyError


def test_known_workout_takes_precedence_over_sport_profile() -> None:
    resolution = resolve_activity(
        workout_name="EB5 - Pesas - Fase 2",
        sport_profile_name="Carrera",
    )

    assert resolution.qpro_key == "PES"
    assert resolution.resolution_source == WORKOUT_NAME_SOURCE
    assert resolution.requires_user_choice is False


@pytest.mark.parametrize(
    "workout_name",
    [
        "EB9 - Salto de altura - Competic",
        "EB9 - Triple Salto - Competicion",
    ],
)
def test_confirmed_eb9_competitions_resolve_cmf(
    workout_name: str,
) -> None:
    resolution = resolve_activity(
        workout_name=workout_name,
        sport_profile_name="Fuerza",
    )

    assert resolution.qpro_key == "CMF"
    assert resolution.resolution_source == WORKOUT_NAME_SOURCE
    assert resolution.requires_user_choice is False


@pytest.mark.parametrize("profile", ["Carrera", "running", "  CARRERA  "])
def test_running_profile_without_known_workout_resolves_ent(
    profile: str,
) -> None:
    resolution = resolve_activity(
        workout_name=None,
        sport_profile_name=profile,
    )

    assert resolution.qpro_key == "ENT"
    assert resolution.resolution_source == SPORT_PROFILE_NAME_SOURCE
    assert resolution.requires_user_choice is False


@pytest.mark.parametrize("profile", ["Caminar", "walking", "  CAMINAR  "])
def test_walking_profile_without_known_workout_resolves_cam(
    profile: str,
) -> None:
    resolution = resolve_activity(
        workout_name=None,
        sport_profile_name=profile,
    )

    assert resolution.qpro_key == "CAM"
    assert resolution.resolution_source == SPORT_PROFILE_NAME_SOURCE
    assert resolution.requires_user_choice is False


def test_unresolved_workout_falls_back_to_running_profile() -> None:
    resolution = resolve_activity(
        workout_name="Entrenamiento libre",
        sport_profile_name="Carrera",
    )

    assert resolution.qpro_key == "ENT"
    assert resolution.resolution_source == SPORT_PROFILE_NAME_SOURCE


@pytest.mark.parametrize(
    "profile",
    ["Entreno de fuerza", "strength_training", "Fuerza"],
)
def test_force_profile_requires_manual_choice(profile: str) -> None:
    resolution = resolve_activity(
        workout_name=None,
        sport_profile_name=profile,
    )

    assert resolution.qpro_key is None
    assert resolution.resolution_source is None
    assert resolution.requires_user_choice is True


def test_explicit_cmf_takes_precedence_over_force_profile() -> None:
    resolution = resolve_activity(
        workout_name=None,
        sport_profile_name="Entreno de fuerza",
        explicit_qpro_key=" cmf ",
    )

    assert resolution.qpro_key == "CMF"
    assert resolution.resolution_source == EXPLICIT_QPRO_KEY_SOURCE
    assert resolution.requires_user_choice is False


def test_explicit_key_takes_precedence_over_known_workout() -> None:
    resolution = resolve_activity(
        workout_name="EB1 - Carrera - 1",
        sport_profile_name="Carrera",
        explicit_qpro_key="PES",
    )

    assert resolution.qpro_key == "PES"
    assert resolution.resolution_source == EXPLICIT_QPRO_KEY_SOURCE


@pytest.mark.parametrize(
    "profile",
    ["Yoga", "Pilates", "Natacion", "", "   ", None],
)
def test_no_general_default_exists(profile: str | None) -> None:
    resolution = resolve_activity(
        workout_name=None,
        sport_profile_name=profile,
    )

    assert resolution.qpro_key is None
    assert resolution.resolution_source is None
    assert resolution.requires_user_choice is True


def test_unknown_explicit_key_is_rejected() -> None:
    with pytest.raises(UnknownQProKeyError):
        resolve_activity(
            workout_name=None,
            sport_profile_name="Carrera",
            explicit_qpro_key="COM",
        )


def test_every_resolved_key_is_validated_by_existing_families(
    monkeypatch,
) -> None:
    validated: list[str] = []

    def fake_family_for_key(key: str):
        validated.append(key)
        return object()

    monkeypatch.setattr(resolution_module, "family_for_key", fake_family_for_key)

    resolution = resolve_activity(
        workout_name=None,
        sport_profile_name="running",
    )

    assert resolution.qpro_key == "ENT"
    assert validated == ["ENT"]


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("workout_name", 1),
        ("sport_profile_name", False),
        ("explicit_qpro_key", 3),
    ],
)
def test_non_string_inputs_are_rejected(field_name: str, value) -> None:
    arguments = {
        "workout_name": None,
        "sport_profile_name": None,
        "explicit_qpro_key": None,
    }
    arguments[field_name] = value

    with pytest.raises(TypeError):
        resolve_activity(**arguments)


def test_activity_resolution_is_immutable() -> None:
    resolution = resolve_activity(
        workout_name=None,
        sport_profile_name="Carrera",
    )

    assert isinstance(resolution, ActivityResolution)
    with pytest.raises((FrozenInstanceError, AttributeError)):
        resolution.qpro_key = "PES"  # type: ignore[misc]
