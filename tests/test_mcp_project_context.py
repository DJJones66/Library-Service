from types import SimpleNamespace

from app import mcp


def _build_request(library_root):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(library_path=library_root)),
        state=SimpleNamespace(user_id="test-user-123"),
    )


def _user_root(library_root):
    root = library_root / "users" / "testuser123"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_create_project_scaffold_and_context(tmp_path):
    response = mcp.create_project_scaffold(
        {"name": "demo"}, _build_request(tmp_path)
    )
    assert response["ok"] is True
    project_root = _user_root(tmp_path) / "projects" / "active" / "demo"
    assert project_root.exists()
    assert (project_root / "spec.md").is_file()

    context = mcp.project_context(
        {"name": "demo"}, _build_request(tmp_path)
    )
    data = context["data"]
    paths = {entry["path"] for entry in data["files"]}
    assert "projects/active/demo/spec.md" in paths
