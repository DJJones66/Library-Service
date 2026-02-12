"""Transcript ingestion endpoint."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import Request

from app.errors import McpError, success_response
from app.mcp_activity import _append_activity_log, _build_activity_entry
from app.mcp_git import (
    _commit_markdown_changes,
    _ensure_git_repo,
    _read_head_state,
    _restore_git_head,
)
from app.mcp_payload import _ensure_payload_dict, _reject_unknown_fields
from app.mcp_router import mcp_router
from app.mcp_utils import _atomic_write, _join_with_newline
from app.user_scope import get_request_library_root


@mcp_router.post("/tool:ingest_transcript")
def ingest_transcript(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Store a transcript and update the transcripts index."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(
        payload, {"content", "filename", "date", "project", "source"}
    )

    if "content" not in payload:
        raise McpError(
            "MISSING_CONTENT",
            "content is required.",
            {"fields": ["content"]},
        )

    content = payload["content"]
    if not isinstance(content, str):
        raise McpError(
            "INVALID_TYPE",
            "content must be a string.",
            {"content": str(content)},
        )

    library_root = get_request_library_root(request)
    date_value = payload.get("date") or datetime.now(timezone.utc).date().isoformat()
    try:
        parsed_date = datetime.fromisoformat(date_value)
    except ValueError:
        raise McpError(
            "INVALID_DATE",
            "date must be ISO format (YYYY-MM-DD).",
            {"date": date_value},
        )
    folder = parsed_date.strftime("%Y-%m")
    filename = payload.get("filename") or f"transcript-{parsed_date.strftime('%Y%m%d-%H%M%S')}.md"
    if not isinstance(filename, str):
        raise McpError(
            "INVALID_TYPE",
            "filename must be a string.",
            {"filename": str(filename)},
        )

    transcript_dir = library_root / "transcripts" / folder
    transcript_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = transcript_dir / filename
    _atomic_write(transcript_path, content)

    index_path = library_root / "transcripts" / "index.md"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_content = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    project = payload.get("project")
    source = payload.get("source")
    entry_parts = [date_value, transcript_path.relative_to(library_root).as_posix()]
    if project:
        entry_parts.append(f"project:{project}")
    if source:
        entry_parts.append(f"source:{source}")
    index_line = " - ".join(entry_parts)
    updated_index = _join_with_newline(index_content, index_line)

    repo = _ensure_git_repo(library_root)
    head_ref_path, previous_head = _read_head_state(library_root)
    relative_paths = [
        transcript_path.relative_to(library_root),
        index_path.relative_to(library_root),
    ]
    _atomic_write(index_path, updated_index)
    try:
        commit_sha = _commit_markdown_changes(
            repo, relative_paths, "ingest_transcript", transcript_path.relative_to(library_root)
        )
    except Exception as exc:
        _restore_git_head(library_root, head_ref_path, previous_head)
        raise McpError(
            "GIT_ERROR",
            "Git commit failed; mutation rolled back.",
            {"path": transcript_path.relative_to(library_root).as_posix(), "operation": "ingest_transcript"},
        ) from exc

    entry = _build_activity_entry(
        "ingest_transcript",
        transcript_path.relative_to(library_root),
        "ingest transcript",
        commit_sha,
    )
    _append_activity_log(library_root, entry)

    return success_response({"success": True, "commitSha": commit_sha, "path": transcript_path.relative_to(library_root).as_posix()})
