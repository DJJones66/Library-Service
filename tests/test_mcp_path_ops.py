import base64
from types import SimpleNamespace

import pytest

from app.errors import McpError
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


def test_read_file_metadata(tmp_path):
    target = _user_root(tmp_path) / "docs" / "readme.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Readme", encoding="utf-8")

    response = mcp.read_file_metadata(
        {"path": "docs/readme.md"}, _build_request(tmp_path)
    )
    data = response["data"]
    assert data["isFile"] is True
    assert data["path"] == "docs/readme.md"


def test_move_copy_delete_path(tmp_path):
    source = _user_root(tmp_path) / "docs" / "file.txt"
    source.parent.mkdir(parents=True)
    source.write_text("content", encoding="utf-8")

    move_response = mcp.move_path(
        {"from_path": "docs/file.txt", "to_path": "docs/moved.txt"},
        _build_request(tmp_path),
    )
    assert move_response["ok"] is True
    assert (_user_root(tmp_path) / "docs" / "moved.txt").exists()
    assert not source.exists()

    copy_response = mcp.copy_path(
        {"from_path": "docs/moved.txt", "to_path": "docs/copied.txt"},
        _build_request(tmp_path),
    )
    assert copy_response["ok"] is True
    assert (_user_root(tmp_path) / "docs" / "copied.txt").exists()

    delete_response = mcp.delete_path(
        {"path": "docs/copied.txt", "confirm": True},
        _build_request(tmp_path),
    )
    assert delete_response["ok"] is True
    assert not (_user_root(tmp_path) / "docs" / "copied.txt").exists()


def test_delete_directory_requires_recursive(tmp_path):
    (_user_root(tmp_path) / "docs").mkdir()
    with pytest.raises(McpError):
        mcp.delete_path(
            {"path": "docs", "confirm": True}, _build_request(tmp_path)
        )


def test_write_binary(tmp_path):
    content = b"binary-data"
    payload = {
        "path": "attachments/file.bin",
        "content_base64": base64.b64encode(content).decode("ascii"),
    }
    response = mcp.write_binary(payload, _build_request(tmp_path))
    assert response["ok"] is True
    stored = (_user_root(tmp_path) / "attachments" / "file.bin").read_bytes()
    assert stored == content
