from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TOOLS_JSON_PATH = Path(__file__).with_name("mcp_tools.json")


class ToolSchemaError(RuntimeError):
    """Raised when tool schema definitions are invalid or unavailable."""


def load_tool_definitions(path: Path | None = None) -> list[dict[str, Any]]:
    tool_path = path or TOOLS_JSON_PATH
    if not tool_path.is_file():
        raise ToolSchemaError(f"Tool definition file not found: {tool_path}")
    try:
        raw = tool_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ToolSchemaError(
            f"Unable to read tool definitions: {tool_path}"
        ) from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ToolSchemaError(f"Tool definitions JSON is invalid: {exc}") from exc
    if not isinstance(data, list):
        raise ToolSchemaError("Tool definitions must be a JSON array.")
    validate_tool_definitions(data)
    return data


def validate_tool_definitions(tools: list[dict[str, Any]]) -> None:
    for index, tool in enumerate(tools):
        if not isinstance(tool, dict):
            raise ToolSchemaError(f"Tool at index {index} must be an object.")
        if tool.get("type") != "function":
            raise ToolSchemaError(
                f"Tool at index {index} must have type='function'."
            )
        function = tool.get("function")
        if not isinstance(function, dict):
            raise ToolSchemaError(
                f"Tool at index {index} is missing 'function' object."
            )
        name = function.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ToolSchemaError(
                f"Tool at index {index} must define a non-empty name."
            )
        parameters = function.get("parameters")
        if not isinstance(parameters, dict):
            raise ToolSchemaError(
                f"Tool '{name}' must include parameters object."
            )
