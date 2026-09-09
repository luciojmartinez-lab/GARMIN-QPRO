from __future__ import annotations

import json
import subprocess
from dataclasses import FrozenInstanceError
from datetime import date, datetime

import pytest

from garmin_qpro.garmin_connect.training_load import (
    GarminPyQueryError,
    GarminPyResponseError,
    GarminPyTrainingLoadAdapter,
    GarminPyUnavailableError,
    HistoricalTrainingLoad,
)


def _result(payload, *, returncode: int = 0):
    return subprocess.CompletedProcess(
        args=("garmin-cli",),
        returncode=returncode,
        stdout=json.dumps(payload),
        stderr="private diagnostic",
    )


def _success(day: str, acute=964, chronic=772):
    return {
        "ok": True,
        "command": "health status",
        "count": 1,
        "data": [
            {
                "date": day,
                "acute_load": acute,
                "chronic_load": chronic,
            }
        ],
    }


def test_queries_garmin_py_public_json_contract_without_shell() -> None:
    calls = []

    def runner(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return _result(_success("2026-09-09"))

    load = GarminPyTrainingLoadAdapter(_runner=runner).get_for_date(
        date(2026, 9, 9)
    )

    assert load == HistoricalTrainingLoad(date(2026, 9, 9), 964.0, 772.0)
    arguments, kwargs = calls[0]
    assert arguments == (
        "garmin-cli",
        "--json",
        "health",
        "status",
        "--date",
        "2026-09-09",
    )
    assert kwargs["shell"] is False
    assert kwargs["check"] is False
    assert kwargs["capture_output"] is True


def test_supports_explicit_isolated_command_prefix() -> None:
    observed = []

    def runner(arguments, **_kwargs):
        observed.append(arguments)
        return _result(_success("2026-09-09"))

    adapter = GarminPyTrainingLoadAdapter(
        ("C:/garmin-py/.venv/Scripts/python.exe", "-m", "garmin_cli"),
        _runner=runner,
    )
    adapter.get_for_date(date(2026, 9, 9))

    assert observed[0][:3] == (
        "C:/garmin-py/.venv/Scripts/python.exe",
        "-m",
        "garmin_cli",
    )


def test_result_is_immutable_and_discards_unrelated_payload_fields() -> None:
    result = HistoricalTrainingLoad(date(2026, 9, 9), 12, 34)

    with pytest.raises(FrozenInstanceError):
        result.acute_load = 1  # type: ignore[misc]
    assert not hasattr(result, "coordinates")


@pytest.mark.parametrize("value", [True, "10", -1, float("nan"), float("inf")])
def test_rejects_invalid_load_values(value) -> None:
    adapter = GarminPyTrainingLoadAdapter(
        _runner=lambda *_args, **_kwargs: _result(
            _success("2026-09-09", acute=value)
        )
    )

    with pytest.raises(GarminPyResponseError):
        adapter.get_for_date(date(2026, 9, 9))


def test_preserves_zero_and_missing_loads() -> None:
    adapter = GarminPyTrainingLoadAdapter(
        _runner=lambda *_args, **_kwargs: _result(
            _success("2026-09-09", acute=0, chronic=None)
        )
    )

    assert adapter.get_for_date(date(2026, 9, 9)) == HistoricalTrainingLoad(
        date(2026, 9, 9), 0.0, None
    )


def test_empty_daily_result_returns_explicit_missing_loads() -> None:
    adapter = GarminPyTrainingLoadAdapter(
        _runner=lambda *_args, **_kwargs: _result(
            {"ok": True, "data": []}
        )
    )

    assert adapter.get_for_date(date(2026, 9, 9)) == HistoricalTrainingLoad(
        date(2026, 9, 9), None, None
    )


def test_rejects_wrong_or_ambiguous_historical_date() -> None:
    adapter = GarminPyTrainingLoadAdapter(
        _runner=lambda *_args, **_kwargs: _result(
            _success("2026-09-08")
        )
    )

    with pytest.raises(GarminPyResponseError, match="requested date"):
        adapter.get_for_date(date(2026, 9, 9))


@pytest.mark.parametrize("payload", [None, [], {"ok": True}, {"ok": True, "data": {}}])
def test_rejects_invalid_json_contract(payload) -> None:
    adapter = GarminPyTrainingLoadAdapter(
        _runner=lambda *_args, **_kwargs: _result(payload)
    )

    with pytest.raises(GarminPyResponseError):
        adapter.get_for_date(date(2026, 9, 9))


def test_rejects_non_json_output_without_echoing_it() -> None:
    private = "token=private-value"
    adapter = GarminPyTrainingLoadAdapter(
        _runner=lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=(), returncode=1, stdout=private, stderr=private
        )
    )

    with pytest.raises(GarminPyResponseError) as exc_info:
        adapter.get_for_date(date(2026, 9, 9))

    assert "private-value" not in str(exc_info.value)


