import os
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.errors import McpError
from app.mcp import read_markdown


def _build_request(library_root):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(library_path=library_root)),
        state=SimpleNamespace(user_id="test-user-123"),
    )


def _user_root(library_root):
    root = library_root / "users" / "testuser123"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_read_markdown_returns_content_and_metadata(tmp_path, monkeypatch):
    git_dir = _user_root(tmp_path) / ".git" / "refs" / "heads"
    git_dir.mkdir(parents=True)
    head_sha = "a" * 40
    (_user_root(tmp_path) / ".git" / "HEAD").write_text(
        "ref: refs/heads/main", encoding="utf-8"
    )
    (git_dir / "main").write_text(head_sha, encoding="utf-8")

    target_dir = _user_root(tmp_path) / "projects" / "active" / "foo"
    target_dir.mkdir(parents=True)
    file_path = target_dir / "spec.md"
    file_path.write_text("# Spec\n", encoding="utf-8")
    timestamp = 1_700_000_000
    os.utime(file_path, (timestamp, timestamp))

    payload = read_markdown(
        {"path": "projects/active/foo/spec.md"}, _build_request(tmp_path)
    )

    assert payload["ok"] is True
    data = payload["data"]
    assert data["content"] == "# Spec\n"
    assert data["metadata"] == {
        "path": "projects/active/foo/spec.md",
        "sizeBytes": file_path.stat().st_size,
        "lastModified": datetime.fromtimestamp(
            timestamp, tz=timezone.utc
        ).isoformat(),
        "gitHead": head_sha,
    }


def test_read_markdown_rejects_non_markdown(tmp_path):
    with pytest.raises(McpError) as excinfo:
        read_markdown(
            {"path": "projects/active/foo/spec.txt"},
            _build_request(tmp_path),
        )

    assert excinfo.value.error.code == "NOT_MARKDOWN"
    assert not (_user_root(tmp_path) / "projects" / "active" / "foo" / "spec.txt").exists()
