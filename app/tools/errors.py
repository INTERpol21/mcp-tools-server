"""Shared error type for tool implementations."""


class ToolError(ValueError):
    """Tool-level failure whose message is safe to show to the caller.

    Raised for invalid input, sandbox violations and rejected SQL.
    The MCP layer converts it into a protocol-level tool error message
    instead of leaking a traceback.
    """
