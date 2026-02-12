from types import SimpleNamespace

import pytest

from app.errors import McpError
from app.mcp import search_markdown


def _build_request(library_root):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(library_path=library_root)),
        state=SimpleNamespace(user_id="test-user-123"),
    )


def _user_root(library_root):
    root = library_root / "users" / "testuser123"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_search_markdown_returns_matches_and_snippets(tmp_path):
    docs = _user_root(tmp_path) / "docs"
    docs.mkdir()
    (docs / "auth.md").write_text(
        "JWT header\nNo match here\nJWT payload\n", encoding="utf-8"
    )
    (_user_root(tmp_path) / "notes.markdown").write_text(
        "Use JWT for tokens\n", encoding="utf-8"
    )
    (_user_root(tmp_path) / "ignore.txt").write_text("JWT\n", encoding="utf-8")

    payload = search_markdown({"query": "JWT"}, _build_request(tmp_path))

    assert payload["ok"] is True
    assert payload["data"]["results"] == [
        {
            "path": "docs/auth.md",
            "matches": [
                {"line": 1, "snippet": "JWT header"},
                {"line": 3, "snippet": "JWT payload"},
            ],
        },
        {
            "path": "notes.markdown",
            "matches": [{"line": 1, "snippet": "Use JWT for tokens"}],
        },
    ]


def test_search_markdown_rejects_empty_query(tmp_path):
    with pytest.raises(McpError) as excinfo:
        search_markdown({"query": ""}, _build_request(tmp_path))

    assert excinfo.value.error.code == "INVALID_QUERY"
