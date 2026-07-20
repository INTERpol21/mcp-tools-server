"""Pure, MCP-agnostic tool implementations.

Every function in this package is plain Python: typed arguments in,
JSON-serialisable dict out, :class:`ToolError` raised on invalid input.
The MCP layer in ``app.server`` only adds protocol plumbing, which keeps
this logic trivially unit-testable and independent of SDK internals.
"""

from app.core.errors import ToolError

__all__ = ["ToolError"]
