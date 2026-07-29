from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from garmin_qpro.desktop.controller import (
    DesktopActivityController,
    DesktopActivityStatus,
    parse_drop_paths,
)
from garmin_qpro.fit.activity_metadata import ActivityContext, ActivityMetadata
from garmin_qpro.input import FitSource
from garmin_qpro.mapping.activity_resolution import ActivityResolution


def _source(name: str) -> FitSource:
    return FitSource(
        source_name=name,
        container_name=None,
        member_path=None,
        data=f"FIT:{name}".encode(),
    )


def _decoded(source: FitSource, *, errors: tuple[object, ...] = ()) -> object:
    return SimpleNamespace(source=source, errors=errors, crc_checked=True)


def _context(
    key: str | None,
    *,
    workout_name: str | None = "EB1 - Carrera - 1",
    profile: str | None = "Carrera",
    requires_choice: bool = False,
) -> ActivityContext:
    return ActivityContext(
        metadata=ActivityMetadata(
            workout_name=workout_name,
            workout_name_field="workout.workout_name" if workout_name else None,
            sport_profile_name=profile,
            sport="running",
            sub_sport="generic",
        ),
        resolution=ActivityResolution(
            workout_name=workout_name,
            sport_profile_name=profile,
            qpro_key=key,
            resolution_source="workout_name" if key else None,
            requires_user_choice=requires_choice,
        ),
    )


def _tsv(key: str = "ENT") -> str:
    return "\t".join((key, *("x" for _ in range(22))))


def _result(
    decoded: object,
    context: ActivityContext,
    *,
    tsv: str | None = None,
    review: bool = False,
    reasons: tuple[str, ...] = (),
) -> object:
    return SimpleNamespace(
        source_name=decoded.source.source_name,
        activity_context=context,
        metrics=SimpleNamespace(
            requires_manual_review=review,
            review_reasons=reasons,
            trim_reasons=(),
        ),
        tsv=tsv or _tsv(context.resolution.qpro_key or "ENT"),
        decoder_errors=decoded.errors,
    )


def _install_success_engine(
    monkeypatch: pytest.MonkeyPatch,
    *,
    contexts: dict[str, ActivityContext] | None = None,
) -> list[str | None]:
    explicit_keys: list[str | None] = []

    def load(path: Path) -> tuple[FitSource, ...]:
        if path.name == "many.zip":
            return (_source("a.fit"), _source("b.fit"))
        return (_source(path.name),)

    def decode(source: FitSource, *, verify_crc: bool = True) -> object:
        assert verify_crc is True
        return _decoded(source)

    def resolve(decoded: object) -> ActivityContext:
        if contexts and decoded.source.source_name in contexts:
            return contexts[decoded.source.source_name]
        return _context("ENT")

    def convert(
        decoded: object,
        *,
        explicit_qpro_key: str | None = None,
    ) -> object:
        explicit_keys.append(explicit_qpro_key)
        context = (
            _context(explicit_qpro_key, workout_name=None, profile="Fuerza")
            if explicit_qpro_key
            else resolve(decoded)
        )
        return _result(decoded, context)

    monkeypatch.setattr(
        "garmin_qpro.desktop.controller.load_fit_sources",
        load,
    )
    monkeypatch.setattr("garmin_qpro.desktop.controller.decode_fit", decode)
    monkeypatch.setattr(
        "garmin_qpro.desktop.controller.resolve_decoded_activity",
        resolve,
    )
    monkeypatch.setattr(
        "garmin_qpro.desktop.controller.convert_decoded_activity",
        convert,
    )
    return explicit_keys


def test_multiple_inputs_and_zip_members_keep_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_success_engine(monkeypatch)
    controller = DesktopActivityController()

    added = controller.process_paths((Path("one.fit"), Path("many.zip")))

    assert [item.source_name for item in added] == ["one.fit", "a.fit", "b.fit"]
    assert all(item.status is DesktopActivityStatus.CONVERTED for item in added)
    assert controller.all_tsv() == "\n".join(item.tsv for item in added)


def test_unresolved_activity_can_be_retried_with_manual_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contexts = {
        "force.fit": _context(
            None,
            workout_name=None,
            profile="Fuerza",
            requires_choice=True,
        )
    }
    explicit_keys = _install_success_engine(monkeypatch, contexts=contexts)
    controller = DesktopActivityController()
    pending = controller.process_paths((Path("force.fit"),))[0]

    converted = controller.apply_manual_key(pending.item_id, "PES")

    assert pending.status is DesktopActivityStatus.NEEDS_KEY
    assert converted.status is DesktopActivityStatus.CONVERTED
    assert converted.qpro_key == "PES"
    assert explicit_keys == ["PES"]


