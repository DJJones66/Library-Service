"""Markdown-related MCP endpoints."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Request

from app.errors import McpError, success_response
from app.mcp_activity import _append_activity_log, _build_activity_entry
from app.mcp_constants import ALLOWED_MARKDOWN_EXTENSIONS
from app.mcp_git import (
    _commit_markdown_change,
    _ensure_git_repo,
    _read_head_state,
    _resolve_git_head,
    _restore_git_head,
    _rollback_created_file,
    _rollback_markdown_change,
)
from app.mcp_operations import (
    _apply_edit_operation,
    _apply_preview_operation,
    _apply_write_operation,
    _assess_risk_level,
    _build_unified_diff,
    _format_activity_summary,
    _format_preview_summary,
    _validate_operation_payload,
)
from app.mcp_payload import _ensure_payload_dict, _reject_unknown_fields
from app.mcp_router import mcp_router
from app.mcp_utils import _atomic_write
from app.paths import validate_path
from app.user_scope import get_request_library_root


@mcp_router.post("/tool:read_markdown")
def read_markdown(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Read markdown content and metadata from the library root."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"path"})

    if "path" not in payload:
        raise McpError(
            "MISSING_PATH",
            "Path is required.",
            {"fields": ["path"]},
        )

    raw_path = payload["path"]
    library_root = get_request_library_root(request)
    resolved_path = validate_path(library_root, raw_path)

    if resolved_path.suffix.lower() not in ALLOWED_MARKDOWN_EXTENSIONS:
        raise McpError(
            "NOT_MARKDOWN",
            "Only markdown files are allowed.",
            {"path": raw_path},
        )

    if not resolved_path.exists():
        raise McpError(
            "FILE_NOT_FOUND",
            "Markdown file does not exist.",
            {"path": raw_path},
        )

    if not resolved_path.is_file():
        raise McpError(
            "INVALID_PATH",
            "Path must reference a file.",
            {"path": raw_path},
        )

    try:
        content = resolved_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise McpError(
            "INVALID_ENCODING",
            "Markdown file must be UTF-8 encoded.",
            {"path": raw_path},
        ) from exc

    metadata = _build_metadata(library_root, resolved_path)
    return success_response({"content": content, "metadata": metadata})


@mcp_router.post("/tool:list_markdown_files")
def list_markdown_files(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """List markdown files recursively from a directory within the library root."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"path"})

    if "path" not in payload:
        raise McpError(
            "MISSING_PATH",
            "Path is required.",
            {"fields": ["path"]},
        )

    raw_path = payload["path"]
    library_root = get_request_library_root(request)
    resolved_path = validate_path(library_root, raw_path)

    if not resolved_path.exists():
        raise McpError(
            "FILE_NOT_FOUND",
            "Path does not exist.",
            {"path": raw_path},
        )

    if not resolved_path.is_dir():
        raise McpError(
            "INVALID_PATH",
            "Path must reference a directory.",
            {"path": raw_path},
        )

    files = _collect_markdown_files(library_root, resolved_path)
    return success_response({"files": files})


