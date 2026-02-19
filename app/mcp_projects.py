"""Project-related MCP endpoints."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import Request

from app.errors import McpError, success_response
from app.mcp_activity import _append_activity_log, _build_activity_entry
from app.mcp_constants import ALLOWED_MARKDOWN_EXTENSIONS, DEFAULT_PROJECT_FILES
from app.mcp_git import (
    _commit_markdown_changes,
    _ensure_git_repo,
    _read_head_state,
    _restore_git_head,
    _rollback_created_project,
)
from app.mcp_markdown import _build_metadata
from app.mcp_payload import _ensure_payload_dict, _reject_unknown_fields
from app.mcp_router import mcp_router
from app.mcp_utils import _atomic_write
from app.paths import validate_path
from app.user_scope import get_request_library_root


def _normalize_scope_path(raw_path: str) -> str:
    return str(raw_path or "").strip().replace("\\", "/").strip("/")


def _scope_slug(raw_path: str) -> str:
    normalized = _normalize_scope_path(raw_path)
    parts = [part for part in normalized.split("/") if part]
    if not parts:
        return "scope"
    if parts[0] == "life" and len(parts) >= 2:
        return parts[1]
    if parts[0] == "projects" and len(parts) >= 3 and parts[1] in {"active", "archived"}:
        return parts[2]
    if parts[0] == "projects" and len(parts) >= 2:
        return parts[1]
    return parts[-1]


def _scope_title(raw_path: str) -> str:
    slug = _scope_slug(raw_path)
    title = re.sub(r"[-_]+", " ", slug).strip()
    if not title:
        return "Scope"
    return " ".join(token.capitalize() for token in title.split())


def _scope_default_files(raw_path: str) -> dict[str, str]:
    normalized = _normalize_scope_path(raw_path)
    title = _scope_title(normalized)

    if normalized.startswith("life/"):
        lowered = title.lower()
        return {
            "AGENT.md": f"# {title} Agent\n\nUse this folder for {lowered} planning and execution.\n",
            "interview.md": (
                f"# {title} Interview\n\n"
                f"## Seed Questions\n"
                f"1. What matters most in {lowered} right now?\n"
                "2. What is working and what is not?\n"
                "3. What constraints are blocking progress?\n"
                "4. What would make the next 30 days successful?\n"
            ),
            "spec.md": (
                f"# {title} Spec\n\n"
                "## Current Reality\n\n"
                "## Desired Outcomes\n\n"
                "## Constraints\n\n"
                "## Success Criteria\n"
            ),
            "build-plan.md": (
                f"# {title} Build Plan\n\n"
                "## Phase 1\n\n"
                "## Phase 2\n\n"
                "## Risks\n\n"
                "## Next Review\n"
            ),
            "goals.md": f"# {title} Goals\n\n## Current Goals\n\n",
            "action-plan.md": f"# {title} Action Plan\n\n## Immediate Actions\n\n",
        }

    if normalized == "capture" or normalized.startswith("capture/"):
        return {
            "AGENT.md": "# Capture Agent\n\nCapture raw input in this scope and route intentionally.\n",
        }

    if normalized.startswith("projects/"):
        defaults = dict(DEFAULT_PROJECT_FILES)
        defaults["AGENT.md"] = f"# {title} Agent\n"
        defaults["spec.md"] = f"# {title}\n"
        return defaults

    return {
        "AGENT.md": f"# {title} Agent\n",
        "spec.md": f"# {title} Spec\n",
        "build-plan.md": f"# {title} Build Plan\n",
    }


def _merge_scope_required_files(
    raw_path: str,
    files_payload: list[dict[str, str]],
) -> list[dict[str, str]]:
    defaults = _scope_default_files(raw_path)
    if not files_payload:
        return [
            {"path": filename, "content": content}
            for filename, content in defaults.items()
        ]

    merged = list(files_payload)
    provided_lower = {
        str(entry.get("path", "")).strip().replace("\\", "/").strip("/").lower()
        for entry in files_payload
        if isinstance(entry, dict)
    }
    for filename, content in defaults.items():
        key = filename.lower()
        if key in provided_lower:
            continue
        merged.append({"path": filename, "content": content})
    return merged


def _ensure_scope_scaffold_files(
    library_root: Path,
    scope_path: str,
) -> list[Path]:
    normalized_scope = _normalize_scope_path(scope_path)
    defaults = _scope_default_files(normalized_scope)

    created_files: list[Path] = []
    for filename, content in defaults.items():
        combined = f"{normalized_scope.rstrip('/')}/{filename}"
        target = validate_path(library_root, combined)
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(target, content)
        created_files.append(target)
    return created_files


def _rollback_scaffold_files(
    created_files: list[Path],
    scope_root: Path,
    *,
    remove_root: bool,
) -> None:
    for created_file in created_files:
        try:
            if created_file.exists():
                created_file.unlink()
        except OSError:
            pass

    if not remove_root:
        return

    for path in sorted(scope_root.rglob("*"), reverse=True):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass
    try:
        scope_root.rmdir()
    except OSError:
        pass


@mcp_router.post("/tool:project_exists")
def project_exists(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Check whether a project directory exists."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"path", "name"})

    if "path" not in payload and "name" not in payload:
        raise McpError(
            "MISSING_PATH",
            "Path or name is required.",
            {"fields": ["path", "name"]},
        )

    candidate_paths: list[str]
    if "path" in payload:
        raw_path = payload["path"]
        if not isinstance(raw_path, str):
            raise McpError(
                "INVALID_TYPE",
                "Path must be a string.",
                {"path": str(raw_path), "type": type(raw_path).__name__},
            )
        candidate_paths = [raw_path]
    else:
        name = payload["name"]
        if not isinstance(name, str):
            raise McpError(
                "INVALID_TYPE",
                "Name must be a string.",
                {"name": str(name), "type": type(name).__name__},
            )
        if not name.strip():
            raise McpError(
                "INVALID_NAME",
                "Name must be a non-empty string.",
                {"name": name},
            )
        if "/" in name or "\\" in name:
            raw_path = name
            candidate_paths = [raw_path]
        else:
            candidate_paths = [
                f"projects/active/{name}",
                f"projects/{name}",
            ]

    library_root = get_request_library_root(request)
    checked_paths: list[str] = []
    conflict_paths: list[str] = []
    found_path: str | None = None
    for candidate in candidate_paths:
        resolved_project = validate_path(library_root, candidate)

        if resolved_project.suffix.lower() in ALLOWED_MARKDOWN_EXTENSIONS:
            raise McpError(
                "INVALID_PATH",
                "Project path must be a directory, not a markdown file.",
                {"path": candidate},
            )

        relative_path = resolved_project.relative_to(library_root).as_posix()
        checked_paths.append(relative_path)
        if resolved_project.exists():
            if resolved_project.is_dir():
                found_path = relative_path
                break
            conflict_paths.append(relative_path)

    exists = found_path is not None
    is_dir = exists
    conflict = bool(conflict_paths) and not exists
    relative_path = found_path or checked_paths[0]

    return success_response(
        {
            "path": relative_path,
            "exists": is_dir,
            "isDir": is_dir,
            "conflict": conflict,
            "checkedPaths": checked_paths,
            "conflictPaths": conflict_paths,
        }
    )


@mcp_router.post("/tool:list_projects")
def list_projects(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """List projects under a directory (defaults to projects/active)."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"path"})

    raw_path = payload.get("path")
    if raw_path is not None and not isinstance(raw_path, str):
        raise McpError(
            "INVALID_TYPE",
            "Path must be a string.",
            {"path": str(raw_path), "type": type(raw_path).__name__},
        )

    library_root = get_request_library_root(request)
    candidate_paths = (
        [raw_path] if raw_path else ["projects/active", "projects"]
    )
    resolved_path: Path | None = None
    for candidate in candidate_paths:
        resolved_candidate = validate_path(library_root, candidate)
        if not resolved_candidate.exists():
            continue
        if not resolved_candidate.is_dir():
            raise McpError(
                "INVALID_PATH",
                "Path must reference a directory.",
                {"path": candidate},
            )
        resolved_path = resolved_candidate
        raw_path = candidate
        break

    if resolved_path is None:
        missing_path = candidate_paths[0]
        raise McpError(
            "FILE_NOT_FOUND",
            "Path does not exist.",
            {"path": missing_path},
        )

    projects: list[dict[str, str]] = []
    for entry in sorted(resolved_path.iterdir(), key=lambda item: item.name):
        if entry.is_symlink() or not entry.is_dir():
            continue
        relative = entry.relative_to(library_root).as_posix()
        projects.append({"name": entry.name, "path": relative})

    return success_response({"projects": projects})


