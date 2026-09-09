from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from garmin_qpro.garmin_connect import HistoricalTrainingLoad
from garmin_qpro.qpro import (
    QPRO_COLUMNS,
    QPRO_COLUMNS_WITH_TRAINING_LOAD,
    QProRowWithTrainingLoad,
    build_force_row,
    enrich_qpro_row_with_training_load,
)


def _historical_load(
    acute_load: float | None,
    chronic_load: float | None,
) -> HistoricalTrainingLoad:
    return HistoricalTrainingLoad(
        date=date(2026, 7, 6),
        acute_load=acute_load,
        chronic_load=chronic_load,
        acwr=9.9,
        training_status="IGNORED_STATUS",
        load_tunnel_min=1.0,
        load_tunnel_max=999.0,
        load_balance_status="IGNORED_BALANCE",
    )


@pytest.mark.parametrize(
    ("acute", "chronic", "expected_acute", "expected_chronic"),
    [
        (312, 236, "'312", "'236"),
        (277, 239, "'277", "'239"),
        (228, 234, "'228", "'234"),
        (None, 236, "", "'236"),
        (312, None, "'312", ""),
        (None, None, "", ""),
    ],
)
def test_enriches_only_historical_load_columns(
    acute,
    chronic,
    expected_acute,
    expected_chronic,
) -> None:
    base_row = build_force_row("PES", exercise_load=67)

    enriched = enrich_qpro_row_with_training_load(
        base_row,
        _historical_load(acute, chronic),
    )

    assert enriched.as_tuple()[:23] == base_row.as_tuple()
    assert enriched.as_tuple()[23:] == (expected_acute, expected_chronic)
    assert enriched.get("CARGA_AGUDA") == expected_acute
    assert enriched.get("CARGA_CRONICA") == expected_chronic


def test_enriched_row_has_exact_25_column_schema() -> None:
    enriched = enrich_qpro_row_with_training_load(
        build_force_row("PES"),
        _historical_load(312, 236),
    )

    assert QPRO_COLUMNS_WITH_TRAINING_LOAD == (
        *QPRO_COLUMNS,
        "CARGA_AGUDA",
        "CARGA_CRONICA",
    )
    assert len(enriched.as_tuple()) == 25
    assert tuple(enriched.as_mapping()) == QPRO_COLUMNS_WITH_TRAINING_LOAD
    assert tuple(enriched.as_mapping().values()) == enriched.as_tuple()


def test_supplementary_garmin_fields_do_not_enter_the_row() -> None:
    enriched = enrich_qpro_row_with_training_load(
        build_force_row("PES"),
        _historical_load(312, 236),
    )
    tsv = "\t".join(enriched.as_tuple())

    assert "9.9" not in tsv
    assert "IGNORED_STATUS" not in tsv
    assert "999.0" not in tsv
    assert "IGNORED_BALANCE" not in tsv


def test_enriched_row_and_mapping_are_immutable() -> None:
    enriched = enrich_qpro_row_with_training_load(
        build_force_row("PES"),
        _historical_load(312, 236),
    )

    with pytest.raises(FrozenInstanceError):
        enriched.acute_load_cell = "'001"  # type: ignore[misc]
    with pytest.raises(TypeError):
        enriched.as_mapping()["CARGA_AGUDA"] = "'001"  # type: ignore[index]


@pytest.mark.parametrize(
    ("row", "load"),
    [
        (object(), _historical_load(312, 236)),
        (build_force_row("PES"), object()),
    ],
)
def test_rejects_incorrect_composition_types(row, load) -> None:
    with pytest.raises(TypeError):
        enrich_qpro_row_with_training_load(row, load)


def test_enriched_row_validates_its_constructor() -> None:
    with pytest.raises(TypeError):
        QProRowWithTrainingLoad(object(), "'312", "'236")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        QProRowWithTrainingLoad(
            build_force_row("PES"),
            312,  # type: ignore[arg-type]
            "'236",
        )
