"""Task-related MCP endpoints."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Request

from app.errors import McpError, success_response
from app.mcp_activity import _append_activity_log, _build_activity_entry
from app.mcp_git import (
    _commit_markdown_change,
    _commit_markdown_changes,
    _ensure_git_repo,
    _read_head_state,
    _rollback_markdown_change,
)
from app.mcp_payload import _ensure_payload_dict, _reject_unknown_fields
from app.mcp_router import mcp_router
from app.mcp_utils import _atomic_write, _join_with_newline
from app.user_scope import get_request_library_root

TASK_LINE_PATTERN = re.compile(
    r"^- \[(?P<status>[ xX])\] T-(?P<id>\d+)\s*\|\s*(?P<rest>.*)$"
)


@mcp_router.post("/tool:list_tasks")
def list_tasks(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """List tasks from pulse/index.md and optionally completed tasks."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(
        payload, {"owner", "priority", "tag", "status", "project"}
    )

    owner = payload.get("owner")
    priority = payload.get("priority")
    tag = payload.get("tag")
    status_filter = payload.get("status", "open")
    project = payload.get("project")

    library_root = get_request_library_root(request)
    tasks = _load_tasks(library_root, status_filter)
    filtered = _filter_tasks(tasks, owner, priority, tag, project)
    return success_response({"tasks": filtered})


@mcp_router.post("/tool:create_task")
def create_task(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Create a task in pulse/index.md with an auto-incremented ID."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(
        payload, {"title", "owner", "priority", "tags", "project", "due"}
    )

    if "title" not in payload:
        raise McpError(
            "MISSING_TITLE",
            "title is required.",
            {"fields": ["title"]},
        )

    library_root = get_request_library_root(request)
    task = _build_task_from_payload(payload, _next_task_id(library_root))
    index_path = library_root / "pulse" / "index.md"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    existing = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    updated = _join_with_newline(existing, _format_task_line(task))

    repo = _ensure_git_repo(library_root)
    head_ref_path, previous_head = _read_head_state(library_root)
    _atomic_write(index_path, updated)
    relative_path = index_path.relative_to(library_root)
    try:
        commit_sha = _commit_markdown_change(
            repo, relative_path, "create_task"
        )
    except Exception as exc:
        _rollback_markdown_change(
            repo, index_path, relative_path, existing
        )
        raise McpError(
            "GIT_ERROR",
            "Git commit failed; mutation rolled back.",
            {"path": "pulse/index.md", "operation": "create_task"},
        ) from exc
    entry = _build_activity_entry(
        "create_task", relative_path, "create task", commit_sha
    )
    _append_activity_log(library_root, entry)

    return success_response({"task": task, "commitSha": commit_sha})


