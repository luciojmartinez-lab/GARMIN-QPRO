import pytest

from garmin_qpro.mapping import workout_names as workout_names_module
from garmin_qpro.mapping.workout_names import (
    WorkoutResolution,
    resolve_workout_name,
)

CONFIRMED_EXACT_MAPPINGS = (
    ("EB0 - Cal. Estadio", "CAL"),
    ("EB0 - Cal. Pesas - 1", "CLP"),
    ("EB0 - Cal. Pesas - 2", "FPN"),
    ("EB0 - Vuelta a la calma", "FIN"),
    ("EB1 - Carrera - 1", "ENT"),
    ("EB1 - Carrera - 2", "ENT"),
    ("EB1 - Carrera Tec Altura", "ENT"),
    ("EB1 - Carrera Técnica-Triple", "ENT"),
    ("EB1 - Carrera Tec Triple", "ENT"),
    ("EB5 - MOVILIDAD VALLAS", "MOF"),
    ("EB9 - Salto de altura - Competic", "CMF"),
    ("EB9 - Triple Salto - Competicion", "CMF"),
    ('EB7 - SPista 3*60m-10"', "SER"),
)

UNCONFIRMED_NAMES = (
    "EB0 - Playa 15'",
    "EB1 - Carrera - Playa",
    "EB1 - Carrera Series",
    "EB2 - Balon Medicinal",
    "EB2 - Circuito",
    "EB2 - Escaleras",
    "EB2 - Movilidad",
    "EB4 - Farklek 4S Playa",
    "EB4 - Fartlek",
    "EB5 Pesas - Basico",
    "EB6 - Series Hierba 200",
    "EB7 - Series Pista 400",
    "EB8 - Competicion",
    "EB9 - Fuerza",
)


@pytest.mark.parametrize(
    ("workout_name", "expected_key"),
    CONFIRMED_EXACT_MAPPINGS,
)
def test_all_confirmed_exact_mappings(
    workout_name: str,
    expected_key: str,
) -> None:
    resolution = resolve_workout_name(workout_name)

    assert resolution.workout_name == workout_name
    assert resolution.qpro_key == expected_key
    assert resolution.matched_rule == workout_name


@pytest.mark.parametrize(
    ("variant", "expected_normalized", "expected_key"),
    [
        ("  eb0-  cal.   estadio  ", "eb0 - cal. estadio", "CAL"),
        ("EB1-CARRERA-1", "eb1 - carrera - 1", "ENT"),
        (
            " eb1 - carrera TÉCNICA- triple ",
            "eb1 - carrera técnica - triple",
            "ENT",
        ),
        ("eb5- movilidad vallas", "eb5 - movilidad vallas", "MOF"),
        (
            "  eb9-  salto DE altura-  COMPETIC ",
            "eb9 - salto de altura - competic",
            "CMF",
        ),
        (
            "EB9-TRIPLE SALTO-COMPETICION",
            "eb9 - triple salto - competicion",
            "CMF",
        ),
        (
            ' eb7-SPista   3*60m-10" ',
            'eb7 - spista 3*60m - 10"',
            "SER",
        ),
    ],
)
def test_case_spaces_and_hyphen_spacing_are_normalized(
    variant: str,
    expected_normalized: str,
    expected_key: str,
) -> None:
    resolution = resolve_workout_name(variant)

    assert resolution.workout_name == variant
    assert resolution.normalized_name == expected_normalized
    assert resolution.qpro_key == expected_key


@pytest.mark.parametrize("phase", range(10))
def test_confirmed_weight_phases_zero_to_nine(phase: int) -> None:
    resolution = resolve_workout_name(f"EB5 - Pesas - Fase {phase}")

    assert resolution.qpro_key == "PES"
    assert resolution.matched_rule == "EB5 - Pesas - Fase <0-9>"


@pytest.mark.parametrize(
    "workout_name",
    [
        "EB5 - Pesas - Fase 10",
        "EB5 - Pesas - Fase -1",
        "EB5 - Pesas - Fase uno",
        "EB5 - Pesas - Fase 1.5",
        "EB5 - Pesas - Fase 01",
    ],
)
def test_unconfirmed_weight_phases_are_unresolved(workout_name: str) -> None:
    resolution = resolve_workout_name(workout_name)

    assert resolution.qpro_key is None
    assert resolution.matched_rule is None


def test_eb1_carrera_one_resolves_ent() -> None:
    assert resolve_workout_name("EB1 - Carrera - 1").qpro_key == "ENT"


@pytest.mark.parametrize(
    "workout_name",
    [
        "EB9 - Salto de longitud - Competicion",
        "EB9 - Salto de altura",
        "EB9 - Triple Salto",
        "EB9 - Competicion",
    ],
)
def test_other_eb9_names_remain_unresolved(workout_name: str) -> None:
    resolution = resolve_workout_name(workout_name)

    assert resolution.qpro_key is None
    assert resolution.matched_rule is None


@pytest.mark.parametrize(
    "workout_name",
    [
        "Carrera",
        "Entreno de fuerza",
        "Fuerza",
        "Series",
        "Fartlek",
        "Competicion",
        "EB0",
        "EB1",
    ],
)
def test_generic_words_and_eb_numbers_are_not_inferred(
    workout_name: str,
) -> None:
    resolution = resolve_workout_name(workout_name)

    assert resolution.qpro_key is None
    assert resolution.matched_rule is None


@pytest.mark.parametrize("profile_name", ["Carrera", "Yoga", "Pilates"])
def test_sport_profiles_are_not_used_as_workout_names(
    profile_name: str,
) -> None:
    assert resolve_workout_name(profile_name).qpro_key is None


@pytest.mark.parametrize("workout_name", UNCONFIRMED_NAMES)
def test_unconfirmed_names_remain_unresolved(workout_name: str) -> None:
    resolution = resolve_workout_name(workout_name)

    assert resolution.qpro_key is None
    assert resolution.matched_rule is None


@pytest.mark.parametrize("workout_name", ["", " ", " \t\r\n "])
def test_empty_names_are_unresolved(workout_name: str) -> None:
    resolution = resolve_workout_name(workout_name)

    assert resolution.workout_name == workout_name
    assert resolution.normalized_name == ""
    assert resolution.qpro_key is None
    assert resolution.matched_rule is None


@pytest.mark.parametrize("workout_name", [None, 1, True])
def test_unavailable_or_non_string_name_is_rejected(workout_name) -> None:
    with pytest.raises(TypeError):
        resolve_workout_name(workout_name)


def test_sport_profile_argument_does_not_exist() -> None:
    with pytest.raises(TypeError):
        resolve_workout_name(
            "EB1 - Carrera - 1",
            sport_profile_name="Carrera",
        )


def test_resolved_key_is_validated_by_existing_qpro_families(
    monkeypatch,
) -> None:
    validated: list[str] = []

    def fake_family_for_key(key: str):
        validated.append(key)
        return object()

    monkeypatch.setattr(
        workout_names_module,
        "family_for_key",
        fake_family_for_key,
    )

    resolution = resolve_workout_name("EB0 - Cal. Estadio")

    assert resolution.qpro_key == "CAL"
    assert validated == ["CAL"]


def test_resolution_is_immutable() -> None:
    resolution = resolve_workout_name("EB0 - Cal. Estadio")

    assert isinstance(resolution, WorkoutResolution)
    with pytest.raises(AttributeError):
        resolution.qpro_key = "ENT"  # type: ignore[misc]
