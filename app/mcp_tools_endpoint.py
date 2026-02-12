"""Tool definition endpoint."""

from __future__ import annotations

from typing import Any

from app.errors import McpError, success_response
from app.mcp_router import mcp_router
from tools.mcp_tools import ToolSchemaError, load_tool_definitions


@mcp_router.get("/tools")
def list_tool_schemas() -> dict[str, Any]:
    """Return the current MCP tool definitions."""
    try:
        tools = load_tool_definitions()
    except ToolSchemaError as exc:
        raise McpError(
            "TOOL_SCHEMA_ERROR",
            "Tool definitions could not be loaded.",
            {"error": str(exc)},
        ) from exc
    return success_response({"tools": tools})
