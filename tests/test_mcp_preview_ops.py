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


def test_preview_move_copy_delete(tmp_path):
    source = _user_root(tmp_path) / "docs" / "file.txt"
    source.parent.mkdir(parents=True)
    source.write_text("content", encoding="utf-8")

    move_preview = mcp.preview_move_path(
        {"from_path": "docs/file.txt", "to_path": "docs/moved.txt"},
        _build_request(tmp_path),
    )
    mappings = move_preview["data"]["mappings"]
    assert mappings[0]["from"] == "docs/file.txt"
    assert mappings[0]["to"] == "docs/moved.txt"

    copy_preview = mcp.preview_copy_path(
        {"from_path": "docs/file.txt", "to_path": "docs/copied.txt"},
        _build_request(tmp_path),
    )
    assert copy_preview["data"]["summary"]["files"] == 1

    delete_preview = mcp.preview_delete_path(
        {"path": "docs/file.txt", "recursive": False},
        _build_request(tmp_path),
    )
    assert delete_preview["data"]["summary"]["files"] == 1
