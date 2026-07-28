from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

import garmin_qpro
from garmin_qpro.batch import (
    BatchConversionFailure,
    BatchConversionResult,
    convert_input_directory,
    convert_input_paths,
    discover_input_paths,
)
from garmin_qpro.conversion import (
    ActivityConversionResult,
    convert_fit_source,
)
from garmin_qpro.fit.force_metrics import ForceMetricsRaw
from garmin_qpro.fit.models import DecodedFit
from garmin_qpro.fit.running_metrics import RunningMetricsRaw
from garmin_qpro.input.sources import FitSource
from garmin_qpro.qpro.formulas import (
    build_vmax_ms_formula,
    build_vmed_ms_formula,
)


ROW_NUMBERS = {
    "CAL": 18,
    "ENT": 23,
    "CMF": 36,
    "FIN": 41,
}


def _source(
    name: str,
    *,
    container: str | None = None,
    member: str | None = None,
    data: bytes | None = None,
) -> FitSource:
    return FitSource(
        source_name=name,
        container_name=container,
        member_path=member,
        data=data if data is not None else name.encode("ascii"),
    )


def _running_session(**overrides):
    values = {
        "message_index": 0,
        "sport_profile_name": "Carrera",
        "sport": "running",
        "sub_sport": "generic",
        "total_timer_time": 100.0,
        "total_moving_time": 80.0,
        "total_distance": 200.0,
        "enhanced_avg_speed": 2.0,
        "enhanced_max_speed": 4.0,
        "avg_heart_rate": 100,
        "max_heart_rate": 120,
        "total_training_effect": 0.5,
        "total_anaerobic_training_effect": 0.0,
        "avg_cadence": 60,
        "max_cadence": 80,
        "avg_step_length": 700.0,
        "avg_stance_time": 300.0,
        "training_load_peak": 5.0,
        "avg_power": 100,
        "max_power": 200,
        "avg_vertical_ratio": 10.0,
        "avg_vertical_oscillation": 70.0,
    }
    values.update(overrides)
    return values


def _force_session(**overrides):
    values = {
        "message_index": 0,
        "sport_profile_name": "Fuerza",
        "sport": "training",
        "sub_sport": "strength_training",
        "total_timer_time": 1663.291,
        "total_elapsed_time": 1701.977,
        "avg_heart_rate": 121,
        "max_heart_rate": 146,
        "total_training_effect": 3.0,
        "total_anaerobic_training_effect": 2.3,
        "training_load_peak": 93.91545104980469,
    }
    values.update(overrides)
    return values


def _decoded(
    source: FitSource,
    *,
    workout_name: str | None = "EB1 - Carrera - 1",
    session=None,
    extra_messages=None,
    errors=(),
    crc_checked: bool = True,
) -> DecodedFit:
    messages = {"session": [session or _running_session()]}
    if workout_name is not None:
        messages["workout"] = [{"wkt_name": workout_name}]
    if extra_messages:
        messages.update(extra_messages)
    return DecodedFit(
        source=source,
        messages=messages,
        errors=errors,
        crc_checked=crc_checked,
    )


def _force_decoded(source: FitSource, **overrides) -> DecodedFit:
    return _decoded(
        source,
        workout_name="EB9 - Salto de altura - Competic",
        session=_force_session(**overrides),
    )


def _patch_sources_and_decoder(monkeypatch, sources_by_path, decoded_by_name):
    monkeypatch.setattr(
        "garmin_qpro.batch.load_fit_sources",
        lambda path: sources_by_path[Path(path)],
    )

    def fake_decode(source, *, verify_crc=True):
        decoded = decoded_by_name[source.source_name]
        return DecodedFit(
            source=decoded.source,
            messages=decoded.messages,
            errors=decoded.errors,
            crc_checked=verify_crc,
        )

    monkeypatch.setattr("garmin_qpro.batch.decode_fit", fake_decode)


def test_failure_and_result_models_are_immutable() -> None:
    failure = BatchConversionFailure(
        input_path=Path("bad.zip"),
        source_name=None,
        container_name=None,
        member_path=None,
        sha256=None,
        qpro_key=None,
        stage="load",
        error_type="InvalidZipError",
        message="bad",
    )
    result = BatchConversionResult(results=(), failures=(failure,), tsv="")

    with pytest.raises((FrozenInstanceError, AttributeError)):
        failure.stage = "decode"  # type: ignore[misc]
    with pytest.raises((FrozenInstanceError, AttributeError)):
        result.tsv = "x"  # type: ignore[misc]
    assert result.success_count == 0
    assert result.failure_count == 1


