"""Safe local smoke client for the Garmin-QPRO MCP STDIO server."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check the local Garmin-QPRO MCP STDIO server",
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--activity-id")
    parser.add_argument("--row-number", type=int)
    parser.add_argument("--qpro-key")
    args = parser.parse_args()
    if args.row_number is not None and args.activity_id is None:
        parser.error("--row-number requires --activity-id")
    if args.qpro_key is not None and args.row_number is None:
        parser.error("--qpro-key requires --row-number")
    return args


def _safe_tool_error(result: Any) -> str:
    for content in getattr(result, "content", ()):
        text = getattr(content, "text", None)
        if isinstance(text, str) and text:
            return text
    return "MCP tool failed"


def _structured_result(result: Any) -> dict[str, Any]:
    if getattr(result, "isError", False):
        raise RuntimeError(_safe_tool_error(result))
    payload = getattr(result, "structuredContent", None)
    if not isinstance(payload, dict):
        raise RuntimeError("MCP tool did not return structured content")
    return payload


async def _run(args: argparse.Namespace) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "garmin_qpro.mcp_server"],
        cwd=Path(__file__).resolve().parents[1],
    )
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool_names = tuple(tool.name for tool in tools.tools)
            print(f"MCP tools ({len(tool_names)}): {', '.join(tool_names)}")

            listed = _structured_result(
                await session.call_tool(
                    "list_garmin_activities",
                    {"start": 0, "limit": args.limit},
                )
            )
            print(f"Garmin activities: {listed['count']}")
            for activity in listed["activities"]:
                print(
                    f"{activity['activity_id']}\t"
                    f"{activity.get('start_time_local') or ''}\t"
                    f"{activity.get('activity_type') or ''}\t"
                    f"{activity.get('name') or ''}"
                )

            if args.activity_id is None:
                return

            inspected = _structured_result(
                await session.call_tool(
                    "inspect_garmin_activity",
                    {
                        "activity_id": args.activity_id,
                        "verify_crc": True,
                    },
                )
            )
            print(
                f"Inspected activity {inspected['activity_id']}: "
                f"{inspected['fit_count']} FIT"
            )
            for source in inspected["sources"]:
                print(
                    f"{source['source_name']}\t"
                    f"key={source.get('qpro_key') or ''}\t"
                    f"choice={source['requires_user_choice']}\t"
                    f"crc={source['crc_checked']}"
                )

            if args.row_number is None:
                return

            converted = _structured_result(
                await session.call_tool(
                    "convert_garmin_activity",
                    {
                        "activity_id": args.activity_id,
                        "row_number": args.row_number,
                        "explicit_qpro_key": args.qpro_key,
                        "verify_crc": True,
                    },
                )
            )
            print(
                f"Converted: {converted['success_count']} success, "
                f"{converted['failure_count']} failure"
            )
            if converted["tsv"]:
                print(converted["tsv"])


def main() -> int:
    args = _arguments()
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"MCP smoke check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
