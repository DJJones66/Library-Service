"""Payload validation helpers for MCP endpoints."""

from __future__ import annotations

from typing import Any

from app.errors import McpError


def _ensure_payload_dict(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise McpError(
            "INVALID_TYPE",
            "Payload must be an object.",
            {"type": type(payload).__name__},
        )
    return payload


def _reject_unknown_fields(payload: dict[str, Any], allowed_fields: set[str]) -> None:
    unknown_fields = sorted(set(payload) - allowed_fields)
    if unknown_fields:
        raise McpError(
            "UNKNOWN_FIELD",
            "Unknown fields are not allowed.",
            {"fields": unknown_fields},
        )
