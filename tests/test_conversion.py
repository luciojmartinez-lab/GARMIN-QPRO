from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import garmin_qpro
from garmin_qpro.conversion import (
    ActivityConversionResult,
    ActivityRequiresChoiceError,
    MultipleFitSourcesError,
    convert_decoded_activity,
    convert_fit_source,
    convert_input_path,
)
from garmin_qpro.fit.force_metrics import ForceMetricsRaw
from garmin_qpro.fit.models import DecodedFit
from garmin_qpro.fit.running_metrics import (
    RunningMetricsRaw,
    UnreliableCamTimeError,
)
from garmin_qpro.input.sources import FitSource, UnsupportedInputError
from garmin_qpro.qpro.formulas import (
    build_vmax_ms_formula,
    build_vmed_ms_formula,
)


def _source(
    name: str = "activity.fit",
    *,
    container: str | None = "activity.zip",
    member: str | None = "activity.fit",
    data: bytes | None = None,
) -> FitSource:
    return FitSource(
        source_name=name,
        container_name=container,
        member_path=member,
        data=data or name.encode("ascii"),
    )


def _session(**overrides):
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
    *,
    source: FitSource | None = None,
    messages=None,
    errors=(),
    crc_checked: bool = True,
) -> DecodedFit:
    return DecodedFit(
        source=source or _source(),
        messages={} if messages is None else messages,
        errors=errors,
        crc_checked=crc_checked,
    )


def _workout(name: str):
    return {"wkt_name": name}


def test_conversion_integrates_resolution_metrics_row_and_tsv() -> None:
    source = _source(data=b"one-fit")
    decoded = _decoded(
        source=source,
        messages={
            "workout": [_workout("EB1 - Carrera - 1")],
            "session": [_session()],
        },
        errors=("warning",),
        crc_checked=False,
    )

    result = convert_decoded_activity(decoded, row_number=23)

    assert isinstance(result, ActivityConversionResult)
    assert isinstance(result.metrics, RunningMetricsRaw)
    assert result.source_name == source.source_name
    assert result.container_name == source.container_name
    assert result.member_path == source.member_path
    assert result.sha256 == source.sha256
    assert result.activity_context.resolution.qpro_key == "ENT"
    assert result.metrics.distance_m == 200.0
    assert result.row.get("CODIGO") == "ENT"
    assert result.tsv == "\t".join(result.row.as_tuple())
    assert result.decoder_errors == ("warning",)
    assert result.crc_checked is False


def test_workout_name_key_is_used() -> None:
    result = convert_decoded_activity(
        _decoded(
            messages={
                "workout": [_workout("EB0 - Vuelta a la calma")],
                "session": [_session()],
            }
        ),
        row_number=41,
    )

    assert result.activity_context.resolution.qpro_key == "FIN"
    assert result.row.get("CODIGO") == "FIN"


def test_running_profile_fallback_resolves_ent_when_workout_is_missing() -> None:
    result = convert_decoded_activity(
        _decoded(messages={"session": [_session()]}),
        row_number=23,
    )

    assert result.activity_context.resolution.qpro_key == "ENT"
    assert result.activity_context.resolution.resolution_source == "sport_profile_name"


def test_explicit_key_takes_precedence() -> None:
    result = convert_decoded_activity(
        _decoded(
            messages={
                "workout": [_workout("EB1 - Carrera - 1")],
                "session": [_session()],
            }
        ),
        row_number=18,
        explicit_qpro_key="CAL",
    )

    assert result.activity_context.resolution.qpro_key == "CAL"
    assert result.row.get("CODIGO") == "CAL"


def test_explicit_force_key_takes_precedence() -> None:
    result = convert_decoded_activity(
        _decoded(
            messages={
                "workout": [_workout("EB1 - Carrera - 1")],
                "session": [_force_session()],
            }
        ),
        row_number=36,
        explicit_qpro_key="CMF",
    )

    assert result.activity_context.resolution.qpro_key == "CMF"
    assert result.activity_context.resolution.resolution_source == (
        "explicit_qpro_key"
    )
    assert isinstance(result.metrics, ForceMetricsRaw)
    assert result.row.get("CODIGO") == "CMF"


