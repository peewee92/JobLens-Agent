"""Local, read-only MCP transport adapters for governed JobLens workflows."""

# Do not import ``server`` here. Keeping the transport SDK lazy lets deterministic
# adapter tests run without opening a protocol transport.
from app.mcp.adapter import JobLensMcpAdapter

__all__ = ["JobLensMcpAdapter"]
