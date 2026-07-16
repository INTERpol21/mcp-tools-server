"""Unit tests for the offline search stub (pure logic, no MCP layer)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.errors import ToolError
from app.tools.search import search_web


def test_relevant_result_ranks_first(index_path: Path) -> None:
    result = search_web("rag chunking strategies", index_path=index_path)
    assert result["results"], "expected at least one hit"
    assert "chunk" in result["results"][0]["title"].lower()
    scores = [item["score"] for item in result["results"]]
    assert scores == sorted(scores, reverse=True)


def test_max_results_respected(index_path: Path) -> None:
    result = search_web("llm agents tools", max_results=2, index_path=index_path)
    assert len(result["results"]) <= 2
    assert result["total_matches"] >= len(result["results"])


def test_empty_query_rejected(index_path: Path) -> None:
    with pytest.raises(ToolError, match="non-empty"):
        search_web("   ", index_path=index_path)


def test_unmatched_query_returns_empty(index_path: Path) -> None:
    result = search_web("quantum knitting recipes", index_path=index_path)
    assert result["results"] == []
    assert result["total_matches"] == 0
