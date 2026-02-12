"""Activity log helpers and endpoints."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Request

from app.errors import McpError, success_response
from app.mcp_constants import ACTIVITY_LOG_FILENAME
from app.mcp_payload import _ensure_payload_dict, _reject_unknown_fields
from app.mcp_router import mcp_router
from app.user_scope import get_request_library_root


def _activity_log_path(library_root: Path) -> Path:
    return library_root / ACTIVITY_LOG_FILENAME


def _append_activity_log(library_root: Path, entry: dict[str, str]) -> None:
    log_path = _activity_log_path(library_root)
    payload = json.dumps(entry, sort_keys=True, separators=(",", ":"))
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(payload + "\n")
        log_file.flush()
        os.fsync(log_file.fileno())


def _build_activity_entry(
    operation: str,
    relative_path: Path,
    summary: str,
    commit_sha: str,
) -> dict[str, str]:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "operation": operation,
        "path": relative_path.as_posix(),
        "summary": summary,
        "commitSha": commit_sha,
    }


def _read_activity_entries(
    library_root: Path, since: datetime | None, limit: int
) -> list[dict[str, Any]]:
    log_path = _activity_log_path(library_root)
    if not log_path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if since:
            timestamp = entry.get("timestamp")
            try:
                entry_time = datetime.fromisoformat(timestamp)
            except (TypeError, ValueError):
                entry_time = None
            if entry_time and entry_time < since:
                continue
        entries.append(entry)
    return entries[-limit:]


@mcp_router.post("/tool:read_activity_log")
def read_activity_log(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Read entries from the activity log."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"limit", "since"})

    limit = payload.get("limit", 50)
    if not isinstance(limit, int) or limit <= 0:
        raise McpError(
            "INVALID_TYPE",
            "limit must be a positive integer.",
            {"limit": str(limit)},
        )

    since_value = payload.get("since")
    since = None
    if since_value is not None:
        try:
            since = datetime.fromisoformat(str(since_value))
        except ValueError:
            raise McpError(
                "INVALID_DATE",
                "since must be ISO date-time.",
                {"since": since_value},
            )

    library_root = get_request_library_root(request)
    entries = _read_activity_entries(library_root, since, limit)
    return success_response({"entries": entries})
