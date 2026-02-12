"""Request-scoped user identity and library root helpers."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import Request

from app.errors import McpError

USER_ID_HEADER = "X-BrainDrive-User-Id"
REQUEST_ID_HEADER = "X-BrainDrive-Request-Id"
SERVICE_TOKEN_HEADER = "X-BrainDrive-Service-Token"
AUTH_EXEMPT_PATHS = {"/health"}

_VALID_USER_ID = re.compile(r"^[A-Za-z0-9_]{3,128}$")


def normalize_user_id(raw_user_id: str) -> str:
    """Normalize and validate a user id from request context."""
    if not isinstance(raw_user_id, str):
        raise McpError(
            "INVALID_USER_ID",
            "User id must be a string.",
            {"type": type(raw_user_id).__name__},
        )

    normalized = raw_user_id.strip().replace("-", "")
    if not normalized:
        raise McpError(
            "AUTH_REQUIRED",
            "Missing required user identity header.",
            {"header": USER_ID_HEADER},
        )

    if not _VALID_USER_ID.fullmatch(normalized):
        raise McpError(
            "INVALID_USER_ID",
            "User id contains invalid characters.",
            {"user_id": raw_user_id},
        )
    return normalized


def resolve_user_library_root(base_root: Path, user_id: str) -> Path:
    """Resolve the scoped user library root path."""
    normalized_user_id = normalize_user_id(user_id)
    return base_root / "users" / normalized_user_id


def get_request_user_id(request: Request) -> str:
    """Read and cache normalized user id from request state/headers."""
    cached = getattr(request.state, "user_id", None)
    if isinstance(cached, str) and cached.strip():
        normalized = normalize_user_id(cached)
        request.state.user_id = normalized
        return normalized

    raw_user_id = request.headers.get(USER_ID_HEADER)
    if raw_user_id is None:
        raise McpError(
            "AUTH_REQUIRED",
            "Missing required user identity header.",
            {"header": USER_ID_HEADER},
        )

    normalized = normalize_user_id(raw_user_id)
    request.state.user_id = normalized
    return normalized


def get_request_library_root(request: Request) -> Path:
    """Resolve and create the user-scoped library root for a request."""
    config = getattr(request.app.state, "config", None)
    if config is not None and hasattr(config, "library_path"):
        base_root = Path(config.library_path)
    else:
        base_root = Path(request.app.state.library_path)

    user_id = get_request_user_id(request)
    scoped_root = resolve_user_library_root(base_root, user_id)
    scoped_root.mkdir(parents=True, exist_ok=True)
    return scoped_root

