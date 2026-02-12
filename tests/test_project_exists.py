from types import SimpleNamespace

import pytest

from app.errors import McpError
from app.mcp import project_exists


def _build_request(library_root):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(library_path=library_root)),
        state=SimpleNamespace(user_id="test-user-123"),
    )


def _user_root(library_root):
    root = library_root / "users" / "testuser123"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_project_exists_returns_true_for_directory(tmp_path):
    project_root = _user_root(tmp_path) / "projects" / "active" / "Alpha"
    project_root.mkdir(parents=True)

    payload = project_exists(
        {"path": "projects/active/Alpha"}, _build_request(tmp_path)
    )

    assert payload["ok"] is True
    data = payload["data"]
    assert data["exists"] is True
    assert data["isDir"] is True
    assert data["conflict"] is False
    assert data["path"] == "projects/active/Alpha"


def test_project_exists_returns_false_for_missing(tmp_path):
    payload = project_exists(
        {"path": "projects/active/Missing"}, _build_request(tmp_path)
    )

    assert payload["ok"] is True
    data = payload["data"]
    assert data["exists"] is False
    assert data["isDir"] is False
    assert data["conflict"] is False


def test_project_exists_reports_conflict_for_file(tmp_path):
    file_path = _user_root(tmp_path) / "projects" / "active" / "Alpha"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("not a directory", encoding="utf-8")

    payload = project_exists(
        {"path": "projects/active/Alpha"}, _build_request(tmp_path)
    )

    assert payload["ok"] is True
    data = payload["data"]
    assert data["exists"] is False
    assert data["isDir"] is False
    assert data["conflict"] is True


def test_project_exists_accepts_name(tmp_path):
    project_root = _user_root(tmp_path) / "projects" / "active" / "Beta"
    project_root.mkdir(parents=True)

    payload = project_exists({"name": "Beta"}, _build_request(tmp_path))

    assert payload["ok"] is True
    data = payload["data"]
    assert data["exists"] is True
    assert data["path"] == "projects/active/Beta"


def test_project_exists_falls_back_to_projects_root(tmp_path):
    project_root = _user_root(tmp_path) / "projects" / "Library"
    project_root.mkdir(parents=True)

    payload = project_exists(
        {"name": "Library"}, _build_request(tmp_path)
    )

    assert payload["ok"] is True
    data = payload["data"]
    assert data["exists"] is True
    assert data["path"] == "projects/Library"


def test_project_exists_rejects_missing_payload(tmp_path):
    with pytest.raises(McpError) as excinfo:
        project_exists({}, _build_request(tmp_path))

    assert excinfo.value.error.code == "MISSING_PATH"


def test_project_exists_rejects_markdown_path(tmp_path):
    with pytest.raises(McpError) as excinfo:
        project_exists(
            {"path": "projects/active/Alpha/spec.md"},
            _build_request(tmp_path),
        )

    assert excinfo.value.error.code == "INVALID_PATH"
