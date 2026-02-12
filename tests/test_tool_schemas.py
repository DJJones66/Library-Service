import copy
from dataclasses import dataclass
import importlib
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from app import paths
from app.errors import McpError
import app.mcp as mcp


def _build_request(library_root):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(library_path=library_root)),
        state=SimpleNamespace(user_id="test-user-123"),
    )


@dataclass(frozen=True)
class ToolCase:
    name: str
    func: Callable[[dict[str, Any], SimpleNamespace], dict[str, Any]]
    payload: dict[str, Any]


TOOL_CASES = [
    ToolCase("read_markdown", mcp.read_markdown, {"path": "docs/readme.md"}),
    ToolCase(
        "list_markdown_files", mcp.list_markdown_files, {"path": "docs"}
    ),
    ToolCase("list_projects", mcp.list_projects, {"path": "projects/active"}),
    ToolCase(
        "project_exists",
        mcp.project_exists,
        {"path": "projects/active/example"},
    ),
    ToolCase(
        "create_project",
        mcp.create_project,
        {"path": "projects/active/example"},
    ),
    ToolCase(
        "create_markdown",
        mcp.create_markdown,
        {"path": "docs/readme.md", "content": "Intro"},
    ),
    ToolCase(
        "search_markdown",
        mcp.search_markdown,
        {"query": "JWT", "path": "docs"},
    ),
    ToolCase(
        "preview_markdown_change",
        mcp.preview_markdown_change,
        {
            "path": "docs/readme.md",
            "operation": {"type": "append", "content": "Note"},
        },
    ),
    ToolCase(
        "write_markdown",
        mcp.write_markdown,
        {
            "path": "docs/readme.md",
            "operation": {"type": "append", "content": "Note"},
        },
    ),
    ToolCase(
        "edit_markdown",
        mcp.edit_markdown,
        {
            "path": "docs/readme.md",
            "operation": {
                "type": "replace_section",
                "target": "## Scope",
                "content": "## Scope\nNew\n",
            },
        },
    ),
    ToolCase(
        "delete_markdown",
        mcp.delete_markdown,
        {"path": "docs/readme.md", "confirm": True},
    ),
]

OPERATION_CASES = [
    ToolCase(
        "preview_markdown_change",
        mcp.preview_markdown_change,
        {
            "path": "docs/readme.md",
            "operation": {"type": "append", "content": "Note"},
        },
    ),
    ToolCase(
        "write_markdown",
        mcp.write_markdown,
        {
            "path": "docs/readme.md",
            "operation": {"type": "append", "content": "Note"},
        },
    ),
    ToolCase(
        "edit_markdown",
        mcp.edit_markdown,
        {
            "path": "docs/readme.md",
            "operation": {
                "type": "replace_section",
                "target": "## Scope",
                "content": "## Scope\nNew\n",
            },
        },
    ),
]


@pytest.mark.parametrize("case", TOOL_CASES, ids=lambda case: case.name)
def test_unknown_fields_rejected_without_filesystem_access(
    tmp_path, monkeypatch, case
):
    payload = copy.deepcopy(case.payload)
    payload["extra"] = "nope"

    def _fail_validate_path(*_args, **_kwargs):
        raise AssertionError("validate_path should not be called")

    handler_module = importlib.import_module(case.func.__module__)
    monkeypatch.setattr(
        handler_module, "validate_path", _fail_validate_path
    )

    with pytest.raises(McpError) as excinfo:
        case.func(payload, _build_request(tmp_path))

    assert excinfo.value.error.code == "UNKNOWN_FIELD"


@pytest.mark.parametrize("case", OPERATION_CASES, ids=lambda case: case.name)
def test_unknown_operation_fields_rejected_without_filesystem_access(
    tmp_path, monkeypatch, case
):
    payload = copy.deepcopy(case.payload)
    payload["operation"]["extra"] = "nope"

    def _fail_validate_path(*_args, **_kwargs):
        raise AssertionError("validate_path should not be called")

    handler_module = importlib.import_module(case.func.__module__)
    monkeypatch.setattr(
        handler_module, "validate_path", _fail_validate_path
    )

    with pytest.raises(McpError) as excinfo:
        case.func(payload, _build_request(tmp_path))

    assert excinfo.value.error.code == "UNKNOWN_FIELD"


@pytest.mark.parametrize("case", TOOL_CASES, ids=lambda case: case.name)
def test_invalid_path_type_rejected_without_filesystem_access(
    tmp_path, monkeypatch, case
):
    payload = copy.deepcopy(case.payload)
    payload["path"] = 123

    def _fail_symlink_check(*_args, **_kwargs):
        raise AssertionError("_contains_symlink should not be called")

    monkeypatch.setattr(paths, "_contains_symlink", _fail_symlink_check)

    with pytest.raises(McpError) as excinfo:
        case.func(payload, _build_request(tmp_path))

    assert excinfo.value.error.code == "INVALID_TYPE"
