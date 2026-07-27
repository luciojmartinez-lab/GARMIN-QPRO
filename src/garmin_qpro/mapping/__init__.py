"""Safe mappings from explicit Garmin workout names."""

from .workout_names import WorkoutResolution, resolve_workout_name

__all__ = [
    "WorkoutResolution",
    "resolve_workout_name",
]
