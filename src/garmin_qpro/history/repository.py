"""SQLite persistence for converted activities."""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

SCHEMA_VERSION = 1
CONVERTER_VERSION = "desktop-2"


class HistoryStatus(str, Enum):
    PENDING = "pending"
    CONVERTED = "converted"
    REVIEWED = "reviewed"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class ConversionDraft:
    garmin_activity_id: str | None
    source_sha256: str | None
    activity_datetime: str | None
    workout_name: str | None
    profile_name: str | None
    qpro_key: str
    tsv: str
    source_type: str
    source_name: str | None = None
    warnings: tuple[str, ...] = ()
    manual_key: bool = False
    status: HistoryStatus = HistoryStatus.CONVERTED
    resolution_source: str | None = None
    converter_version: str = CONVERTER_VERSION


@dataclass(frozen=True, slots=True)
class ConversionRecord:
    id: int
    garmin_activity_id: str | None
    source_sha256: str | None
    activity_datetime: str | None
    workout_name: str | None
    profile_name: str | None
    qpro_key: str
    tsv: str
    converted_at: str
    converter_version: str
    source_type: str
    source_name: str | None
    warnings: tuple[str, ...]
    manual_key: bool
    status: HistoryStatus
    resolution_source: str | None
    updated_at: str


@dataclass(frozen=True, slots=True)
class HistoryFilters:
    search: str | None = None
    qpro_key: str | None = None
    status: HistoryStatus | None = None
    date_from: str | None = None
    date_to: str | None = None
    include_archived: bool = False


class DuplicateConversionError(ValueError):
    def __init__(self, existing_id: int) -> None:
        self.existing_id = existing_id
        super().__init__(f"Conversion already exists as history item {existing_id}")


def default_database_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "GARMIN-QPRO" / "garmin_qpro.db"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("optional text values must be strings or None")
    normalized = value.strip()
    return normalized or None


def _validate_tsv(tsv: str) -> str:
    if not isinstance(tsv, str):
        raise TypeError("tsv must be text")
    if (
        tsv.count("\t") != 22
        or len(tsv.split("\t")) != 23
        or tsv.endswith("\t")
        or "\n" in tsv
        or "\r" in tsv
    ):
        raise ValueError("tsv must contain exactly 23 columns and 22 tabs")
    return tsv


def _validate_draft(draft: ConversionDraft) -> ConversionDraft:
    if not isinstance(draft, ConversionDraft):
        raise TypeError("draft must be a ConversionDraft")
    key = draft.qpro_key.strip().upper()
    if not key:
        raise ValueError("qpro_key cannot be empty")
    source_type = draft.source_type.strip().lower()
    if source_type not in {"garmin", "fit", "zip"}:
        raise ValueError("source_type must be garmin, fit or zip")
    if not isinstance(draft.status, HistoryStatus):
        raise TypeError("status must be a HistoryStatus")
    if not isinstance(draft.manual_key, bool):
        raise TypeError("manual_key must be a bool")
    if not all(isinstance(item, str) for item in draft.warnings):
        raise TypeError("warnings must contain text values")
    _validate_tsv(draft.tsv)
    return ConversionDraft(
        garmin_activity_id=_normalize_optional(draft.garmin_activity_id),
        source_sha256=_normalize_optional(draft.source_sha256),
        activity_datetime=_normalize_optional(draft.activity_datetime),
        workout_name=_normalize_optional(draft.workout_name),
        profile_name=_normalize_optional(draft.profile_name),
        qpro_key=key,
        tsv=draft.tsv,
        source_type=source_type,
        source_name=_normalize_optional(draft.source_name),
        warnings=tuple(item.strip() for item in draft.warnings if item.strip()),
        manual_key=draft.manual_key,
        status=draft.status,
        resolution_source=_normalize_optional(draft.resolution_source),
        converter_version=draft.converter_version.strip() or CONVERTER_VERSION,
    )