@mcp_router.post("/tool:search_markdown")
def search_markdown(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Search for a substring within markdown files and return matching snippets."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"query", "path"})

    if "query" not in payload:
        raise McpError(
            "MISSING_QUERY",
            "Query is required.",
            {"fields": ["query"]},
        )

    query = payload["query"]
    if not isinstance(query, str):
        raise McpError(
            "INVALID_TYPE",
            "Query must be a string.",
            {"query": str(query), "type": type(query).__name__},
        )

    if not query.strip():
        raise McpError(
            "INVALID_QUERY",
            "Query must be a non-empty string.",
            {"query": query},
        )

    library_root = get_request_library_root(request)
    search_files: list[Path] = []
    search_root = library_root

    if "path" in payload:
        raw_path = payload["path"]
        resolved_path = validate_path(library_root, raw_path)

        if not resolved_path.exists():
            raise McpError(
                "FILE_NOT_FOUND",
                "Path does not exist.",
                {"path": raw_path},
            )

        if resolved_path.is_file():
            if resolved_path.suffix.lower() not in ALLOWED_MARKDOWN_EXTENSIONS:
                raise McpError(
                    "NOT_MARKDOWN",
                    "Only markdown files are allowed.",
                    {"path": raw_path},
                )
            search_files = [resolved_path]
        elif resolved_path.is_dir():
            search_root = resolved_path
        else:
            raise McpError(
                "INVALID_PATH",
                "Path must reference a file or directory.",
                {"path": raw_path},
            )

    if not search_files:
        relative_files = _collect_markdown_files(library_root, search_root)
        search_files = [library_root / relative for relative in relative_files]

    results = _search_markdown_files(library_root, search_files, query)
    return success_response({"results": results})


@mcp_router.post("/tool:create_markdown")
def create_markdown(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Create a new markdown file with the provided content."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"path", "content"})

    if "path" not in payload:
        raise McpError(
            "MISSING_PATH",
            "Path is required.",
            {"fields": ["path"]},
        )
    if "content" not in payload:
        raise McpError(
            "MISSING_CONTENT",
            "Content is required.",
            {"fields": ["content"]},
        )

    raw_path = payload["path"]
    content = payload["content"]
    if not isinstance(content, str):
        raise McpError(
            "INVALID_TYPE",
            "Content must be a string.",
            {"content": str(content), "type": type(content).__name__},
        )

    library_root = get_request_library_root(request)
    resolved_path = validate_path(library_root, raw_path)

    if resolved_path.suffix.lower() not in ALLOWED_MARKDOWN_EXTENSIONS:
        raise McpError(
            "NOT_MARKDOWN",
            "Only markdown files are allowed.",
            {"path": raw_path},
        )

    if resolved_path.exists():
        raise McpError(
            "PATH_EXISTS",
            "Path already exists.",
            {"path": raw_path},
        )

    if resolved_path.parent.exists() and not resolved_path.parent.is_dir():
        raise McpError(
            "INVALID_PATH",
            "Parent path must be a directory.",
            {"path": raw_path},
        )

    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    repo = _ensure_git_repo(library_root)
    head_ref_path, previous_head = _read_head_state(library_root)
    relative_path = resolved_path.relative_to(library_root)
    summary = "create file"
    _atomic_write(resolved_path, content)

    try:
        commit_sha = _commit_markdown_change(
            repo, relative_path, "create_markdown"
        )
    except Exception as exc:
        _rollback_created_file(repo, resolved_path, relative_path)
        raise McpError(
            "GIT_ERROR",
            "Git commit failed; mutation rolled back.",
            {"path": raw_path, "operation": "create_markdown"},
        ) from exc

    try:
        entry = _build_activity_entry(
            "create_markdown", relative_path, summary, commit_sha
        )
        _append_activity_log(library_root, entry)
    except Exception as exc:
        _rollback_created_file(repo, resolved_path, relative_path)
        _restore_git_head(library_root, head_ref_path, previous_head)
        raise McpError(
            "LOG_ERROR",
            "Activity log write failed; mutation rolled back.",
            {"path": raw_path, "operation": "create_markdown"},
        ) from exc

    return success_response({"success": True, "commitSha": commit_sha})


@mcp_router.post("/tool:preview_markdown_change")
def preview_markdown_change(
    payload: dict[str, Any], request: Request
) -> dict[str, Any]:
    """Preview a markdown edit by returning a unified diff without writing."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"path", "operation"})

    if "path" not in payload:
        raise McpError(
            "MISSING_PATH",
            "Path is required.",
            {"fields": ["path"]},
        )

    if "operation" not in payload:
        raise McpError(
            "MISSING_OPERATION",
            "Operation is required.",
            {"fields": ["operation"]},
        )

    _validate_operation_payload(payload["operation"])

    raw_path = payload["path"]
    library_root = get_request_library_root(request)
    resolved_path = validate_path(library_root, raw_path)

    if resolved_path.suffix.lower() not in ALLOWED_MARKDOWN_EXTENSIONS:
        raise McpError(
            "NOT_MARKDOWN",
            "Only markdown files are allowed.",
            {"path": raw_path},
        )

    if not resolved_path.exists():
        raise McpError(
            "FILE_NOT_FOUND",
            "Markdown file does not exist.",
            {"path": raw_path},
        )

    if not resolved_path.is_file():
        raise McpError(
            "INVALID_PATH",
            "Path must reference a file.",
            {"path": raw_path},
        )

    try:
        current_content = resolved_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise McpError(
            "INVALID_ENCODING",
            "Markdown file must be UTF-8 encoded.",
            {"path": raw_path},
        ) from exc

    updated_content, op_type, target = _apply_preview_operation(
        current_content, payload["operation"]
    )
    relative_path = resolved_path.relative_to(library_root).as_posix()
    diff, added, removed = _build_unified_diff(
        current_content, updated_content, relative_path
    )
    summary = _format_preview_summary(op_type, target, added, removed)
    risk_level = _assess_risk_level(added, removed)

    return success_response(
        {"diff": diff, "summary": summary, "riskLevel": risk_level}
    )


@mcp_router.post("/tool:preview_bulk_changes")
def preview_bulk_changes(
    payload: dict[str, Any], request: Request
) -> dict[str, Any]:
    """Preview multiple markdown changes in a single request."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"changes"})

    if "changes" not in payload:
        raise McpError(
            "MISSING_CHANGES",
            "changes is required.",
            {"fields": ["changes"]},
        )

    changes = payload["changes"]
    if not isinstance(changes, list):
        raise McpError(
            "INVALID_TYPE",
            "changes must be a list.",
            {"changes": str(changes)},
        )

    library_root = get_request_library_root(request)
    results: list[dict[str, Any]] = []
    total_added = 0
    total_removed = 0
    for change in changes:
        if not isinstance(change, dict):
            raise McpError(
                "INVALID_TYPE",
                "Each change must be an object.",
                {"change": str(change)},
            )
        _reject_unknown_fields(
            change, {"path", "action", "operation", "content"}
        )
        if "path" not in change or "action" not in change:
            raise McpError(
                "MISSING_FIELDS",
                "Each change requires path and action.",
                {"fields": ["path", "action"]},
            )

        raw_path = change["path"]
        action = change["action"]
        if not isinstance(action, str):
            raise McpError(
                "INVALID_TYPE",
                "action must be a string.",
                {"action": str(action)},
            )
        action = action.lower()
        if action not in {"create", "write", "edit", "delete"}:
            raise McpError(
                "INVALID_ACTION",
                "action must be one of create/write/edit/delete.",
                {"action": action},
            )

        resolved_path = validate_path(library_root, raw_path)
        if resolved_path.suffix.lower() not in ALLOWED_MARKDOWN_EXTENSIONS:
            raise McpError(
                "NOT_MARKDOWN",
                "Only markdown files are allowed.",
                {"path": raw_path},
            )

        current_content = ""
        if resolved_path.exists():
            if not resolved_path.is_file():
                raise McpError(
                    "INVALID_PATH",
                    "Path must reference a file.",
                    {"path": raw_path},
                )
            try:
                current_content = resolved_path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise McpError(
                    "INVALID_ENCODING",
                    "Markdown file must be UTF-8 encoded.",
                    {"path": raw_path},
                ) from exc

        updated_content = current_content
        summary = ""
        target = None
        if action == "create":
            if resolved_path.exists():
                raise McpError(
                    "PATH_EXISTS",
                    "Path already exists.",
                    {"path": raw_path},
                )
            content = change.get("content")
            if not isinstance(content, str):
                raise McpError(
                    "MISSING_CONTENT",
                    "content is required for create.",
                    {"path": raw_path},
                )
            updated_content = content
            summary = "create file"
        elif action == "delete":
            if not resolved_path.exists():
                raise McpError(
                    "FILE_NOT_FOUND",
                    "Markdown file does not exist.",
                    {"path": raw_path},
                )
            updated_content = ""
            summary = "delete file"
        elif action == "write":
            if not resolved_path.exists():
                raise McpError(
                    "FILE_NOT_FOUND",
                    "Markdown file does not exist.",
                    {"path": raw_path},
                )
            if "operation" not in change:
                raise McpError(
                    "MISSING_OPERATION",
                    "operation is required for write.",
                    {"path": raw_path},
                )
            updated_content = _apply_write_operation(
                current_content, change["operation"]
            )
            op_type, _content, target = _validate_operation_payload(
                change["operation"]
            )
            summary = _format_preview_summary(op_type, target, 0, 0)
        elif action == "edit":
            if not resolved_path.exists():
                raise McpError(
                    "FILE_NOT_FOUND",
                    "Markdown file does not exist.",
                    {"path": raw_path},
                )
            if "operation" not in change:
                raise McpError(
                    "MISSING_OPERATION",
                    "operation is required for edit.",
                    {"path": raw_path},
                )
            updated_content = _apply_edit_operation(
                current_content, change["operation"]
            )
            op_type, _content, target = _validate_operation_payload(
                change["operation"]
            )
            summary = _format_preview_summary(op_type, target, 0, 0)

        relative_path = resolved_path.relative_to(library_root).as_posix()
        diff, added, removed = _build_unified_diff(
            current_content, updated_content, relative_path
        )
        total_added += added
        total_removed += removed
        risk_level = _assess_risk_level(added, removed)
        results.append(
            {
                "path": relative_path,
                "action": action,
                "summary": summary,
                "diff": diff,
                "riskLevel": risk_level,
                "added": added,
                "removed": removed,
            }
        )

    overall_risk = _assess_risk_level(total_added, total_removed)
    return success_response(
        {
            "changes": results,
            "summary": {
                "added": total_added,
                "removed": total_removed,
                "riskLevel": overall_risk,
            },
        }
    )


@mcp_router.post("/tool:write_markdown")
def write_markdown(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Apply an append/prepend operation to a markdown file atomically."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"path", "operation"})

    if "path" not in payload:
        raise McpError(
            "MISSING_PATH",
            "Path is required.",
            {"fields": ["path"]},
        )

    if "operation" not in payload:
        raise McpError(
            "MISSING_OPERATION",
            "Operation is required.",
            {"fields": ["operation"]},
        )

    _validate_operation_payload(payload["operation"])

    raw_path = payload["path"]
    library_root = get_request_library_root(request)
    resolved_path = validate_path(library_root, raw_path)

    if resolved_path.suffix.lower() not in ALLOWED_MARKDOWN_EXTENSIONS:
        raise McpError(
            "NOT_MARKDOWN",
            "Only markdown files are allowed.",
            {"path": raw_path},
        )

    if not resolved_path.exists():
        raise McpError(
            "FILE_NOT_FOUND",
            "Markdown file does not exist.",
            {"path": raw_path},
        )

    if not resolved_path.is_file():
        raise McpError(
            "INVALID_PATH",
            "Path must reference a file.",
            {"path": raw_path},
        )

    try:
        current_content = resolved_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise McpError(
            "INVALID_ENCODING",
            "Markdown file must be UTF-8 encoded.",
            {"path": raw_path},
        ) from exc

    updated_content = _apply_write_operation(
        current_content, payload["operation"]
    )
    repo = _ensure_git_repo(library_root)
    head_ref_path, previous_head = _read_head_state(library_root)
    relative_path = resolved_path.relative_to(library_root)
    summary = _format_activity_summary(
        "write_markdown", payload["operation"]
    )
    _atomic_write(resolved_path, updated_content)

    try:
        commit_sha = _commit_markdown_change(
            repo, relative_path, "write_markdown"
        )
    except Exception as exc:
        _rollback_markdown_change(
            repo, resolved_path, relative_path, current_content
        )
        raise McpError(
            "GIT_ERROR",
            "Git commit failed; mutation rolled back.",
            {"path": raw_path, "operation": "write_markdown"},
        ) from exc

    try:
        entry = _build_activity_entry(
            "write_markdown", relative_path, summary, commit_sha
        )
        _append_activity_log(library_root, entry)
    except Exception as exc:
        _rollback_markdown_change(
            repo, resolved_path, relative_path, current_content
        )
        _restore_git_head(library_root, head_ref_path, previous_head)
        raise McpError(
            "LOG_ERROR",
            "Activity log write failed; mutation rolled back.",
            {"path": raw_path, "operation": "write_markdown"},
        ) from exc

    return success_response({"success": True, "commitSha": commit_sha})


@mcp_router.post("/tool:edit_markdown")
def edit_markdown(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Apply a section-aware operation to a markdown file atomically."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"path", "operation"})

    if "path" not in payload:
        raise McpError(
            "MISSING_PATH",
            "Path is required.",
            {"fields": ["path"]},
        )

    if "operation" not in payload:
        raise McpError(
            "MISSING_OPERATION",
            "Operation is required.",
            {"fields": ["operation"]},
        )

    _validate_operation_payload(payload["operation"])

    raw_path = payload["path"]
    library_root = get_request_library_root(request)
    resolved_path = validate_path(library_root, raw_path)

    if resolved_path.suffix.lower() not in ALLOWED_MARKDOWN_EXTENSIONS:
        raise McpError(
            "NOT_MARKDOWN",
            "Only markdown files are allowed.",
            {"path": raw_path},
        )

    if not resolved_path.exists():
        raise McpError(
            "FILE_NOT_FOUND",
            "Markdown file does not exist.",
            {"path": raw_path},
        )

    if not resolved_path.is_file():
        raise McpError(
            "INVALID_PATH",
            "Path must reference a file.",
            {"path": raw_path},
        )

    try:
        current_content = resolved_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise McpError(
            "INVALID_ENCODING",
            "Markdown file must be UTF-8 encoded.",
            {"path": raw_path},
        ) from exc

    updated_content = _apply_edit_operation(
        current_content, payload["operation"]
    )
    repo = _ensure_git_repo(library_root)
    head_ref_path, previous_head = _read_head_state(library_root)
    relative_path = resolved_path.relative_to(library_root)
    summary = _format_activity_summary(
        "edit_markdown", payload["operation"]
    )
    _atomic_write(resolved_path, updated_content)

    try:
        commit_sha = _commit_markdown_change(
            repo, relative_path, "edit_markdown"
        )
    except Exception as exc:
        _rollback_markdown_change(
            repo, resolved_path, relative_path, current_content
        )
        raise McpError(
            "GIT_ERROR",
            "Git commit failed; mutation rolled back.",
            {"path": raw_path, "operation": "edit_markdown"},
        ) from exc

    try:
        entry = _build_activity_entry(
            "edit_markdown", relative_path, summary, commit_sha
        )
        _append_activity_log(library_root, entry)
    except Exception as exc:
        _rollback_markdown_change(
            repo, resolved_path, relative_path, current_content
        )
        _restore_git_head(library_root, head_ref_path, previous_head)
        raise McpError(
            "LOG_ERROR",
            "Activity log write failed; mutation rolled back.",
            {"path": raw_path, "operation": "edit_markdown"},
        ) from exc

    return success_response({"success": True, "commitSha": commit_sha})


@mcp_router.post("/tool:delete_markdown")
def delete_markdown(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Delete a markdown file only when explicit confirmation is provided."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"path", "confirm"})

    if "path" not in payload:
        raise McpError(
            "MISSING_PATH",
            "Path is required.",
            {"fields": ["path"]},
        )

    raw_path = payload["path"]
    library_root = get_request_library_root(request)
    resolved_path = validate_path(library_root, raw_path)

    confirm = payload.get("confirm", False)
    if not isinstance(confirm, bool):
        raise McpError(
            "INVALID_TYPE",
            "Confirm must be a boolean.",
            {"confirm": str(confirm), "type": type(confirm).__name__},
        )

    if not confirm:
        raise McpError(
            "CONFIRM_REQUIRED",
            "Deletion requires explicit confirmation.",
            {"path": raw_path},
        )

    if resolved_path.suffix.lower() not in ALLOWED_MARKDOWN_EXTENSIONS:
        raise McpError(
            "NOT_MARKDOWN",
            "Only markdown files are allowed.",
            {"path": raw_path},
        )

    if not resolved_path.exists():
        raise McpError(
            "FILE_NOT_FOUND",
            "Markdown file does not exist.",
            {"path": raw_path},
        )

    if not resolved_path.is_file():
        raise McpError(
            "INVALID_PATH",
            "Path must reference a file.",
            {"path": raw_path},
        )

    try:
        original_bytes = resolved_path.read_bytes()
    except OSError as exc:
        raise McpError(
            "FILE_READ_FAILED",
            "Markdown file could not be read.",
            {"path": raw_path},
        ) from exc

    repo = _ensure_git_repo(library_root)
    head_ref_path, previous_head = _read_head_state(library_root)
    relative_path = resolved_path.relative_to(library_root)
    summary = _format_activity_summary("delete_markdown", None)
    resolved_path.unlink()

    try:
        commit_sha = _commit_markdown_change(
            repo, relative_path, "delete_markdown"
        )
    except Exception as exc:
        _rollback_markdown_change(
            repo, resolved_path, relative_path, original_bytes
        )
        raise McpError(
            "GIT_ERROR",
            "Git commit failed; mutation rolled back.",
            {"path": raw_path, "operation": "delete_markdown"},
        ) from exc

    try:
        entry = _build_activity_entry(
            "delete_markdown", relative_path, summary, commit_sha
        )
        _append_activity_log(library_root, entry)
    except Exception as exc:
        _rollback_markdown_change(
            repo, resolved_path, relative_path, original_bytes
        )
        _restore_git_head(library_root, head_ref_path, previous_head)
        raise McpError(
            "LOG_ERROR",
            "Activity log write failed; mutation rolled back.",
            {"path": raw_path, "operation": "delete_markdown"},
        ) from exc

    return success_response({"success": True, "commitSha": commit_sha})


def _build_metadata(library_root: Path, file_path: Path) -> dict[str, Any]:
    stat = file_path.stat()
    relative_path = file_path.relative_to(library_root).as_posix()
    last_modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

    return {
        "path": relative_path,
        "sizeBytes": stat.st_size,
        "lastModified": last_modified.isoformat(),
        "gitHead": _resolve_git_head(library_root),
    }


def _collect_markdown_files(library_root: Path, start_path: Path) -> list[str]:
    files: list[str] = []
    for root, dirnames, filenames in os.walk(start_path, followlinks=False):
        dir_path = Path(root)
        dirnames[:] = sorted(
            [name for name in dirnames if not (dir_path / name).is_symlink()]
        )

        for filename in sorted(filenames):
            file_path = dir_path / filename
            if file_path.is_symlink():
                continue
            if file_path.suffix.lower() not in ALLOWED_MARKDOWN_EXTENSIONS:
                continue
            files.append(file_path.relative_to(library_root).as_posix())

    return sorted(files)


def _search_markdown_files(
    library_root: Path, file_paths: list[Path], query: str
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for file_path in file_paths:
        relative_path = file_path.relative_to(library_root).as_posix()
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise McpError(
                "INVALID_ENCODING",
                "Markdown file must be UTF-8 encoded.",
                {"path": relative_path},
            ) from exc

        matches: list[dict[str, Any]] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            if query in line:
                matches.append({"line": line_number, "snippet": line})
        if matches:
            results.append({"path": relative_path, "matches": matches})
    return results
