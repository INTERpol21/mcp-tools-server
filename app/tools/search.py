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

from app.tools.errors import ToolError

MAX_RESULTS_CAP = 20

_TOKEN_RE = re.compile(r"[^\W_]+")

_KEYWORD_WEIGHT = 2
_TITLE_WEIGHT = 1


def _tokenize(text: str) -> set[str]:
    """Lowercase a string and split it into unique word tokens."""
    return set(_TOKEN_RE.findall(text.lower()))


def _load_index(index_path: Path) -> list[dict[str, Any]]:
    """Load and minimally validate the JSON search index."""
    if not index_path.is_file():
        raise ToolError(f"Search index not found at '{index_path}'.")
    with index_path.open(encoding="utf-8") as handle:
        entries = json.load(handle)
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


def search_web(query: str, max_results: int = 5, *, index_path: Path) -> dict[str, Any]:
    """Rank curated index entries against ``query`` and return the best hits.

    Args:
        query: Free-text query, e.g. ``"rag chunking strategies"``.
        max_results: Maximum number of results (clamped to 1..20).
        index_path: Location of ``search_index.json``.

    Returns:
        Dict with ``results`` (best first), ``total_matches`` and ``source``.

    Raises:
        ToolError: If the query is empty or the index is missing/malformed.
    """
    if not query or not query.strip():
        raise ToolError("Query must be a non-empty string.")
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

    results = [
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
