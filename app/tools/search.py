"""Offline web-search stub over a curated local index.

Honest by design: this is NOT a real search engine. It ranks 14 hand-picked
entries (``data/search_index.json``) by keyword overlap with the query, so
demos and tests are deterministic, free and network-independent. In
production the implementation would call a real search API (Tavily, Brave,
SerpAPI, ...) while keeping the exact same tool contract.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from typing_extensions import TypedDict

from app.core.errors import ToolError

MAX_RESULTS_CAP = 20
MAX_QUERY_CHARS = 2_000


class SearchHit(TypedDict):
    """One ranked entry from the offline index."""

    title: str
    url: str
    snippet: str
    score: int


class SearchWebResult(TypedDict):
    """Shape of a ``search_web`` response (drives MCP structured output)."""

    query: str
    results: list[SearchHit]
    total_matches: int
    source: str

_TOKEN_RE = re.compile(r"[^\W_]+")

_KEYWORD_WEIGHT = 2
_TITLE_WEIGHT = 1


def _tokenize(text: str) -> set[str]:
    """Lowercase a string and split it into unique word tokens."""
    return set(_TOKEN_RE.findall(text.lower()))


def _load_index(index_path: Path) -> list[dict[str, Any]]:
    """Load and minimally validate the JSON search index."""
    if not index_path.is_file():
        raise ToolError(
            "Search index not found; expected search_index.json in the data directory."
        )
    try:
        with index_path.open(encoding="utf-8") as handle:
            entries = json.load(handle)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ToolError("Search index is malformed: not valid JSON.") from exc
    if not isinstance(entries, list):
        raise ToolError("Search index is malformed: expected a JSON array of entries.")
    return entries


def _score(query_tokens: set[str], entry: dict[str, Any]) -> int:
    """Keyword-overlap score: keywords weigh more than title words."""
    keyword_tokens = _tokenize(" ".join(entry.get("keywords", [])))
    title_tokens = _tokenize(entry.get("title", ""))
    return _KEYWORD_WEIGHT * len(query_tokens & keyword_tokens) + _TITLE_WEIGHT * len(
        query_tokens & title_tokens
    )


def search_web(
    query: str, max_results: int = 5, *, index_path: Path
) -> SearchWebResult:
    """Rank curated index entries against ``query``, best match first.

    Ties break on index order, so output is fully deterministic. Raises
    ToolError for empty/tokenless queries and a missing/malformed index.
    """
    if not query or not query.strip():
        raise ToolError("Query must be a non-empty string.")
    if len(query) > MAX_QUERY_CHARS:
        raise ToolError(
            f"Query too long: {len(query)} chars exceeds the {MAX_QUERY_CHARS}-char limit."
        )
    query_tokens = _tokenize(query)
    if not query_tokens:
        raise ToolError("Query contains no searchable terms.")
    limit = max(1, min(int(max_results), MAX_RESULTS_CAP))

    scored: list[tuple[int, int, dict[str, Any]]] = []
    for position, entry in enumerate(_load_index(index_path)):
        score = _score(query_tokens, entry)
        if score > 0:
            scored.append((score, position, entry))
    scored.sort(key=lambda item: (-item[0], item[1]))

    results: list[SearchHit] = [
        {
            "title": entry.get("title", ""),
            "url": entry.get("url", ""),
            "snippet": entry.get("snippet", ""),
            "score": score,
        }
        for score, _, entry in scored[:limit]
    ]
    return {
        "query": query,
        "results": results,
        "total_matches": len(scored),
        "source": "offline_index",
    }