def test_cal_special_rule_is_applied() -> None:
    result = convert_decoded_activity(
        _decoded(
            messages={
                "workout": [_workout("EB0 - Cal. Estadio")],
                "session": [_session(avg_cadence=1, avg_power=1)],
                "lap": [
                    {
                        "intensity": "warmup",
                        "total_timer_time": 10.0,
                        "avg_cadence": 70,
                        "max_cadence": 80,
                        "avg_power": 150,
                        "max_power": 250,
                    }
                ],
            }
        ),
        row_number=18,
    )

    assert result.metrics.source_scope == "cal_warmup_laps"
    assert result.metrics.warmup_lap_count == 1
    assert result.row.get("CADM") == "'140"
    assert result.row.get("PTM") == "'150"


def test_cam_conversion_uses_coherent_session_time_and_current_schema() -> None:
    start = datetime(2026, 7, 20, tzinfo=timezone.utc)
    records = [
        {
            "timestamp": start + timedelta(seconds=index),
            "enhanced_speed": 1.0,
        }
        for index in range(147)
    ]
    result = convert_decoded_activity(
        _decoded(
            messages={
                "session": [
                    _session(
                        sport_profile_name="Caminar",
                        sport="walking",
                        total_timer_time=5152.979,
                        total_elapsed_time=5152.979,
                        total_moving_time=None,
                        total_distance=3577.58,
                        enhanced_avg_speed=0.694,
                        enhanced_max_speed=5.682,
                    )
                ],
                "record": records,
            }
        ),
        row_number=55,
        explicit_qpro_key="CAM",
    )

    assert result.metrics.moving_time_s == 5152.979
    assert result.row.get("MIN") == "'086"
    assert result.row.get("DISTANCIA") == "3,58"
    assert result.row.get("VMED") == "2,50"
    assert result.row.get("RITMO") == "'24,00"
    assert len(result.row.as_tuple()) == 23
    assert result.tsv.count("\t") == 22
    assert result.tsv.split("\t")[-1] == result.row.get("OVM")
    assert not result.tsv.endswith("\t")


def test_cam_conversion_rejects_unreliable_time_before_building_row() -> None:
    with pytest.raises(UnreliableCamTimeError):
        convert_decoded_activity(
            _decoded(
                messages={
                    "session": [
                        _session(
                            sport_profile_name="Caminar",
                            sport="walking",
                            total_timer_time=147.0,
                            total_elapsed_time=5152.979,
                            total_moving_time=None,
                            total_distance=3577.58,
                            enhanced_avg_speed=0.694,
                        )
                    ]
                }
            ),
            row_number=55,
            explicit_qpro_key="CAM",
        )


def test_received_row_number_is_used_in_formulas() -> None:
    result = convert_decoded_activity(
        _decoded(messages={"session": [_session()]}),
        row_number=77,
    )

    assert result.row.get("VMED_M_S") == build_vmed_ms_formula(77)


def test_result_is_immutable_and_tsv_has_23_columns() -> None:
    result = convert_decoded_activity(
        _decoded(messages={"session": [_session()]}),
        row_number=23,
    )

    with pytest.raises((FrozenInstanceError, AttributeError)):
        result.tsv = ""  # type: ignore[misc]
    assert result.tsv.count("\t") == 22
    assert len(result.tsv.split("\t")) == 23
    assert result.tsv.split("\t")[-1] == result.row.get("OVM")


def test_identity_hash_errors_and_crc_are_preserved() -> None:
    source = _source(name="solo.fit", container=None, member=None, data=b"abc")
    result = convert_decoded_activity(
        _decoded(
            source=source,
            messages={"session": [_session()]},
            errors=({"message": "sdk"},),
            crc_checked=False,
        ),
        row_number=23,
    )

    assert result.source_name == "solo.fit"
    assert result.container_name is None
    assert result.member_path is None
    assert result.sha256 == source.sha256
    assert result.decoder_errors == ({"message": "sdk"},)
    assert result.crc_checked is False


def test_unresolved_activity_requires_choice() -> None:
    decoded = _decoded(messages={"session": [_session(sport_profile_name="Fuerza")]})

    with pytest.raises(ActivityRequiresChoiceError) as exc_info:
        convert_decoded_activity(decoded, row_number=23)

    assert exc_info.value.source is decoded.source
    assert exc_info.value.activity_context.metadata.sport_profile_name == "Fuerza"
    assert exc_info.value.qpro_key is None
    assert exc_info.value.reason


