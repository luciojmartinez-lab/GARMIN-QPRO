from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from garmin_qpro.history import (
    ConversionDraft,
    DuplicateConversionError,
    HistoryFilters,
    HistoryRepository,
    HistoryStatus,
)


def _tsv(key: str = "ENT") -> str:
    return "\t".join((key, *("0" for _ in range(22))))


def _draft(**overrides: object) -> ConversionDraft:
    values = {
        "garmin_activity_id": "123",
        "source_sha256": "a" * 64,
        "activity_datetime": "2026-07-30T08:00:00",
        "workout_name": "EB1 - Carrera - 1",
        "profile_name": "Carrera",
        "qpro_key": "ENT",
        "tsv": _tsv(),
        "source_type": "garmin",
        "warnings": (),
    }
    values.update(overrides)
    return ConversionDraft(**values)


def test_empty_database_is_migrated_to_current_schema(tmp_path) -> None:
    repository = HistoryRepository(tmp_path / "history.db")

    assert repository.schema_version == 1
    assert repository.list() == ()


def test_save_and_get_preserve_conversion_fields(tmp_path) -> None:
    repository = HistoryRepository(tmp_path / "history.db")

    saved = repository.save(
        _draft(warnings=("speed_requires_review",), manual_key=True)
    )

    assert repository.get(saved.id) == saved
    assert saved.tsv == _tsv()
    assert saved.warnings == ("speed_requires_review",)
    assert saved.manual_key is True
    assert saved.status is HistoryStatus.CONVERTED


def test_duplicate_garmin_id_is_rejected(tmp_path) -> None:
    repository = HistoryRepository(tmp_path / "history.db")
    original = repository.save(_draft())

    with pytest.raises(DuplicateConversionError) as exc_info:
        repository.save(
            _draft(source_sha256="b" * 64, qpro_key="CAM", tsv=_tsv("CAM"))
        )

    assert exc_info.value.existing_id == original.id


def test_duplicate_manual_fingerprint_is_rejected(tmp_path) -> None:
    repository = HistoryRepository(tmp_path / "history.db")
    original = repository.save(
        _draft(garmin_activity_id=None, source_type="fit")
    )

    with pytest.raises(DuplicateConversionError) as exc_info:
        repository.save(
            _draft(
                garmin_activity_id=None,
                source_type="zip",
                workout_name="Otra",
            )
        )

    assert exc_info.value.existing_id == original.id


def test_filters_cover_search_key_date_and_status(tmp_path) -> None:
    repository = HistoryRepository(tmp_path / "history.db")
    first = repository.save(_draft())
    second = repository.save(
        _draft(
            garmin_activity_id="456",
            source_sha256="b" * 64,
            activity_datetime="2026-08-02T09:00:00",
            workout_name="Paseo largo",
            qpro_key="CAM",
            tsv=_tsv("CAM"),
            status=HistoryStatus.PENDING,
        )
    )

    assert repository.list(HistoryFilters(search="paseo")) == (second,)
    assert repository.list(HistoryFilters(qpro_key="ent")) == (first,)
    assert repository.list(
        HistoryFilters(
            status=HistoryStatus.PENDING,
            date_from="2026-08-01",
            date_to="2026-08-31T23:59:59",
        )
    ) == (second,)


def test_archived_items_are_hidden_and_can_be_restored(tmp_path) -> None:
    repository = HistoryRepository(tmp_path / "history.db")
    saved = repository.save(_draft())

    archived = repository.update_status(saved.id, HistoryStatus.ARCHIVED)

    assert archived.status is HistoryStatus.ARCHIVED
    assert repository.list() == ()
    assert repository.list(HistoryFilters(include_archived=True)) == (archived,)
    assert (
        repository.update_status(saved.id, HistoryStatus.REVIEWED).status
        is HistoryStatus.REVIEWED
    )


def test_replace_conversion_updates_key_tsv_and_version(tmp_path) -> None:
    repository = HistoryRepository(tmp_path / "history.db")
    saved = repository.save(_draft())

    updated = repository.replace_conversion(
        saved.id,
        qpro_key="CAM",
        tsv=_tsv("CAM"),
        warnings=("review",),
        manual_key=True,
        converter_version="new-engine",
        resolution_source="explicit_qpro_key",
    )

    assert updated.qpro_key == "CAM"
    assert updated.tsv == _tsv("CAM")
    assert updated.warnings == ("review",)
    assert updated.converter_version == "new-engine"
    assert updated.status is HistoryStatus.CONVERTED


def test_delete_requires_an_existing_manual_target(tmp_path) -> None:
    repository = HistoryRepository(tmp_path / "history.db")
    saved = repository.save(_draft())

    repository.delete(saved.id)

    with pytest.raises(KeyError):
        repository.get(saved.id)


def test_invalid_tsv_is_never_persisted(tmp_path) -> None:
    repository = HistoryRepository(tmp_path / "history.db")

    with pytest.raises(ValueError):
        repository.save(_draft(tsv="ENT\ttoo-short"))


def test_records_and_filters_are_immutable(tmp_path) -> None:
    repository = HistoryRepository(tmp_path / "history.db")
    saved = repository.save(_draft())

    with pytest.raises(FrozenInstanceError):
        saved.qpro_key = "CAM"  # type: ignore[misc]
    filters = HistoryFilters(search="run")
    with pytest.raises(FrozenInstanceError):
        filters.search = "walk"  # type: ignore[misc]
