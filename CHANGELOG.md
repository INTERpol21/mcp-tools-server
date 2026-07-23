# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] - 2026-07-23

### Added
- Bearer auth on the streamable-HTTP transport: requests to `/mcp` must carry
  `Authorization: Bearer <key>` with a key from `MCP_API_KEYS` (comma-separated,
  default `demo-key` — the platform's shared offline key). Wrong or missing
  keys get 401 with `WWW-Authenticate: Bearer`; comparison is constant-time.
  stdio is deliberately not gated: its client is whoever spawned the process.
  Previously the tools were reachable by anyone who could hit the port.
  Pairs with agent-orchestrator 1.2.0, which sends the header.

## [1.0.0] - 2026-07-21

First tagged release. An MCP server on the official Python SDK (FastMCP),
exposing tools and resources over both stdio and streamable HTTP from one
codebase.

### Added
- Four tools — `search_web`, `query_database`, `read_file`, `list_dir` — each
  returning typed results as `structuredContent` alongside readable JSON.
- `data/docs/` published as MCP resources, both concrete entries and a template.
- Read-only SQL: a sqlite authorizer allowlisting SELECT/READ/FUNCTION, rejection
  of multi-statement payloads, and row/cell/result-size caps.
- Filesystem sandbox rooted at `DATA_DIR`, denying `..`, absolute escapes and
  symlink traversal.
- Structured JSON logging to stderr (stdout carries stdio JSON-RPC frames) that
  records shapes and sizes, never SQL text, rows or file contents.

### Notes
- `search_web` is an offline keyword-ranked stub over a curated index, kept
  deterministic for demos and tests; a real search API drops in behind the same
  contract.
- The streamable-HTTP transport is unauthenticated — deliberate for the offline
  demo, tracked in the roadmap.

[1.0.0]: https://github.com/INTERpol21/mcp-tools-server/releases/tag/v1.0.0
