from datetime import date, datetime

import pytest

from garmin_qpro.fit.force_metrics import ForceMetricsRaw
from garmin_qpro.fit.models import DecodedFit
from garmin_qpro.fit.running_metrics import RunningMetricsRaw
from garmin_qpro.garmin_connect import (
    GarminPyQueryError,
    HistoricalTrainingLoad,
)
from garmin_qpro.input.sources import FitSource
from garmin_qpro.pipeline import garmin_load as service_module
from garmin_qpro.pipeline.garmin_load import (
    ActivityDateUnavailableForGarminLoadError,
    convert_input_path_to_qpro_with_garmin_load,
)
from garmin_qpro.qpro.rows import QProFamily


class FakeAdapter:
    def __init__(
        self,
        load: HistoricalTrainingLoad | None = None,
        error: Exception | None = None,
    ) -> None:
        self.load = load
        self.error = error
        self.calls: list[date] = []

    def get_for_date(self, day: date) -> HistoricalTrainingLoad:
        self.calls.append(day)
        if self.error is not None:
            raise self.error
        assert self.load is not None
        return self.load


def _source() -> FitSource:
    return FitSource("activity.fit", None, None, b"synthetic-fit")


def _decoded(messages) -> DecodedFit:
    return DecodedFit(
        source=_source(),
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
        "local_timestamp": datetime(2026, 7, 6, 10, 0),
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
        "local_timestamp": datetime(2026, 7, 6, 10, 0),
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


def _load(
    acute: float | None,
    chronic: float | None,
) -> HistoricalTrainingLoad:
    return HistoricalTrainingLoad(
        date=date(2026, 7, 6),
        acute_load=acute,
        chronic_load=chronic,
        acwr=9.9,
        training_status="IGNORED",
        load_tunnel_min=1.0,
        load_tunnel_max=999.0,
        load_balance_status="IGNORED",
    )


def _patch_input(monkeypatch, decoded: DecodedFit) -> None:
    monkeypatch.setattr(
        service_module,
        "load_fit_sources",
        lambda path: (decoded.source,),
    )
    monkeypatch.setattr(
        service_module,
        "decode_fit",
        lambda source, *, verify_crc=True: decoded,
    )


@pytest.mark.parametrize(
    ("acute", "chronic", "expected"),
    [
        (277, 239, ("'277", "'239")),
        (None, 239, ("", "'239")),
        (277, None, ("'277", "")),
        (None, None, ("", "")),
    ],
)
def test_queries_exact_activity_date_and_populates_load_columns(
    monkeypatch,
    acute,
    chronic,
    expected,
) -> None:
    decoded = _decoded(
        {
            "workout": [_workout("EB1 - Carrera - 1")],
            "session": [_running_session()],
        }
    )
    _patch_input(monkeypatch, decoded)
    adapter = FakeAdapter(_load(acute, chronic))

    result = convert_input_path_to_qpro_with_garmin_load(
        "activity.fit",
        adapter=adapter,
    )

    assert adapter.calls == [date(2026, 7, 6)]
    assert result.final_row.as_tuple()[23:] == expected
    assert len(result.final_row.as_tuple()) == 25
    assert result.tsv.count("\t") == 24


def test_missing_activity_date_does_not_query_adapter(monkeypatch) -> None:
    decoded = _decoded(
        {
            "workout": [_workout("EB1 - Carrera - 1")],
            "session": [_running_session(local_timestamp=None)],
        }
    )
    _patch_input(monkeypatch, decoded)
    adapter = FakeAdapter(_load(277, 239))

    with pytest.raises(ActivityDateUnavailableForGarminLoadError):
        convert_input_path_to_qpro_with_garmin_load(
            "activity.fit",
            adapter=adapter,
        )

    assert adapter.calls == []


def test_adapter_error_is_propagated_without_fake_load(monkeypatch) -> None:
    decoded = _decoded(
        {
            "workout": [_workout("EB1 - Carrera - 1")],
            "session": [_running_session()],
        }
    )
    _patch_input(monkeypatch, decoded)
    adapter = FakeAdapter(error=GarminPyQueryError("RATE_LIMITED"))

    with pytest.raises(GarminPyQueryError) as caught:
        convert_input_path_to_qpro_with_garmin_load(
            "activity.fit",
            adapter=adapter,
        )

    assert caught.value.error_code == "RATE_LIMITED"
    assert adapter.calls == [date(2026, 7, 6)]


def test_running_activity_uses_existing_running_path(monkeypatch) -> None:
    decoded = _decoded(
        {
            "workout": [_workout("EB1 - Carrera - 1")],
            "session": [_running_session()],
        }
    )
    _patch_input(monkeypatch, decoded)

    result = convert_input_path_to_qpro_with_garmin_load(
        "activity.fit",
        adapter=FakeAdapter(_load(277, 239)),
    )

    assert result.qpro_key == "ENT"
    assert result.family is QProFamily.RUNNING
    assert isinstance(result.metrics, RunningMetricsRaw)
    assert len(result.final_row.as_tuple()) == 25


def test_force_activity_uses_existing_force_path(monkeypatch) -> None:
    decoded = _decoded(
        {
            "workout": [_workout("EB5 - Pesas - Fase 1")],
            "session": [_force_session()],
        }
    )
    _patch_input(monkeypatch, decoded)

    result = convert_input_path_to_qpro_with_garmin_load(
        "activity.fit",
        adapter=FakeAdapter(_load(277, 239)),
    )

    assert result.qpro_key == "PES"
    assert result.family is QProFamily.FORCE
    assert isinstance(result.metrics, ForceMetricsRaw)
    assert len(result.final_row.as_tuple()) == 25
