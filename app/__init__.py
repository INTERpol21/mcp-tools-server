"""portfolio-tools: a Model Context Protocol server showcasing tool design.

The package is deliberately split in two layers:

- ``app.tools``  -- pure, MCP-agnostic tool logic (typed functions, unit-testable);
- ``app.server`` -- a thin FastMCP wiring layer plus transport selection.
"""