def test_maps_structured_garmin_py_error_without_private_text() -> None:
    adapter = GarminPyTrainingLoadAdapter(
        _runner=lambda *_args, **_kwargs: _result(
            {
                "ok": False,
                "error_code": "RATE_LIMITED",
                "error": "token=private-value",
            },
            returncode=1,
        )
    )

    with pytest.raises(GarminPyQueryError) as exc_info:
        adapter.get_for_date(date(2026, 9, 9))

    assert exc_info.value.error_code == "RATE_LIMITED"
    assert "private-value" not in str(exc_info.value)


def test_unsafe_error_code_is_not_echoed() -> None:
    adapter = GarminPyTrainingLoadAdapter(
        _runner=lambda *_args, **_kwargs: _result(
            {
                "ok": False,
                "error_code": "token=private-value",
                "error": "private-value",
            },
            returncode=1,
        )
    )

    with pytest.raises(GarminPyQueryError) as exc_info:
        adapter.get_for_date(date(2026, 9, 9))

    assert exc_info.value.error_code is None
    assert "private-value" not in str(exc_info.value)


def test_missing_command_has_clear_optional_integration_error() -> None:
    def runner(*_args, **_kwargs):
        raise FileNotFoundError("garmin-cli")

    with pytest.raises(GarminPyUnavailableError, match="install"):
        GarminPyTrainingLoadAdapter(_runner=runner).get_for_date(
            date(2026, 9, 9)
        )


def test_timeout_is_mapped_without_process_details() -> None:
    def runner(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("private command", 60)

    with pytest.raises(GarminPyQueryError) as exc_info:
        GarminPyTrainingLoadAdapter(_runner=runner).get_for_date(
            date(2026, 9, 9)
        )

    assert exc_info.value.error_code == "TIMEOUT"
    assert "private command" not in str(exc_info.value)


def test_history_is_inclusive_ascending_and_immutable() -> None:
    dates = []

    def runner(arguments, **_kwargs):
        day = arguments[-1]
        dates.append(day)
        return _result(_success(day, acute=len(dates), chronic=10))

    result = GarminPyTrainingLoadAdapter(_runner=runner).get_history(
        date(2026, 9, 7),
        date(2026, 9, 9),
    )

    assert dates == ["2026-09-07", "2026-09-08", "2026-09-09"]
    assert isinstance(result, tuple)
    assert tuple(item.acute_load for item in result) == (1.0, 2.0, 3.0)


def test_history_rejects_reversed_dates() -> None:
    with pytest.raises(ValueError, match="earlier"):
        GarminPyTrainingLoadAdapter().get_history(
            date(2026, 9, 9),
            date(2026, 9, 8),
        )


@pytest.mark.parametrize(
    "value",
    [None, "2026-09-09", 1, datetime(2026, 9, 9)],
)
def test_date_arguments_require_date_instances(value) -> None:
    adapter = GarminPyTrainingLoadAdapter()

    with pytest.raises(TypeError):
        adapter.get_for_date(value)  # type: ignore[arg-type]


@pytest.mark.parametrize("timeout", [True, 0, -1, float("nan"), "60"])
def test_timeout_must_be_positive_and_finite(timeout) -> None:
    with pytest.raises((TypeError, ValueError)):
        GarminPyTrainingLoadAdapter(timeout_s=timeout)  # type: ignore[arg-type]
