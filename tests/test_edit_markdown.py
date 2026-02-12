from types import SimpleNamespace

import pytest

from app.errors import McpError
from app.mcp import _resolve_git_head, edit_markdown


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


def test_edit_markdown_replace_section_updates_target(tmp_path):
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

    _assert_commit_payload(payload, _user_root(tmp_path))
    assert file_path.read_text(encoding="utf-8") == "\n".join(
        [
            "# Doc",
            "",
            "## Scope",
            "New scope.",
            "",
            "More here.",
            "",
            "## Details",
            "Other.",
            "",
        ]
    )


def test_edit_markdown_insert_before_adds_content(tmp_path):
    docs = _user_root(tmp_path) / "docs"
    docs.mkdir()
    file_path = docs / "readme.md"
    file_path.write_text(_sample_content(), encoding="utf-8")

    payload = edit_markdown(
        {
            "path": "docs/readme.md",
            "operation": {
                "type": "insert_before",
                "target": "## Scope",
                "content": "\n".join(["## Intro", "Inserted.", "", ""]),
            },
        },
        _build_request(tmp_path),
    )

    _assert_commit_payload(payload, _user_root(tmp_path))
    assert file_path.read_text(encoding="utf-8") == "\n".join(
        [
            "# Doc",
            "",
            "## Intro",
            "Inserted.",
            "",
            "## Scope",
            "Old scope.",
            "",
            "## Details",
            "Other.",
            "",
        ]
    )


def test_edit_markdown_insert_after_adds_content(tmp_path):
    docs = _user_root(tmp_path) / "docs"
    docs.mkdir()
    file_path = docs / "readme.md"
    file_path.write_text(_sample_content(), encoding="utf-8")

    payload = edit_markdown(
        {
            "path": "docs/readme.md",
            "operation": {
                "type": "insert_after",
                "target": "## Scope",
                "content": "\n".join(["## Notes", "Inserted after.", "", ""]),
            },
        },
        _build_request(tmp_path),
    )

    _assert_commit_payload(payload, _user_root(tmp_path))
    assert file_path.read_text(encoding="utf-8") == "\n".join(
        [
            "# Doc",
            "",
            "## Scope",
            "Old scope.",
            "",
            "## Notes",
            "Inserted after.",
            "",
            "## Details",
            "Other.",
            "",
        ]
    )


def test_edit_markdown_missing_section_is_safe(tmp_path):
    docs = _user_root(tmp_path) / "docs"
    docs.mkdir()
    file_path = docs / "readme.md"
    original = _sample_content()
    file_path.write_text(original, encoding="utf-8")

    with pytest.raises(McpError) as excinfo:
        edit_markdown(
            {
                "path": "docs/readme.md",
                "operation": {
                    "type": "replace_section",
                    "target": "## Missing",
                    "content": "## Missing\nNew content\n",
                },
            },
            _build_request(tmp_path),
        )

    assert excinfo.value.error.code == "SECTION_NOT_FOUND"
    assert file_path.read_text(encoding="utf-8") == original
