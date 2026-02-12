"""Filesystem-related MCP endpoints."""

from __future__ import annotations

import base64
import binascii
import os
import shutil
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
    _resolve_git_head,
    _restore_git_head,
    _rollback_created_file,
)
from app.mcp_payload import _ensure_payload_dict, _reject_unknown_fields
from app.mcp_router import mcp_router
from app.mcp_utils import _atomic_write, _atomic_write_bytes
from app.paths import validate_path
from app.user_scope import get_request_library_root


@mcp_router.post("/tool:create_directory")
def create_directory(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Create a directory within the library root."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"path", "gitkeep"})

    if "path" not in payload:
        raise McpError(
            "MISSING_PATH",
            "Path is required.",
            {"fields": ["path"]},
        )

    raw_path = payload["path"]
    gitkeep = payload.get("gitkeep", False)
    if not isinstance(gitkeep, bool):
        raise McpError(
            "INVALID_TYPE",
            "gitkeep must be a boolean.",
            {"gitkeep": str(gitkeep), "type": type(gitkeep).__name__},
        )

    library_root = get_request_library_root(request)
    resolved_path = validate_path(library_root, raw_path)

    if resolved_path.exists() and not resolved_path.is_dir():
        raise McpError(
            "INVALID_PATH",
            "Path must reference a directory.",
            {"path": raw_path},
        )

    resolved_path.mkdir(parents=True, exist_ok=True)

    commit_sha: str | None = None
    if gitkeep:
        gitkeep_path = resolved_path / ".gitkeep"
        if not gitkeep_path.exists():
            _atomic_write(gitkeep_path, "")
        repo = _ensure_git_repo(library_root)
        relative_path = gitkeep_path.relative_to(library_root)
        head_ref_path, previous_head = _read_head_state(library_root)
        try:
            commit_sha = _commit_markdown_change(
                repo, relative_path, "create_directory"
            )
        except Exception as exc:
            _rollback_created_file(repo, gitkeep_path, relative_path)
            raise McpError(
                "GIT_ERROR",
                "Git commit failed; mutation rolled back.",
                {"path": raw_path, "operation": "create_directory"},
            ) from exc
        try:
            entry = _build_activity_entry(
                "create_directory",
                relative_path,
                "create directory",
                commit_sha,
            )
            _append_activity_log(library_root, entry)
        except Exception as exc:
            _rollback_created_file(repo, gitkeep_path, relative_path)
            _restore_git_head(library_root, head_ref_path, previous_head)
            raise McpError(
                "LOG_ERROR",
                "Activity log write failed; mutation rolled back.",
                {"path": raw_path, "operation": "create_directory"},
            ) from exc

    return success_response({"success": True, "commitSha": commit_sha})


@mcp_router.post("/tool:list_directory")
def list_directory(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """List files and directories under a path."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"path", "recursive", "include_files", "include_dirs"})

    if "path" not in payload:
        raise McpError(
            "MISSING_PATH",
            "Path is required.",
            {"fields": ["path"]},
        )

    raw_path = payload["path"]
    recursive = payload.get("recursive", False)
    include_files = payload.get("include_files", True)
    include_dirs = payload.get("include_dirs", True)
    if not isinstance(recursive, bool) or not isinstance(include_files, bool) or not isinstance(include_dirs, bool):
        raise McpError(
            "INVALID_TYPE",
            "recursive/include_files/include_dirs must be booleans.",
            {
                "recursive": str(recursive),
                "include_files": str(include_files),
                "include_dirs": str(include_dirs),
            },
        )

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

    files: list[str] = []
    dirs: list[str] = []
    if recursive:
        for root, dirnames, filenames in os.walk(resolved_path, followlinks=False):
            root_path = Path(root)
            dirnames[:] = sorted([name for name in dirnames if not (root_path / name).is_symlink()])
            if include_dirs:
                for dirname in dirnames:
                    dirs.append((root_path / dirname).relative_to(library_root).as_posix())
            if include_files:
                for filename in sorted(filenames):
                    file_path = root_path / filename
                    if file_path.is_symlink():
                        continue
                    files.append(file_path.relative_to(library_root).as_posix())
    else:
        for entry in sorted(resolved_path.iterdir(), key=lambda item: item.name):
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if include_dirs:
                    dirs.append(entry.relative_to(library_root).as_posix())
            elif include_files:
                files.append(entry.relative_to(library_root).as_posix())

    return success_response({"files": files, "directories": dirs})


@mcp_router.post("/tool:read_file_metadata")
def read_file_metadata(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Read metadata for any file or directory."""
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

    stat = resolved_path.stat()
    relative_path = resolved_path.relative_to(library_root).as_posix()
    last_modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    return success_response(
        {
            "path": relative_path,
            "isDir": resolved_path.is_dir(),
            "isFile": resolved_path.is_file(),
            "sizeBytes": stat.st_size,
            "lastModified": last_modified.isoformat(),
            "gitHead": _resolve_git_head(library_root),
        }
    )


@mcp_router.post("/tool:move_path")
def move_path(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Move or rename a file or directory."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"from_path", "to_path", "overwrite"})

    if "from_path" not in payload or "to_path" not in payload:
        raise McpError(
            "MISSING_PATH",
            "from_path and to_path are required.",
            {"fields": ["from_path", "to_path"]},
        )

    overwrite = payload.get("overwrite", False)
    if not isinstance(overwrite, bool):
        raise McpError(
            "INVALID_TYPE",
            "overwrite must be a boolean.",
            {"overwrite": str(overwrite), "type": type(overwrite).__name__},
        )

    library_root = get_request_library_root(request)
    source = validate_path(library_root, payload["from_path"])
    destination = validate_path(library_root, payload["to_path"])

    if not source.exists():
        raise McpError(
            "FILE_NOT_FOUND",
            "Source path does not exist.",
            {"path": payload["from_path"]},
        )

    if destination.exists() and not overwrite:
        raise McpError(
            "PATH_EXISTS",
            "Destination already exists.",
            {"path": payload["to_path"]},
        )

    if destination.exists() and overwrite:
        _remove_path(destination, recursive=True)

    pre_paths = _collect_file_paths(library_root, source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    post_paths = _collect_file_paths(library_root, destination)

    repo = _ensure_git_repo(library_root)
    head_ref_path, previous_head = _read_head_state(library_root)
    relative_paths = pre_paths + [p for p in post_paths if p not in pre_paths]
    try:
        commit_sha = _commit_markdown_changes(
            repo, relative_paths, "move_path", destination.relative_to(library_root)
        )
    except Exception as exc:
        _restore_git_head(library_root, head_ref_path, previous_head)
        raise McpError(
            "GIT_ERROR",
            "Git commit failed; mutation rolled back.",
            {"path": payload["from_path"], "operation": "move_path"},
        ) from exc

    entry = _build_activity_entry(
        "move_path",
        destination.relative_to(library_root),
        "move path",
        commit_sha,
    )
    _append_activity_log(library_root, entry)

    return success_response({"success": True, "commitSha": commit_sha})


@mcp_router.post("/tool:copy_path")
def copy_path(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Copy a file or directory."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"from_path", "to_path", "overwrite"})

    if "from_path" not in payload or "to_path" not in payload:
        raise McpError(
            "MISSING_PATH",
            "from_path and to_path are required.",
            {"fields": ["from_path", "to_path"]},
        )

    overwrite = payload.get("overwrite", False)
    if not isinstance(overwrite, bool):
        raise McpError(
            "INVALID_TYPE",
            "overwrite must be a boolean.",
            {"overwrite": str(overwrite), "type": type(overwrite).__name__},
        )

    library_root = get_request_library_root(request)
    source = validate_path(library_root, payload["from_path"])
    destination = validate_path(library_root, payload["to_path"])

    if not source.exists():
        raise McpError(
            "FILE_NOT_FOUND",
            "Source path does not exist.",
            {"path": payload["from_path"]},
        )

    if destination.exists() and not overwrite:
        raise McpError(
            "PATH_EXISTS",
            "Destination already exists.",
            {"path": payload["to_path"]},
        )

    if destination.exists() and overwrite:
        _remove_path(destination, recursive=True)

    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=False)
    else:
        shutil.copy2(source, destination)

    post_paths = _collect_file_paths(library_root, destination)
    repo = _ensure_git_repo(library_root)
    head_ref_path, previous_head = _read_head_state(library_root)
    try:
        commit_sha = _commit_markdown_changes(
            repo, post_paths, "copy_path", destination.relative_to(library_root)
        )
    except Exception as exc:
        _restore_git_head(library_root, head_ref_path, previous_head)
        raise McpError(
            "GIT_ERROR",
            "Git commit failed; mutation rolled back.",
            {"path": payload["to_path"], "operation": "copy_path"},
        ) from exc

    entry = _build_activity_entry(
        "copy_path",
        destination.relative_to(library_root),
        "copy path",
        commit_sha,
    )
    _append_activity_log(library_root, entry)

    return success_response({"success": True, "commitSha": commit_sha})


@mcp_router.post("/tool:delete_path")
def delete_path(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Delete a file or directory with explicit confirmation."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"path", "confirm", "recursive"})

    if "path" not in payload:
        raise McpError(
            "MISSING_PATH",
            "Path is required.",
            {"fields": ["path"]},
        )

    confirm = payload.get("confirm", False)
    if not isinstance(confirm, bool):
        raise McpError(
            "INVALID_TYPE",
            "confirm must be a boolean.",
            {"confirm": str(confirm), "type": type(confirm).__name__},
        )
    if not confirm:
        raise McpError(
            "CONFIRM_REQUIRED",
            "Deletion requires explicit confirmation.",
            {"path": payload["path"]},
        )

    recursive = payload.get("recursive", False)
    if not isinstance(recursive, bool):
        raise McpError(
            "INVALID_TYPE",
            "recursive must be a boolean.",
            {"recursive": str(recursive), "type": type(recursive).__name__},
        )

    library_root = get_request_library_root(request)
    target = validate_path(library_root, payload["path"])

    if not target.exists():
        raise McpError(
            "FILE_NOT_FOUND",
            "Path does not exist.",
            {"path": payload["path"]},
        )

    if target.is_dir() and not recursive:
        raise McpError(
            "RECURSIVE_REQUIRED",
            "Directory deletion requires recursive=true.",
            {"path": payload["path"]},
        )

    pre_paths = _collect_file_paths(library_root, target)
    _remove_path(target, recursive=recursive)

    repo = _ensure_git_repo(library_root)
    head_ref_path, previous_head = _read_head_state(library_root)
    try:
        commit_sha = _commit_markdown_changes(
            repo, pre_paths, "delete_path", target.relative_to(library_root)
        )
    except Exception as exc:
        _restore_git_head(library_root, head_ref_path, previous_head)
        raise McpError(
            "GIT_ERROR",
            "Git commit failed; mutation rolled back.",
            {"path": payload["path"], "operation": "delete_path"},
        ) from exc

    entry = _build_activity_entry(
        "delete_path",
        target.relative_to(library_root),
        "delete path",
        commit_sha,
    )
    _append_activity_log(library_root, entry)

    return success_response({"success": True, "commitSha": commit_sha})


@mcp_router.post("/tool:write_binary")
def write_binary(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Write a binary file (base64-encoded) within the library."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"path", "content_base64", "content_type"})

    if "path" not in payload:
        raise McpError(
            "MISSING_PATH",
            "Path is required.",
            {"fields": ["path"]},
        )
    if "content_base64" not in payload:
        raise McpError(
            "MISSING_CONTENT",
            "content_base64 is required.",
            {"fields": ["content_base64"]},
        )

    raw_path = payload["path"]
    content_base64 = payload["content_base64"]
    if not isinstance(content_base64, str):
        raise McpError(
            "INVALID_TYPE",
            "content_base64 must be a string.",
            {"content_base64": str(content_base64)},
        )

    try:
        content_bytes = base64.b64decode(content_base64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise McpError(
            "INVALID_CONTENT",
            "content_base64 must be valid base64.",
            {"path": raw_path},
        ) from exc

    library_root = get_request_library_root(request)
    resolved_path = validate_path(library_root, raw_path)
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
    _atomic_write_bytes(resolved_path, content_bytes)
    try:
        commit_sha = _commit_markdown_change(
            repo, relative_path, "write_binary"
        )
    except Exception as exc:
        _rollback_created_file(repo, resolved_path, relative_path)
        raise McpError(
            "GIT_ERROR",
            "Git commit failed; mutation rolled back.",
            {"path": raw_path, "operation": "write_binary"},
        ) from exc

    try:
        entry = _build_activity_entry(
            "write_binary", relative_path, "write binary", commit_sha
        )
        _append_activity_log(library_root, entry)
    except Exception as exc:
        _rollback_created_file(repo, resolved_path, relative_path)
        _restore_git_head(library_root, head_ref_path, previous_head)
        raise McpError(
            "LOG_ERROR",
            "Activity log write failed; mutation rolled back.",
            {"path": raw_path, "operation": "write_binary"},
        ) from exc

    return success_response({"success": True, "commitSha": commit_sha})


@mcp_router.post("/tool:preview_move_path")
def preview_move_path(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Preview a move operation by listing affected paths."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"from_path", "to_path", "overwrite"})

    if "from_path" not in payload or "to_path" not in payload:
        raise McpError(
            "MISSING_PATH",
            "from_path and to_path are required.",
            {"fields": ["from_path", "to_path"]},
        )

    overwrite = payload.get("overwrite", False)
    if not isinstance(overwrite, bool):
        raise McpError(
            "INVALID_TYPE",
            "overwrite must be a boolean.",
            {"overwrite": str(overwrite)},
        )

    library_root = get_request_library_root(request)
    source = validate_path(library_root, payload["from_path"])
    destination = validate_path(library_root, payload["to_path"])

    if not source.exists():
        raise McpError(
            "FILE_NOT_FOUND",
            "Source path does not exist.",
            {"path": payload["from_path"]},
        )

    mappings, conflicts = _build_path_mappings(
        library_root, source, destination
    )
    if conflicts and not overwrite:
        return success_response(
            {
                "mappings": mappings,
                "conflicts": conflicts,
                "summary": _mapping_summary(mappings),
            }
        )
    return success_response(
        {
            "mappings": mappings,
            "conflicts": conflicts,
            "summary": _mapping_summary(mappings),
        }
    )


@mcp_router.post("/tool:preview_copy_path")
def preview_copy_path(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Preview a copy operation by listing affected paths."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"from_path", "to_path", "overwrite"})

    if "from_path" not in payload or "to_path" not in payload:
        raise McpError(
            "MISSING_PATH",
            "from_path and to_path are required.",
            {"fields": ["from_path", "to_path"]},
        )

    overwrite = payload.get("overwrite", False)
    if not isinstance(overwrite, bool):
        raise McpError(
            "INVALID_TYPE",
            "overwrite must be a boolean.",
            {"overwrite": str(overwrite)},
        )

    library_root = get_request_library_root(request)
    source = validate_path(library_root, payload["from_path"])
    destination = validate_path(library_root, payload["to_path"])

    if not source.exists():
        raise McpError(
            "FILE_NOT_FOUND",
            "Source path does not exist.",
            {"path": payload["from_path"]},
        )

    mappings, conflicts = _build_path_mappings(
        library_root, source, destination
    )
    return success_response(
        {
            "mappings": mappings,
            "conflicts": conflicts,
            "summary": _mapping_summary(mappings),
        }
    )


@mcp_router.post("/tool:preview_delete_path")
def preview_delete_path(
    payload: dict[str, Any], request: Request
) -> dict[str, Any]:
    """Preview a delete operation by listing affected paths."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"path", "recursive"})

    if "path" not in payload:
        raise McpError(
            "MISSING_PATH",
            "Path is required.",
            {"fields": ["path"]},
        )

    recursive = payload.get("recursive", False)
    if not isinstance(recursive, bool):
        raise McpError(
            "INVALID_TYPE",
            "recursive must be a boolean.",
            {"recursive": str(recursive)},
        )

    library_root = get_request_library_root(request)
    target = validate_path(library_root, payload["path"])

    if not target.exists():
        raise McpError(
            "FILE_NOT_FOUND",
            "Path does not exist.",
            {"path": payload["path"]},
        )

    if target.is_dir() and not recursive:
        raise McpError(
            "RECURSIVE_REQUIRED",
            "Directory deletion requires recursive=true.",
            {"path": payload["path"]},
        )

    files = [
        path.as_posix()
        for path in _collect_file_paths(library_root, target)
    ]
    return success_response(
        {
            "paths": files,
            "summary": {"files": len(files)},
        }
    )


def _remove_path(target: Path, recursive: bool) -> None:
    if target.is_dir():
        if recursive:
            shutil.rmtree(target)
        else:
            target.rmdir()
    else:
        target.unlink()


def _collect_file_paths(library_root: Path, target: Path) -> list[Path]:
    paths: list[Path] = []
    if target.is_file():
        relative = target.relative_to(library_root)
        if ".git" not in relative.parts:
            paths.append(relative)
        return paths
    if not target.exists():
        return paths
    for path in target.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(library_root)
        if ".git" in relative.parts:
            continue
        paths.append(relative)
    return paths


def _build_path_mappings(
    library_root: Path, source: Path, destination: Path
) -> tuple[list[dict[str, str]], list[str]]:
    mappings: list[dict[str, str]] = []
    conflicts: list[str] = []
    if source.is_file():
        dest_path = destination
        if destination.is_dir():
            dest_path = destination / source.name
        relative_from = source.relative_to(library_root).as_posix()
        relative_to = dest_path.relative_to(library_root).as_posix()
        mappings.append({"from": relative_from, "to": relative_to})
        if dest_path.exists():
            conflicts.append(relative_to)
        return mappings, conflicts

    for path in source.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        dest_path = destination / relative
        relative_from = path.relative_to(library_root).as_posix()
        relative_to = dest_path.relative_to(library_root).as_posix()
        mappings.append({"from": relative_from, "to": relative_to})
        if dest_path.exists():
            conflicts.append(relative_to)
    return mappings, conflicts


def _mapping_summary(mappings: list[dict[str, str]]) -> dict[str, int]:
    return {"files": len(mappings)}
