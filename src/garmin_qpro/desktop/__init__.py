"""Desktop orchestration for the GARMIN-QPRO Windows application."""

from .controller import (
    DesktopActivityController,
    DesktopActivityStatus,
    DesktopActivityView,
    parse_drop_paths,
)

__all__ = [
    "DesktopActivityController",
    "DesktopActivityStatus",
    "DesktopActivityView",
    "parse_drop_paths",
]
