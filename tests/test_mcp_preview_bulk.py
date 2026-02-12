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


def test_preview_bulk_changes(tmp_path):
    target = _user_root(tmp_path) / "docs" / "spec.md"
    target.parent.mkdir(parents=True)
    target.write_text("Hello\n", encoding="utf-8")

    payload = {
        "changes": [
            {
                "path": "docs/spec.md",
                "action": "write",
                "operation": {"type": "append", "content": "World\n"},
            },
            {
                "path": "docs/new.md",
                "action": "create",
                "content": "# New\n",
            },
        ]
    }
    response = mcp.preview_bulk_changes(payload, _build_request(tmp_path))
    data = response["data"]
    assert data["summary"]["added"] > 0
    assert len(data["changes"]) == 2
