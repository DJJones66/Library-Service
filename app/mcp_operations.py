"""Markdown operation helpers for MCP endpoints."""

from __future__ import annotations

import difflib
from typing import Any

from app.errors import McpError
from app.mcp_constants import (
    PREVIEW_OPERATIONS,
    SECTION_OPERATIONS,
    WRITE_OPERATIONS,
)
from app.mcp_payload import _reject_unknown_fields
from app.mcp_utils import _join_with_newline


def _apply_preview_operation(
    content: str, operation: Any
) -> tuple[str, str, str | None]:
    op_type, op_content, target = _validate_operation_payload(operation)

    if op_type not in PREVIEW_OPERATIONS:
        raise McpError(
            "INVALID_OPERATION",
            "Unsupported operation type.",
            {"type": op_type},
        )

    if op_type in SECTION_OPERATIONS and not target:
        raise McpError(
            "MISSING_TARGET",
            "Target is required for section operations.",
            {"type": op_type},
        )

    if op_type == "append":
        return _join_with_newline(content, op_content), op_type, None
    if op_type == "prepend":
        return _join_with_newline(op_content, content), op_type, None

    updated = _apply_section_operation(content, op_type, target or "", op_content)
    return updated, op_type, target


def _apply_write_operation(content: str, operation: Any) -> str:
    op_type, op_content, _target = _validate_operation_payload(operation)

    if op_type not in WRITE_OPERATIONS:
        raise McpError(
            "INVALID_OPERATION",
            "Unsupported operation type.",
            {"type": op_type},
        )

    if op_type == "append":
        return _join_with_newline(content, op_content)
    return _join_with_newline(op_content, content)


def _apply_edit_operation(content: str, operation: Any) -> str:
    op_type, op_content, target = _validate_operation_payload(operation)

    if op_type not in SECTION_OPERATIONS:
        raise McpError(
            "INVALID_OPERATION",
            "Unsupported operation type.",
            {"type": op_type},
        )

    if not target:
        raise McpError(
            "MISSING_TARGET",
            "Target is required for section operations.",
            {"type": op_type},
        )

    return _apply_section_operation(content, op_type, target, op_content)


def _validate_operation_payload(
    operation: Any,
) -> tuple[str, str, str | None]:
    if not isinstance(operation, dict):
        raise McpError(
            "INVALID_TYPE",
            "Operation must be an object.",
            {"operation": str(operation), "type": type(operation).__name__},
        )

    _reject_unknown_fields(operation, {"type", "content", "target"})

    if "type" not in operation:
        raise McpError(
            "MISSING_OPERATION_TYPE",
            "Operation type is required.",
            {"fields": ["type"]},
        )

    if "content" not in operation:
        raise McpError(
            "MISSING_CONTENT",
            "Operation content is required.",
            {"fields": ["content"]},
        )

    op_type = operation["type"]
    if not isinstance(op_type, str):
        raise McpError(
            "INVALID_TYPE",
            "Operation type must be a string.",
            {"type": type(op_type).__name__},
        )

    op_content = operation["content"]
    if not isinstance(op_content, str):
        raise McpError(
            "INVALID_TYPE",
            "Operation content must be a string.",
            {"type": type(op_content).__name__},
        )

    target = operation.get("target")
    if target is not None and not isinstance(target, str):
        raise McpError(
            "INVALID_TYPE",
            "Operation target must be a string.",
            {"type": type(target).__name__},
        )

    return op_type, op_content, target


def _apply_section_operation(
    content: str, op_type: str, target: str, op_content: str
) -> str:
    lines = content.splitlines(keepends=True)
    start, end = _find_section_bounds(lines, target)

    if op_type == "replace_section":
        replacement = op_content.splitlines(keepends=True)
        return "".join(lines[:start] + replacement + lines[end:])

    if op_type == "insert_before":
        insert_lines = op_content.splitlines(keepends=True)
        return "".join(lines[:start] + insert_lines + lines[start:])

    insert_lines = op_content.splitlines(keepends=True)
    return "".join(lines[:end] + insert_lines + lines[end:])


def _find_section_bounds(lines: list[str], target: str) -> tuple[int, int]:
    target_line = target.strip()
    if not target_line:
        raise McpError(
            "INVALID_TARGET",
            "Target must be a non-empty heading.",
            {"target": target},
        )

    target_level = _heading_level(target_line)
    if target_level is None:
        raise McpError(
            "INVALID_TARGET",
            "Target must be a markdown heading.",
            {"target": target},
        )

    for index, line in enumerate(lines):
        if line.strip() != target_line:
            continue
        level = _heading_level(line.strip())
        if level is None:
            continue
        for next_index in range(index + 1, len(lines)):
            next_level = _heading_level(lines[next_index].rstrip("\r\n"))
            if next_level is not None and next_level <= level:
                return index, next_index
        return index, len(lines)

    raise McpError(
        "SECTION_NOT_FOUND",
        "Target section not found.",
        {"target": target},
    )


def _heading_level(line: str) -> int | None:
    stripped = line.lstrip()
    if not stripped.startswith("#"):
        return None
    return len(stripped) - len(stripped.lstrip("#"))


def _build_unified_diff(
    before: str, after: str, relative_path: str
) -> tuple[str, int, int]:
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    diff_lines = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=relative_path,
            tofile=relative_path,
            lineterm="",
        )
    )
    added, removed = _count_diff_changes(diff_lines)
    return "\n".join(diff_lines), added, removed


def _count_diff_changes(diff_lines: list[str]) -> tuple[int, int]:
    added = 0
    removed = 0
    for line in diff_lines:
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed


def _format_preview_summary(
    op_type: str, target: str | None, added: int, removed: int
) -> str:
    base = op_type
    if target:
        base = f"{op_type} ({target})"
    if added == 0 and removed == 0:
        return base
    return f"{base}: +{added} -{removed} lines"


def _assess_risk_level(added: int, removed: int) -> str:
    change_count = added + removed
    if change_count <= 5:
        return "low"
    if change_count <= 20:
        return "medium"
    return "high"


def _format_activity_summary(operation: str, payload: Any | None) -> str:
    if operation in {"write_markdown", "edit_markdown"}:
        op_type, _content, target = _validate_operation_payload(payload)
        if target:
            return f"{op_type} ({target})"
        return op_type
    if operation == "delete_markdown":
        return "delete file"
    return operation
