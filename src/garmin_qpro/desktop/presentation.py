"""Pure presentation helpers for the desktop UI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from garmin_qpro.history import HistoryStatus


@dataclass(frozen=True, slots=True)
class DashboardSummary:
    new_activities: int
    converted: int
    pending_review: int
    archived: int


STATUS_LABELS = {
    HistoryStatus.PENDING: "Pendiente",
    HistoryStatus.CONVERTED: "Convertida",
    HistoryStatus.REVIEWED: "Revisada",
    HistoryStatus.ARCHIVED: "Archivada",
}


def display_activity_name(
    workout_name: str | None,
    profile_name: str | None,
    fallback: str | None,
) -> str:
    return workout_name or profile_name or fallback or "Actividad sin nombre"


def format_activity_datetime(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.strip()
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return normalized
    return parsed.strftime("%d/%m/%Y %H:%M")


def validate_clipboard_rows(rows: tuple[str, ...]) -> str:
    for row in rows:
        if (
            row.count("\t") != 22
            or len(row.split("\t")) != 23
            or row.endswith("\t")
            or "\n" in row
            or "\r" in row
        ):
            raise ValueError("La fila no tiene el formato QPro de 23 columnas.")
    return "\n".join(rows)
