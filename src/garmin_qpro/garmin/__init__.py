"""Optional read-only Garmin Connect integration."""

from .errors import (
    GarminAuthenticationError,
    GarminConnectionError,
    GarminIntegrationUnavailableError,
    GarminResponseError,
)
from .models import GarminActivityDownload, GarminActivitySummary
from .reader import (
    DEFAULT_TOKEN_STORE,
    GarminConnectReader,
    connect_garmin,
)

__all__ = [
    "DEFAULT_TOKEN_STORE",
    "GarminActivityDownload",
    "GarminActivitySummary",
    "GarminAuthenticationError",
    "GarminConnectReader",
    "GarminConnectionError",
    "GarminIntegrationUnavailableError",
    "GarminResponseError",
    "connect_garmin",
]
