# Contributing — mcp-tools-server

FastMCP tool server (:8082): offline web search, read-only SQL over a bundled
demo SQLite DB, and sandboxed file access. stdio + streamable-HTTP transports.

## Setup

```bash
make install-dev      # uv sync (runtime + dev)
make seed             # (re)build the demo SQLite database
make run              # streamable HTTP on :8082 (endpoint /mcp)
make run-stdio        # stdio transport for local MCP clients
```

`uv` is the source of truth; `requirements*.txt` are exported from `uv.lock`
(`make lock` after editing `pyproject.toml`, and commit the diff).

## Gates (all must be green before a PR)

```bash
make lint             # ruff
make typecheck        # mypy (strict)
make test             # pytest, offline
```

CI runs ruff + mypy + pytest, plus pip-audit, bandit and CodeQL.

## Layout

```
app/
  server.py           # FastMCP factory + tool/resource registration + transport
  core/               # settings · errors · logging
  tools/              # search · database (read-only SQL) · files (sandbox) · seed
  resources/          # docs:// resources
```

- Tool logic lives in `tools/` as pure typed functions; `server.py` only
  registers thin wrappers. Return `TypedDict`s — they double as MCP output
  schemas (`structuredContent`).
- Docstrings are the tool "UI" an LLM reads to pick a tool — keep schemas,
  examples and constraints in them.

## Conventions (safety is the product here)

- **Read-only SQL** (`tools/database.py`): SQLite `mode=ro` + authorizer allowing
  only SELECT/READ + multi-statement rejection + row/cell/result-size caps.
  Never widen this; any change needs tests proving writes/DDL/PRAGMA stay blocked.
- **File sandbox** (`tools/files.py`): paths are resolved (symlinks + `..`) and
  must stay inside the data dir; error messages echo the caller path, never host
  paths. Add a traversal-rejection test for any change.
- **Logging:** log shapes/sizes only (`query_len`, `sql_chars`, `path`), never DB
  rows or file contents.
- **Tests:** behaviour through the tool contract; deterministic/offline; negative
  cases required (rejected SQL, escaped paths, oversized results).

## Commits & branches

Small, focused commits with a clear subject line. Develop on a feature branch
(`claude/<topic>` in this project) and open a PR against the default branch; keep
gates green.
