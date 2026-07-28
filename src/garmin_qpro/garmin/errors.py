"""Public errors for the optional Garmin Connect integration."""


class GarminIntegrationUnavailableError(RuntimeError):
    """Raised when the optional integration cannot be loaded."""


class GarminAuthenticationError(RuntimeError):
    """Raised when Garmin Connect authentication fails."""


class GarminConnectionError(RuntimeError):
    """Raised when Garmin Connect cannot complete a remote read."""


class GarminResponseError(ValueError):
    """Raised when Garmin Connect returns an unusable response."""
