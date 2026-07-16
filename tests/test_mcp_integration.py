"""Integration tests through the real MCP layer, fully in-memory.

Uses ``mcp.shared.memory.create_connected_server_and_client_session`` -- the
same helper the official SDK uses in its own test-suite -- to run a client
session against our FastMCP server without spawning processes or sockets.
The helper lives in a semi-private module, so if a future SDK release moves
or reshapes it these tests skip (with a reason) instead of failing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.server import create_server

REPO_ROOT = Path(__file__).resolve().parent.parent

try:
    from mcp.shared.memory import (
        create_connected_server_and_client_session as connected_session,
    )
except ImportError:  # pragma: no cover - depends on installed SDK version
    connected_session = None

pytestmark = pytest.mark.skipif(
    connected_session is None,
    reason="mcp.shared.memory helper is not available in this SDK version",
)

EXPECTED_TOOLS = {"search_web", "query_database", "read_file", "list_dir"}


def _make_low_level_server():
    settings = Settings(data_dir=REPO_ROOT / "data", host="127.0.0.1", port=8099)
    server = create_server(settings)
    low_level = getattr(server, "_mcp_server", None)
    if low_level is None:  # pragma: no cover - depends on installed SDK version
        pytest.skip("FastMCP no longer exposes ._mcp_server; adapt this test")
    return low_level


async def test_list_tools_over_mcp() -> None:
    async with connected_session(_make_low_level_server()) as session:
        listed = await session.list_tools()
        names = {tool.name for tool in listed.tools}
        assert names == EXPECTED_TOOLS
        descriptions = {tool.name: (tool.description or "") for tool in listed.tools}
        assert "offline" in descriptions["search_web"].lower()


async def test_call_search_web_over_mcp() -> None:
    async with connected_session(_make_low_level_server()) as session:
        result = await session.call_tool(
            "search_web",
            {"query": "model context protocol transports", "max_results": 3},
        )
        assert result.isError is False
        text = "".join(
            block.text for block in result.content if block.type == "text"
        )
        assert "results" in text
        assert "modelcontextprotocol.io" in text


async def test_tool_error_maps_to_protocol_error() -> None:
    """A sandbox violation surfaces as a protocol-level tool error:
    isError=True, the ToolError message, and no traceback."""
    async with connected_session(_make_low_level_server()) as session:
        result = await session.call_tool("read_file", {"path": "../secret.txt"})
        assert result.isError is True
        text = "".join(
            block.text for block in result.content if block.type == "text"
        )
        assert "sandbox" in text
        assert "Traceback" not in text
