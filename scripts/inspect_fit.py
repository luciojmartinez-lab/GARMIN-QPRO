"""Inspect FIT and ZIP inputs locally without exposing GPS coordinates."""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, time
from pathlib import Path, PurePosixPath, PureWindowsPath
from pprint import pformat
import sys
from typing import Any, TextIO

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from garmin_qpro.fit.decoder import decode_fit
from garmin_qpro.fit.models import DecodedFit
from garmin_qpro.input.sources import FitSource, load_fit_sources

SENSITIVE_FIELD_FRAGMENTS = (
    "position_lat",
    "position_long",
    "latitude",
    "longitude",
    "gps_position",
    "coordinates",
)
SENSITIVE_FIELD_NAMES = frozenset({"lat", "lon", "lng"})

SUMMARY_MESSAGE_TYPES = (
    "session",
    "lap",
    "record",
    "workout",
    "event",
)
FIELD_INVENTORY_TYPES = (
    "workout",
    "session",
    "activity",
    "sport",
    "lap",
    "event",
)


def is_sensitive_field_name(field_name: object) -> bool:
    """Return whether a field name can contain GPS coordinates."""

    normalized = str(field_name).casefold()
    return normalized in SENSITIVE_FIELD_NAMES or any(
        fragment in normalized for fragment in SENSITIVE_FIELD_FRAGMENTS
    )


def _safe_text(value: str) -> str:
    posix_path = PurePosixPath(value)
    windows_path = PureWindowsPath(value)
    if (
        posix_path.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
    ):
        return "<ruta absoluta omitida>"
    return value


def sanitize_value(value: Any) -> Any:
    """Recursively remove coordinate fields and redact absolute paths."""

    if isinstance(value, Mapping):
        return {
            str(key): sanitize_value(nested_value)
            for key, nested_value in value.items()
            if not is_sensitive_field_name(key)
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((sanitize_value(item) for item in value), key=repr)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, str):
        return _safe_text(value)
    return value


def _field_names(decoded: DecodedFit, message_type: str) -> tuple[str, ...]:
    fields: set[str] = set()
    for message in decoded.get_messages(message_type):
        if not isinstance(message, Mapping):
            continue
        fields.update(
            str(field_name)
            for field_name in message
            if not is_sensitive_field_name(field_name)
        )
    return tuple(sorted(fields, key=str.casefold))


def _display_value(value: Any) -> str | None:
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace").strip("\x00 ")
    elif isinstance(value, str):
        text = value.strip()
    else:
        return None
    return _safe_text(text) if text else None


def _find_field(
    decoded: DecodedFit,
    field_names: Sequence[str],
    message_types: Sequence[str],
) -> tuple[str, str] | None:
    wanted = tuple(field_name.casefold() for field_name in field_names)
    for message_type in message_types:
        for message in decoded.get_messages(message_type):
            if not isinstance(message, Mapping):
                continue
            by_normalized_name = {
                str(key).casefold(): (str(key), value)
                for key, value in message.items()
            }
            for field_name in wanted:
                found = by_normalized_name.get(field_name)
                if found is None:
                    continue
                original_name, value = found
                display_value = _display_value(value)
                if display_value is not None:
                    return display_value, f"{message_type}.{original_name}"
    return None


def find_activity_name(decoded: DecodedFit) -> tuple[str, str] | None:
    """Find an explicit Garmin activity name without falling back to sport."""

    all_types = tuple(decoded.messages)
    explicit = _find_field(
        decoded,
        ("activity_name", "workout_name", "sport_profile_name"),
        all_types,
    )
    if explicit is not None:
        return explicit
    return _find_field(
        decoded,
        ("name", "title"),
        ("workout", "session", "activity", "sport"),
    )


