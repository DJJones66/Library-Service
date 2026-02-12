"""Path validation utilities for enforcing the library boundary."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from app.errors import McpError


def validate_path(library_root: Path, raw_path: str) -> Path:
    """Validate a user-supplied path and return a normalized absolute path."""
    if not isinstance(raw_path, str):
        raise McpError(
            "INVALID_TYPE",
            "Path must be a string.",
            {"path": str(raw_path), "type": type(raw_path).__name__},
        )

    normalized = raw_path.replace("\\", "/")
    candidate = PurePosixPath(normalized)

    if candidate.is_absolute():
        raise McpError(
            "ABSOLUTE_PATH",
            "Absolute paths are not allowed.",
            {"path": raw_path},
        )

    if ".." in candidate.parts:
        raise McpError(
            "PATH_TRAVERSAL",
            "Path traversal is not allowed.",
            {"path": raw_path},
        )

    if _contains_symlink(library_root, candidate):
        raise McpError(
            "PATH_SYMLINK",
            "Symlinked paths are not allowed.",
            {"path": raw_path},
        )

    return library_root.joinpath(*candidate.parts)


def _contains_symlink(library_root: Path, relative_path: PurePosixPath) -> bool:
    current = library_root
    for segment in relative_path.parts:
        current = current / segment
        if current.is_symlink():
            return True
    return False
