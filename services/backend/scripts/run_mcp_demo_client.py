"""Call the three local JobLens MCP tools through a standard SDK client.

The database must already contain released Career Context, released Requirement
facts, and current MatchReports created through the normal JobLens workflow.
This script never seeds, changes, or calls a Provider against that database.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters


def _as_json(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    return value


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    database_url = f"sqlite:///{args.database.resolve()}"
    environment = dict(os.environ, DATABASE_URL=database_url)
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "scripts.run_mcp_server"],
        env=environment,
    )
    async with Client(server) as client:
        tools = await client.list_tools()
        discovered = [tool.name for tool in tools.tools]
        results = {
            "rank_match_reports": _as_json(
                await client.call_tool(
                    "rank_match_reports",
                    {"job_ids": args.job_ids, "top_n": min(len(args.job_ids), 5)},
                )
            ),
            "target_cohort_gaps": _as_json(
                await client.call_tool(
                    "target_cohort_gaps",
                    {"selected_job_ids": args.job_ids, "name": "Synthetic MCP demo cohort"},
                )
            ),
            "job_preparation": _as_json(
                await client.call_tool("job_preparation", {"job_id": args.prepare_job_id})
            ),
        }
    return {"discovered": discovered, "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--job-id", dest="job_ids", action="append", required=True)
    parser.add_argument("--prepare-job-id", required=True)
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error("--database must point to an existing local SQLite file")
    print(json.dumps(asyncio.run(_run(args)), ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
