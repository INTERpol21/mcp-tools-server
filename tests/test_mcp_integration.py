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
from mcp.shared.exceptions import McpError
from pydantic import AnyUrl

from app.core.settings import Settings
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
EXPECTED_DOC_RESOURCES = {
    "docs://notes.md",
    "docs://pipeline.md",
    "docs://prompts.txt",
}


def _make_low_level_server(data_dir: Path | None = None):
    """Server over the repo's data directory, or a caller-supplied one.

    Tests that hit query_database pass a tmp directory: the demo database is
    seeded on first use and tests must never write inside the repository.
    """
    settings = Settings(
        data_dir=data_dir or REPO_ROOT / "data", host="127.0.0.1", port=8099
    )
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
    isError=True, the ToolError message, no structured payload, no traceback."""
    async with connected_session(_make_low_level_server()) as session:
        result = await session.call_tool("read_file", {"path": "../secret.txt"})
        assert result.isError is True
        assert result.structuredContent is None
        text = "".join(
            block.text for block in result.content if block.type == "text"
        )
        assert "sandbox" in text
        assert "Traceback" not in text


async def test_query_database_error_over_mcp(tmp_path: Path) -> None:
    """Rejected SQL maps to isError with the read-only message, no traceback."""
    async with connected_session(_make_low_level_server(tmp_path)) as session:
        result = await session.call_tool("query_database", {"sql": "DROP TABLE companies"})
        assert result.isError is True
        assert result.structuredContent is None
        text = "".join(
            block.text for block in result.content if block.type == "text"
        )
        assert "read-only" in text
        assert "Traceback" not in text


async def test_tools_declare_output_schemas() -> None:
    """Typed returns surface as an MCP output schema on every tool."""
    async with connected_session(_make_low_level_server()) as session:
        listed = await session.list_tools()
        schemas = {tool.name: tool.outputSchema for tool in listed.tools}
        assert set(schemas) == EXPECTED_TOOLS
        for name, schema in schemas.items():
            assert schema is not None, f"{name} lost its output schema"
        assert "results" in schemas["search_web"]["properties"]
        assert "rows" in schemas["query_database"]["properties"]
        assert "content" in schemas["read_file"]["properties"]
        assert "entries" in schemas["list_dir"]["properties"]


async def test_search_web_structured_content() -> None:
    async with connected_session(_make_low_level_server()) as session:
        result = await session.call_tool(
            "search_web",
            {"query": "model context protocol transports", "max_results": 2},
        )
        assert result.isError is False
        structured = result.structuredContent
        assert structured is not None
        assert structured["query"] == "model context protocol transports"
        assert structured["total_matches"] >= 1
        assert structured["source"] == "offline_index"
        first = structured["results"][0]
        assert {"title", "url", "snippet", "score"} <= set(first)


async def test_query_database_structured_content(tmp_path: Path) -> None:
    async with connected_session(_make_low_level_server(tmp_path)) as session:
        result = await session.call_tool(
            "query_database",
            {"sql": "SELECT name, city FROM companies ORDER BY id", "max_rows": 3},
        )
        assert result.isError is False
        structured = result.structuredContent
        assert structured is not None
        assert structured["columns"] == ["name", "city"]
        assert structured["rows"][0] == ["Aurora Labs", "Moscow"]
        assert structured["row_count"] == 3
        assert structured["truncated"] is True  # 6 companies, max_rows=3


async def test_read_file_structured_content() -> None:
    async with connected_session(_make_low_level_server()) as session:
        result = await session.call_tool("read_file", {"path": "docs/pipeline.md"})
        assert result.isError is False
        structured = result.structuredContent
        assert structured is not None
        assert structured["path"] == "docs/pipeline.md"
        assert structured["size_bytes"] > 0
        assert "RAG pipeline" in structured["content"]


async def test_list_dir_structured_content() -> None:
    async with connected_session(_make_low_level_server()) as session:
        result = await session.call_tool("list_dir", {"path": "."})
        assert result.isError is False
        structured = result.structuredContent
        assert structured is not None
        assert structured["path"] == "."
        assert structured["count"] == len(structured["entries"])
        entries = {entry["name"]: entry for entry in structured["entries"]}
        assert entries["docs"]["type"] == "dir"
        assert "size_bytes" not in entries["docs"]  # NotRequired field stays absent
        index_entry = entries["search_index.json"]
        assert index_entry["type"] == "file"
        assert index_entry["size_bytes"] > 0


async def test_list_doc_resources_over_mcp() -> None:
    """Static registrations expose data/docs with names and mime types."""
    async with connected_session(_make_low_level_server()) as session:
        listed = await session.list_resources()
        by_uri = {str(resource.uri): resource for resource in listed.resources}
        assert set(by_uri) == EXPECTED_DOC_RESOURCES
        assert by_uri["docs://pipeline.md"].mimeType == "text/markdown"
        assert by_uri["docs://prompts.txt"].mimeType == "text/plain"
        assert by_uri["docs://notes.md"].name == "notes.md"


async def test_list_resource_templates_over_mcp() -> None:
    async with connected_session(_make_low_level_server()) as session:
        listed = await session.list_resource_templates()
        templates = {template.uriTemplate for template in listed.resourceTemplates}
        assert "docs://{name}" in templates


async def test_read_doc_resource_over_mcp() -> None:
    async with connected_session(_make_low_level_server()) as session:
        result = await session.read_resource(AnyUrl("docs://pipeline.md"))
        content = result.contents[0]
        assert content.mimeType == "text/markdown"
        assert "RAG pipeline" in content.text


async def test_resource_escape_fails_cleanly() -> None:
    """docs:// reads share read_file's sandbox (rooted at data/docs), so
    escape attempts fail with a clean protocol error, never file content."""
    async with connected_session(_make_low_level_server()) as session:
        with pytest.raises(McpError) as excinfo:
            await session.read_resource(AnyUrl("docs://../demo.db"))
        assert "Traceback" not in str(excinfo.value)
        with pytest.raises(McpError) as excinfo:
            await session.read_resource(AnyUrl("docs://.."))
        assert "escapes the data directory sandbox" in str(excinfo.value)
