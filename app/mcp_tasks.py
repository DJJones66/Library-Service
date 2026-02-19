"""Task-related MCP endpoints."""

from __future__ import annotations

import re
from collections import Counter
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
        payload, {"owner", "priority", "tag", "status", "project", "scope", "path"}
    )

    owner = payload.get("owner")
    priority = payload.get("priority")
    tag = payload.get("tag")
    status_filter = payload.get("status", "open")
    project = payload.get("scope") or payload.get("path") or payload.get("project")

    library_root = get_request_library_root(request)
    tasks = _load_tasks(library_root, status_filter)
    filtered = _filter_tasks(tasks, owner, priority, tag, project, library_root)
    return success_response({"tasks": filtered})


@mcp_router.post("/tool:create_task")
def create_task(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Create a task in pulse/index.md with an auto-incremented ID."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(
        payload, {"title", "owner", "priority", "tags", "project", "scope", "path", "due"}
    )

    if "title" not in payload:
        raise McpError(
            "MISSING_TITLE",
            "title is required.",
            {"fields": ["title"]},
        )

    library_root = get_request_library_root(request)
    scope_lookup = _build_scope_lookup(library_root)
    default_scope_path = _infer_default_scope_for_new_task(library_root, scope_lookup)
    task = _build_task_from_payload(
        payload,
        _next_task_id(library_root),
        scope_lookup,
        default_scope_path,
    )
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
    scope_lookup = _build_scope_lookup(library_root)
    _enrich_tasks_scope(tasks, scope_lookup)
    _apply_dominant_scope(tasks, scope_lookup)
    updated = False
    for task in tasks:
        if task.get("id") == task_id:
            _apply_task_updates(task, fields)
            _enrich_task_scope(task, scope_lookup)
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
    scope_lookup = _build_scope_lookup(library_root)
    _enrich_tasks_scope(tasks, scope_lookup)
    _apply_dominant_scope(tasks, scope_lookup)
    task = _pop_task(tasks, lines, task_id)
    if task is None:
        raise McpError(
            "TASK_NOT_FOUND",
            "Task ID not found.",
            {"id": task_id},
        )

    task["status"] = "x"
    _enrich_task_scope(task, scope_lookup)
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
    scope_lookup = _build_scope_lookup(library_root)
    _enrich_tasks_scope(tasks, scope_lookup)
    _apply_dominant_scope(tasks, scope_lookup)
    task = _pop_task(tasks, lines, task_id)
    if task is None:
        raise McpError(
            "TASK_NOT_FOUND",
            "Task ID not found.",
            {"id": task_id},
        )

    task["status"] = " "
    _enrich_task_scope(task, scope_lookup)
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
            "scopePath": None,
            "scopeRoot": None,
            "scopeType": None,
            "scopeName": None,
            "raw": line,
        }

        title_parts: list[str] = []
        for part in parts:
            part_lower = part.lower()
            if part_lower in {"p0", "p1", "p2", "p3", "high", "medium", "low"}:
                task["priority"] = part_lower
                continue
            if part_lower.startswith("owner:"):
                task["owner"] = part.split(":", 1)[1].strip()
                continue
            if part_lower.startswith("tags:"):
                tags_value = part.split(":", 1)[1].strip()
                task["tags"] = [
                    tag.strip() for tag in tags_value.split(",") if tag.strip()
                ]
                continue
            if part_lower.startswith("scope:") or part_lower.startswith("path:"):
                task["scopePath"] = part.split(":", 1)[1].strip()
                continue
            if part_lower.startswith("life:"):
                task["scopePath"] = f"life/{part.split(':', 1)[1].strip()}"
                continue
            if part_lower.startswith("project:"):
                task["project"] = part.split(":", 1)[1].strip()
                continue
            if part_lower.startswith("due:"):
                task["due"] = part.split(":", 1)[1].strip()
                continue
            title_parts.append(part)

        task["title"] = " | ".join(title_parts).strip()
        tasks.append(task)
        lines.append(line)

    return tasks, lines


