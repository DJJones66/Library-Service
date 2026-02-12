"""Structured error types for MCP responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ErrorResponse:
    """Serializable error payload returned by MCP handlers."""

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


class McpError(RuntimeError):
    """Exception carrying a structured error response."""

    def __init__(
        self, code: str, message: str, details: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.error = ErrorResponse(
            code=code, message=message, details=dict(details or {})
        )


def success_response(payload: dict[str, Any]) -> dict[str, Any]:
    """Wrap a successful MCP response in the standard envelope."""
    return {"ok": True, "data": payload}


def error_response(error: ErrorResponse) -> dict[str, Any]:
    """Wrap an error response in the standard envelope."""
    return {"ok": False, "error": error.to_dict()}