class HistoryRepository:
    """Small repository with one connection per operation."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def migrate(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            applied = {
                row[0]
                for row in connection.execute(
                    "SELECT version FROM schema_migrations"
                )
            }
            if 1 not in applied:
                connection.executescript(
                    """
                    CREATE TABLE conversions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        garmin_activity_id TEXT,
                        source_sha256 TEXT,
                        activity_datetime TEXT,
                        workout_name TEXT,
                        profile_name TEXT,
                        qpro_key TEXT NOT NULL,
                        tsv TEXT NOT NULL,
                        converted_at TEXT NOT NULL,
                        converter_version TEXT NOT NULL,
                        source_type TEXT NOT NULL,
                        source_name TEXT,
                        warnings_json TEXT NOT NULL DEFAULT '[]',
                        manual_key INTEGER NOT NULL DEFAULT 0,
                        status TEXT NOT NULL,
                        resolution_source TEXT,
                        updated_at TEXT NOT NULL
                    );
                    CREATE UNIQUE INDEX conversions_garmin_id_unique
                        ON conversions(garmin_activity_id)
                        WHERE garmin_activity_id IS NOT NULL;
                    CREATE UNIQUE INDEX conversions_source_hash_unique
                        ON conversions(source_sha256)
                        WHERE source_sha256 IS NOT NULL;
                    CREATE INDEX conversions_activity_date_idx
                        ON conversions(activity_datetime);
                    CREATE INDEX conversions_key_idx ON conversions(qpro_key);
                    CREATE INDEX conversions_status_idx ON conversions(status);
                    """
                )
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES(?, ?)",
                    (1, _utc_now()),
                )

    @property
    def schema_version(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()
        return int(row[0])

    def save(self, draft: ConversionDraft) -> ConversionRecord:
        clean = _validate_draft(draft)
        duplicate = self.find_duplicate(
            garmin_activity_id=clean.garmin_activity_id,
            source_sha256=clean.source_sha256,
        )
        if duplicate is not None:
            raise DuplicateConversionError(duplicate.id)
        now = _utc_now()
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO conversions (
                        garmin_activity_id, source_sha256, activity_datetime,
                        workout_name, profile_name, qpro_key, tsv,
                        converted_at, converter_version, source_type,
                        source_name, warnings_json, manual_key, status,
                        resolution_source, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        clean.garmin_activity_id,
                        clean.source_sha256,
                        clean.activity_datetime,
                        clean.workout_name,
                        clean.profile_name,
                        clean.qpro_key,
                        clean.tsv,
                        now,
                        clean.converter_version,
                        clean.source_type,
                        clean.source_name,
                        json.dumps(clean.warnings, ensure_ascii=True),
                        int(clean.manual_key),
                        clean.status.value,
                        clean.resolution_source,
                        now,
                    ),
                )
                record_id = int(cursor.lastrowid)
        except sqlite3.IntegrityError:
            duplicate = self.find_duplicate(
                garmin_activity_id=clean.garmin_activity_id,
                source_sha256=clean.source_sha256,
            )
            if duplicate is not None:
                raise DuplicateConversionError(duplicate.id) from None
            raise
        return self.get(record_id)

    def get(self, record_id: int) -> ConversionRecord:
        if isinstance(record_id, bool) or not isinstance(record_id, int):
            raise TypeError("record_id must be an integer")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM conversions WHERE id = ?",
                (record_id,),
            ).fetchone()
        if row is None:
            raise KeyError(record_id)
        return self._row_to_record(row)

    def find_duplicate(
        self,
        *,
        garmin_activity_id: str | None,
        source_sha256: str | None,
    ) -> ConversionRecord | None:
        garmin_id = _normalize_optional(garmin_activity_id)
        source_hash = _normalize_optional(source_sha256)
        clauses: list[str] = []
        values: list[str] = []
        if garmin_id is not None:
            clauses.append("garmin_activity_id = ?")
            values.append(garmin_id)
        if source_hash is not None:
            clauses.append("source_sha256 = ?")
            values.append(source_hash)
        if not clauses:
            return None
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT * FROM conversions WHERE {' OR '.join(clauses)} "
                "ORDER BY id LIMIT 1",
                values,
            ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def has_garmin_activity(self, activity_id: str) -> bool:
        return (
            self.find_duplicate(
                garmin_activity_id=activity_id,
                source_sha256=None,
            )
            is not None
        )

    def list(self, filters: HistoryFilters | None = None) -> tuple[ConversionRecord, ...]:
        selected = filters or HistoryFilters()
        if not isinstance(selected, HistoryFilters):
            raise TypeError("filters must be a HistoryFilters")
        clauses: list[str] = []
        values: list[str] = []
        if not selected.include_archived and selected.status is None:
            clauses.append("status <> ?")
            values.append(HistoryStatus.ARCHIVED.value)
        if selected.status is not None:
            clauses.append("status = ?")
            values.append(selected.status.value)
        if selected.qpro_key:
            clauses.append("qpro_key = ?")
            values.append(selected.qpro_key.strip().upper())
        if selected.search:
            clauses.append(
                "(LOWER(COALESCE(workout_name, '')) LIKE ? "
                "OR LOWER(COALESCE(profile_name, '')) LIKE ? "
                "OR LOWER(COALESCE(source_name, '')) LIKE ?)"
            )
            pattern = f"%{selected.search.strip().lower()}%"
            values.extend((pattern, pattern, pattern))
        if selected.date_from:
            clauses.append("activity_datetime >= ?")
            values.append(selected.date_from.strip())
        if selected.date_to:
            clauses.append("activity_datetime <= ?")
            values.append(selected.date_to.strip())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM conversions
                {where}
                ORDER BY COALESCE(activity_datetime, converted_at) DESC, id DESC
                """,
                values,
            ).fetchall()
        return tuple(self._row_to_record(row) for row in rows)

    def update_status(
        self,
        record_id: int,
        status: HistoryStatus,
    ) -> ConversionRecord:
        if not isinstance(status, HistoryStatus):
            raise TypeError("status must be a HistoryStatus")
        self.get(record_id)
        with self._connect() as connection:
            connection.execute(
                "UPDATE conversions SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, _utc_now(), record_id),
            )
        return self.get(record_id)

    def replace_conversion(
        self,
        record_id: int,
        *,
        qpro_key: str,
        tsv: str,
        warnings: tuple[str, ...],
        manual_key: bool,
        converter_version: str = CONVERTER_VERSION,
        resolution_source: str | None = None,
    ) -> ConversionRecord:
        self.get(record_id)
        key = qpro_key.strip().upper()
        if not key:
            raise ValueError("qpro_key cannot be empty")
        _validate_tsv(tsv)
        if not isinstance(manual_key, bool):
            raise TypeError("manual_key must be a bool")
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE conversions
                SET qpro_key = ?, tsv = ?, warnings_json = ?,
                    manual_key = ?, converter_version = ?,
                    resolution_source = ?, converted_at = ?,
                    status = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    key,
                    tsv,
                    json.dumps(tuple(warnings), ensure_ascii=True),
                    int(manual_key),
                    converter_version,
                    _normalize_optional(resolution_source),
                    _utc_now(),
                    HistoryStatus.CONVERTED.value,
                    _utc_now(),
                    record_id,
                ),
            )
        return self.get(record_id)

    def delete(self, record_id: int) -> None:
        self.get(record_id)
        with self._connect() as connection:
            connection.execute("DELETE FROM conversions WHERE id = ?", (record_id,))

    def count(self, *, status: HistoryStatus | None = None) -> int:
        with self._connect() as connection:
            if status is None:
                row = connection.execute("SELECT COUNT(*) FROM conversions").fetchone()
            else:
                row = connection.execute(
                    "SELECT COUNT(*) FROM conversions WHERE status = ?",
                    (status.value,),
                ).fetchone()
        return int(row[0])

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ConversionRecord:
        warnings_value = json.loads(row["warnings_json"])
        return ConversionRecord(
            id=int(row["id"]),
            garmin_activity_id=row["garmin_activity_id"],
            source_sha256=row["source_sha256"],
            activity_datetime=row["activity_datetime"],
            workout_name=row["workout_name"],
            profile_name=row["profile_name"],
            qpro_key=row["qpro_key"],
            tsv=row["tsv"],
            converted_at=row["converted_at"],
            converter_version=row["converter_version"],
            source_type=row["source_type"],
            source_name=row["source_name"],
            warnings=tuple(str(item) for item in warnings_value),
            manual_key=bool(row["manual_key"]),
            status=HistoryStatus(row["status"]),
            resolution_source=row["resolution_source"],
            updated_at=row["updated_at"],
        )
