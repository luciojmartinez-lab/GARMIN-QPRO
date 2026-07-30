"""Optional read-only Garmin Connect integration."""

from .errors import (
    GarminAuthenticationError,
    GarminChallengeError,
    GarminConnectionError,
    GarminCredentialStoreError,
    GarminIntegrationUnavailableError,
    GarminInvalidSessionError,
    GarminLoginDiagnostic,
    GarminLoginIssue,
    GarminMfaCancelledError,
    GarminMfaError,
    GarminNetworkError,
    GarminRateLimitError,
    GarminResponseError,
    diagnose_login_error,
    garminconnect_package_version,
)
from .models import GarminActivityDownload, GarminActivitySummary
from .reader import (
    DEFAULT_TOKEN_STORE,
    GarminConnectReader,
    connect_garmin,
)
from .session import (
    DEFAULT_DESKTOP_SESSION_FILE,
    DpapiSessionVault,
    GarminDesktopSession,
    KeyringSessionVault,
    StoredGarminSession,
    WindowsDpapiProtector,
)

__all__ = [
    "DEFAULT_DESKTOP_SESSION_FILE",
    "DEFAULT_TOKEN_STORE",
    "DpapiSessionVault",
    "GarminActivityDownload",
    "GarminActivitySummary",
    "GarminAuthenticationError",
    "GarminChallengeError",
    "GarminConnectReader",
    "GarminConnectionError",
    "GarminCredentialStoreError",
    "GarminIntegrationUnavailableError",
    "GarminInvalidSessionError",
    "GarminLoginDiagnostic",
    "GarminLoginIssue",
    "GarminMfaCancelledError",
    "GarminMfaError",
    "GarminNetworkError",
    "GarminRateLimitError",
    "GarminResponseError",
    "diagnose_login_error",
    "garminconnect_package_version",
    "connect_garmin",
    "GarminDesktopSession",
    "KeyringSessionVault",
    "StoredGarminSession",
    "WindowsDpapiProtector",
]
