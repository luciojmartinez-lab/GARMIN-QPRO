from __future__ import annotations

from datetime import date
from io import StringIO
from types import SimpleNamespace

from garmin_qpro import cli
from garmin_qpro.conversion import (
    ActivityRequiresChoiceError,
    MultipleFitSourcesError,
)
from garmin_qpro.fit.activity_metadata import ActivityContext, ActivityMetadata
from garmin_qpro.garmin_connect import GarminPyQueryError
from garmin_qpro.input.sources import FitSource
from garmin_qpro.mapping.activity_resolution import ActivityResolution
from garmin_qpro.qpro.rows import QProFamily


def _result(
    *,
    key: str = "ENT",
    family: QProFamily = QProFamily.RUNNING,
    workout_name: str | None = "EB1 - Carrera - 1",
    profile: str | None = "Carrera",
    acute: str = "'277",
    chronic: str = "'239",
):
    cells = [""] * 25
    cells[0] = key
    cells[18] = "'008"
    cells[23] = acute
    cells[24] = chronic
    metadata = ActivityMetadata(
        workout_name=workout_name,
        workout_name_field=(
            "workout.workout_name" if workout_name is not None else None
        ),
        sport_profile_name=profile,
        sport="running" if family is QProFamily.RUNNING else "training",
        sub_sport=(
            "generic"
            if family is QProFamily.RUNNING
            else "strength_training"
        ),
        activity_date=date(2026, 7, 6),
    )
    resolution = ActivityResolution(
        workout_name=workout_name,
        sport_profile_name=profile,
        qpro_key=key,
        resolution_source=(
            "workout_name" if workout_name is not None else "sport_profile_name"
        ),
        requires_user_choice=False,
    )
    return SimpleNamespace(
        qpro_key=key,
        family=family,
        activity_context=ActivityContext(metadata, resolution),
        final_row=SimpleNamespace(as_tuple=lambda: tuple(cells)),
        tsv="\t".join(cells),
    )


def _run(monkeypatch, result, argv=None, *, garmin=True):
    calls = []

    def converter(path, **kwargs):
        calls.append((path, kwargs))
        if isinstance(result, Exception):
            raise result
        return result

    target = (
        "convert_input_path_to_qpro_with_garmin_load"
        if garmin
        else "convert_input_path_to_qpro"
    )
    monkeypatch.setattr(cli, target, converter)
    stdout = StringIO()
    stderr = StringIO()
    status = cli.run(
        ["activity.zip", *(argv or [])],
        adapter=object(),
        stdout=stdout,
        stderr=stderr,
    )
    return status, stdout.getvalue(), stderr.getvalue(), calls


def test_running_resolved_prints_only_25_column_tsv(monkeypatch) -> None:
    result = _result()

    status, stdout, stderr, _ = _run(monkeypatch, result)

    assert status == 0
    assert stdout == f"{result.tsv}\n"
    assert stdout.rstrip("\n").count("\t") == 24
    assert stderr == ""


def test_force_resolved_uses_existing_result(monkeypatch) -> None:
    result = _result(
        key="PES",
        family=QProFamily.FORCE,
        workout_name="EB5 - Pesas - Fase 1",
        profile="Fuerza",
    )

    status, stdout, stderr, _ = _run(monkeypatch, result)

    assert status == 0
    assert stdout == f"{result.tsv}\n"
    assert stderr == ""


def test_free_running_keeps_automatic_ent_resolution(monkeypatch) -> None:
    result = _result(key="ENT", workout_name=None, profile="Carrera")

    status, stdout, _, _ = _run(monkeypatch, result)

    assert status == 0
    assert stdout.split("\t", 1)[0] == "ENT"


def test_ambiguous_force_explains_manual_key(monkeypatch) -> None:
    source = FitSource("force.fit", None, None, b"fit")
    metadata = ActivityMetadata(None, None, "Fuerza", "training", "strength_training")
    resolution = ActivityResolution(None, "Fuerza", None, None, True)
    error = ActivityRequiresChoiceError(
        source=source,
        activity_context=ActivityContext(metadata, resolution),
        reason="Activity requires a manual QPro key choice",
    )

    status, stdout, stderr, _ = _run(monkeypatch, error)

    assert status == 2
    assert stdout == ""
    assert "workout_name=None" in stderr
    assert "sport_profile_name='Fuerza'" in stderr
    assert "--key XXX" in stderr


def test_manual_key_is_forwarded_with_priority(monkeypatch) -> None:
    result = _result(key="PES", family=QProFamily.FORCE, profile="Fuerza")

    status, _, _, calls = _run(monkeypatch, result, ["--key", "PES"])

    assert status == 0
    assert calls[0][1]["explicit_qpro_key"] == "PES"


def test_no_garmin_load_uses_pure_pipeline_and_empty_columns(monkeypatch) -> None:
    result = _result(acute="", chronic="")

    status, stdout, stderr, calls = _run(
        monkeypatch,
        result,
        ["--no-garmin-load"],
        garmin=False,
    )

    assert status == 0
    assert stderr == ""
    assert stdout.rstrip("\n").split("\t")[23:] == ["", ""]
    assert "adapter" not in calls[0][1]


def test_garmin_load_is_kept_in_final_columns(monkeypatch) -> None:
    result = _result(acute="'312", chronic="'236")

    status, stdout, _, calls = _run(monkeypatch, result)

    assert status == 0
    assert stdout.rstrip("\n").split("\t")[23:] == ["'312", "'236"]
    assert calls[0][1]["adapter"] is not None


def test_garmin_error_writes_only_stderr(monkeypatch) -> None:
    status, stdout, stderr, _ = _run(
        monkeypatch,
        GarminPyQueryError("RATE_LIMITED"),
    )

    assert status == 3
    assert stdout == ""
    assert "Garmin Connect" in stderr
    assert "RATE_LIMITED" in stderr
    assert "No se genero ninguna fila" in stderr


def test_multiple_fit_sources_are_enumerated(monkeypatch) -> None:
    sources = (
        FitSource("one.fit", "bundle.zip", "one.fit", b"one"),
        FitSource("two.fit", "bundle.zip", "two.fit", b"two"),
    )
    error = MultipleFitSourcesError(path="bundle.zip", sources=sources)

    status, stdout, stderr, _ = _run(monkeypatch, error)

    assert status == 2
    assert stdout == ""
    assert "one.fit" in stderr
    assert "two.fit" in stderr
    assert "exactamente una" in stderr


def test_verbose_metadata_goes_to_stderr(monkeypatch) -> None:
    result = _result()

    status, stdout, stderr, _ = _run(monkeypatch, result, ["--verbose"])

    assert status == 0
    assert stdout == f"{result.tsv}\n"
    assert "archivo: activity.zip" in stderr
    assert "workout_name: EB1 - Carrera - 1" in stderr
    assert "sport_profile_name: Carrera" in stderr
    assert "activity_date: 2026-07-06" in stderr
    assert "qpro_key: ENT" in stderr
    assert "family: RUNNING" in stderr
    assert "CARGA: '008" in stderr
    assert "CARGA_AGUDA: '277" in stderr
    assert "CARGA_CRONICA: '239" in stderr


def test_console_script_is_registered() -> None:
    pyproject = (
        __import__("pathlib").Path(__file__).parents[1] / "pyproject.toml"
    ).read_text(encoding="utf-8")

    assert 'garmin-qpro = "garmin_qpro.cli:main"' in pyproject