def find_sport(decoded: DecodedFit) -> tuple[str | None, str | None]:
    """Return explicit sport and subtype values when present."""

    message_types = ("session", "sport", "activity", "workout")
    sport = _find_field(decoded, ("sport",), message_types)
    sub_sport = _find_field(decoded, ("sub_sport",), message_types)
    return (
        sport[0] if sport is not None else None,
        sub_sport[0] if sub_sport is not None else None,
    )


def _field_occurrences(decoded: DecodedFit) -> tuple[tuple[str, str], ...]:
    occurrences: set[tuple[str, str]] = set()
    for message_type in decoded.messages:
        for field_name in _field_names(decoded, message_type):
            occurrences.add((message_type, field_name))
    return tuple(
        sorted(occurrences, key=lambda item: (item[0].casefold(), item[1].casefold()))
    )


def candidate_fields(decoded: DecodedFit) -> Mapping[str, tuple[str, ...]]:
    """Return field-name candidates only; no metric is selected or extracted."""

    occurrences = _field_occurrences(decoded)

    def matching(predicate) -> tuple[str, ...]:
        return tuple(
            f"{message_type}.{field_name}"
            for message_type, field_name in occurrences
            if predicate(field_name.casefold())
        )

    return {
        "tiempo en movimiento": matching(
            lambda name: "moving_time" in name
            or name
            in {
                "elapsed_time",
                "timer_time",
                "total_elapsed_time",
                "total_timer_time",
            }
        ),
        "distancia": matching(lambda name: "distance" in name),
        "pulso": matching(
            lambda name: "heart_rate" in name
            or name in {"hr", "avg_hr", "max_hr"}
        ),
        "cadencia": matching(lambda name: "cadence" in name),
        "potencia": matching(lambda name: "power" in name),
        "Training Effect aerobico": matching(
            lambda name: "training_effect" in name and "anaerobic" not in name
        ),
        "Training Effect anaerobico": matching(
            lambda name: "training_effect" in name and "anaerobic" in name
        ),
        "Exercise Load": matching(
            lambda name: "exercise_load" in name
            or (
                "training_load" in name
                and "acute" not in name
                and "chronic" not in name
            )
        ),
        "TCS": matching(
            lambda name: "ground_contact_time" in name
            or "stance_time" in name
        ),
        "RVM": matching(lambda name: "vertical_ratio" in name),
        "OVM": matching(lambda name: "vertical_oscillation" in name),
        "ZAN": matching(
            lambda name: "stride_length" in name or "step_length" in name
        ),
    }


def _developer_field_names(decoded: DecodedFit) -> tuple[str, ...]:
    names: set[str] = set()
    for message in decoded.get_messages("field_description"):
        if not isinstance(message, Mapping):
            continue
        for key, value in message.items():
            if str(key).casefold() not in {"field_name", "name"}:
                continue
            if isinstance(value, (list, tuple)):
                values: Iterable[Any] = value
            else:
                values = (value,)
            for item in values:
                display_value = _display_value(item)
                if display_value is not None:
                    names.add(display_value)
    return tuple(sorted(names, key=str.casefold))


def _format_collection(value: Any) -> str:
    return pformat(sanitize_value(value), width=100, sort_dicts=True)


def _format_errors(errors: tuple[Any, ...]) -> tuple[str, ...]:
    return tuple(
        _safe_text(f"{type(error).__name__}: {error}") for error in errors
    )


