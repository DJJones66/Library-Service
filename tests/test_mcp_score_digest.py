from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app import mcp


def _build_request(library_root):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(library_path=library_root)),
        state=SimpleNamespace(user_id="test-user-123"),
    )


def test_score_digest_tasks(tmp_path):
    now = datetime.now(timezone.utc)
    tasks = [
        {
            "id": 1,
            "title": "Urgent",
            "priority": "p0",
            "project": "demo",
            "tags": [],
            "due": (now + timedelta(days=1)).isoformat(),
        },
        {
            "id": 2,
            "title": "Blocked",
            "priority": "p1",
            "project": "demo",
            "tags": ["blocked"],
        },
    ]

    response = mcp.score_digest_tasks(
        {"tasks": tasks, "focus_project": "demo", "now": now.isoformat()},
        _build_request(tmp_path),
    )
    data = response["data"]["tasks"]
    assert data[0]["task"]["id"] == 1
