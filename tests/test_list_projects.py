from types import SimpleNamespace

import pytest

from app.errors import McpError
from app.mcp import list_projects


def _build_request(library_root):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(library_path=library_root)),
        state=SimpleNamespace(user_id="test-user-123"),
    )


def _user_root(library_root):
    root = library_root / "users" / "testuser123"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_list_projects_defaults_to_active(tmp_path):
    active_root = _user_root(tmp_path) / "projects" / "active"
    (active_root / "Alpha").mkdir(parents=True)
    (active_root / "Beta").mkdir()
    (active_root / "note.txt").write_text("skip", encoding="utf-8")

    payload = list_projects({}, _build_request(tmp_path))

    assert payload["ok"] is True
    data = payload["data"]
    assert data["projects"] == [
        {"name": "Alpha", "path": "projects/active/Alpha"},
        {"name": "Beta", "path": "projects/active/Beta"},
    ]


def test_list_projects_falls_back_to_projects_root(tmp_path):
    projects_root = _user_root(tmp_path) / "projects"
    (projects_root / "Library").mkdir(parents=True)

    payload = list_projects({}, _build_request(tmp_path))

    assert payload["ok"] is True
    data = payload["data"]
    assert data["projects"] == [
        {"name": "Library", "path": "projects/Library"}
    ]


def test_list_projects_with_custom_path(tmp_path):
    custom_root = _user_root(tmp_path) / "projects" / "archived"
    (custom_root / "Gamma").mkdir(parents=True)

    payload = list_projects(
        {"path": "projects/archived"}, _build_request(tmp_path)
    )

    assert payload["ok"] is True
    data = payload["data"]
    assert data["projects"] == [
        {"name": "Gamma", "path": "projects/archived/Gamma"}
    ]


def test_list_projects_rejects_file_path(tmp_path):
    file_path = _user_root(tmp_path) / "projects" / "active"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("nope", encoding="utf-8")

    with pytest.raises(McpError) as excinfo:
        list_projects({"path": "projects/active"}, _build_request(tmp_path))

    assert excinfo.value.error.code == "INVALID_PATH"
