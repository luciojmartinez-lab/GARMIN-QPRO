"""Official MCP SDK adapter for the local Garmin-QPRO STDIO server."""

from __future__ import annotations

import importlib
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from garmin_qpro.garmin import (
    DEFAULT_TOKEN_STORE,
    GarminAuthenticationError,
    GarminConnectionError,
    GarminIntegrationUnavailableError,
    GarminResponseError,
)
from garmin_qpro.input import (
    InvalidZipError,
    NoFitFilesError,
    UnsafeZipPathError,
)

from . import McpIntegrationUnavailableError
from .service import TOKEN_REFRESH_COMMAND, GarminQProMcpService

MIN_MCP_PYTHON = (3, 12)
TOKEN_STORE_ENV = "GARMIN_QPRO_TOKEN_STORE"

SERVER_INSTRUCTIONS = (
    "Servidor Garmin-QPRO exclusivamente de lectura. Lista actividades antes "
    "de convertir cuando el usuario no haya identificado una. No inventes "
    "claves QPro ni numeros de fila. Si una actividad requiere eleccion "
    "manual, pregunta al usuario. No uses CURRENT_ROW_HINTS automaticamente. "
    "No expongas tokens, credenciales, coordenadas, mensajes FIT record ni "
    "bytes. Las descargas permanecen en memoria. "
    "Usa inspect_garmin_activity para revisar una actividad antes de convertir "
    "cuando su identificacion o clave no este clara. La conversion requiere "
    "siempre un numero de fila proporcionado expresamente."
)


@dataclass(frozen=True, slots=True)
class _McpSdk:
    FastMCP: type
    ToolAnnotations: type
    ToolError: type[Exception]


def _load_mcp_sdk() -> _McpSdk:
    if sys.version_info < MIN_MCP_PYTHON:
        raise McpIntegrationUnavailableError(
            "The Garmin-QPRO MCP server requires Python 3.12 or later"
        )
    try:
        fastmcp = importlib.import_module("mcp.server.fastmcp")
        exceptions = importlib.import_module(
            "mcp.server.fastmcp.exceptions"
        )
        types = importlib.import_module("mcp.types")
        return _McpSdk(
            FastMCP=fastmcp.FastMCP,
            ToolAnnotations=types.ToolAnnotations,
            ToolError=exceptions.ToolError,
        )
    except (ImportError, AttributeError) as exc:
        raise McpIntegrationUnavailableError(
            'MCP support is unavailable; install ".[mcp]"'
        ) from exc


def token_store_from_environment(
    environment: Mapping[str, str] | None = None,
) -> Path:
    values = os.environ if environment is None else environment
    configured = values.get(TOKEN_STORE_ENV)
    if configured is None or not configured.strip():
        return DEFAULT_TOKEN_STORE
    return Path(configured.strip()).expanduser()


def _safe_tool_call(
    operation: str,
    action: Callable[[], dict[str, Any]],
    *,
    tool_error: type[Exception],
) -> dict[str, Any]:
    try:
        return action()
    except GarminAuthenticationError as exc:
        raise tool_error(
            "Garmin tokens require local authentication; run "
            f"{TOKEN_REFRESH_COMMAND}"
        ) from exc
    except GarminIntegrationUnavailableError as exc:
        raise tool_error(str(exc)) from exc
    except GarminConnectionError as exc:
        raise tool_error(f"Garmin Connect {operation} failed") from exc
    except GarminResponseError as exc:
        raise tool_error(f"Garmin Connect {operation} response is invalid") from exc
    except (InvalidZipError, NoFitFilesError, UnsafeZipPathError) as exc:
        raise tool_error(f"Garmin original archive is unusable: {type(exc).__name__}") from exc
    except (TypeError, ValueError) as exc:
        raise tool_error(str(exc)) from exc
    except Exception as exc:
        raise tool_error(f"Garmin-QPRO {operation} failed safely") from exc


def create_mcp_server(
    service: GarminQProMcpService | None = None,
):
    """Build the MCP server without connecting to Garmin Connect."""

    sdk = _load_mcp_sdk()
    active_service = service or GarminQProMcpService(
        token_store=token_store_from_environment()
    )
    server = sdk.FastMCP(
        name="garmin-qpro",
        instructions=SERVER_INSTRUCTIONS,
        log_level="ERROR",
    )
    annotations = sdk.ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )

    @server.tool(
        name="list_garmin_activities",
        description=(
            "List recent Garmin activities using only safe summary fields."
        ),
        annotations=annotations,
        structured_output=True,
    )
    def list_garmin_activities(
        start: int = 0,
        limit: int = 10,
    ) -> dict[str, Any]:
        return _safe_tool_call(
            "activity listing",
            lambda: active_service.list_garmin_activities(
                start=start,
                limit=limit,
            ),
            tool_error=sdk.ToolError,
        )

    @server.tool(
        name="inspect_garmin_activity",
        description=(
            "Inspect safe FIT metadata and QPro resolution without metrics."
        ),
        annotations=annotations,
        structured_output=True,
    )
    def inspect_garmin_activity(
        activity_id: str | int,
        verify_crc: bool = True,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        return _safe_tool_call(
            "activity inspection",
            lambda: active_service.inspect_garmin_activity(
                activity_id=activity_id,
                verify_crc=verify_crc,
                force_refresh=force_refresh,
            ),
            tool_error=sdk.ToolError,
        )

    @server.tool(
        name="convert_garmin_activity",
        description=(
            "Convert every FIT in one original Garmin archive to QPro TSV."
        ),
        annotations=annotations,
        structured_output=True,
    )
    def convert_garmin_activity(
        activity_id: str | int,
        row_number: int,
        explicit_qpro_key: str | None = None,
        verify_crc: bool = True,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        return _safe_tool_call(
            "activity conversion",
            lambda: active_service.convert_garmin_activity(
                activity_id=activity_id,
                row_number=row_number,
                explicit_qpro_key=explicit_qpro_key,
                verify_crc=verify_crc,
                force_refresh=force_refresh,
            ),
            tool_error=sdk.ToolError,
        )

    return server


def run_stdio() -> None:
    """Run only the STDIO transport."""

    create_mcp_server().run(transport="stdio")