def test_failure_rejects_unknown_stage() -> None:
    with pytest.raises(ValueError):
        BatchConversionFailure(
            input_path=Path("bad.zip"),
            source_name=None,
            container_name=None,
            member_path=None,
            sha256=None,
            qpro_key=None,
            stage="other",  # type: ignore[arg-type]
            error_type="Error",
            message="bad",
        )


@pytest.mark.parametrize(
    ("workout_name", "session", "expected_type", "expected_key"),
    [
        (
            "EB1 - Carrera - 1",
            _running_session(),
            RunningMetricsRaw,
            "ENT",
        ),
        (
            "EB9 - Salto de altura - Competic",
            _force_session(),
            ForceMetricsRaw,
            "CMF",
        ),
    ],
)
def test_convert_fit_source_converts_both_families(
    monkeypatch,
    workout_name,
    session,
    expected_type,
    expected_key,
) -> None:
    source = _source("activity.fit")
    decoded = _decoded(
        source,
        workout_name=workout_name,
        session=session,
    )
    observed_crc = []

    def fake_decode(fit_source, *, verify_crc=True):
        assert fit_source is source
        observed_crc.append(verify_crc)
        return decoded

    monkeypatch.setattr("garmin_qpro.conversion.decode_fit", fake_decode)

    result = convert_fit_source(
        source,
        row_number=ROW_NUMBERS[expected_key],
        verify_crc=False,
    )

    assert isinstance(result, ActivityConversionResult)
    assert isinstance(result.metrics, expected_type)
    assert result.activity_context.resolution.qpro_key == expected_key
    assert observed_crc == [False]


@pytest.mark.parametrize(
    ("argument", "expected_error"),
    [
        ({"source": object(), "row_number": 23}, TypeError),
        ({"source": _source("a.fit"), "row_number": True}, TypeError),
        ({"source": _source("a.fit"), "row_number": 0}, ValueError),
        (
            {
                "source": _source("a.fit"),
                "row_number": 23,
                "verify_crc": "yes",
            },
            TypeError,
        ),
    ],
)
def test_convert_fit_source_validates_arguments(argument, expected_error) -> None:
    with pytest.raises(expected_error):
        convert_fit_source(**argument)


def test_empty_paths_produce_empty_batch() -> None:
    batch = convert_input_paths([], row_numbers=ROW_NUMBERS)

    assert batch == BatchConversionResult(results=(), failures=(), tsv="")
    assert batch.success_count == 0
    assert batch.failure_count == 0


def test_paths_and_zip_members_preserve_received_order(monkeypatch) -> None:
    first_path = Path("second-input.zip")
    second_path = Path("first-input.fit")
    first_member = _source(
        "b.fit",
        container=first_path.name,
        member="b.fit",
    )
    second_member = _source(
        "a.fit",
        container=first_path.name,
        member="a.fit",
    )
    last_source = _source("last.fit")
    _patch_sources_and_decoder(
        monkeypatch,
        {
            first_path: (first_member, second_member),
            second_path: (last_source,),
        },
        {
            "b.fit": _decoded(first_member),
            "a.fit": _force_decoded(second_member),
            "last.fit": _decoded(last_source),
        },
    )

    batch = convert_input_paths(
        [first_path, second_path],
        row_numbers=ROW_NUMBERS,
    )

    assert [result.source_name for result in batch.results] == [
        "b.fit",
        "a.fit",
        "last.fit",
    ]
    assert batch.success_count == 3
    assert batch.failure_count == 0


def test_same_sha_sources_are_not_removed(monkeypatch) -> None:
    path = Path("duplicates.zip")
    first = _source("one.fit", container=path.name, data=b"same")
    second = _source("two.fit", container=path.name, data=b"same")
    assert first.sha256 == second.sha256
    _patch_sources_and_decoder(
        monkeypatch,
        {path: (first, second)},
        {
            "one.fit": _decoded(first),
            "two.fit": _decoded(second),
        },
    )

    batch = convert_input_paths([path], row_numbers=ROW_NUMBERS)

    assert batch.success_count == 2
    assert [result.sha256 for result in batch.results] == [
        first.sha256,
        second.sha256,
    ]


