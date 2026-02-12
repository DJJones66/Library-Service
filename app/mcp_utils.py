"""Shared filesystem helpers for MCP endpoints."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _join_with_newline(left: str, right: str) -> str:
    if not left or not right:
        return left + right
    if left.endswith("\n") or right.startswith("\n"):
        return left + right
    return left + "\n" + right


def _atomic_write(target_path: Path, content: str) -> None:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=target_path.parent, delete=False
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, target_path)
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def _atomic_write_bytes(target_path: Path, content: bytes) -> None:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb", dir=target_path.parent, delete=False
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, target_path)
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
