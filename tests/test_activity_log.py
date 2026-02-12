import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.errors import McpError
import app.mcp as mcp
import app.mcp_markdown as mcp_markdown
from app.mcp import delete_markdown, edit_markdown, write_markdown, _resolve_git_head


def _build_request(library_root):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(library_path=library_root)),
        state=SimpleNamespace(user_id="test-user-123"),
    )


def _user_root(library_root):
    root = library_root / "users" / "testuser123"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _read_activity_entries(library_root):
    log_path = _user_root(library_root) / mcp.ACTIVITY_LOG_FILENAME
    assert log_path.exists()
    entries = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


def _assert_activity_entry(entry, operation, path, commit_sha, summary):
    assert entry["operation"] == operation
    assert entry["path"] == path
    assert entry["commitSha"] == commit_sha
    assert entry["summary"] == summary
    datetime.fromisoformat(entry["timestamp"])


def _sample_content() -> str:
    return "\n".join(
        [
            "# Doc",
            "",
            "## Scope",
            "Old scope.",
            "",
            "## Details",
            "Other.",
            "",
        ]
    )


def test_write_markdown_appends_activity_log_entry(tmp_path):
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

    entries = _read_activity_entries(tmp_path)
    assert len(entries) == 1
    _assert_activity_entry(
        entries[0],
        "write_markdown",
        "docs/readme.md",
        payload["data"]["commitSha"],
        "append",
    )


def test_edit_markdown_appends_activity_log_entry(tmp_path):
    docs = _user_root(tmp_path) / "docs"
    docs.mkdir()
    file_path = docs / "readme.md"
    file_path.write_text(_sample_content(), encoding="utf-8")

    payload = edit_markdown(
        {
            "path": "docs/readme.md",
            "operation": {
                "type": "replace_section",
                "target": "## Scope",
                "content": "\n".join(
                    ["## Scope", "New scope.", "", "More here.", "", ""]
                ),
            },
        },
        _build_request(tmp_path),
    )

    entries = _read_activity_entries(tmp_path)
    assert len(entries) == 1
    _assert_activity_entry(
        entries[0],
        "edit_markdown",
        "docs/readme.md",
        payload["data"]["commitSha"],
        "replace_section (## Scope)",
    )


def test_delete_markdown_appends_activity_log_entry(tmp_path):
    docs = _user_root(tmp_path) / "docs"
    docs.mkdir()
    file_path = docs / "readme.md"
    file_path.write_text("Intro", encoding="utf-8")

    payload = delete_markdown(
        {"path": "docs/readme.md", "confirm": True}, _build_request(tmp_path)
    )

    entries = _read_activity_entries(tmp_path)
    assert len(entries) == 1
    _assert_activity_entry(
        entries[0],
        "delete_markdown",
        "docs/readme.md",
        payload["data"]["commitSha"],
        "delete file",
    )


def test_activity_log_failure_rolls_back_commit(tmp_path, monkeypatch):
    docs = _user_root(tmp_path) / "docs"
    docs.mkdir()
    file_path = docs / "readme.md"
    file_path.write_text("Intro", encoding="utf-8")

    initial_payload = write_markdown(
        {
            "path": "docs/readme.md",
            "operation": {"type": "append", "content": "First"},
        },
        _build_request(tmp_path),
    )
    initial_head = _resolve_git_head(_user_root(tmp_path))
    initial_content = file_path.read_text(encoding="utf-8")

    def _fail_log(*_args, **_kwargs):
        raise RuntimeError("log failed")

    monkeypatch.setattr(mcp_markdown, "_append_activity_log", _fail_log)

    with pytest.raises(McpError) as excinfo:
        write_markdown(
            {
                "path": "docs/readme.md",
                "operation": {"type": "append", "content": "Second"},
            },
            _build_request(tmp_path),
        )

    assert excinfo.value.error.code == "LOG_ERROR"
    assert file_path.read_text(encoding="utf-8") == initial_content
    assert _resolve_git_head(_user_root(tmp_path)) == initial_head

    entries = _read_activity_entries(tmp_path)
    assert len(entries) == 1
    assert entries[0]["commitSha"] == initial_payload["data"]["commitSha"]