@mcp_router.post("/tool:update_task")
def update_task(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Update a task by ID in pulse/index.md."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"id", "fields"})

    if "id" not in payload or "fields" not in payload:
        raise McpError(
            "MISSING_FIELDS",
            "id and fields are required.",
            {"fields": ["id", "fields"]},
        )

    task_id = payload["id"]
    fields = payload["fields"]
    if not isinstance(task_id, int):
        raise McpError(
            "INVALID_TYPE",
            "id must be an integer.",
            {"id": str(task_id)},
        )
    if not isinstance(fields, dict):
        raise McpError(
            "INVALID_TYPE",
            "fields must be an object.",
            {"fields": str(fields)},
        )

    library_root = get_request_library_root(request)
    index_path = library_root / "pulse" / "index.md"
    if not index_path.exists():
        raise McpError(
            "FILE_NOT_FOUND",
            "Task index does not exist.",
            {"path": "pulse/index.md"},
        )

    tasks, lines = _parse_tasks(index_path.read_text(encoding="utf-8"))
    updated = False
    for task in tasks:
        if task.get("id") == task_id:
            _apply_task_updates(task, fields)
            line_index = _find_task_line_index(lines, task_id)
            if line_index is not None:
                lines[line_index] = _format_task_line(task)
            updated = True
            break

    if not updated:
        raise McpError(
            "TASK_NOT_FOUND",
            "Task ID not found.",
            {"id": task_id},
        )

    repo = _ensure_git_repo(library_root)
    head_ref_path, previous_head = _read_head_state(library_root)
    original = index_path.read_text(encoding="utf-8")
    _atomic_write(index_path, "\n".join(lines).rstrip() + "\n")
    relative_path = index_path.relative_to(library_root)
    try:
        commit_sha = _commit_markdown_change(
            repo, relative_path, "update_task"
        )
    except Exception as exc:
        _rollback_markdown_change(repo, index_path, relative_path, original)
        raise McpError(
            "GIT_ERROR",
            "Git commit failed; mutation rolled back.",
            {"path": "pulse/index.md", "operation": "update_task"},
        ) from exc
    entry = _build_activity_entry(
        "update_task", relative_path, "update task", commit_sha
    )
    _append_activity_log(library_root, entry)
    return success_response({"task": task, "commitSha": commit_sha})


@mcp_router.post("/tool:complete_task")
def complete_task(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Complete a task by ID and move it to the completed log."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"id"})

    if "id" not in payload:
        raise McpError(
            "MISSING_ID",
            "id is required.",
            {"fields": ["id"]},
        )

    task_id = payload["id"]
    if not isinstance(task_id, int):
        raise McpError(
            "INVALID_TYPE",
            "id must be an integer.",
            {"id": str(task_id)},
        )

    library_root = get_request_library_root(request)
    index_path = library_root / "pulse" / "index.md"
    if not index_path.exists():
        raise McpError(
            "FILE_NOT_FOUND",
            "Task index does not exist.",
            {"path": "pulse/index.md"},
        )

    tasks, lines = _parse_tasks(index_path.read_text(encoding="utf-8"))
    task = _pop_task(tasks, lines, task_id)
    if task is None:
        raise McpError(
            "TASK_NOT_FOUND",
            "Task ID not found.",
            {"id": task_id},
        )

    task["status"] = "x"
    completed_path = _completed_tasks_path(library_root)
    completed_path.parent.mkdir(parents=True, exist_ok=True)
    completed_content = (
        completed_path.read_text(encoding="utf-8")
        if completed_path.exists()
        else ""
    )
    updated_completed = _join_with_newline(
        completed_content, _format_task_line(task)
    )

    repo = _ensure_git_repo(library_root)
    head_ref_path, previous_head = _read_head_state(library_root)
    original_index = index_path.read_text(encoding="utf-8")
    _atomic_write(index_path, "\n".join(lines).rstrip() + "\n")
    _atomic_write(completed_path, updated_completed)
    relative_paths = [
        index_path.relative_to(library_root),
        completed_path.relative_to(library_root),
    ]
    try:
        commit_sha = _commit_markdown_changes(
            repo, relative_paths, "complete_task", completed_path.relative_to(library_root)
        )
    except Exception as exc:
        _rollback_markdown_change(
            repo, index_path, index_path.relative_to(library_root), original_index
        )
        raise McpError(
            "GIT_ERROR",
            "Git commit failed; mutation rolled back.",
            {"path": "pulse/index.md", "operation": "complete_task"},
        ) from exc

    entry = _build_activity_entry(
        "complete_task", completed_path.relative_to(library_root), "complete task", commit_sha
    )
    _append_activity_log(library_root, entry)
    return success_response({"task": task, "commitSha": commit_sha})


@mcp_router.post("/tool:reopen_task")
def reopen_task(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Reopen a completed task by ID."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"id"})

    if "id" not in payload:
        raise McpError(
            "MISSING_ID",
            "id is required.",
            {"fields": ["id"]},
        )

    task_id = payload["id"]
    if not isinstance(task_id, int):
        raise McpError(
            "INVALID_TYPE",
            "id must be an integer.",
            {"id": str(task_id)},
        )

    library_root = get_request_library_root(request)
    completed_path = _completed_tasks_path(library_root)
    if not completed_path.exists():
        raise McpError(
            "FILE_NOT_FOUND",
            "Completed tasks file does not exist.",
            {"path": completed_path.relative_to(library_root).as_posix()},
        )

    tasks, lines = _parse_tasks(completed_path.read_text(encoding="utf-8"))
    task = _pop_task(tasks, lines, task_id)
    if task is None:
        raise McpError(
            "TASK_NOT_FOUND",
            "Task ID not found.",
            {"id": task_id},
        )

    task["status"] = " "
    index_path = library_root / "pulse" / "index.md"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_content = (
        index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    )
    updated_index = _join_with_newline(index_content, _format_task_line(task))

    repo = _ensure_git_repo(library_root)
    head_ref_path, previous_head = _read_head_state(library_root)
    original_completed = completed_path.read_text(encoding="utf-8")
    _atomic_write(completed_path, "\n".join(lines).rstrip() + "\n")
    _atomic_write(index_path, updated_index)
    relative_paths = [
        completed_path.relative_to(library_root),
        index_path.relative_to(library_root),
    ]
    try:
        commit_sha = _commit_markdown_changes(
            repo, relative_paths, "reopen_task", index_path.relative_to(library_root)
        )
    except Exception as exc:
        _rollback_markdown_change(
            repo, completed_path, completed_path.relative_to(library_root), original_completed
        )
        raise McpError(
            "GIT_ERROR",
            "Git commit failed; mutation rolled back.",
            {"path": "pulse/completed", "operation": "reopen_task"},
        ) from exc

    entry = _build_activity_entry(
        "reopen_task", index_path.relative_to(library_root), "reopen task", commit_sha
    )
    _append_activity_log(library_root, entry)
    return success_response({"task": task, "commitSha": commit_sha})


def _parse_tasks(content: str) -> tuple[list[dict[str, Any]], list[str]]:
    tasks: list[dict[str, Any]] = []
    lines: list[str] = []
    for line in content.splitlines():
        match = TASK_LINE_PATTERN.match(line.strip())
        if not match:
            lines.append(line)
            continue
        status = match.group("status")
        task_id = int(match.group("id"))
        rest = match.group("rest")
        parts = [part.strip() for part in rest.split("|") if part.strip()]
        task = {
            "id": task_id,
            "status": "x" if status.lower() == "x" else " ",
            "title": "",
            "priority": None,
            "owner": None,
            "tags": [],
            "project": None,
            "due": None,
            "raw": line,
        }
        title_parts: list[str] = []
        for part in parts:
            if part.startswith("p") and len(part) <= 3:
                task["priority"] = part
                continue
            if part.startswith("owner:"):
                task["owner"] = part.split(":", 1)[1].strip()
                continue
            if part.startswith("tags:"):
                tags_value = part.split(":", 1)[1].strip()
                task["tags"] = [tag.strip() for tag in tags_value.split(",") if tag.strip()]
                continue
            if part.startswith("project:"):
                task["project"] = part.split(":", 1)[1].strip()
                continue
            if part.startswith("due:"):
                task["due"] = part.split(":", 1)[1].strip()
                continue
            title_parts.append(part)
        task["title"] = " | ".join(title_parts).strip()
        tasks.append(task)
        lines.append(line)
    return tasks, lines


def _load_tasks(library_root: Path, status_filter: str) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    if status_filter in {"open", "all"}:
        index_path = library_root / "pulse" / "index.md"
        if index_path.exists():
            parsed, _lines = _parse_tasks(index_path.read_text(encoding="utf-8"))
            tasks.extend(parsed)
    if status_filter in {"completed", "all"}:
        completed_root = library_root / "pulse" / "completed"
        if completed_root.exists():
            for path in completed_root.glob("*.md"):
                parsed, _lines = _parse_tasks(path.read_text(encoding="utf-8"))
                tasks.extend(parsed)
    return tasks


def _load_completed_tasks(
    library_root: Path, since: datetime | None
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    completed_root = library_root / "pulse" / "completed"
    if not completed_root.exists():
        return tasks
    completed_files = sorted(
        completed_root.glob("*.md"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in completed_files:
        if since is not None:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if mtime < since:
                continue
        parsed, _lines = _parse_tasks(path.read_text(encoding="utf-8"))
        for task in parsed:
            task["sourcePath"] = path.relative_to(library_root).as_posix()
        tasks.extend(parsed)
    return tasks


def _next_task_id(library_root: Path) -> int:
    tasks = _load_tasks(library_root, "all")
    if not tasks:
        return 1
    return max(task["id"] for task in tasks) + 1


def _filter_tasks(
    tasks: list[dict[str, Any]],
    owner: str | None,
    priority: str | None,
    tag: str | None,
    project: str | None,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for task in tasks:
        if owner and task.get("owner") != owner:
            continue
        if priority and task.get("priority") != priority:
            continue
        if tag and tag not in task.get("tags", []):
            continue
        if project and task.get("project") != project:
            continue
        filtered.append(task)
    return filtered


def _build_task_from_payload(payload: dict[str, Any], task_id: int) -> dict[str, Any]:
    tags = payload.get("tags", [])
    if tags is None:
        tags = []
    if not isinstance(tags, list):
        tags = []
    return {
        "id": task_id,
        "status": " ",
        "title": payload["title"],
        "priority": payload.get("priority") or "p2",
        "owner": payload.get("owner"),
        "tags": tags,
        "project": payload.get("project"),
        "due": payload.get("due"),
    }


def _format_task_line(task: dict[str, Any]) -> str:
    parts: list[str] = []
    priority = task.get("priority")
    if priority:
        parts.append(priority)
    owner = task.get("owner")
    if owner:
        parts.append(f"owner:{owner}")
    tags = task.get("tags") or []
    if tags:
        parts.append(f"tags:{','.join(tags)}")
    project = task.get("project")
    if project:
        parts.append(f"project:{project}")
    due = task.get("due")
    if due:
        parts.append(f"due:{due}")
    title = task.get("title", "")
    parts.append(title)
    meta = " | ".join(parts)
    status = task.get("status", " ")
    return f"- [{status}] T-{task['id']:03d} | {meta}".rstrip()


def _apply_task_updates(task: dict[str, Any], fields: dict[str, Any]) -> None:
    for key in ["title", "priority", "owner", "project", "due"]:
        if key in fields:
            task[key] = fields[key]
    if "tags" in fields and isinstance(fields["tags"], list):
        task["tags"] = fields["tags"]
    if "status" in fields:
        status = fields["status"]
        if isinstance(status, str) and status.lower() in {"open", "completed"}:
            task["status"] = " " if status.lower() == "open" else "x"


def _completed_tasks_path(library_root: Path) -> Path:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return library_root / "pulse" / "completed" / f"{month}.md"


def _pop_task(
    tasks: list[dict[str, Any]], lines: list[str], task_id: int
) -> dict[str, Any] | None:
    for idx, task in enumerate(tasks):
        if task.get("id") == task_id:
            line_index = _find_task_line_index(lines, task_id)
            if line_index is not None:
                lines.pop(line_index)
            return task
    return None


def _find_task_line_index(lines: list[str], task_id: int) -> int | None:
    pattern = f"T-{task_id:03d}"
    for idx, line in enumerate(lines):
        if pattern in line:
            return idx
    return None
