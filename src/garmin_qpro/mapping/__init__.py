"""Safe mappings from explicit Garmin workout names."""

from .activity_resolution import ActivityResolution, resolve_activity
from .workout_names import WorkoutResolution, resolve_workout_name

__all__ = [
    "ActivityResolution",
    "WorkoutResolution",
    "resolve_activity",
    "resolve_workout_name",
]
