import os

import pytest

from app.errors import McpError
from app.paths import validate_path


def test_validate_path_returns_normalized_path(tmp_path):
    result = validate_path(tmp_path, "notes/spec.md")

    assert result == tmp_path / "notes" / "spec.md"


def test_validate_path_rejects_absolute_path(tmp_path):
    with pytest.raises(McpError) as excinfo:
        validate_path(tmp_path, "/etc/passwd")

    assert excinfo.value.error.code == "ABSOLUTE_PATH"


def test_validate_path_rejects_traversal_without_fs_access(tmp_path, monkeypatch):
    def _unexpected_call(*_args, **_kwargs):
        raise AssertionError("symlink check should not run for traversal paths")

    monkeypatch.setattr("app.paths._contains_symlink", _unexpected_call)

    with pytest.raises(McpError) as excinfo:
        validate_path(tmp_path, "../../etc/passwd")

    assert excinfo.value.error.code == "PATH_TRAVERSAL"


def test_validate_path_rejects_symlink(tmp_path):
    target = tmp_path / "target"
    target.write_text("data", encoding="utf-8")
    link = tmp_path / "link"
    os.symlink(target, link)

    with pytest.raises(McpError) as excinfo:
        validate_path(tmp_path, "link")

    assert excinfo.value.error.code == "PATH_SYMLINK"
