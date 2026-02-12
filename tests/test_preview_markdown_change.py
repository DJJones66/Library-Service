from types import SimpleNamespace

import pytest

from app.errors import McpError
from app.mcp import preview_markdown_change


def _build_request(library_root):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(library_path=library_root)),
        state=SimpleNamespace(user_id="test-user-123"),
    )


def _user_root(library_root):
    root = library_root / "users" / "testuser123"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_preview_append_returns_diff_and_leaves_file_unchanged(tmp_path):
    docs = _user_root(tmp_path) / "docs"
    docs.mkdir()
    file_path = docs / "readme.md"
    file_path.write_text("Intro\n", encoding="utf-8")

    payload = preview_markdown_change(
        {
            "path": "docs/readme.md",
            "operation": {"type": "append", "content": "More details\n"},
        },
        _build_request(tmp_path),
    )

    assert payload["ok"] is True
    data = payload["data"]
    assert file_path.read_text(encoding="utf-8") == "Intro\n"
    assert data["diff"].splitlines() == [
        "--- docs/readme.md",
        "+++ docs/readme.md",
        "@@ -1 +1,2 @@",
        " Intro",
        "+More details",
    ]
    assert data["summary"] == "append: +1 -0 lines"
    assert data["riskLevel"] == "low"


def test_preview_rejects_non_markdown_paths(tmp_path):
    with pytest.raises(McpError) as excinfo:
        preview_markdown_change(
            {
                "path": "docs/readme.txt",
                "operation": {"type": "append", "content": "Note\n"},
            },
            _build_request(tmp_path),
        )

    assert excinfo.value.error.code == "NOT_MARKDOWN"
    assert not (_user_root(tmp_path) / "docs" / "readme.txt").exists()