def test_load_failure_does_not_stop_later_paths(monkeypatch) -> None:
    bad_path = Path("missing.fit")
    good_path = Path("good.fit")
    source = _source("good.fit")

    def fake_load(path):
        if Path(path) == bad_path:
            raise FileNotFoundError(bad_path)
        return (source,)

    monkeypatch.setattr("garmin_qpro.batch.load_fit_sources", fake_load)
    monkeypatch.setattr(
        "garmin_qpro.batch.decode_fit",
        lambda fit_source, *, verify_crc=True: _decoded(fit_source),
    )

    batch = convert_input_paths(
        [bad_path, good_path],
        row_numbers=ROW_NUMBERS,
    )

    assert batch.success_count == 1
    assert batch.failure_count == 1
    failure = batch.failures[0]
    assert failure.stage == "load"
    assert failure.input_path == bad_path
    assert failure.source_name is None
    assert failure.container_name is None
    assert failure.member_path is None
    assert failure.sha256 is None


def test_decode_failure_does_not_stop_next_source(monkeypatch) -> None:
    path = Path("mixed.zip")
    bad = _source(
        "bad.fit",
        container=path.name,
        member="dir/bad.fit",
    )
    good = _source(
        "good.fit",
        container=path.name,
        member="dir/good.fit",
    )
    monkeypatch.setattr(
        "garmin_qpro.batch.load_fit_sources",
        lambda input_path: (bad, good),
    )

    def fake_decode(source, *, verify_crc=True):
        if source is bad:
            raise ValueError("invalid FIT")
        return _decoded(source)

    monkeypatch.setattr("garmin_qpro.batch.decode_fit", fake_decode)

    batch = convert_input_paths([path], row_numbers=ROW_NUMBERS)

    assert batch.success_count == 1
    assert batch.failure_count == 1
    failure = batch.failures[0]
    assert failure.stage == "decode"
    assert failure.source_name == "bad.fit"
    assert failure.container_name == path.name
    assert failure.member_path == "dir/bad.fit"
    assert failure.sha256 == bad.sha256


def test_unresolved_activity_becomes_resolve_failure(monkeypatch) -> None:
    path = Path("unknown.fit")
    source = _source("unknown.fit")
    _patch_sources_and_decoder(
        monkeypatch,
        {path: (source,)},
        {
            source.source_name: _decoded(
                source,
                workout_name="EB9 - Desconocido",
                session=_force_session(),
            )
        },
    )

    batch = convert_input_paths([path], row_numbers=ROW_NUMBERS)

    assert batch.success_count == 0
    assert batch.failure_count == 1
    failure = batch.failures[0]
    assert failure.stage == "resolve"
    assert failure.qpro_key is None
    assert failure.source_name == source.source_name
    assert failure.sha256 == source.sha256


def test_missing_row_number_isolated_after_resolution(monkeypatch) -> None:
    path = Path("running.fit")
    source = _source("running.fit")
    _patch_sources_and_decoder(
        monkeypatch,
        {path: (source,)},
        {source.source_name: _decoded(source)},
    )

    batch = convert_input_paths(
        [path],
        row_numbers={"CAL": 18},
    )

    assert batch.success_count == 0
    failure = batch.failures[0]
    assert failure.stage == "row_number"
    assert failure.qpro_key == "ENT"
    assert failure.source_name == source.source_name


def test_convert_failure_isolated_after_row_lookup(monkeypatch) -> None:
    path = Path("running.fit")
    source = _source("running.fit")
    _patch_sources_and_decoder(
        monkeypatch,
        {path: (source,)},
        {source.source_name: _decoded(source)},
    )
    monkeypatch.setattr(
        "garmin_qpro.batch.convert_decoded_activity",
        lambda decoded, *, row_number: (_ for _ in ()).throw(
            RuntimeError("conversion failed")
        ),
    )

    batch = convert_input_paths([path], row_numbers=ROW_NUMBERS)

    assert batch.success_count == 0
    failure = batch.failures[0]
    assert failure.stage == "convert"
    assert failure.qpro_key == "ENT"
    assert failure.error_type == "RuntimeError"
    assert failure.message == "conversion failed"


