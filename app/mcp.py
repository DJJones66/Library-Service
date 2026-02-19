"""MCP handler registration."""

# ruff: noqa: F401

from __future__ import annotations

from fastapi import FastAPI

from app.mcp_constants import ACTIVITY_LOG_FILENAME
from app.mcp_router import mcp_router

# Import modules to register routes with the shared router.
from app import (
    mcp_activity,
    mcp_digest,
    mcp_files,
    mcp_markdown,
    mcp_onboarding,
    mcp_projects,
    mcp_tasks,
    mcp_tools_endpoint,
    mcp_transcripts,
)

# Re-export endpoints for tests and direct imports.
from app.mcp_activity import read_activity_log
from app.mcp_digest import digest_snapshot, rollup_digest_period, score_digest_tasks
from app.mcp_files import (
    copy_path,
    create_directory,
    delete_path,
    list_directory,
    move_path,
    preview_copy_path,
    preview_delete_path,
    preview_move_path,
    read_file_metadata,
    write_binary,
)
from app.mcp_git import _read_head_state, _resolve_git_head
from app.mcp_markdown import (
    create_markdown,
    delete_markdown,
    edit_markdown,
    list_markdown_files,
    preview_bulk_changes,
    preview_markdown_change,
    read_markdown,
    search_markdown,
    write_markdown,
)
from app.mcp_onboarding import (
    bootstrap_user_library,
    complete_topic_onboarding,
    get_onboarding_state,
    rebuild_profile_context,
    save_topic_onboarding_context,
    start_topic_onboarding,
)
from app.mcp_projects import (
    create_project,
    create_project_scaffold,
    ensure_scope_scaffold,
    list_projects,
    project_context,
    project_exists,
)
from app.mcp_tasks import (
    complete_task,
    create_task,
    list_tasks,
    reopen_task,
    update_task,
)
from app.mcp_tools_endpoint import list_tool_schemas
from app.mcp_transcripts import ingest_transcript


def register_mcp_handlers(app: FastAPI) -> None:
    """Attach MCP routes to the FastAPI application."""
    app.include_router(mcp_router)
