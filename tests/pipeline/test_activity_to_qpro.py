from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from garmin_qpro.conversion import ActivityRequiresChoiceError
from garmin_qpro.fit.force_metrics import ForceMetricsRaw
from garmin_qpro.fit.models import DecodedFit
from garmin_qpro.fit.running_metrics import RunningMetricsRaw
from garmin_qpro.garmin_connect import HistoricalTrainingLoad
from garmin_qpro.input.sources import FitSource
from garmin_qpro.pipeline.activity_to_qpro import (
    ActivityToQProResult,
    convert_decoded_activity_to_qpro,
)
from garmin_qpro.qpro.rows import QProFamily
from garmin_qpro.qpro.schema import QPRO_COLUMNS
from garmin_qpro.qpro.training_load import QPRO_COLUMNS_WITH_TRAINING_LOAD


def _decoded(messages) -> DecodedFit:
    return DecodedFit(
        source=FitSource(
            source_name="activity.fit",
            container_name=None,
            member_path=None,
            data=b"synthetic-fit",
        ),
        messages=messages,
        errors=(),
        crc_checked=True,
    )


def _workout(name: str):
    return {"wkt_name": name}


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


def _historical_load(
    acute_load: float | None = 277,
    chronic_load: float | None = 239,
) -> HistoricalTrainingLoad:
    return HistoricalTrainingLoad(
        date=date(2026, 7, 6),
        acute_load=acute_load,
        chronic_load=chronic_load,
        acwr=None,
        training_status=None,
        load_tunnel_min=None,
        load_tunnel_max=None,
        load_balance_status=None,
    )


def _assert_final_shape(result: ActivityToQProResult) -> None:
    assert QPRO_COLUMNS_WITH_TRAINING_LOAD == (
        *QPRO_COLUMNS,
        "CARGA_AGUDA",
        "CARGA_CRONICA",
    )
    assert len(result.base_row.as_tuple()) == 23
    assert len(result.final_row.as_tuple()) == 25
    assert result.tsv.split("\t") == list(result.final_row.as_tuple())
    assert result.tsv.count("\t") == 24


def test_running_ent_uses_running_pipeline() -> None:
    result = convert_decoded_activity_to_qpro(
        _decoded(
            {
                "workout": [_workout("EB1 - Carrera - 1")],
                "session": [_running_session()],
            }
        )
    )

    assert result.qpro_key == "ENT"
    assert result.family is QProFamily.RUNNING
    assert isinstance(result.metrics, RunningMetricsRaw)
    assert result.base_row.get("CODIGO") == "ENT"
    _assert_final_shape(result)


def test_running_cal_preserves_approved_warmup_rule() -> None:
    result = convert_decoded_activity_to_qpro(
        _decoded(
            {
                "workout": [_workout("EB0 - Cal. Estadio")],
                "session": [_running_session(avg_cadence=1, avg_power=1)],
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
        )
    )

    assert result.qpro_key == "CAL"
    assert result.family is QProFamily.RUNNING
    assert isinstance(result.metrics, RunningMetricsRaw)
    assert result.metrics.source_scope == "cal_warmup_laps"
    assert result.base_row.get("CADM") == "'140"
    assert result.base_row.get("PTM") == "'150"
    _assert_final_shape(result)


@pytest.mark.parametrize(
    ("workout_name", "expected_key"),
    [
        ("EB5 - Pesas - Fase 1", "PES"),
        ("EB9 - Salto de altura - Competic", "CMF"),
    ],
)
def test_force_keys_use_force_pipeline(workout_name, expected_key) -> None:
    result = convert_decoded_activity_to_qpro(
        _decoded(
            {
                "workout": [_workout(workout_name)],
                "session": [_force_session()],
            }
        )
    )

    assert result.qpro_key == expected_key
    assert result.family is QProFamily.FORCE
    assert isinstance(result.metrics, ForceMetricsRaw)
    assert result.base_row.get("CODIGO") == expected_key
    assert result.base_row.get("DISTANCIA") == "0,00"
    _assert_final_shape(result)


def test_unresolved_activity_does_not_generate_a_row() -> None:
    decoded = _decoded(
        {
            "session": [
                _running_session(
                    sport_profile_name="Yoga",
                    sport="training",
                    sub_sport="yoga",
                )
            ]
        }
    )

    with pytest.raises(ActivityRequiresChoiceError):
        convert_decoded_activity_to_qpro(decoded)


def test_historical_load_populates_only_columns_24_and_25() -> None:
    result = convert_decoded_activity_to_qpro(
        _decoded(
            {
                "workout": [_workout("EB1 - Carrera - 1")],
                "session": [_running_session()],
            }
        ),
        historical_training_load=_historical_load(),
    )

    assert result.final_row.as_tuple()[:23] == result.base_row.as_tuple()
    assert result.final_row.get("CARGA_AGUDA") == "'277"
    assert result.final_row.get("CARGA_CRONICA") == "'239"
    _assert_final_shape(result)


def test_missing_historical_load_keeps_two_empty_columns() -> None:
    result = convert_decoded_activity_to_qpro(
        _decoded(
            {
                "workout": [_workout("EB1 - Carrera - 1")],
                "session": [_running_session()],
            }
        )
    )

    assert result.final_row.as_tuple()[:23] == result.base_row.as_tuple()
    assert result.final_row.as_tuple()[23:] == ("", "")
    _assert_final_shape(result)


def test_result_is_immutable() -> None:
    result = convert_decoded_activity_to_qpro(
        _decoded(
            {
                "workout": [_workout("EB1 - Carrera - 1")],
                "session": [_running_session()],
            }
        )
    )

    with pytest.raises(FrozenInstanceError):
        result.qpro_key = "CAL"  # type: ignore[misc]
