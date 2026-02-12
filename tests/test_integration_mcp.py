from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from dulwich import porcelain
from fastapi.testclient import TestClient

from app.main import create_app
from app.mcp import ACTIVITY_LOG_FILENAME

TEST_USER_ID = "test-user-123"


def _apply_user_identity_header(client: TestClient) -> None:
    client.headers.update({"X-BrainDrive-User-Id": TEST_USER_ID})


def _scoped_library_root(library_root: Path) -> Path:
    normalized_user_id = TEST_USER_ID.replace("-", "")
    return library_root / "users" / normalized_user_id


def _seed_library(library_root: Path) -> dict[str, Path]:
    scoped_root = _scoped_library_root(library_root)
    docs = scoped_root / "docs"
    docs.mkdir(parents=True)
    readme = docs / "readme.md"
    readme.write_text("Intro\n", encoding="utf-8")
    guide = docs / "guide.md"
    guide.write_text(_sample_guide_content(), encoding="utf-8")
    search = docs / "search.md"
    search.write_text("Token JWT details\n", encoding="utf-8")
    delete = docs / "delete.md"
    delete.write_text("Remove me\n", encoding="utf-8")
    return {
        "root": scoped_root,
        "readme": readme,
        "guide": guide,
        "search": search,
        "delete": delete,
    }


def _seed_minimal_library(library_root: Path) -> Path:
    scoped_root = _scoped_library_root(library_root)
    docs = scoped_root / "docs"
    docs.mkdir(parents=True)
    readme = docs / "readme.md"
    readme.write_text("Intro\n", encoding="utf-8")
    return readme


def _sample_guide_content() -> str:
    return "\n".join(
        [
            "# Guide",
            "",
            "## Scope",
            "Old scope.",
            "",
            "## Details",
            "More.",
            "",
        ]
    )


def _read_activity_entries(library_root: Path) -> list[dict[str, str]]:
    log_path = _scoped_library_root(library_root) / ACTIVITY_LOG_FILENAME
    assert log_path.exists()
    entries = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


def _assert_repo_clean(library_root: Path) -> None:
    status = porcelain.status(_scoped_library_root(library_root))
    assert not status.unstaged
    untracked = {
        item.decode("utf-8") if isinstance(item, bytes) else str(item)
        for item in status.untracked
    }
    assert untracked.issubset({ACTIVITY_LOG_FILENAME})
    assert not any(status.staged.values())


