"""Local read-only MCP integration for Garmin-QPRO."""

from .service import (
    MAX_DOWNLOAD_CACHE_SIZE,
    TOKEN_REFRESH_COMMAND,
    GarminQProMcpService,
)


class McpIntegrationUnavailableError(RuntimeError):
    """Raised when the optional MCP runtime cannot be loaded."""


__all__ = [
    "MAX_DOWNLOAD_CACHE_SIZE",
    "McpIntegrationUnavailableError",
    "TOKEN_REFRESH_COMMAND",
    "GarminQProMcpService",
]
