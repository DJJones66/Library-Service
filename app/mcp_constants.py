"""Shared constants for MCP endpoints."""

from __future__ import annotations

ALLOWED_MARKDOWN_EXTENSIONS = {".md", ".markdown"}
SECTION_OPERATIONS = {"replace_section", "insert_before", "insert_after"}
PREVIEW_OPERATIONS = {"append", "prepend"} | SECTION_OPERATIONS
WRITE_OPERATIONS = {"append", "prepend"}
ACTIVITY_LOG_FILENAME = "activity.log"
DEFAULT_PROJECT_FILES = [
    ("AGENT.md", "# Project Agent\n"),
    ("spec.md", "# Spec\n\n## Scope\nInitial scope.\n"),
    ("build-plan.md", "# Build Plan\n\n## Phase 1\n\n## Phase 2\n"),
    ("decisions.md", "# Decisions\n"),
    ("ideas.md", "# Ideas\n"),
]