def test_mcp_endpoints_route_all_markdown_operations(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_PATH", str(tmp_path))
    paths = _seed_library(tmp_path)

    app = create_app()
    with TestClient(app) as client:
        _apply_user_identity_header(client)
        response = client.post(
            "/tool:read_markdown", json={"path": "docs/readme.md"}
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["data"]["content"] == "Intro\n"
        assert payload["data"]["metadata"]["path"] == "docs/readme.md"

        response = client.post(
            "/tool:list_markdown_files", json={"path": "docs"}
        )
        assert response.status_code == 200
        assert response.json()["data"]["files"] == [
            "docs/delete.md",
            "docs/guide.md",
            "docs/readme.md",
            "docs/search.md",
        ]

        response = client.post(
            "/tool:search_markdown",
            json={"query": "JWT", "path": "docs"},
        )
        assert response.status_code == 200
        results = response.json()["data"]["results"]
        assert results[0]["path"] == "docs/search.md"
        assert results[0]["matches"][0]["snippet"] == "Token JWT details"

        response = client.post(
            "/tool:preview_markdown_change",
            json={
                "path": "docs/readme.md",
                "operation": {"type": "append", "content": "More details\n"},
            },
        )
        assert response.status_code == 200
        preview = response.json()["data"]
        assert "+More details" in preview["diff"]
        assert paths["readme"].read_text(encoding="utf-8") == "Intro\n"

        response = client.post(
            "/tool:write_markdown",
            json={
                "path": "docs/readme.md",
                "operation": {"type": "append", "content": "More details\n"},
            },
        )
        assert response.status_code == 200
        write_data = response.json()["data"]
        assert len(write_data["commitSha"]) == 40

        response = client.post(
            "/tool:edit_markdown",
            json={
                "path": "docs/guide.md",
                "operation": {
                    "type": "replace_section",
                    "target": "## Scope",
                    "content": "## Scope\nNew scope.\n",
                },
            },
        )
        assert response.status_code == 200
        edit_data = response.json()["data"]
        assert len(edit_data["commitSha"]) == 40

        response = client.post(
            "/tool:delete_markdown",
            json={"path": "docs/delete.md", "confirm": True},
        )
        assert response.status_code == 200
        delete_data = response.json()["data"]
        assert len(delete_data["commitSha"]) == 40

    assert paths["readme"].read_text(encoding="utf-8") == "Intro\nMore details\n"
    assert "New scope." in paths["guide"].read_text(encoding="utf-8")
    assert not paths["delete"].exists()

    entries = _read_activity_entries(tmp_path)
    assert [entry["operation"] for entry in entries] == [
        "write_markdown",
        "edit_markdown",
        "delete_markdown",
    ]
    assert entries[0]["commitSha"] == write_data["commitSha"]
    assert entries[1]["commitSha"] == edit_data["commitSha"]
    assert entries[2]["commitSha"] == delete_data["commitSha"]


def test_agent_flow_preview_approve_execute_records_audit(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_PATH", str(tmp_path))
    paths = _seed_library(tmp_path)

    app = create_app()
    with TestClient(app) as client:
        _apply_user_identity_header(client)
        preview = client.post(
            "/tool:preview_markdown_change",
            json={
                "path": "docs/readme.md",
                "operation": {"type": "append", "content": "Approved\n"},
            },
        )
        assert preview.status_code == 200
        diff = preview.json()["data"]["diff"]
        assert "+Approved" in diff
        assert paths["readme"].read_text(encoding="utf-8") == "Intro\n"

        approved = True
        assert approved is True

        write = client.post(
            "/tool:write_markdown",
            json={
                "path": "docs/readme.md",
                "operation": {"type": "append", "content": "Approved\n"},
            },
        )
        assert write.status_code == 200
        commit_sha = write.json()["data"]["commitSha"]
        assert len(commit_sha) == 40

    entries = _read_activity_entries(tmp_path)
    assert entries[-1]["operation"] == "write_markdown"
    assert entries[-1]["commitSha"] == commit_sha
    assert paths["readme"].read_text(encoding="utf-8") == "Intro\nApproved\n"


def _preview_request(library_root: Path, content: str) -> str:
    os.environ["BRAINDRIVE_LIBRARY_PATH"] = str(library_root)
    app = create_app()
    with TestClient(app) as client:
        _apply_user_identity_header(client)
        response = client.post(
            "/tool:preview_markdown_change",
            json={
                "path": "docs/readme.md",
                "operation": {"type": "append", "content": content},
            },
        )
        assert response.status_code == 200
        return response.json()["data"]["diff"]


def test_concurrent_previews_are_safe(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_PATH", str(tmp_path))
    paths = _seed_library(tmp_path)
    original = paths["readme"].read_text(encoding="utf-8")

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_preview_request, tmp_path, "Alpha\n"),
            executor.submit(_preview_request, tmp_path, "Beta\n"),
        ]
        diffs = [future.result() for future in futures]

    assert any("+Alpha" in diff for diff in diffs)
    assert any("+Beta" in diff for diff in diffs)
    assert paths["readme"].read_text(encoding="utf-8") == original


def test_external_tool_error_envelope_via_mcp(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_PATH", str(tmp_path))
    _seed_library(tmp_path)

    app = create_app()
    with TestClient(app) as client:
        _apply_user_identity_header(client)
        response = client.post("/tool:read_markdown", json={"path": 123})

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_TYPE"


def test_direct_filesystem_write_is_detected(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_PATH", str(tmp_path))
    readme = _seed_minimal_library(tmp_path)

    app = create_app()
    with TestClient(app) as client:
        _apply_user_identity_header(client)
        response = client.post(
            "/tool:write_markdown",
            json={
                "path": "docs/readme.md",
                "operation": {"type": "append", "content": "Audit\n"},
            },
        )
        assert response.status_code == 200

    _assert_repo_clean(tmp_path)

    readme.write_text("Bypass\n", encoding="utf-8")

    with pytest.raises(AssertionError):
        _assert_repo_clean(tmp_path)