@pytest.mark.parametrize(
    "workout_name",
    [
        "EB9 - Salto de altura - Competic",
        "EB9 - Triple Salto - Competicion",
    ],
)
def test_confirmed_eb9_workouts_use_force_conversion(
    workout_name: str,
) -> None:
    result = convert_decoded_activity(
        _decoded(
            messages={
                "workout": [_workout(workout_name)],
                "session": [_force_session()],
            }
        ),
        row_number=36,
    )

    assert isinstance(result, ActivityConversionResult)
    assert isinstance(result.metrics, ForceMetricsRaw)
    assert result.activity_context.resolution.qpro_key == "CMF"
    assert result.activity_context.resolution.resolution_source == (
        "workout_name"
    )
    assert result.row.get("CODIGO") == "CMF"
    assert result.row.get("PPME") == "'121"
    assert result.row.get("PPMAX") == "'146"
    assert result.row.get("MIN") == "'028"
    assert result.row.get("AER") == "3,0"
    assert result.row.get("ANA") == "2,3"
    assert result.row.get("CARGA") == "'094"


def test_unknown_eb9_workout_still_requires_choice() -> None:
    decoded = _decoded(
        messages={
            "workout": [_workout("EB9 - Competicion desconocida")],
            "session": [_force_session()],
        }
    )

    with pytest.raises(ActivityRequiresChoiceError):
        convert_decoded_activity(decoded, row_number=36)


def test_force_uses_timer_time_and_session_training_load_only() -> None:
    result = convert_decoded_activity(
        _decoded(
            messages={
                "session": [
                    _force_session(
                        total_timer_time=90.0,
                        total_elapsed_time=3600.0,
                        training_load_peak=12.5,
                    )
                ],
                "set": [
                    {
                        "set_type": "active",
                        "weight": 999.0,
                        "repetitions": 100,
                    }
                ],
            }
        ),
        row_number=36,
        explicit_qpro_key="CMF",
    )

    assert result.row.get("MIN") == "'002"
    assert result.row.get("CARGA") == "'013"


def test_force_elapsed_time_does_not_replace_missing_timer_time() -> None:
    result = convert_decoded_activity(
        _decoded(
            messages={
                "session": [
                    _force_session(
                        total_timer_time=None,
                        total_elapsed_time=3600.0,
                    )
                ]
            }
        ),
        row_number=36,
        explicit_qpro_key="CMF",
    )

    assert result.metrics.timer_time_s is None
    assert result.metrics.elapsed_time_s == 3600.0
    assert result.row.get("MIN") == ""


def test_force_result_uses_received_row_and_current_schema() -> None:
    result = convert_decoded_activity(
        _decoded(messages={"session": [_force_session()]}),
        row_number=36,
        explicit_qpro_key="CMF",
    )

    assert result.row.get("VMED_M_S") == build_vmed_ms_formula(36)
    assert result.row.get("VMAX_M_S") == build_vmax_ms_formula(36)
    assert len(result.row.as_tuple()) == 23
    assert result.tsv.count("\t") == 22
    assert result.tsv.split("\t")[-1] == result.row.get("OVM")


def test_unknown_explicit_key_is_rejected() -> None:
    with pytest.raises(ValueError):
        convert_decoded_activity(
            _decoded(messages={"session": [_session()]}),
            row_number=23,
            explicit_qpro_key="COM",
        )


def test_decoded_type_is_validated() -> None:
    with pytest.raises(TypeError):
        convert_decoded_activity(object(), row_number=23)  # type: ignore[arg-type]


@pytest.mark.parametrize("row_number", [True, 0, -1, 1.5, "23"])
def test_row_number_is_validated(row_number) -> None:
    with pytest.raises((TypeError, ValueError)):
        convert_decoded_activity(
            _decoded(messages={"session": [_session()]}),
            row_number=row_number,
        )


def test_verify_crc_type_is_validated() -> None:
    with pytest.raises(TypeError):
        convert_input_path(Path("x.fit"), row_number=23, verify_crc="yes")


def test_fit_individual_with_single_source_is_converted(monkeypatch) -> None:
    source = _source("one.fit", container=None, member=None)

    def fake_load(path):
        assert path == Path("one.fit")
        return (source,)

    def fake_decode(fit_source, *, verify_crc=True):
        assert fit_source is source
        assert verify_crc is False
        return _decoded(
            source=source,
            messages={"session": [_session()]},
            crc_checked=False,
        )

    monkeypatch.setattr("garmin_qpro.conversion.load_fit_sources", fake_load)
    monkeypatch.setattr("garmin_qpro.conversion.decode_fit", fake_decode)

    result = convert_input_path(Path("one.fit"), row_number=23, verify_crc=False)

    assert result.source_name == "one.fit"
    assert result.crc_checked is False


