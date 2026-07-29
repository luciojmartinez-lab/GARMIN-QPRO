import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / "src"
FIXTURE_SERVER = Path(__file__).with_name("stdio_fixture_server.py")


def _environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(SOURCE_ROOT)
    return environment


def _run(coroutine):
    return asyncio.run(coroutine)


async def _list_default_server():
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "garmin_qpro.mcp_server"],
        cwd=ROOT,
        env=_environment(),
    )
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await session.initialize()
            tools = await session.list_tools()
            resources = await session.list_resources()
            prompts = await session.list_prompts()
            return initialized, tools, resources, prompts


async def _use_synthetic_server():
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[str(FIXTURE_SERVER)],
        cwd=ROOT,
        env=_environment(),
    )
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            listed = await session.call_tool(
                "list_garmin_activities",
                {"start": 0, "limit": 10},
            )
            inspected = await session.call_tool(
                "inspect_garmin_activity",
                {"activity_id": "42", "verify_crc": True},
            )
            converted = await session.call_tool(
                "convert_garmin_activity",
                {
                    "activity_id": "42",
                    "explicit_qpro_key": None,
                    "verify_crc": True,
                },
            )
            return tools, listed, inspected, converted


def test_default_stdio_initializes_and_lists_without_garmin_connection() -> None:
    initialized, tools, resources, prompts = _run(_list_default_server())

    assert initialized.serverInfo.name == "garmin-qpro"
    assert tuple(tool.name for tool in tools.tools) == (
        "list_garmin_activities",
        "inspect_garmin_activity",
        "convert_garmin_activity",
    )
    assert resources.resources == []
    assert prompts.prompts == []


def test_stdio_tools_keep_security_annotations() -> None:
    _, tools, _, _ = _run(_list_default_server())

    for tool in tools.tools:
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.idempotentHint is True
        assert tool.annotations.openWorldHint is True


def test_synthetic_stdio_can_call_all_three_tools() -> None:
    tools, listed, inspected, converted = _run(_use_synthetic_server())

    assert len(tools.tools) == 3
    assert listed.isError is False
    assert listed.structuredContent["count"] == 1
    assert listed.structuredContent["activities"][0]["activity_id"] == "42"
    assert inspected.isError is False
    assert inspected.structuredContent["fit_count"] == 1
    assert converted.isError is False
    assert converted.structuredContent["success_count"] == 1
    assert converted.structuredContent["results"][0]["column_count"] == 23
    assert converted.structuredContent["results"][0]["tab_count"] == 22


def test_synthetic_stdio_output_contains_no_private_fields() -> None:
    _, listed, inspected, converted = _run(_use_synthetic_server())
    representation = repr(
        (
            listed.structuredContent,
            inspected.structuredContent,
            converted.structuredContent,
        )
    ).casefold()

    for forbidden in (
        "password",
        "token",
        "cookie",
        "latitude",
        "longitude",
        "record",
        "bytes",
    ):
        assert forbidden not in representation
