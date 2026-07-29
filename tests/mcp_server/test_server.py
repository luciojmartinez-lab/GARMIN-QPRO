import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

import garmin_qpro
from garmin_qpro.garmin import (
    DEFAULT_TOKEN_STORE,
    GarminAuthenticationError,
    GarminConnectionError,
)
from garmin_qpro.mcp_server import McpIntegrationUnavailableError
from garmin_qpro.mcp_server import server as server_module
from garmin_qpro.mcp_server.server import (
    SERVER_INSTRUCTIONS,
    TOKEN_STORE_ENV,
    create_mcp_server,
    token_store_from_environment,
)


class FakeService:
    def __init__(self):
        self.calls = []

    def list_garmin_activities(self, *, start=0, limit=10):
        self.calls.append(("list", start, limit))
        return {
            "activities": (),
            "count": 0,
            "start": start,
            "limit": limit,
        }

    def inspect_garmin_activity(
        self,
        *,
        activity_id,
        verify_crc=True,
        force_refresh=False,
    ):
        self.calls.append(
            ("inspect", activity_id, verify_crc, force_refresh)
        )
        return {
            "activity_id": str(activity_id),
            "container_name": "garmin.zip",
            "archive_sha256": "a" * 64,
            "archive_size": 1,
            "fit_count": 0,
            "sources": (),
        }

    def convert_garmin_activity(
        self,
        *,
        activity_id,
        row_number,
        explicit_qpro_key=None,
        verify_crc=True,
        force_refresh=False,
    ):
        self.calls.append(
            (
                "convert",
                activity_id,
                row_number,
                explicit_qpro_key,
                verify_crc,
                force_refresh,
            )
        )
        return {
            "activity_id": str(activity_id),
            "container_name": "garmin.zip",
            "archive_sha256": "a" * 64,
            "archive_size": 1,
            "success_count": 0,
            "failure_count": 0,
            "results": (),
            "failures": (),
            "tsv": "",
        }


def _run(coroutine):
    return asyncio.run(coroutine)


def test_main_package_import_does_not_import_mcp_runtime(monkeypatch) -> None:
    monkeypatch.setattr(
        server_module.importlib,
        "import_module",
        lambda name: (_ for _ in ()).throw(AssertionError(name)),
    )

    assert garmin_qpro.convert_input_path is not None


