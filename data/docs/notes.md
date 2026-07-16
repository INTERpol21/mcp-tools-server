# Demo notes

This directory is served by the `read_file` and `list_dir` MCP tools.

Everything under `data/` is sandboxed: the server refuses to read anything
outside of it (including `..` traversal, absolute paths and symlink escapes)
and caps file reads at 100 KB.

Try it from an MCP client:

- `list_dir {"path": "docs"}`
- `read_file {"path": "docs/pipeline.md"}`