@mcp_router.post("/tool:create_project")
def create_project(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Create a project directory with one or more markdown files."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"path", "files", "name"})

    if "path" not in payload and "name" not in payload:
        raise McpError(
            "MISSING_PATH",
            "Path or name is required.",
            {"fields": ["path", "name"]},
        )

    if "path" in payload:
        raw_path = payload["path"]
        if not isinstance(raw_path, str):
            raise McpError(
                "INVALID_TYPE",
                "Path must be a string.",
                {"path": str(raw_path), "type": type(raw_path).__name__},
            )
    else:
        name = payload["name"]
        if not isinstance(name, str):
            raise McpError(
                "INVALID_TYPE",
                "Name must be a string.",
                {"name": str(name), "type": type(name).__name__},
            )
        if not name.strip():
            raise McpError(
                "INVALID_NAME",
                "Name must be a non-empty string.",
                {"name": name},
            )
        if "/" in name or "\\" in name:
            raw_path = name
        else:
            raw_path = f"projects/active/{name}"
    library_root = get_request_library_root(request)
    resolved_project = validate_path(library_root, raw_path)

    if resolved_project.suffix.lower() in ALLOWED_MARKDOWN_EXTENSIONS:
        raise McpError(
            "INVALID_PATH",
            "Project path must be a directory, not a markdown file.",
            {"path": raw_path},
        )

    if resolved_project.exists():
        if resolved_project.is_dir():
            raise McpError(
                "PROJECT_EXISTS",
                "Project already exists.",
                {"path": raw_path},
            )
        raise McpError(
            "INVALID_PATH",
            "Project path conflicts with a non-directory.",
            {"path": raw_path},
        )

    if resolved_project.parent.exists() and not resolved_project.parent.is_dir():
        raise McpError(
            "INVALID_PATH",
            "Project parent path must be a directory.",
            {"path": raw_path},
        )

    files_payload = payload.get("files")
    if files_payload is None:
        files_payload = []

    if not isinstance(files_payload, list):
        raise McpError(
            "INVALID_TYPE",
            "Files must be a list.",
            {"files": str(files_payload), "type": type(files_payload).__name__},
        )

    validated_files: list[dict[str, str]] = []
    provided_paths: set[str] = set()
    for entry in files_payload:
        if not isinstance(entry, dict):
            raise McpError(
                "INVALID_TYPE",
                "File entries must be objects.",
                {"file": str(entry), "type": type(entry).__name__},
            )
        _reject_unknown_fields(entry, {"path", "content"})

        if "path" not in entry:
            raise McpError(
                "MISSING_PATH",
                "File path is required.",
                {"fields": ["path"]},
            )
        if "content" not in entry:
            raise McpError(
                "MISSING_CONTENT",
                "File content is required.",
                {"fields": ["content"]},
            )

        file_path = entry["path"]
        file_content = entry["content"]
        if not isinstance(file_path, str):
            raise McpError(
                "INVALID_TYPE",
                "File path must be a string.",
                {"path": str(file_path), "type": type(file_path).__name__},
            )
        if not isinstance(file_content, str):
            raise McpError(
                "INVALID_TYPE",
                "File content must be a string.",
                {
                    "content": str(file_content),
                    "type": type(file_content).__name__,
                },
            )

        normalized_file_path = file_path.replace("\\", "/").strip("/")
        normalized_key = normalized_file_path.lower()
        if normalized_key in provided_paths:
            raise McpError(
                "DUPLICATE_FILES",
                "Duplicate file paths are not allowed.",
                {"path": normalized_file_path},
            )
        provided_paths.add(normalized_key)

        validated_files.append(
            {
                "path": normalized_file_path,
                "content": file_content,
            }
        )

    merged_files = _merge_scope_required_files(raw_path, validated_files)

    resolved_files: list[tuple[Path, str]] = []
    seen_paths: set[str] = set()
    for entry in merged_files:
        file_path = entry["path"]
        file_content = entry["content"]

        combined = f"{raw_path.rstrip('/')}/{file_path.lstrip('/')}"
        resolved_file = validate_path(library_root, combined)

        if resolved_file.suffix.lower() not in ALLOWED_MARKDOWN_EXTENSIONS:
            raise McpError(
                "NOT_MARKDOWN",
                "Only markdown files are allowed.",
                {"path": combined},
            )

        relative_file = resolved_file.relative_to(library_root).as_posix()
        if relative_file in seen_paths:
            raise McpError(
                "DUPLICATE_FILES",
                "Duplicate file paths are not allowed.",
                {"path": relative_file},
            )
        seen_paths.add(relative_file)

        if resolved_file.exists():
            raise McpError(
                "FILE_EXISTS",
                "Markdown file already exists.",
                {"path": relative_file},
            )

        resolved_files.append((resolved_file, file_content))

    resolved_project.mkdir(parents=True, exist_ok=False)
    created_files: list[Path] = []
    try:
        for resolved_file, file_content in resolved_files:
            resolved_file.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(resolved_file, file_content)
            created_files.append(resolved_file)
    except Exception:
        relative_paths = [
            created_file.relative_to(library_root)
            for created_file in created_files
        ]
        _rollback_created_project(
            None, created_files, resolved_project, relative_paths
        )
        raise

    repo = _ensure_git_repo(library_root)
    head_ref_path, previous_head = _read_head_state(library_root)
    relative_paths = [
        created_file.relative_to(library_root)
        for created_file in created_files
    ]
    project_relative = resolved_project.relative_to(library_root)
    summary = "create project"

    try:
        commit_sha = _commit_markdown_changes(
            repo, relative_paths, "create_project", project_relative
        )
    except Exception as exc:
        _rollback_created_project(
            repo, created_files, resolved_project, relative_paths
        )
        raise McpError(
            "GIT_ERROR",
            "Git commit failed; mutation rolled back.",
            {"path": raw_path, "operation": "create_project"},
        ) from exc

    try:
        entry = _build_activity_entry(
            "create_project", project_relative, summary, commit_sha
        )
        _append_activity_log(library_root, entry)
    except Exception as exc:
        _rollback_created_project(
            repo, created_files, resolved_project, relative_paths
        )
        _restore_git_head(library_root, head_ref_path, previous_head)
        raise McpError(
            "LOG_ERROR",
            "Activity log write failed; mutation rolled back.",
            {"path": raw_path, "operation": "create_project"},
        ) from exc

    created_relative = [
        created_file.relative_to(library_root).as_posix()
        for created_file in created_files
    ]

    return success_response(
        {
            "success": True,
            "commitSha": commit_sha,
            "path": project_relative.as_posix(),
            "createdFiles": created_relative,
        }
    )


@mcp_router.post("/tool:ensure_scope_scaffold")
def ensure_scope_scaffold(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Ensure canonical scaffold files exist for a scope path."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"path", "name"})

    if "path" not in payload and "name" not in payload:
        raise McpError(
            "MISSING_PATH",
            "Path or name is required.",
            {"fields": ["path", "name"]},
        )

    if "path" in payload:
        raw_path = payload["path"]
        if not isinstance(raw_path, str):
            raise McpError(
                "INVALID_TYPE",
                "Path must be a string.",
                {"path": str(raw_path), "type": type(raw_path).__name__},
            )
    else:
        name = payload["name"]
        if not isinstance(name, str):
            raise McpError(
                "INVALID_TYPE",
                "Name must be a string.",
                {"name": str(name), "type": type(name).__name__},
            )
        if not name.strip():
            raise McpError(
                "INVALID_NAME",
                "Name must be a non-empty string.",
                {"name": name},
            )
        if "/" in name or "\\" in name:
            raw_path = name
        else:
            raw_path = f"projects/active/{name}"

    library_root = get_request_library_root(request)
    scope_root = validate_path(library_root, raw_path)

    if scope_root.suffix.lower() in ALLOWED_MARKDOWN_EXTENSIONS:
        raise McpError(
            "INVALID_PATH",
            "Scope path must be a directory, not a markdown file.",
            {"path": raw_path},
        )

    if scope_root.exists() and not scope_root.is_dir():
        raise McpError(
            "INVALID_PATH",
            "Scope path conflicts with a non-directory.",
            {"path": raw_path},
        )

    scope_preexisting = scope_root.exists()
    scope_root.mkdir(parents=True, exist_ok=True)

    created_files: list[Path] = []
    try:
        created_files = _ensure_scope_scaffold_files(
            library_root,
            scope_root.relative_to(library_root).as_posix(),
        )
    except Exception as exc:
        _rollback_scaffold_files(created_files, scope_root, remove_root=not scope_preexisting)
        raise McpError(
            "WRITE_ERROR",
            "Failed to scaffold scope.",
            {"path": raw_path},
        ) from exc

    if not created_files:
        return success_response(
            {
                "success": True,
                "path": scope_root.relative_to(library_root).as_posix(),
                "createdFiles": [],
                "commitSha": None,
            }
        )

    repo = _ensure_git_repo(library_root)
    head_ref_path, previous_head = _read_head_state(library_root)
    relative_paths = [path.relative_to(library_root) for path in created_files]
    scope_relative = scope_root.relative_to(library_root)

    try:
        commit_sha = _commit_markdown_changes(
            repo,
            relative_paths,
            "ensure_scope_scaffold",
            scope_relative,
        )
    except Exception as exc:
        _rollback_scaffold_files(created_files, scope_root, remove_root=not scope_preexisting)
        raise McpError(
            "GIT_ERROR",
            "Git commit failed; mutation rolled back.",
            {"path": raw_path, "operation": "ensure_scope_scaffold"},
        ) from exc

    try:
        entry = _build_activity_entry(
            "ensure_scope_scaffold",
            scope_relative,
            "ensure scope scaffold",
            commit_sha,
        )
        _append_activity_log(library_root, entry)
    except Exception as exc:
        _rollback_scaffold_files(created_files, scope_root, remove_root=not scope_preexisting)
        _restore_git_head(library_root, head_ref_path, previous_head)
        raise McpError(
            "LOG_ERROR",
            "Activity log write failed; mutation rolled back.",
            {"path": raw_path, "operation": "ensure_scope_scaffold"},
        ) from exc

    created_relative = [
        created_file.relative_to(library_root).as_posix()
        for created_file in created_files
    ]

    return success_response(
        {
            "success": True,
            "commitSha": commit_sha,
            "path": scope_relative.as_posix(),
            "createdFiles": created_relative,
        }
    )


@mcp_router.post("/tool:project_context")
def project_context(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Return key project files and metadata in one response."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(
        payload, {"path", "name", "include_files", "include_transcripts"}
    )

    if "path" not in payload and "name" not in payload:
        raise McpError(
            "MISSING_PATH",
            "Path or name is required.",
            {"fields": ["path", "name"]},
        )

    library_root = get_request_library_root(request)
    if "path" in payload:
        raw_path = payload["path"]
        resolved_root = validate_path(library_root, raw_path)
    else:
        name = payload["name"]
        if not isinstance(name, str) or not name.strip():
            raise McpError(
                "INVALID_NAME",
                "Name must be a non-empty string.",
                {"name": name},
            )
        resolved_root = validate_path(
            library_root, f"projects/active/{name}"
        )

    if not resolved_root.exists() or not resolved_root.is_dir():
        raise McpError(
            "FILE_NOT_FOUND",
            "Project path does not exist.",
            {"path": resolved_root.relative_to(library_root).as_posix()},
        )

    include_files = payload.get("include_files")
    if include_files is None:
        include_files = [entry[0] for entry in DEFAULT_PROJECT_FILES]
    if not isinstance(include_files, list):
        raise McpError(
            "INVALID_TYPE",
            "include_files must be a list.",
            {"include_files": str(include_files)},
        )

    files: list[dict[str, Any]] = []
    missing: list[str] = []
    for relative_name in include_files:
        if not isinstance(relative_name, str):
            continue
        target = resolved_root / relative_name
        if not target.exists():
            missing.append(target.relative_to(library_root).as_posix())
            continue
        if not target.is_file():
            continue
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        metadata = _build_metadata(library_root, target)
        files.append(
            {
                "path": target.relative_to(library_root).as_posix(),
                "content": content,
                "metadata": metadata,
            }
        )

    transcripts: list[str] = []
    if payload.get("include_transcripts"):
        transcripts_root = library_root / "transcripts"
        if transcripts_root.exists():
            for transcript in sorted(
                transcripts_root.rglob("*"), key=lambda p: p.name
            ):
                if transcript.is_file():
                    transcripts.append(
                        transcript.relative_to(library_root).as_posix()
                    )

    return success_response(
        {"files": files, "missing": missing, "transcripts": transcripts}
    )


@mcp_router.post("/tool:create_project_scaffold")
def create_project_scaffold(
    payload: dict[str, Any], request: Request
) -> dict[str, Any]:
    """Create a project with a default scaffold."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"path", "name"})

    if "path" not in payload and "name" not in payload:
        raise McpError(
            "MISSING_PATH",
            "Path or name is required.",
            {"fields": ["path", "name"]},
        )

    if "path" in payload:
        raw_path = payload["path"]
    else:
        raw_path = f"projects/active/{payload['name']}"

    files = [
        {"path": filename, "content": content}
        for filename, content in DEFAULT_PROJECT_FILES
    ]
    return create_project({"path": raw_path, "files": files}, request)
