"""Unit tests for the offline search stub (pure logic, no MCP layer)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import ToolError
from app.tools.search import MAX_QUERY_CHARS, MAX_RESULTS_CAP, search_web


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


# --------------------------------------------------------------------------- #
# Hostile-input hardening (adversarial regression tests)
# --------------------------------------------------------------------------- #


def test_oversized_query_rejected(index_path: Path) -> None:
    with pytest.raises(ToolError, match="too long"):
        search_web("x" * (MAX_QUERY_CHARS + 1), index_path=index_path)


def test_punctuation_only_query_rejected(index_path: Path) -> None:
    with pytest.raises(ToolError, match="no searchable terms"):
        search_web("... !!! ,,, ???", index_path=index_path)


@pytest.mark.parametrize("max_results", [0, -1, 10000])
def test_max_results_clamped_to_valid_range(index_path: Path, max_results: int) -> None:
    result = search_web("rag chunking agents", max_results=max_results, index_path=index_path)
    assert 1 <= len(result["results"]) <= MAX_RESULTS_CAP


def test_regex_special_chars_are_literal(index_path: Path) -> None:
    """Metacharacters must be treated as literal tokens, never compiled as a
    regex; scoring is set-overlap, so 'rag'/'chunk' still match with no error."""
    result = search_web(r"rag.*(chunk)+[a-z]?|\d{3}", index_path=index_path)
    assert result["results"]


def test_unicode_query_returns_clean_empty(index_path: Path) -> None:
    # Failure: a non-ASCII query throwing (bad tokenisation) instead of a clean
    # zero-match result; the index is English, so no hits is the correct answer.
    result = search_web("модель контекст протокол 東京", index_path=index_path)
    assert result["results"] == []
    assert result["total_matches"] == 0


def test_ranking_is_deterministic_across_calls(index_path: Path) -> None:
    # Failure: non-deterministic ordering (e.g. dict/set iteration leaking into
    # rank) making the tool's output unstable between identical calls.
    first = search_web("rag agents tools embeddings", max_results=20, index_path=index_path)
    second = search_web("rag agents tools embeddings", max_results=20, index_path=index_path)
    assert first == second


def test_score_ties_break_on_index_order(index_path: Path) -> None:
    # Failure: tied scores ordered arbitrarily; the contract is a stable
    # index-order tiebreak, so results must be non-increasing in score with a
    # deterministic sequence.
    result = search_web("security injection", max_results=20, index_path=index_path)
    scores = [hit["score"] for hit in result["results"]]
    assert scores == sorted(scores, reverse=True)
    # Re-running yields the identical URL sequence (stable tiebreak).
    again = search_web("security injection", max_results=20, index_path=index_path)
    assert [h["url"] for h in result["results"]] == [h["url"] for h in again["results"]]


def test_long_but_valid_query_is_accepted(index_path: Path) -> None:
    # Failure: an off-by-one on the length gate rejecting a query exactly at the
    # limit, or a huge (but legal) query crashing tokenisation.
    query = ("rag " * 400).strip()  # < MAX_QUERY_CHARS, thousands of tokens
    assert len(query) < MAX_QUERY_CHARS
    result = search_web(query, index_path=index_path)
    assert result["results"]  # 'rag' still matches
