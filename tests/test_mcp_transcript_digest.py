from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app import mcp


def _build_request(library_root):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(library_path=library_root)),
        state=SimpleNamespace(user_id="test-user-123"),
    )


def _user_root(library_root):
    root = library_root / "users" / "testuser123"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_ingest_transcript_and_activity(tmp_path):
    response = mcp.ingest_transcript(
        {"content": "Meeting notes", "project": "demo"},
        _build_request(tmp_path),
    )
    assert response["ok"] is True
    path = response["data"]["path"]
    assert (_user_root(tmp_path) / path).is_file()
    index = _user_root(tmp_path) / "transcripts" / "index.md"
    assert index.is_file()

    log = mcp.read_activity_log({"limit": 5}, _build_request(tmp_path))
    assert log["ok"] is True
    assert log["data"]["entries"]


def test_digest_snapshot(tmp_path):
    mcp.create_task(
        {"title": "Draft spec", "priority": "p1", "project": "demo"},
        _build_request(tmp_path),
    )
    task = mcp.create_task(
        {"title": "Write tests", "priority": "p2", "project": "demo"},
        _build_request(tmp_path),
    )["data"]["task"]
    mcp.complete_task({"id": task["id"]}, _build_request(tmp_path))

    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    snapshot = mcp.digest_snapshot(
        {"project": "demo", "activity_since": since},
        _build_request(tmp_path),
    )
    data = snapshot["data"]
    assert "tasks" in data
    assert "completed" in data
    assert "activity" in data


def test_digest_snapshot_accepts_naive_activity_since(tmp_path):
    mcp.create_task(
        {"title": "Draft spec", "priority": "p1", "project": "demo"},
        _build_request(tmp_path),
    )
    completed_task = mcp.create_task(
        {"title": "Write tests", "priority": "p2", "project": "demo"},
        _build_request(tmp_path),
    )["data"]["task"]
    mcp.complete_task({"id": completed_task["id"]}, _build_request(tmp_path))

    naive_since = (datetime.now(timezone.utc) - timedelta(days=1)).replace(tzinfo=None).isoformat()
    snapshot = mcp.digest_snapshot(
        {"project": "demo", "activity_since": naive_since},
        _build_request(tmp_path),
    )
    assert snapshot["ok"] is True
    data = snapshot["data"]
    assert isinstance(data.get("tasks"), list)
    assert isinstance(data.get("completed"), list)
    assert isinstance(data.get("activity"), list)


def test_read_activity_log_accepts_naive_since(tmp_path):
    mcp.create_task(
        {"title": "Capture note", "priority": "p2", "project": "demo"},
        _build_request(tmp_path),
    )

    naive_since = (datetime.now(timezone.utc) - timedelta(days=1)).replace(tzinfo=None).isoformat()
    log = mcp.read_activity_log({"limit": 20, "since": naive_since}, _build_request(tmp_path))
    assert log["ok"] is True
    assert isinstance(log["data"].get("entries"), list)
