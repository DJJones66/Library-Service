from types import SimpleNamespace

import pytest

from app import mcp
from app.errors import McpError

TEST_USER_ID = "test-user-123"


def _build_request(library_root):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(library_path=library_root)),
        state=SimpleNamespace(user_id=TEST_USER_ID),
    )


def _scoped_root(library_root):
    return library_root / "users" / TEST_USER_ID.replace("-", "")


def _seed_template(template_root):
    (template_root / "me").mkdir(parents=True, exist_ok=True)
    (template_root / "me" / "profile.md").write_text("# Template Profile\n", encoding="utf-8")
    (template_root / "life" / "finances").mkdir(parents=True, exist_ok=True)
    (template_root / "life" / "finances" / "interview.md").write_text(
        "# Finances Interview\n", encoding="utf-8"
    )
    (template_root / ".braindrive").mkdir(parents=True, exist_ok=True)
    (template_root / ".braindrive" / "onboarding_state.json").write_text(
        "{}\n", encoding="utf-8"
    )


def test_bootstrap_user_library_creates_structure_and_is_idempotent(tmp_path, monkeypatch):
    template_root = tmp_path / "template"
    _seed_template(template_root)
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_BASE_TEMPLATE_PATH", str(template_root))

    first = mcp.bootstrap_user_library({}, _build_request(tmp_path))

    assert first["ok"] is True
    assert first["data"]["changed"] is True
    assert len(first["data"]["commitSha"]) == 40

    scoped_root = _scoped_root(tmp_path)
    assert (scoped_root / "me" / "profile.md").is_file()
    assert (scoped_root / "capture" / "inbox" / ".gitkeep").is_file()
    assert (scoped_root / "life" / "career" / "action-plan.md").is_file()
    assert (scoped_root / "digest" / "_meta" / "rollup-state.json").is_file()

    second = mcp.bootstrap_user_library({}, _build_request(tmp_path))
    assert second["ok"] is True
    assert second["data"]["changed"] is False
    assert second["data"]["commitSha"] is None


def test_topic_onboarding_lifecycle(tmp_path, monkeypatch):
    template_root = tmp_path / "template"
    _seed_template(template_root)
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_BASE_TEMPLATE_PATH", str(template_root))

    request = _build_request(tmp_path)
    mcp.bootstrap_user_library({}, request)

    initial = mcp.get_onboarding_state({}, request)
    assert initial["ok"] is True
    assert initial["data"]["state"]["starter_topics"]["finances"] == "not_started"

    started = mcp.start_topic_onboarding({"topic": "finances"}, request)
    assert started["ok"] is True
    assert started["data"]["status"] == "in_progress"
    assert len(started["data"]["commitSha"]) == 40

    with pytest.raises(McpError) as excinfo:
        mcp.save_topic_onboarding_context(
            {
                "topic": "finances",
                "context": "Budget baseline and debt plan.",
                "approved": False,
            },
            request,
        )
    assert excinfo.value.error.code == "APPROVAL_REQUIRED"

    saved = mcp.save_topic_onboarding_context(
        {
            "topic": "finances",
            "context": "Budget baseline and debt plan.",
            "approved": True,
        },
        request,
    )
    assert saved["ok"] is True
    assert saved["data"]["status"] == "in_progress"
    assert len(saved["data"]["commitSha"]) == 40

    interview_content = (
        _scoped_root(tmp_path) / "life" / "finances" / "interview.md"
    ).read_text(encoding="utf-8")
    assert "Budget baseline and debt plan." in interview_content

    completed = mcp.complete_topic_onboarding(
        {"topic": "finances", "summary": "Weekly budget review every Monday."},
        request,
    )
    assert completed["ok"] is True
    assert completed["data"]["status"] == "complete"
    assert completed["data"]["next_topic"] == "fitness"
    assert len(completed["data"]["commitSha"]) == 40

    final_state = mcp.get_onboarding_state({}, request)
    assert final_state["data"]["state"]["starter_topics"]["finances"] == "complete"

    action_plan = (
        _scoped_root(tmp_path) / "life" / "finances" / "action-plan.md"
    ).read_text(encoding="utf-8")
    assert "Onboarding Summary" in action_plan