def _normalize_scope_key(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip().replace("\\", "/")
    if not normalized:
        return None

    if ":" in normalized and "/" not in normalized:
        normalized = normalized.split(":", 1)[1]
    normalized = normalized.strip("/")
    if not normalized:
        return None

    tail = normalized.split("/")[-1].strip()
    if not tail:
        return None

    tail = re.sub(r"[\s_]+", "-", tail.lower())
    tail = re.sub(r"-{2,}", "-", tail).strip("-")
    return tail or None


def _normalize_scope_path(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip().replace("\\", "/")
    if not normalized:
        return None

    normalized = re.sub(r"/{2,}", "/", normalized)
    lowered = normalized.lower()
    if lowered.startswith("scope:") or lowered.startswith("path:"):
        return _normalize_scope_path(normalized.split(":", 1)[1])
    if lowered.startswith("life:"):
        return _normalize_scope_path(f"life/{normalized.split(':', 1)[1]}")
    if lowered.startswith("project:") or lowered.startswith("projects:"):
        return _normalize_scope_path(
            f"projects/active/{normalized.split(':', 1)[1]}"
        )

    normalized = normalized.strip("/")
    if not normalized:
        return None

    parts = [part.strip() for part in normalized.split("/") if part.strip()]
    if not parts:
        return None

    head = parts[0].lower()
    if head == "life":
        if len(parts) < 2:
            return None
        return f"life/{parts[1].lower()}"

    if head == "project":
        if len(parts) < 2:
            return None
        return f"projects/active/{parts[1].lower()}"

    if head == "projects":
        if len(parts) < 2:
            return None
        if parts[1].lower() == "active":
            if len(parts) < 3:
                return None
            return f"projects/active/{parts[2].lower()}"
        return f"projects/{parts[1].lower()}"

    return None


def _scope_parts(scope_path: str | None) -> tuple[str | None, str | None]:
    normalized = _normalize_scope_path(scope_path)
    if not normalized:
        return None, None

    parts = normalized.split("/")
    if parts[0] == "life" and len(parts) >= 2:
        return "life", parts[1]
    if parts[0] == "projects":
        if len(parts) >= 3 and parts[1] == "active":
            return "projects", parts[2]
        if len(parts) >= 2:
            return "projects", parts[1]
    return None, None


def _build_scope_lookup(library_root: Path) -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {"life": {}, "projects": {}}

    life_root = library_root / "life"
    if life_root.exists():
        for entry in sorted(life_root.iterdir(), key=lambda path: path.name.lower()):
            if entry.is_symlink() or not entry.is_dir():
                continue
            key = _normalize_scope_key(entry.name)
            scope_path = _normalize_scope_path(f"life/{entry.name}")
            if key and scope_path:
                lookup["life"].setdefault(key, scope_path)

    for base in ("projects/active", "projects"):
        projects_root = library_root / base
        if not projects_root.exists():
            continue
        for entry in sorted(projects_root.iterdir(), key=lambda path: path.name.lower()):
            if entry.is_symlink() or not entry.is_dir():
                continue
            if base == "projects" and entry.name.lower() == "active":
                continue
            key = _normalize_scope_key(entry.name)
            scope_path = _normalize_scope_path(f"{base}/{entry.name}")
            if key and scope_path:
                lookup["projects"].setdefault(key, scope_path)

    return lookup


def _resolve_scope_path(
    value: str | None,
    lookup: dict[str, dict[str, str]],
) -> str | None:
    if not isinstance(value, str):
        return None

    raw_value = value.strip()
    if not raw_value:
        return None

    lowered = raw_value.lower()
    preference: str | None = None
    if lowered.startswith("life:") or lowered.startswith("life/"):
        preference = "life"
    elif lowered.startswith("project:") or lowered.startswith("project/"):
        preference = "projects"
    elif lowered.startswith("projects:") or lowered.startswith("projects/"):
        preference = "projects"

    normalized_path = _normalize_scope_path(raw_value)
    if normalized_path:
        scope_root, scope_name = _scope_parts(normalized_path)
        scope_key = _normalize_scope_key(scope_name)
        if scope_root == "life" and scope_key:
            life_path = lookup["life"].get(scope_key)
            project_path = lookup["projects"].get(scope_key)
            if life_path:
                return life_path
            if project_path:
                return project_path
            return normalized_path
        if scope_root == "projects" and scope_key:
            project_path = lookup["projects"].get(scope_key)
            life_path = lookup["life"].get(scope_key)
            if project_path:
                return project_path
            if life_path:
                return life_path
            return normalized_path
        return normalized_path

    scope_key = _normalize_scope_key(raw_value)
    if not scope_key:
        return None

    life_path = lookup["life"].get(scope_key)
    project_path = lookup["projects"].get(scope_key)
    if preference == "life" and life_path:
        return life_path
    if preference == "projects" and project_path:
        return project_path
    if life_path:
        return life_path
    if project_path:
        return project_path
    return None


def _task_tag_keys(task: dict[str, Any]) -> set[str]:
    tag_keys: set[str] = set()
    for tag in task.get("tags") or []:
        if not isinstance(tag, str):
            continue
        key = _normalize_scope_key(tag)
        if key:
            tag_keys.add(key)
    return tag_keys


def _enrich_task_scope(
    task: dict[str, Any],
    lookup: dict[str, dict[str, str]],
) -> None:
    scope_path = _resolve_scope_path(task.get("scopePath"), lookup)
    if not scope_path:
        scope_path = _resolve_scope_path(task.get("path"), lookup)
    if not scope_path:
        scope_path = _resolve_scope_path(task.get("scope"), lookup)
    if not scope_path:
        scope_path = _resolve_scope_path(task.get("project"), lookup)

    if not scope_path:
        from_tags: set[str] = set()
        for tag_key in _task_tag_keys(task):
            if tag_key in lookup["life"]:
                from_tags.add(lookup["life"][tag_key])
            if tag_key in lookup["projects"]:
                from_tags.add(lookup["projects"][tag_key])
        if len(from_tags) == 1:
            scope_path = next(iter(from_tags))

    task["scopePath"] = scope_path
    if not scope_path:
        task["scopeRoot"] = None
        task["scopeType"] = None
        task["scopeName"] = None
        return

    scope_root, scope_name = _scope_parts(scope_path)
    task["scopeRoot"] = scope_root
    task["scopeType"] = "life" if scope_root == "life" else "project"
    task["scopeName"] = scope_name

    existing_project = task.get("project")
    if (
        not isinstance(existing_project, str)
        or not existing_project.strip()
        or "/" in existing_project
        or ":" in existing_project
    ):
        task["project"] = scope_name


def _enrich_tasks_scope(
    tasks: list[dict[str, Any]],
    lookup: dict[str, dict[str, str]],
) -> None:
    for task in tasks:
        _enrich_task_scope(task, lookup)


def _apply_dominant_scope(
    tasks: list[dict[str, Any]],
    lookup: dict[str, dict[str, str]] | None = None,
) -> None:
    scoped_paths = [
        task.get("scopePath")
        for task in tasks
        if isinstance(task.get("scopePath"), str) and task.get("scopePath")
    ]
    if not scoped_paths:
        return

    path_counts = Counter(scoped_paths)
    if len(path_counts) != 1:
        return

    dominant_scope = next(iter(path_counts))
    _, dominant_name = _scope_parts(dominant_scope)
    dominant_name_key = _normalize_scope_key(dominant_name)
    known_scope_keys: set[str] = set()
    if lookup is not None:
        known_scope_keys.update(lookup["life"].keys())
        known_scope_keys.update(lookup["projects"].keys())

    for task in tasks:
        if task.get("scopePath"):
            continue

        project_key = _normalize_scope_key(task.get("project"))
        if project_key and dominant_name_key and project_key != dominant_name_key:
            continue

        tag_keys = _task_tag_keys(task)
        if tag_keys and dominant_name_key not in tag_keys:
            if known_scope_keys and any(
                key in known_scope_keys and key != dominant_name_key for key in tag_keys
            ):
                continue
            if not known_scope_keys:
                continue

        task["scopePath"] = dominant_scope
        scope_root, scope_name = _scope_parts(dominant_scope)
        task["scopeRoot"] = scope_root
        task["scopeType"] = "life" if scope_root == "life" else "project"
        task["scopeName"] = scope_name
        if not task.get("project"):
            task["project"] = scope_name


def _infer_default_scope_for_new_task(
    library_root: Path,
    lookup: dict[str, dict[str, str]],
) -> str | None:
    index_path = library_root / "pulse" / "index.md"
    if not index_path.exists():
        return None

    tasks, _lines = _parse_tasks(index_path.read_text(encoding="utf-8"))
    _enrich_tasks_scope(tasks, lookup)
    _apply_dominant_scope(tasks, lookup)
    scoped_paths = {
        task.get("scopePath")
        for task in tasks
        if isinstance(task.get("scopePath"), str) and task.get("scopePath")
    }
    if len(scoped_paths) == 1:
        return next(iter(scoped_paths))
    return None


def _scope_paths_equivalent(left: str | None, right: str | None) -> bool:
    left_normalized = _normalize_scope_path(left)
    right_normalized = _normalize_scope_path(right)
    if left_normalized and right_normalized and left_normalized == right_normalized:
        return True

    left_root, left_name = _scope_parts(left_normalized or left)
    right_root, right_name = _scope_parts(right_normalized or right)
    if not left_root or not right_root:
        return False
    if left_root != right_root:
        return False
    return _normalize_scope_key(left_name) == _normalize_scope_key(right_name)


def _task_matches_project(
    task: dict[str, Any],
    project: str,
    lookup: dict[str, dict[str, str]],
) -> bool:
    requested_scope = _resolve_scope_path(project, lookup)
    requested_root, requested_name = _scope_parts(requested_scope)
    requested_name_key = _normalize_scope_key(requested_name) or _normalize_scope_key(
        project
    )

    project_value = project.strip().lower()
    explicit_scope = (
        "/" in project_value
        or project_value.startswith("life:")
        or project_value.startswith("project:")
        or project_value.startswith("projects:")
        or project_value.startswith("scope:")
        or project_value.startswith("path:")
    )
    ambiguous_name = bool(
        requested_name_key
        and requested_name_key in lookup["life"]
        and requested_name_key in lookup["projects"]
        and not explicit_scope
    )

    task_scope = task.get("scopePath")
    task_scope_root, task_scope_name = _scope_parts(task_scope)
    task_scope_name_key = _normalize_scope_key(task_scope_name) or _normalize_scope_key(
        task.get("scopeName")
    )
    task_project_key = _normalize_scope_key(task.get("project"))
    tag_keys = _task_tag_keys(task)

    if requested_scope and task_scope:
        if _scope_paths_equivalent(task_scope, requested_scope):
            return True
        if not ambiguous_name:
            return False

    if requested_name_key and (
        task_scope_name_key == requested_name_key
        or task_project_key == requested_name_key
        or requested_name_key in tag_keys
    ):
        if requested_root and task_scope_root and requested_root != task_scope_root:
            return ambiguous_name
        return True

    return False


def _load_tasks(library_root: Path, status_filter: str) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    scope_lookup = _build_scope_lookup(library_root)

    if status_filter in {"open", "all"}:
        index_path = library_root / "pulse" / "index.md"
        if index_path.exists():
            parsed, _lines = _parse_tasks(index_path.read_text(encoding="utf-8"))
            _enrich_tasks_scope(parsed, scope_lookup)
            _apply_dominant_scope(parsed, scope_lookup)
            for task in parsed:
                task["sourcePath"] = "pulse/index.md"
            tasks.extend(parsed)

    if status_filter in {"completed", "all"}:
        completed_root = library_root / "pulse" / "completed"
        if completed_root.exists():
            for path in completed_root.glob("*.md"):
                parsed, _lines = _parse_tasks(path.read_text(encoding="utf-8"))
                _enrich_tasks_scope(parsed, scope_lookup)
                _apply_dominant_scope(parsed, scope_lookup)
                source_path = path.relative_to(library_root).as_posix()
                for task in parsed:
                    task["sourcePath"] = source_path
                tasks.extend(parsed)

        # Compatibility: legacy archives stored completed tasks in pulse/archive.md.
        archive_path = library_root / "pulse" / "archive.md"
        if archive_path.exists():
            parsed, _lines = _parse_tasks(archive_path.read_text(encoding="utf-8"))
            _enrich_tasks_scope(parsed, scope_lookup)
            _apply_dominant_scope(parsed, scope_lookup)
            for task in parsed:
                task.setdefault("sourcePath", "pulse/archive.md")
            tasks.extend(parsed)

    return tasks


def _load_completed_tasks(
    library_root: Path,
    since: datetime | None,
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    scope_lookup = _build_scope_lookup(library_root)
    if since is not None:
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        else:
            since = since.astimezone(timezone.utc)

    completed_root = library_root / "pulse" / "completed"
    if completed_root.exists():
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
            _enrich_tasks_scope(parsed, scope_lookup)
            _apply_dominant_scope(parsed, scope_lookup)
            source_path = path.relative_to(library_root).as_posix()
            for task in parsed:
                task["sourcePath"] = source_path
            tasks.extend(parsed)

    archive_path = library_root / "pulse" / "archive.md"
    if archive_path.exists() and since is None:
        parsed, _lines = _parse_tasks(archive_path.read_text(encoding="utf-8"))
        _enrich_tasks_scope(parsed, scope_lookup)
        _apply_dominant_scope(parsed, scope_lookup)
        for task in parsed:
            task["sourcePath"] = "pulse/archive.md"
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
    library_root: Path | None = None,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    scope_lookup = (
        _build_scope_lookup(library_root)
        if library_root is not None
        else {"life": {}, "projects": {}}
    )

    for task in tasks:
        if owner and task.get("owner") != owner:
            continue
        if priority and task.get("priority") != priority:
            continue
        if tag and tag not in task.get("tags", []):
            continue
        if project:
            _enrich_task_scope(task, scope_lookup)
            if not _task_matches_project(task, project, scope_lookup):
                continue
        filtered.append(task)

    return filtered


def _build_task_from_payload(
    payload: dict[str, Any],
    task_id: int,
    scope_lookup: dict[str, dict[str, str]],
    default_scope_path: str | None,
) -> dict[str, Any]:
    raw_tags = payload.get("tags", [])
    tags: list[str] = []
    if isinstance(raw_tags, list):
        for item in raw_tags:
            if isinstance(item, str) and item.strip():
                tags.append(item.strip())

    scope_value = payload.get("scope") or payload.get("path")
    project_value = payload.get("project")
    if (
        scope_value is None
        and isinstance(project_value, str)
        and (
            "/" in project_value
            or project_value.lower().startswith("life:")
            or project_value.lower().startswith("project:")
            or project_value.lower().startswith("projects:")
        )
    ):
        scope_value = project_value

    task = {
        "id": task_id,
        "status": " ",
        "title": payload["title"],
        "priority": payload.get("priority") or "p2",
        "owner": payload.get("owner"),
        "tags": tags,
        "project": project_value,
        "due": payload.get("due"),
        "scopePath": scope_value,
        "scopeRoot": None,
        "scopeType": None,
        "scopeName": None,
    }

    _enrich_task_scope(task, scope_lookup)
    if not task.get("scopePath") and default_scope_path:
        task["scopePath"] = default_scope_path
        _enrich_task_scope(task, scope_lookup)

    return task


def _format_task_line(task: dict[str, Any]) -> str:
    parts: list[str] = []
    priority = task.get("priority")
    if priority:
        parts.append(str(priority))

    owner = task.get("owner")
    if owner:
        parts.append(f"owner:{owner}")

    tags = task.get("tags") or []
    if tags:
        parts.append(f"tags:{','.join(str(tag) for tag in tags)}")

    scope_path = _normalize_scope_path(task.get("scopePath"))
    if scope_path:
        parts.append(f"scope:{scope_path}")

    project = task.get("project")
    if not project and scope_path:
        _, scope_name = _scope_parts(scope_path)
        project = scope_name
    if project:
        parts.append(f"project:{project}")

    due = task.get("due")
    if due:
        parts.append(f"due:{due}")

    title = task.get("title", "")
    parts.append(str(title))
    meta = " | ".join(parts)
    status = task.get("status", " ")
    return f"- [{status}] T-{task['id']:03d} | {meta}".rstrip()


def _apply_task_updates(task: dict[str, Any], fields: dict[str, Any]) -> None:
    for key in ["title", "priority", "owner", "project", "due", "scopePath"]:
        if key in fields:
            task[key] = fields[key]
    if "scope" in fields:
        task["scopePath"] = fields["scope"]
    if "path" in fields:
        task["scopePath"] = fields["path"]
    if "tags" in fields and isinstance(fields["tags"], list):
        task["tags"] = [tag for tag in fields["tags"] if isinstance(tag, str)]
    if "status" in fields:
        status = fields["status"]
        if isinstance(status, str) and status.lower() in {"open", "completed"}:
            task["status"] = " " if status.lower() == "open" else "x"


def _completed_tasks_path(library_root: Path) -> Path:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return library_root / "pulse" / "completed" / f"{month}.md"


def _pop_task(
    tasks: list[dict[str, Any]],
    lines: list[str],
    task_id: int,
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