def test_main_package_import_does_not_require_garminconnect() -> None:
    source_root = Path(__file__).resolve().parents[2] / "src"
    code = """
import importlib.abc
import sys

class BlockGarminConnect(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "garminconnect":
            raise ImportError("garminconnect intentionally unavailable")
        return None

sys.meta_path.insert(0, BlockGarminConnect())
import garmin_qpro
assert garmin_qpro.convert_input_path is not None
assert "garminconnect" not in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=source_root.parent,
        env={**os.environ, "PYTHONPATH": str(source_root)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_missing_mcp_sdk_has_clear_error(monkeypatch) -> None:
    monkeypatch.setattr(
        server_module.importlib,
        "import_module",
        lambda name: (_ for _ in ()).throw(ImportError(name)),
    )

    with pytest.raises(McpIntegrationUnavailableError, match="install"):
        server_module._load_mcp_sdk()


def test_python_311_is_rejected_before_sdk_import(monkeypatch) -> None:
    monkeypatch.setattr(server_module.sys, "version_info", (3, 11, 9))

    with pytest.raises(McpIntegrationUnavailableError, match="3.12"):
        server_module._load_mcp_sdk()


def test_server_construction_does_not_call_service() -> None:
    service = FakeService()

    create_mcp_server(service)

    assert service.calls == []


def test_tools_list_does_not_call_service() -> None:
    service = FakeService()
    server = create_mcp_server(service)

    tools = _run(server.list_tools())

    assert len(tools) == 3
    assert service.calls == []


def test_exactly_three_read_only_tools_are_registered() -> None:
    tools = _run(create_mcp_server(FakeService()).list_tools())

    assert tuple(tool.name for tool in tools) == (
        "list_garmin_activities",
        "inspect_garmin_activity",
        "convert_garmin_activity",
    )
    for tool in tools:
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.idempotentHint is True
        assert tool.annotations.openWorldHint is True


def test_no_write_tools_resources_or_prompts_are_registered() -> None:
    server = create_mcp_server(FakeService())
    tools = _run(server.list_tools())

    assert not any(
        word in tool.name
        for tool in tools
        for word in ("upload", "delete", "edit", "write", "update")
    )
    assert _run(server.list_resources()) == []
    assert _run(server.list_prompts()) == []


def test_instructions_first_512_characters_are_self_contained() -> None:
    prefix = SERVER_INSTRUCTIONS[:512]

    assert len(prefix) == 512
    for required in (
        "exclusivamente de lectura",
        "No inventes claves QPro ni numeros de fila",
        "requiere eleccion manual",
        "CURRENT_ROW_HINTS",
        "tokens",
        "coordenadas",
        "FIT record",
        "bytes",
        "memoria",
    ):
        assert required in prefix


def test_tool_inputs_have_no_secret_parameters() -> None:
    tools = _run(create_mcp_server(FakeService()).list_tools())
    properties = {
        tool.name: set(tool.inputSchema["properties"])
        for tool in tools
    }

    assert properties == {
        "list_garmin_activities": {"start", "limit"},
        "inspect_garmin_activity": {
            "activity_id",
            "verify_crc",
            "force_refresh",
        },
        "convert_garmin_activity": {
            "activity_id",
            "row_number",
            "explicit_qpro_key",
            "verify_crc",
            "force_refresh",
        },
    }
    forbidden = {"password", "mfa", "cookie", "token"}
    assert all(not forbidden.intersection(names) for names in properties.values())


def test_tool_calls_delegate_exact_arguments() -> None:
    service = FakeService()
    server = create_mcp_server(service)

    listed = _run(
        server.call_tool(
            "list_garmin_activities",
            {"start": 2, "limit": 3},
        )
    )
    inspected = _run(
        server.call_tool(
            "inspect_garmin_activity",
            {
                "activity_id": "7",
                "verify_crc": False,
                "force_refresh": True,
            },
        )
    )
    converted = _run(
        server.call_tool(
            "convert_garmin_activity",
            {
                "activity_id": "7",
                "row_number": 36,
                "explicit_qpro_key": "CMF",
                "verify_crc": False,
                "force_refresh": True,
            },
        )
    )

    assert listed[1]["count"] == 0
    assert inspected[1]["activity_id"] == "7"
    assert converted[1]["activity_id"] == "7"
    assert service.calls == [
        ("list", 2, 3),
        ("inspect", "7", False, True),
        ("convert", "7", 36, "CMF", False, True),
    ]


@pytest.mark.parametrize(
    ("error", "forbidden"),
    [
        (GarminAuthenticationError("password=secret"), "secret"),
        (GarminConnectionError("token=secret"), "secret"),
        (RuntimeError("cookie=secret"), "secret"),
    ],
)
def test_tool_errors_are_sanitized(error, forbidden: str) -> None:
    class FailingService(FakeService):
        def list_garmin_activities(self, **kwargs):
            raise error

    server = create_mcp_server(FailingService())

    with pytest.raises(Exception) as exc_info:
        _run(server.call_tool("list_garmin_activities", {}))

    assert forbidden not in str(exc_info.value)
    inner_error = exc_info.value.__cause__
    assert inner_error is not None
    assert inner_error.__cause__ is error


def test_default_and_environment_token_paths() -> None:
    assert token_store_from_environment({}) == DEFAULT_TOKEN_STORE
    assert token_store_from_environment(
        {TOKEN_STORE_ENV: "  custom/tokens  "}
    ) == Path("custom/tokens")


def test_empty_token_environment_uses_default() -> None:
    assert token_store_from_environment({TOKEN_STORE_ENV: "  "}) == (
        DEFAULT_TOKEN_STORE
    )


def test_run_stdio_selects_only_stdio_transport(monkeypatch) -> None:
    observed = []

    class FakeServer:
        def run(self, *, transport):
            observed.append(transport)

    monkeypatch.setattr(
        server_module,
        "create_mcp_server",
        lambda: FakeServer(),
    )

    server_module.run_stdio()

    assert observed == ["stdio"]
