from dataclasses import FrozenInstanceError

import pytest

from garmin_qpro.fit.models import DecodedFit
from garmin_qpro.fit.workout_intervals import (
    WorkoutIntervalSelection,
    select_running_workout_intervals,
)
from garmin_qpro.input.sources import FitSource


def _decoded(messages=None) -> DecodedFit:
    return DecodedFit(
        source=FitSource("activity.fit", None, None, b"fit"),
        messages={} if messages is None else messages,
        errors=(),
        crc_checked=True,
    )


def test_selects_only_active_laps_linked_to_active_workout_steps() -> None:
    selection = select_running_workout_intervals(
        _decoded(
            {
                "workout_step": [
                    {"message_index": 0, "intensity": "warmup"},
                    {"message_index": 1, "intensity": "active"},
                    {"message_index": 2, "intensity": "recovery"},
                ],
                "lap": [
                    {
                        "message_index": 0,
                        "intensity": "warmup",
                        "wkt_step_index": 0,
                    },
                    {
                        "message_index": 1,
                        "intensity": "active",
                        "wkt_step_index": 1,
                    },
                    {
                        "message_index": 2,
                        "intensity": "recovery",
                        "wkt_step_index": 2,
                    },
                    {
                        "message_index": 3,
                        "intensity": "active",
                        "wkt_step_index": 1,
                    },
                    {
                        "message_index": 4,
                        "intensity": "active",
                    },
                ],
            }
        )
    )

    assert selection.active_step_indices == (1,)
    assert tuple(lap["message_index"] for lap in selection.laps) == (1, 3)


def test_selection_is_deterministic_and_limit_keeps_first_laps() -> None:
    selection = select_running_workout_intervals(
        _decoded(
            {
                "workout_step": [
                    {"message_index": 4, "intensity": "active"},
                ],
                "lap": [
                    {
                        "message_index": index,
                        "intensity": "active",
                        "wkt_step_index": 4,
                    }
                    for index in (5, 1, 4, 2, 3)
                ],
            }
        ),
        limit=4,
    )

    assert tuple(lap["message_index"] for lap in selection.laps) == (
        1,
        2,
        3,
        4,
    )


def test_missing_steps_or_laps_produces_empty_selection() -> None:
    assert select_running_workout_intervals(_decoded()).count == 0


def test_selection_and_lap_values_are_immutable() -> None:
    selection = select_running_workout_intervals(
        _decoded(
            {
                "workout_step": [
                    {"message_index": 1, "intensity": "active"},
                ],
                "lap": [
                    {
                        "message_index": 1,
                        "intensity": "active",
                        "wkt_step_index": 1,
                    },
                ],
            }
        )
    )

    assert isinstance(selection, WorkoutIntervalSelection)
    with pytest.raises(FrozenInstanceError):
        selection.laps = ()  # type: ignore[misc]
    with pytest.raises(TypeError):
        selection.laps[0]["message_index"] = 9  # type: ignore[index]


@pytest.mark.parametrize("limit", [True, 0, -1, 1.5, "4"])
def test_invalid_limit_is_rejected(limit) -> None:
    with pytest.raises((TypeError, ValueError)):
        select_running_workout_intervals(_decoded(), limit=limit)


def test_decoded_type_is_required() -> None:
    with pytest.raises(TypeError):
        select_running_workout_intervals(object())  # type: ignore[arg-type]
