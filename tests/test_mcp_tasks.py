from types import SimpleNamespace

from app import mcp
from app.user_scope import normalize_user_id

TEST_USER_ID = "test-user-123"


def _build_request(library_root):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(library_path=library_root)),
        state=SimpleNamespace(user_id=TEST_USER_ID),
    )


def _user_root(base_root):
    return base_root / "users" / normalize_user_id(TEST_USER_ID)


def _write_pulse_index(base_root, content: str) -> None:
    index_path = _user_root(base_root) / "pulse" / "index.md"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(content, encoding="utf-8")


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


def test_life_scope_filter_infers_finance_tasks(tmp_path):
    (_user_root(tmp_path) / "life" / "finances").mkdir(parents=True, exist_ok=True)
    _write_pulse_index(
        tmp_path,
        """# Pulse

## Active Tasks

- [ ] T-001 | high | tags:savings,goals | due:next Friday | Save $50 by next Friday for goals
- [ ] T-002 | high | owner:you | tags:savings,goals | project:finances | Saved $55 extra in savings
- [ ] T-003 | medium | tags:finances,savings | due:this weekend | Determine savings amount for paycheck
- [ ] T-004 | medium | tags:finances,savings | due:this weekend | Determine savings amount for paycheck
- [ ] T-005 | low | tags:finances,savings,reminders | due:this weekend | Schedule conversation about savings plan
""",
    )

    listed = mcp.list_tasks({"scope": "life/finances"}, _build_request(tmp_path))
    assert listed["ok"] is True
    tasks = listed["data"]["tasks"]

    assert len(tasks) == 5
    assert {task["scopePath"] for task in tasks} == {"life/finances"}
    assert {task["scopeType"] for task in tasks} == {"life"}
    assert {task["scopeName"] for task in tasks} == {"finances"}



def test_create_task_persists_scope_metadata(tmp_path):
    (_user_root(tmp_path) / "life" / "fitness").mkdir(parents=True, exist_ok=True)

    created = mcp.create_task(
        {
            "title": "Run 5k this week",
            "priority": "p1",
            "scope": "life/fitness",
            "tags": ["fitness", "health"],
        },
        _build_request(tmp_path),
    )
    assert created["ok"] is True

    task = created["data"]["task"]
    assert task["scopePath"] == "life/fitness"
    assert task["scopeType"] == "life"
    assert task["scopeName"] == "fitness"

    index_text = (_user_root(tmp_path) / "pulse" / "index.md").read_text(
        encoding="utf-8"
    )
    assert "scope:life/fitness" in index_text
    assert "project:fitness" in index_text

    by_path = mcp.list_tasks({"path": "life/fitness"}, _build_request(tmp_path))
    assert by_path["ok"] is True
    assert len(by_path["data"]["tasks"]) == 1
