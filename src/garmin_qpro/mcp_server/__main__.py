"""Executable entry point for the Garmin-QPRO MCP STDIO server."""

from __future__ import annotations

import sys

from . import McpIntegrationUnavailableError


def main() -> int:
    try:
        from .server import run_stdio

        run_stdio()
    except McpIntegrationUnavailableError as exc:
        print(f"Garmin-QPRO MCP unavailable: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