def test_input_path_delegates_one_loaded_source(monkeypatch) -> None:
    source = _source("one.fit", container=None, member=None)
    sentinel = object()
    observed = {}

    monkeypatch.setattr(
        "garmin_qpro.conversion.load_fit_sources",
        lambda path: (source,),
    )

    def fake_convert(
        fit_source,
        *,
        row_number,
        explicit_qpro_key=None,
        verify_crc=True,
    ):
        observed["source"] = fit_source
        observed["row_number"] = row_number
        observed["key"] = explicit_qpro_key
        observed["crc"] = verify_crc
        return sentinel

    monkeypatch.setattr(
        "garmin_qpro.conversion.convert_fit_source",
        fake_convert,
    )

    result = convert_input_path(
        Path("one.fit"),
        row_number=36,
        explicit_qpro_key="CMF",
        verify_crc=False,
    )

    assert result is sentinel
    assert observed == {
        "source": source,
        "row_number": 36,
        "key": "CMF",
        "crc": False,
    }


def test_zip_with_single_source_is_converted(monkeypatch) -> None:
    source = _source("activity.fit", container="one.zip", member="dir/activity.fit")

    monkeypatch.setattr(
        "garmin_qpro.conversion.load_fit_sources",
        lambda path: (source,),
    )
    monkeypatch.setattr(
        "garmin_qpro.conversion.decode_fit",
        lambda fit_source, *, verify_crc=True: _decoded(
            source=fit_source,
            messages={"session": [_session()]},
            crc_checked=verify_crc,
        ),
    )

    result = convert_input_path(Path("one.zip"), row_number=23)

    assert result.container_name == "one.zip"
    assert result.member_path == "dir/activity.fit"


def test_input_path_converts_one_force_source(monkeypatch) -> None:
    source = _source(
        "strength.fit",
        container="strength.zip",
        member="strength.fit",
    )
    monkeypatch.setattr(
        "garmin_qpro.conversion.load_fit_sources",
        lambda path: (source,),
    )
    monkeypatch.setattr(
        "garmin_qpro.conversion.decode_fit",
        lambda fit_source, *, verify_crc=True: _decoded(
            source=fit_source,
            messages={
                "workout": [
                    _workout("EB9 - Salto de altura - Competic")
                ],
                "session": [_force_session()],
            },
            crc_checked=verify_crc,
        ),
    )

    result = convert_input_path(Path("strength.zip"), row_number=36)

    assert isinstance(result, ActivityConversionResult)
    assert isinstance(result.metrics, ForceMetricsRaw)
    assert result.activity_context.resolution.qpro_key == "CMF"
    assert result.row.get("CARGA") == "'094"


def test_multiple_fit_sources_are_rejected(monkeypatch) -> None:
    sources = (_source("a.fit"), _source("b.fit"))
    monkeypatch.setattr(
        "garmin_qpro.conversion.load_fit_sources",
        lambda path: sources,
    )

    with pytest.raises(MultipleFitSourcesError) as exc_info:
        convert_input_path(Path("multi.zip"), row_number=23)

    assert exc_info.value.path == Path("multi.zip")
    assert exc_info.value.sources == sources


def test_loader_and_decoder_errors_are_propagated(monkeypatch) -> None:
    monkeypatch.setattr(
        "garmin_qpro.conversion.load_fit_sources",
        lambda path: (_ for _ in ()).throw(UnsupportedInputError("bad")),
    )

    with pytest.raises(UnsupportedInputError):
        convert_input_path(Path("bad.txt"), row_number=23)

    source = _source()
    monkeypatch.setattr(
        "garmin_qpro.conversion.load_fit_sources",
        lambda path: (source,),
    )
    monkeypatch.setattr(
        "garmin_qpro.conversion.decode_fit",
        lambda fit_source, *, verify_crc=True: (_ for _ in ()).throw(
            ValueError("invalid fit")
        ),
    )

    with pytest.raises(ValueError, match="invalid fit"):
        convert_input_path(Path("bad.fit"), row_number=23)


def test_public_api_exposes_only_the_general_result() -> None:
    old_result_name = "Running" + "ConversionResult"
    old_error_name = "Unsupported" + "ActivityFamilyError"

    assert garmin_qpro.ActivityConversionResult is ActivityConversionResult
    assert "ActivityConversionResult" in garmin_qpro.__all__
    assert not hasattr(garmin_qpro, old_result_name)
    assert not hasattr(garmin_qpro, old_error_name)
    assert old_result_name not in garmin_qpro.__all__
    assert old_error_name not in garmin_qpro.__all__
