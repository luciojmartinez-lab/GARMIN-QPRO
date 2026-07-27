from pathlib import Path

import pytest

from garmin_qpro.fit.models import DecodedFit
from garmin_qpro.input.sources import FitSource
from scripts import inspect_fit


def _source(
    name: str = "activity.fit",
    *,
    container: str | None = "export.zip",
) -> FitSource:
    return FitSource(
        source_name=name,
        container_name=container,
        member_path=f"activities/{name}" if container else None,
        data=name.encode("ascii"),
    )


def _decoded(
    source: FitSource,
    *,
    messages=None,
    errors=(),
) -> DecodedFit:
    return DecodedFit(
        source=source,
        messages={} if messages is None else messages,
        errors=errors,
        crc_checked=True,
    )


def test_coordinate_fields_are_never_printed() -> None:
    source = _source()
    decoded = _decoded(
        source,
        messages={
            "session": [
                {
                    "sport": "running",
                    "position_lat": 123,
                    "start_position_long": 456,
                    "nested": {
                        "latitude": 12.3,
                        "longitude": 45.6,
                        "safe": "value",
                    },
                }
            ],
            "lap": [{"end_position_lat": 789, "distance": 1000}],
            "record": [{"position_long": 321, "heart_rate": 98}],
        },
    )

    output = inspect_fit.render_decoded_fit(source, decoded).casefold()

    for forbidden in (
        "position_lat",
        "position_long",
        "latitude",
        "longitude",
    ):
        assert forbidden not in output
    assert "safe" in output


def test_message_types_and_counts_are_printed() -> None:
    source = _source()
    decoded = _decoded(
        source,
        messages={
            "session": [{"sport": "running"}],
            "record": [{"speed": 1}, {"speed": 2}],
            "event": [{"event": "start"}],
        },
    )

    output = inspect_fit.render_decoded_fit(source, decoded)

    assert "Conteos: session=1, lap=0, record=2, workout=0, event=1" in output
    assert "- session: 1" in output
    assert "- record: 2" in output


def test_missing_workout_does_not_fail() -> None:
    source = _source()
    decoded = _decoded(source, messages={"session": [{"sport": "running"}]})

    output = inspect_fit.render_decoded_fit(source, decoded)

    assert "- workout: ninguno" in output


def test_activity_name_is_not_invented_from_sport() -> None:
    source = _source()
    decoded = _decoded(
        source,
        messages={
            "session": [
                {
                    "sport_profile_name": "Carrera",
                    "sport": "running",
                    "sub_sport": "generic",
                }
            ]
        },
    )

    output = inspect_fit.render_decoded_fit(source, decoded)

    assert "Nombre Garmin: no encontrado en campos explicitos" in output
    assert "Nombre Garmin: running" not in output
    assert "Nombre Garmin: Carrera" not in output
    assert "Perfil deportivo Garmin: Carrera" in output


def test_workout_name_has_priority_over_generic_sport_profile() -> None:
    source = _source()
    decoded = _decoded(
        source,
        messages={
            "session": [
                {
                    "sport_profile_name": "Carrera",
                    "sport": "running",
                }
            ],
            "workout": [{"workout_name": "EB0 - Cal. Estadio"}],
        },
    )

    output = inspect_fit.render_decoded_fit(source, decoded)

    assert "Nombre Garmin: EB0 - Cal. Estadio" in output
    assert "Campo nombre Garmin: workout.workout_name" in output
    assert "Perfil deportivo Garmin: Carrera" in output


@pytest.mark.parametrize(
    "expected_name",
    [
        "EB0 - Cal. Estadio",
        "EB1 - Carrera - 1",
        "EB0 - Vuelta a la calma",
    ],
)
def test_expected_real_names_are_detected_from_workout(
    expected_name: str,
) -> None:
    source = _source()
    decoded = _decoded(
        source,
        messages={
            "session": [{"sport_profile_name": "Carrera"}],
            "workout": [
                {
                    "wkt_name": (
                        expected_name,
                        "",
                        "perfil generico ignorado",
                    )
                }
            ],
        },
    )

    assert inspect_fit.find_activity_name(decoded) == (
        expected_name,
        "workout.workout_name",
    )


@pytest.mark.parametrize("session_name", ["running", "Carrera"])
def test_session_name_matching_sport_or_profile_is_rejected(
    session_name: str,
) -> None:
    source = _source()
    decoded = _decoded(
        source,
        messages={
            "session": [
                {
                    "name": session_name,
                    "sport": "running",
                    "sport_profile_name": "Carrera",
                }
            ]
        },
    )

    assert inspect_fit.find_activity_name(decoded) is None


def test_multiple_zip_inputs_are_processed(monkeypatch) -> None:
    first = _source("first.fit", container="first.zip")
    second = _source("second.fit", container="second.zip")
    sources_by_name = {
        "first.zip": (first,),
        "second.zip": (second,),
    }
    loaded: list[str] = []

    def fake_load(path: Path):
        loaded.append(path.name)
        return sources_by_name[path.name]

    def fake_decode(source: FitSource):
        return _decoded(
            source,
            messages={"session": [{"activity_name": source.source_name}]},
        )

    monkeypatch.setattr(inspect_fit, "load_fit_sources", fake_load)
    monkeypatch.setattr(inspect_fit, "decode_fit", fake_decode)

    output = inspect_fit.inspect_paths(
        [Path("first.zip"), Path("second.zip")]
    )

    assert loaded == ["first.zip", "second.zip"]
    assert "ZIP origen: first.zip" in output
    assert "ZIP origen: second.zip" in output


def test_sdk_errors_are_preserved_in_output() -> None:
    source = _source()
    decoded = _decoded(
        source,
        messages={"session": [{"activity_name": "Strength"}]},
        errors=(ValueError("CRC mismatch"),),
    )

    output = inspect_fit.render_decoded_fit(source, decoded)

    assert "Errores SDK: ValueError: CRC mismatch" in output


def test_absolute_paths_in_values_are_redacted() -> None:
    source = _source()
    decoded = _decoded(
        source,
        messages={
            "session": [
                {
                    "activity_name": "Strength",
                    "custom_path": r"C:\Users\private\activity.fit",
                }
            ]
        },
    )

    output = inspect_fit.render_decoded_fit(source, decoded)

    assert r"C:\Users\private" not in output
    assert "<ruta absoluta omitida>" in output
