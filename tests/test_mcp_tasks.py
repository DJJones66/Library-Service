from types import SimpleNamespace

from app import mcp


def _build_request(library_root):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(library_path=library_root)),
        state=SimpleNamespace(user_id="test-user-123"),
    )


def test_task_lifecycle(tmp_path):
    create = mcp.create_task(
        {"title": "Write tests", "priority": "p1", "project": "demo"},
        _build_request(tmp_path),
    )
    assert create["ok"] is True
    task = create["data"]["task"]
    task_id = task["id"]

    listed = mcp.list_tasks({"project": "demo"}, _build_request(tmp_path))
    assert listed["ok"] is True
    assert any(item["id"] == task_id for item in listed["data"]["tasks"])

    updated = mcp.update_task(
        {"id": task_id, "fields": {"priority": "p0"}},
        _build_request(tmp_path),
    )
    assert updated["ok"] is True
    assert updated["data"]["task"]["priority"] == "p0"

    completed = mcp.complete_task({"id": task_id}, _build_request(tmp_path))
    assert completed["ok"] is True

    reopened = mcp.reopen_task({"id": task_id}, _build_request(tmp_path))
    assert reopened["ok"] is True