def test_normalized_row_map_is_used_without_mutating_input(monkeypatch) -> None:
    path = Path("running.fit")
    source = _source("running.fit")
    _patch_sources_and_decoder(
        monkeypatch,
        {path: (source,)},
        {source.source_name: _decoded(source)},
    )
    row_numbers = {" ent ": 23}
    before = dict(row_numbers)

    batch = convert_input_paths([path], row_numbers=row_numbers)

    assert batch.success_count == 1
    assert row_numbers == before
    assert result_formula_rows(batch.results[0]) == (23, 23)


def result_formula_rows(result: ActivityConversionResult) -> tuple[int, int]:
    vmed = result.row.get("VMED_M_S")
    vmax = result.row.get("VMAX_M_S")
    for row_number in range(1, 100):
        if (
            vmed == build_vmed_ms_formula(row_number)
            and vmax == build_vmax_ms_formula(row_number)
        ):
            return row_number, row_number
    raise AssertionError("formula row not found")


@pytest.mark.parametrize(
    ("row_numbers", "expected_error"),
    [
        ({"UNKNOWN": 1}, ValueError),
        ({"ENT": 0}, ValueError),
        ({"ENT": -1}, ValueError),
        ({"ENT": True}, TypeError),
        ({"ENT": 1.5}, TypeError),
        ({"ENT": "23"}, TypeError),
        ({"ENT": 23, " ent ": 24}, ValueError),
        ({1: 23}, TypeError),
    ],
)
def test_invalid_row_number_configuration_is_rejected_before_loading(
    monkeypatch,
    row_numbers,
    expected_error,
) -> None:
    called = False

    def fake_load(path):
        nonlocal called
        called = True
        return ()

    monkeypatch.setattr("garmin_qpro.batch.load_fit_sources", fake_load)

    with pytest.raises(expected_error):
        convert_input_paths([Path("input.fit")], row_numbers=row_numbers)
    assert called is False


def test_non_mapping_rows_and_single_path_text_are_rejected() -> None:
    with pytest.raises(TypeError):
        convert_input_paths([], row_numbers=[])  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        convert_input_paths("one.fit", row_numbers=ROW_NUMBERS)
    with pytest.raises(TypeError):
        convert_input_paths(Path("one.fit"), row_numbers=ROW_NUMBERS)


def test_verify_crc_is_validated_and_forwarded_to_every_source(
    monkeypatch,
) -> None:
    path = Path("two.zip")
    sources = (
        _source("one.fit", container=path.name),
        _source("two.fit", container=path.name),
    )
    monkeypatch.setattr(
        "garmin_qpro.batch.load_fit_sources",
        lambda input_path: sources,
    )
    observed = []

    def fake_decode(source, *, verify_crc=True):
        observed.append((source.source_name, verify_crc))
        return _decoded(source)

    monkeypatch.setattr("garmin_qpro.batch.decode_fit", fake_decode)

    batch = convert_input_paths(
        [path],
        row_numbers=ROW_NUMBERS,
        verify_crc=False,
    )

    assert batch.success_count == 2
    assert observed == [("one.fit", False), ("two.fit", False)]
    with pytest.raises(TypeError):
        convert_input_paths([], row_numbers=ROW_NUMBERS, verify_crc="yes")


def test_batch_tsv_contains_only_successes_in_result_order(
    monkeypatch,
) -> None:
    path = Path("three.zip")
    first = _source("first.fit", container=path.name)
    bad = _source("bad.fit", container=path.name)
    last = _source("last.fit", container=path.name)
    monkeypatch.setattr(
        "garmin_qpro.batch.load_fit_sources",
        lambda input_path: (first, bad, last),
    )

    def fake_decode(source, *, verify_crc=True):
        if source is bad:
            raise ValueError("bad")
        return _decoded(source)

    monkeypatch.setattr("garmin_qpro.batch.decode_fit", fake_decode)

    batch = convert_input_paths([path], row_numbers=ROW_NUMBERS)
    lines = batch.tsv.split("\n")

    assert batch.success_count == 2
    assert batch.failure_count == 1
    assert lines == [result.tsv for result in batch.results]
    assert batch.tsv.count("\n") == 1
    assert not batch.tsv.endswith("\n")
    for line, result in zip(lines, batch.results, strict=True):
        assert line.count("\t") == 22
        assert len(line.split("\t")) == 23
        assert line.split("\t")[-1] == result.row.get("OVM")
        assert not line.endswith("\t")


