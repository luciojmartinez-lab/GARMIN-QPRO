"""Resolve confirmed Garmin workout names to Quattro Pro keys."""

from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Final, Mapping

from garmin_qpro.qpro.rows import family_for_key


def _normalize_workout_name(workout_name: str) -> str:
    collapsed = " ".join(workout_name.strip().split())
    normalized_hyphens = re.sub(r"\s*-\s*", " - ", collapsed)
    return " ".join(normalized_hyphens.split()).casefold()


_CONFIRMED_RULES: Final[Mapping[str, tuple[str, str]]] = MappingProxyType(
    {
        _normalize_workout_name(name): (qpro_key, name)
        for name, qpro_key in (
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
        )
    }
)

_PESAS_PHASE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^eb5 - pesas - fase ([0-9])$"
)
_PESAS_PHASE_RULE: Final[str] = "EB5 - Pesas - Fase <0-9>"


@dataclass(frozen=True, slots=True)
class WorkoutResolution:
    """Immutable result of a closed Garmin workout-name lookup."""

    workout_name: str
    normalized_name: str
    qpro_key: str | None
    matched_rule: str | None


def _resolved(
    workout_name: str,
    normalized_name: str,
    qpro_key: str,
    matched_rule: str,
) -> WorkoutResolution:
    family_for_key(qpro_key)
    return WorkoutResolution(
        workout_name=workout_name,
        normalized_name=normalized_name,
        qpro_key=qpro_key,
        matched_rule=matched_rule,
    )


def resolve_workout_name(workout_name: str) -> WorkoutResolution:
    """Resolve only confirmed workout names, without sport-profile inference."""

    if not isinstance(workout_name, str):
        raise TypeError("workout_name must be a string")

    normalized_name = _normalize_workout_name(workout_name)
    exact_rule = _CONFIRMED_RULES.get(normalized_name)
    if exact_rule is not None:
        qpro_key, matched_rule = exact_rule
        return _resolved(
            workout_name,
            normalized_name,
            qpro_key,
            matched_rule,
        )

    if _PESAS_PHASE_PATTERN.fullmatch(normalized_name):
        return _resolved(
            workout_name,
            normalized_name,
            "PES",
            _PESAS_PHASE_RULE,
        )

    return WorkoutResolution(
        workout_name=workout_name,
        normalized_name=normalized_name,
        qpro_key=None,
        matched_rule=None,
    )
