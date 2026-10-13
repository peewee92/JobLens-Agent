"""Run the local JobLens MCP server over STDIO.

STDOUT is reserved for MCP protocol messages. Configure application logging to
stderr if diagnostics are needed.
"""
from app.mcp.composition import build_mcp_adapter
from app.mcp.server import create_mcp_server


def main() -> None:
    create_mcp_server(build_mcp_adapter()).run("stdio")


if __name__ == "__main__":
    main()