def test_batch_preserves_cal_and_force_rules(monkeypatch) -> None:
    cal_path = Path("cal.fit")
    force_path = Path("force.fit")
    cal_source = _source("cal.fit")
    force_source = _source("force.fit")
    cal_decoded = _decoded(
        cal_source,
        workout_name="EB0 - Cal. Estadio",
        session=_running_session(avg_cadence=1, avg_power=1),
        extra_messages={
            "lap": [
                {
                    "intensity": "warmup",
                    "total_timer_time": 10.0,
                    "avg_cadence": 70,
                    "max_cadence": 80,
                    "avg_power": 150,
                    "max_power": 250,
                }
            ]
        },
    )
    _patch_sources_and_decoder(
        monkeypatch,
        {cal_path: (cal_source,), force_path: (force_source,)},
        {
            cal_source.source_name: cal_decoded,
            force_source.source_name: _force_decoded(force_source),
        },
    )

    batch = convert_input_paths(
        [cal_path, force_path],
        row_numbers=ROW_NUMBERS,
    )

    assert batch.results[0].row.get("CADM") == "'140"
    assert batch.results[0].row.get("PTM") == "'150"
    assert batch.results[1].row.get("MIN") == "'028"
    assert batch.results[1].row.get("CARGA") == "'094"
    assert result_formula_rows(batch.results[0]) == (18, 18)
    assert result_formula_rows(batch.results[1]) == (36, 36)


def test_discover_input_paths_filters_and_orders_without_recursion(
    tmp_path,
) -> None:
    (tmp_path / "b.ZIP").write_bytes(b"zip")
    (tmp_path / "A.fit").write_bytes(b"fit")
    (tmp_path / "c.FIT").write_bytes(b"fit")
    (tmp_path / "notes.txt").write_text("ignore", encoding="ascii")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "inside.fit").write_bytes(b"fit")

    discovered = discover_input_paths(tmp_path)

    assert isinstance(discovered, tuple)
    assert [path.name for path in discovered] == [
        "A.fit",
        "b.ZIP",
        "c.FIT",
    ]


def test_discover_rejects_missing_and_non_directory(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        discover_input_paths(tmp_path / "missing")

    file_path = tmp_path / "one.fit"
    file_path.write_bytes(b"fit")
    with pytest.raises(NotADirectoryError):
        discover_input_paths(file_path)


def test_empty_directory_produces_empty_batch(tmp_path) -> None:
    (tmp_path / "notes.txt").write_text("ignore", encoding="ascii")

    batch = convert_input_directory(
        tmp_path,
        row_numbers=ROW_NUMBERS,
    )

    assert batch == BatchConversionResult(results=(), failures=(), tsv="")


def test_directory_conversion_delegates_discovered_order(
    monkeypatch,
    tmp_path,
) -> None:
    first = tmp_path / "A.fit"
    second = tmp_path / "b.zip"
    first.write_bytes(b"fit")
    second.write_bytes(b"zip")
    observed = {}
    sentinel = BatchConversionResult(results=(), failures=(), tsv="")

    def fake_batch(paths, *, row_numbers, verify_crc=True):
        observed["paths"] = tuple(paths)
        observed["rows"] = row_numbers
        observed["crc"] = verify_crc
        return sentinel

    monkeypatch.setattr("garmin_qpro.batch.convert_input_paths", fake_batch)

    result = convert_input_directory(
        tmp_path,
        row_numbers=ROW_NUMBERS,
        verify_crc=False,
    )

    assert result is sentinel
    assert observed == {
        "paths": (first, second),
        "rows": ROW_NUMBERS,
        "crc": False,
    }


def test_public_api_exports_batch_components() -> None:
    expected = {
        "BatchConversionFailure",
        "BatchConversionResult",
        "convert_fit_source",
        "convert_input_paths",
        "discover_input_paths",
        "convert_input_directory",
    }

    assert expected <= set(garmin_qpro.__all__)
    assert garmin_qpro.BatchConversionFailure is BatchConversionFailure
    assert garmin_qpro.BatchConversionResult is BatchConversionResult
    assert garmin_qpro.convert_fit_source is convert_fit_source
    assert garmin_qpro.convert_input_paths is convert_input_paths
    assert garmin_qpro.discover_input_paths is discover_input_paths
    assert garmin_qpro.convert_input_directory is convert_input_directory
