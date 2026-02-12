from types import SimpleNamespace

import pytest

from app.errors import McpError
from app.mcp import list_markdown_files


def _build_request(library_root):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(library_path=library_root)),
        state=SimpleNamespace(user_id="test-user-123"),
    )


def _user_root(library_root):
    root = library_root / "users" / "testuser123"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_list_markdown_files_returns_sorted_results(tmp_path):
    base = _user_root(tmp_path) / "projects"
    (base / "nested").mkdir(parents=True)
    (base / "other").mkdir(parents=True)
    (base / "a.md").write_text("# A", encoding="utf-8")
    (base / "z.txt").write_text("nope", encoding="utf-8")
    (base / "nested" / "b.markdown").write_text("B", encoding="utf-8")
    (base / "nested" / "a.md").write_text("A", encoding="utf-8")
    (base / "other" / "c.MD").write_text("C", encoding="utf-8")

    payload = list_markdown_files(
        {"path": "projects"}, _build_request(tmp_path)
    )

    assert payload["ok"] is True
    assert payload["data"]["files"] == [
        "projects/a.md",
        "projects/nested/a.md",
        "projects/nested/b.markdown",
        "projects/other/c.MD",
    ]


def test_list_markdown_files_rejects_traversal(tmp_path):
    with pytest.raises(McpError) as excinfo:
        list_markdown_files({"path": "../../"}, _build_request(tmp_path))

    assert excinfo.value.error.code == "PATH_TRAVERSAL"
