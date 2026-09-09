"""Read historical training load through garmin-py's public JSON CLI.

The adapter deliberately runs ``garmin-cli`` out of process. The current
garmin-py release pins a different python-garminconnect version from
GARMIN-QPRO, so importing it into this process would couple two otherwise
independent authentication and dependency stacks.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from math import isfinite
from os import PathLike
from typing import Any


_SAFE_ERROR_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")


class TrainingLoadAdapterError(RuntimeError):
    """Base error for the isolated garmin-py adapter."""


class GarminPyUnavailableError(TrainingLoadAdapterError):
    """Raised when the garmin-py command cannot be started."""


class GarminPyQueryError(TrainingLoadAdapterError):
    """Raised when garmin-py reports a safe, structured query failure."""

    def __init__(self, error_code: str | None = None) -> None:
        self.error_code = error_code
        suffix = f" ({error_code})" if error_code else ""
        super().__init__(f"garmin-py could not read training load{suffix}")


class GarminPyResponseError(TrainingLoadAdapterError):
    """Raised when garmin-py returns an unexpected response contract."""


@dataclass(frozen=True, slots=True)
class HistoricalTrainingLoad:
    """Acute and chronic load reported by Garmin for one calendar date."""

    date: date
    acute_load: float | None
    chronic_load: float | None

    def __post_init__(self) -> None:
        if type(self.date) is not date:
            raise TypeError("date must be a date")
        for field_name in ("acute_load", "chronic_load"):
            value = getattr(self, field_name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{field_name} must be numeric or None")
            parsed = float(value)
            if not isfinite(parsed) or parsed < 0:
                raise ValueError(
                    f"{field_name} must be finite and non-negative"
                )
            object.__setattr__(self, field_name, parsed)


CommandResult = subprocess.CompletedProcess[str]
CommandRunner = Callable[..., CommandResult]


def _normalize_command(
    command: str | PathLike[str] | Sequence[str | PathLike[str]],
) -> tuple[str, ...]:
    if isinstance(command, (str, PathLike)):
        values = (str(command),)
    elif isinstance(command, Sequence):
        values = tuple(str(part) for part in command)
    else:
        raise TypeError("command must be a path or sequence of arguments")
    if not values or any(not value.strip() for value in values):
        raise ValueError("command cannot contain empty arguments")
    return values


def _load_value(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GarminPyResponseError(
            f"garmin-py returned an invalid {field_name}"
        )
    parsed = float(value)
    if not isfinite(parsed) or parsed < 0:
        raise GarminPyResponseError(
            f"garmin-py returned an invalid {field_name}"
        )
    return parsed


class GarminPyTrainingLoadAdapter:
    """Query garmin-py's daily health-status command without shared state."""

    __slots__ = ("_command", "_runner", "_timeout_s")

    def __init__(
        self,
        command: str | PathLike[str] | Sequence[str | PathLike[str]] = (
            "garmin-cli",
        ),
        *,
        timeout_s: float = 60.0,
        _runner: CommandRunner = subprocess.run,
    ) -> None:
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)):
            raise TypeError("timeout_s must be numeric")
        parsed_timeout = float(timeout_s)
        if not isfinite(parsed_timeout) or parsed_timeout <= 0:
            raise ValueError("timeout_s must be finite and positive")
        if not callable(_runner):
            raise TypeError("_runner must be callable")
        self._command = _normalize_command(command)
        self._timeout_s = parsed_timeout
        self._runner = _runner

    def get_for_date(self, day: date) -> HistoricalTrainingLoad:
        """Return Garmin's reported acute and chronic load for ``day``."""

        if type(day) is not date:
            raise TypeError("day must be a date")
        arguments = (
            *self._command,
            "--json",
            "health",
            "status",
            "--date",
            day.isoformat(),
        )
        try:
            completed = self._runner(
                arguments,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._timeout_s,
                check=False,
                shell=False,
            )
        except (FileNotFoundError, OSError) as exc:
            raise GarminPyUnavailableError(
                "garmin-py is unavailable; install and authenticate garmin-cli"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise GarminPyQueryError("TIMEOUT") from exc

        envelope = self._parse_envelope(completed.stdout)
        if completed.returncode != 0 or envelope.get("ok") is not True:
            raise GarminPyQueryError(self._error_code(envelope))
        return self._parse_load(day, envelope)

    def get_history(
        self,
        start: date,
        end: date,
    ) -> tuple[HistoricalTrainingLoad, ...]:
        """Return an inclusive, ascending sequence of daily load snapshots."""

        if type(start) is not date or type(end) is not date:
            raise TypeError("start and end must be dates")
        if end < start:
            raise ValueError("end cannot be earlier than start")
        current = start
        snapshots: list[HistoricalTrainingLoad] = []
        while current <= end:
            snapshots.append(self.get_for_date(current))
            current += timedelta(days=1)
        return tuple(snapshots)

    @staticmethod
    def _parse_envelope(stdout: str) -> Mapping[str, Any]:
        if not isinstance(stdout, str):
            raise GarminPyResponseError("garmin-py returned non-text output")
        try:
            envelope = json.loads(stdout)
        except (json.JSONDecodeError, TypeError) as exc:
            raise GarminPyResponseError(
                "garmin-py returned invalid JSON"
            ) from exc
        if not isinstance(envelope, Mapping):
            raise GarminPyResponseError(
                "garmin-py returned an invalid JSON envelope"
            )
        return envelope

    @staticmethod
    def _error_code(envelope: Mapping[str, Any]) -> str | None:
        value = envelope.get("error_code")
        if not isinstance(value, str) or not _SAFE_ERROR_CODE.fullmatch(value):
            return None
        return value

    @staticmethod
    def _parse_load(
        requested_day: date,
        envelope: Mapping[str, Any],
    ) -> HistoricalTrainingLoad:
        data = envelope.get("data")
        if not isinstance(data, list):
            raise GarminPyResponseError(
                "garmin-py returned invalid training-load data"
            )
        if not data:
            return HistoricalTrainingLoad(requested_day, None, None)

        matching_rows: list[Mapping[str, Any]] = []
        for item in data:
            if not isinstance(item, Mapping):
                raise GarminPyResponseError(
                    "garmin-py returned an invalid training-load row"
                )
            if item.get("date") == requested_day.isoformat():
                matching_rows.append(item)
        if len(matching_rows) != 1:
            raise GarminPyResponseError(
                "garmin-py did not return exactly one row for the requested date"
            )
        row = matching_rows[0]
        return HistoricalTrainingLoad(
            date=requested_day,
            acute_load=_load_value(row.get("acute_load"), "acute_load"),
            chronic_load=_load_value(
                row.get("chronic_load"),
                "chronic_load",
            ),
        )