def test_load_failure_does_not_block_following_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_success_engine(monkeypatch)
    original_load = __import__(
        "garmin_qpro.desktop.controller",
        fromlist=["load_fit_sources"],
    ).load_fit_sources

    def load(path: Path) -> tuple[FitSource, ...]:
        if path.name == "bad.zip":
            raise ValueError("ZIP defectuoso")
        return original_load(path)

    monkeypatch.setattr(
        "garmin_qpro.desktop.controller.load_fit_sources",
        load,
    )
    controller = DesktopActivityController()

    added = controller.process_paths((Path("bad.zip"), Path("good.fit")))

    assert added[0].status is DesktopActivityStatus.FAILED
    assert added[1].status is DesktopActivityStatus.CONVERTED
    assert len(controller.all_tsv().splitlines()) == 1


def test_decode_failure_does_not_block_following_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_success_engine(monkeypatch)
    monkeypatch.setattr(
        "garmin_qpro.desktop.controller.load_fit_sources",
        lambda _path: (_source("bad.fit"), _source("good.fit")),
    )
    original_decode = __import__(
        "garmin_qpro.desktop.controller",
        fromlist=["decode_fit"],
    ).decode_fit

    def decode(source: FitSource, *, verify_crc: bool = True) -> object:
        if source.source_name == "bad.fit":
            raise ValueError("FIT invalido")
        return original_decode(source, verify_crc=verify_crc)

    monkeypatch.setattr("garmin_qpro.desktop.controller.decode_fit", decode)
    controller = DesktopActivityController()

    added = controller.process_paths((Path("two.zip"),))

    assert [item.status for item in added] == [
        DesktopActivityStatus.FAILED,
        DesktopActivityStatus.CONVERTED,
    ]


def test_review_and_decoder_warnings_are_exposed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_success_engine(monkeypatch)
    monkeypatch.setattr(
        "garmin_qpro.desktop.controller.decode_fit",
        lambda source, *, verify_crc=True: _decoded(source, errors=("crc",)),
    )

    def convert(decoded: object, *, explicit_qpro_key: str | None = None) -> object:
        return _result(
            decoded,
            _context("CAM"),
            review=True,
            reasons=("speed_requires_review",),
        )

    monkeypatch.setattr(
        "garmin_qpro.desktop.controller.convert_decoded_activity",
        convert,
    )
    controller = DesktopActivityController()

    item = controller.process_paths((Path("walk.fit"),))[0]

    assert item.requires_manual_review is True
    assert "speed_requires_review" in item.warning
    assert "decodificador" in item.warning


def test_invalid_tsv_shape_is_reported_as_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_success_engine(monkeypatch)

    def convert(decoded: object, *, explicit_qpro_key: str | None = None) -> object:
        return _result(decoded, _context("ENT"), tsv="ENT\ttoo-short")

    monkeypatch.setattr(
        "garmin_qpro.desktop.controller.convert_decoded_activity",
        convert,
    )
    controller = DesktopActivityController()

    item = controller.process_paths((Path("bad-shape.fit"),))[0]

    assert item.status is DesktopActivityStatus.FAILED
    assert item.tsv is None
    assert "23-column" in item.warning


def test_copy_payloads_include_only_valid_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_success_engine(monkeypatch)
    controller = DesktopActivityController()
    converted = controller.process_paths((Path("ok.fit"),))[0]
    failed = controller._append_failure(
        "bad.fit",
        None,
        ValueError("defectuoso"),
    )

    assert controller.tsv_for_item(converted.item_id) == converted.tsv
    assert controller.all_tsv() == converted.tsv
    with pytest.raises(ValueError):
        controller.tsv_for_item(failed.item_id)


def test_clear_removes_items_and_pending_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_success_engine(monkeypatch)
    controller = DesktopActivityController()
    item = controller.process_paths((Path("one.fit"),))[0]

    controller.clear()

    assert controller.items == ()
    assert controller.all_tsv() == ""
    with pytest.raises(KeyError):
        controller.get_item(item.item_id)


def test_parse_drop_paths_preserves_paths_with_spaces() -> None:
    raw = "{C:/Carpeta Con Espacios/one.fit} C:/Garmin/two.zip"

    paths = parse_drop_paths(
        raw,
        lambda _value: (
            "C:/Carpeta Con Espacios/one.fit",
            "C:/Garmin/two.zip",
        ),
    )

    assert paths == (
        Path("C:/Carpeta Con Espacios/one.fit"),
        Path("C:/Garmin/two.zip"),
    )