def render_decoded_fit(source: FitSource, decoded: DecodedFit) -> str:
    """Render one decoded FIT with a compact summary and sanitized detail."""

    name = find_activity_name(decoded)
    sport, sub_sport = find_sport(decoded)
    counts = {
        message_type: len(decoded.get_messages(message_type))
        for message_type in SUMMARY_MESSAGE_TYPES
    }
    errors = _format_errors(decoded.errors)
    candidates = candidate_fields(decoded)

    lines = [
        "=" * 72,
        f"ZIP origen: {source.container_name or '(FIT individual)'}",
        f"FIT origen: {source.member_path or source.source_name}",
        f"SHA-256: {source.sha256}",
        f"CRC comprobado: {'si' if decoded.crc_checked else 'no'}",
        (
            f"Nombre Garmin: {name[0]} [{name[1]}]"
            if name is not None
            else "Nombre Garmin: no encontrado en campos explicitos"
        ),
        f"Deporte: {sport or 'no encontrado'}",
        f"Subtipo: {sub_sport or 'no encontrado'}",
        "Conteos: "
        + ", ".join(f"{key}={value}" for key, value in counts.items()),
        (
            "Errores SDK: ninguno"
            if not errors
            else "Errores SDK: " + " | ".join(errors)
        ),
        "",
        "Campos candidatos (inventario, sin seleccionar reglas):",
    ]
    for label, field_names in candidates.items():
        lines.append(
            f"Candidato {label}: "
            + (", ".join(field_names) if field_names else "ninguno")
        )

    lines.extend(["", "Tipos de mensajes:"])
    if decoded.messages:
        lines.extend(
            f"- {message_type}: {len(messages)}"
            for message_type, messages in sorted(decoded.messages.items())
        )
    else:
        lines.append("- ninguno")

    lines.extend(["", "Campos disponibles por tipo:"])
    for message_type in FIELD_INVENTORY_TYPES:
        field_names = _field_names(decoded, message_type)
        lines.append(
            f"- {message_type}: "
            + (", ".join(field_names) if field_names else "ninguno")
        )

    record_fields = _field_names(decoded, "record")
    lines.extend(
        [
            "",
            "Campos de record (solo nombres):",
            ", ".join(record_fields) if record_fields else "ninguno",
            "",
            "Primera session completa (sin coordenadas):",
        ]
    )
    sessions = decoded.get_messages("session")
    lines.append(
        _format_collection(sessions[0]) if sessions else "no disponible"
    )

    lines.extend(["", "Vueltas completas (sin coordenadas):"])
    laps = decoded.get_messages("lap")
    lines.append(_format_collection(laps) if laps else "no disponibles")

    lines.extend(["", "Developer fields:"])
    developer_data = decoded.get_messages("developer_data_id")
    field_descriptions = decoded.get_messages("field_description")
    lines.append(
        "developer_data_id: "
        + (_format_collection(developer_data) if developer_data else "ninguno")
    )
    lines.append(
        "field_description: "
        + (
            _format_collection(field_descriptions)
            if field_descriptions
            else "ninguno"
        )
    )
    proprietary_names = _developer_field_names(decoded)
    lines.append(
        "Nombres de campos propietarios: "
        + (", ".join(proprietary_names) if proprietary_names else "ninguno")
    )
    return "\n".join(lines)


def inspect_paths(paths: Sequence[Path]) -> str:
    """Load and decode one or more FIT/ZIP paths, continuing per input."""

    sections: list[str] = []
    for input_path in paths:
        safe_input_name = Path(input_path).name
        try:
            sources = load_fit_sources(Path(input_path))
        except Exception as error:
            sections.append(
                "\n".join(
                    [
                        "=" * 72,
                        f"Entrada: {safe_input_name}",
                        f"Error de carga: {type(error).__name__}",
                    ]
                )
            )
            continue

        for source in sources:
            try:
                decoded = decode_fit(source)
            except Exception as error:
                sections.append(
                    "\n".join(
                        [
                            "=" * 72,
                            f"ZIP origen: {source.container_name or '(FIT individual)'}",
                            f"FIT origen: {source.member_path or source.source_name}",
                            f"SHA-256: {source.sha256}",
                            f"Error de decodificacion: {type(error).__name__}",
                        ]
                    )
                )
                continue
            sections.append(render_decoded_fit(source, decoded))
    return "\n\n".join(sections)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspeccion local y segura de archivos FIT o ZIP."
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="Uno o varios archivos FIT/ZIP.",
    )
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    *,
    output: TextIO = sys.stdout,
) -> int:
    args = _parse_args(argv)
    print(inspect_paths(args.paths), file=output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
