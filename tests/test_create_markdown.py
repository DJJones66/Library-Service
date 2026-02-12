from types import SimpleNamespace

import pytest

from app.errors import McpError
import app.mcp_markdown as mcp_markdown
from app.mcp import _resolve_git_head, create_markdown


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


def test_create_markdown_creates_file_and_commit(tmp_path):
    payload = create_markdown(
        {"path": "docs/readme.md", "content": "Intro\n"},
        _build_request(tmp_path),
    )

    _assert_commit_payload(payload, _user_root(tmp_path))
    assert (_user_root(tmp_path) / "docs" / "readme.md").read_text(
        encoding="utf-8"
    ) == "Intro\n"


def test_create_markdown_rejects_existing_path(tmp_path):
    docs = _user_root(tmp_path) / "docs"
    docs.mkdir()
    file_path = docs / "readme.md"
    file_path.write_text("Intro\n", encoding="utf-8")

    with pytest.raises(McpError) as excinfo:
        create_markdown(
            {"path": "docs/readme.md", "content": "More\n"},
            _build_request(tmp_path),
        )

    assert excinfo.value.error.code == "PATH_EXISTS"


def test_create_markdown_rejects_non_markdown(tmp_path):
    with pytest.raises(McpError) as excinfo:
        create_markdown(
            {"path": "docs/readme.txt", "content": "Intro\n"},
            _build_request(tmp_path),
        )

    assert excinfo.value.error.code == "NOT_MARKDOWN"


def test_create_markdown_rolls_back_on_commit_failure(tmp_path, monkeypatch):
    def _fail_commit(*_args, **_kwargs):
        raise RuntimeError("commit failed")

    monkeypatch.setattr(mcp_markdown, "_commit_markdown_change", _fail_commit)

    with pytest.raises(McpError) as excinfo:
        create_markdown(
            {"path": "docs/readme.md", "content": "Intro\n"},
            _build_request(tmp_path),
        )

    assert excinfo.value.error.code == "GIT_ERROR"
    assert not (_user_root(tmp_path) / "docs" / "readme.md").exists()
