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


def test_create_directory_with_gitkeep(tmp_path):
    payload = {"path": "docs/reports", "gitkeep": True}
    response = mcp.create_directory(payload, _build_request(tmp_path))
    assert response["ok"] is True
    assert (_user_root(tmp_path) / "docs" / "reports").is_dir()
    assert (_user_root(tmp_path) / "docs" / "reports" / ".gitkeep").is_file()


def test_list_directory(tmp_path):
    (_user_root(tmp_path) / "alpha").mkdir()
    (_user_root(tmp_path) / "alpha" / "notes.txt").write_text("hi", encoding="utf-8")
    (_user_root(tmp_path) / "beta").mkdir()

    payload = {"path": ".", "recursive": False}
    response = mcp.list_directory(payload, _build_request(tmp_path))
    data = response["data"]
    assert "directories" in data
    assert "files" in data
    assert "alpha" in {path.split("/")[-1] for path in data["directories"]}
    assert "beta" in {path.split("/")[-1] for path in data["directories"]}
