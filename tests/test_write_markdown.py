from types import SimpleNamespace

import pytest

from app.errors import McpError
import app.mcp_markdown as mcp_markdown
from app.mcp import _resolve_git_head, write_markdown


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


def test_write_markdown_append_updates_file(tmp_path):
    docs = _user_root(tmp_path) / "docs"
    docs.mkdir()
    file_path = docs / "readme.md"
    file_path.write_text("Intro", encoding="utf-8")

    payload = write_markdown(
        {
            "path": "docs/readme.md",
            "operation": {"type": "append", "content": "More"},
        },
        _build_request(tmp_path),
    )

    _assert_commit_payload(payload, _user_root(tmp_path))
    assert file_path.read_text(encoding="utf-8") == "Intro\nMore"


def test_write_markdown_prepend_updates_file(tmp_path):
    docs = _user_root(tmp_path) / "docs"
    docs.mkdir()
    file_path = docs / "readme.md"
    file_path.write_text("Details", encoding="utf-8")

    payload = write_markdown(
        {
            "path": "docs/readme.md",
            "operation": {"type": "prepend", "content": "Intro"},
        },
        _build_request(tmp_path),
    )

    _assert_commit_payload(payload, _user_root(tmp_path))
    assert file_path.read_text(encoding="utf-8") == "Intro\nDetails"


def test_write_markdown_rejects_invalid_operation(tmp_path):
    docs = _user_root(tmp_path) / "docs"
    docs.mkdir()
    file_path = docs / "readme.md"
    file_path.write_text("Intro\n", encoding="utf-8")

    with pytest.raises(McpError) as excinfo:
        write_markdown(
            {
                "path": "docs/readme.md",
                "operation": {
                    "type": "replace_section",
                    "content": "Nope",
                    "target": "## Scope",
                },
            },
            _build_request(tmp_path),
        )

    assert excinfo.value.error.code == "INVALID_OPERATION"
    assert file_path.read_text(encoding="utf-8") == "Intro\n"


def test_write_markdown_rolls_back_on_commit_failure(tmp_path, monkeypatch):
    docs = _user_root(tmp_path) / "docs"
    docs.mkdir()
    file_path = docs / "readme.md"
    file_path.write_text("Intro", encoding="utf-8")

    def _fail_commit(*_args, **_kwargs):
        raise RuntimeError("commit failed")

    monkeypatch.setattr(mcp_markdown, "_commit_markdown_change", _fail_commit)

    with pytest.raises(McpError) as excinfo:
        write_markdown(
            {
                "path": "docs/readme.md",
                "operation": {"type": "append", "content": "More"},
            },
            _build_request(tmp_path),
        )

    assert excinfo.value.error.code == "GIT_ERROR"
    assert file_path.read_text(encoding="utf-8") == "Intro"
