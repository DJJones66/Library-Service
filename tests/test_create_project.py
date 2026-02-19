from types import SimpleNamespace

import pytest

from app.errors import McpError
import app.mcp_projects as mcp_projects
from app.mcp import (
    _resolve_git_head,
    create_project,
    ensure_scope_scaffold,
)


def _build_request(library_root):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(library_path=library_root)),
        state=SimpleNamespace(user_id="test-user-123"),
    )


def _user_root(library_root):
    root = library_root / "users" / "testuser123"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _assert_commit_payload(payload, library_root):
    assert payload["ok"] is True
    data = payload["data"]
    assert data["success"] is True
    assert isinstance(data["commitSha"], str)
    assert len(data["commitSha"]) == 40
    assert (library_root / ".git").exists()
    assert _resolve_git_head(library_root) == data["commitSha"]


def test_create_project_with_default_scaffold(tmp_path):
    payload = create_project(
        {"path": "projects/active/Test1"},
        _build_request(tmp_path),
    )

    user_root = _user_root(tmp_path)
    _assert_commit_payload(payload, user_root)

    project_root = user_root / "projects" / "active" / "Test1"
    assert (project_root / "AGENT.md").is_file()
    assert (project_root / "spec.md").is_file()
    assert (project_root / "build-plan.md").is_file()
    assert (project_root / "decisions.md").is_file()
    assert (project_root / "ideas.md").is_file()
    assert (project_root / "spec.md").read_text(encoding="utf-8").startswith("# Test1")


def test_create_project_with_name_defaults_to_active(tmp_path):
    payload = create_project(
        {"name": "Gamma"},
        _build_request(tmp_path),
    )

    user_root = _user_root(tmp_path)
    _assert_commit_payload(payload, user_root)

    project_root = user_root / "projects" / "active" / "Gamma"
    assert (project_root / "AGENT.md").is_file()
    assert (project_root / "spec.md").is_file()
    assert (project_root / "build-plan.md").is_file()
    assert (project_root / "decisions.md").is_file()
    assert (project_root / "ideas.md").is_file()


def test_create_project_with_files_keeps_custom_and_fills_required(tmp_path):
    payload = create_project(
        {
            "path": "projects/active/Test2",
            "files": [
                {"path": "spec.md", "content": "# Custom Spec\n"},
                {"path": "notes.md", "content": "Notes\n"},
            ],
        },
        _build_request(tmp_path),
    )

    user_root = _user_root(tmp_path)
    _assert_commit_payload(payload, user_root)

    project_root = user_root / "projects" / "active" / "Test2"
    assert (project_root / "spec.md").read_text(encoding="utf-8") == "# Custom Spec\n"
    assert (project_root / "notes.md").read_text(encoding="utf-8") == "Notes\n"
    assert (project_root / "AGENT.md").is_file()
    assert (project_root / "build-plan.md").is_file()
    assert (project_root / "decisions.md").is_file()
    assert (project_root / "ideas.md").is_file()


def test_create_project_life_path_auto_scaffold(tmp_path):
    payload = create_project(
        {"path": "life/travel"},
        _build_request(tmp_path),
    )

    user_root = _user_root(tmp_path)
    _assert_commit_payload(payload, user_root)

    life_root = user_root / "life" / "travel"
    assert (life_root / "AGENT.md").is_file()
    assert (life_root / "spec.md").is_file()
    assert (life_root / "build-plan.md").is_file()
    assert (life_root / "interview.md").is_file()
    assert (life_root / "goals.md").is_file()
    assert (life_root / "action-plan.md").is_file()


def test_ensure_scope_scaffold_repairs_existing_scope(tmp_path):
    life_root = _user_root(tmp_path) / "life" / "budgeting"
    life_root.mkdir(parents=True, exist_ok=True)

    payload = ensure_scope_scaffold(
        {"path": "life/budgeting"},
        _build_request(tmp_path),
    )

    _assert_commit_payload(payload, _user_root(tmp_path))
    data = payload["data"]
    assert data["path"] == "life/budgeting"
    assert len(data["createdFiles"]) >= 6

    assert (life_root / "AGENT.md").is_file()
    assert (life_root / "spec.md").is_file()
    assert (life_root / "build-plan.md").is_file()
    assert (life_root / "interview.md").is_file()
    assert (life_root / "goals.md").is_file()
    assert (life_root / "action-plan.md").is_file()



def test_ensure_scope_scaffold_noop_when_complete(tmp_path):
    create_project({"path": "life/habits"}, _build_request(tmp_path))

    payload = ensure_scope_scaffold(
        {"path": "life/habits"},
        _build_request(tmp_path),
    )

    assert payload["ok"] is True
    data = payload["data"]
    assert data["path"] == "life/habits"
    assert data["createdFiles"] == []
    assert data["commitSha"] is None


def test_create_project_rejects_existing_project(tmp_path):
    project_root = _user_root(tmp_path) / "projects" / "active" / "Test3"
    project_root.mkdir(parents=True)

    with pytest.raises(McpError) as excinfo:
        create_project(
            {"path": "projects/active/Test3"},
            _build_request(tmp_path),
        )

    assert excinfo.value.error.code == "PROJECT_EXISTS"


def test_create_project_rejects_non_markdown_file(tmp_path):
    with pytest.raises(McpError) as excinfo:
        create_project(
            {
                "path": "projects/active/Test4",
                "files": [{"path": "spec.txt", "content": "Nope\n"}],
            },
            _build_request(tmp_path),
        )

    assert excinfo.value.error.code == "NOT_MARKDOWN"


def test_create_project_rolls_back_on_commit_failure(tmp_path, monkeypatch):
    def _fail_commit(*_args, **_kwargs):
        raise RuntimeError("commit failed")

    monkeypatch.setattr(
        mcp_projects, "_commit_markdown_changes", _fail_commit
    )

    with pytest.raises(McpError) as excinfo:
        create_project(
            {
                "path": "projects/active/Test5",
                "files": [{"path": "spec.md", "content": "# Spec\n"}],
            },
            _build_request(tmp_path),
        )

    assert excinfo.value.error.code == "GIT_ERROR"
    assert not (_user_root(tmp_path) / "projects" / "active" / "Test5").exists()
