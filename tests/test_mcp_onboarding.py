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
    assert (scoped_root / "AGENT.md").is_file()
    assert (scoped_root / "capture" / "AGENT.md").is_file()
    assert (scoped_root / "life" / "career" / "AGENT.md").is_file()
    assert (scoped_root / "life" / "career" / "spec.md").is_file()
    assert (scoped_root / "life" / "career" / "build-plan.md").is_file()
    assert (scoped_root / ".braindrive" / "schema-version.json").is_file()
    assert (scoped_root / "digest" / "_meta" / "rollup-state.json").is_file()

    second = mcp.bootstrap_user_library({}, _build_request(tmp_path))
    assert second["ok"] is True
    assert second["data"]["changed"] is False
    assert second["data"]["commitSha"] is None


def test_bootstrap_user_library_migrates_legacy_agents_file(tmp_path, monkeypatch):
    template_root = tmp_path / "template"
    _seed_template(template_root)
    (template_root / "life" / "finances" / "agents.md").write_text(
        "# Legacy Finances Agent\n", encoding="utf-8"
    )
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_BASE_TEMPLATE_PATH", str(template_root))

    result = mcp.bootstrap_user_library({}, _build_request(tmp_path))

    assert result["ok"] is True
    scoped_root = _scoped_root(tmp_path)
    assert (scoped_root / "life" / "finances" / "agents.md").is_file()
    assert (scoped_root / "life" / "finances" / "AGENT.md").is_file()
    assert "Legacy Finances Agent" in (
        scoped_root / "life" / "finances" / "AGENT.md"
    ).read_text(encoding="utf-8")


def test_save_topic_onboarding_context_requires_question_answer_pair(tmp_path, monkeypatch):
    template_root = tmp_path / "template"
    _seed_template(template_root)
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_BASE_TEMPLATE_PATH", str(template_root))

    request = _build_request(tmp_path)
    mcp.bootstrap_user_library({}, request)

    with pytest.raises(McpError) as excinfo:
        mcp.save_topic_onboarding_context(
            {
                "topic": "finances",
                "question": "What does success look like?",
                "context": "Initial onboarding context.",
                "approved": True,
            },
            request,
        )

    assert excinfo.value.error.code == "MISSING_FIELDS"


def test_topic_onboarding_lifecycle(tmp_path, monkeypatch):
    template_root = tmp_path / "template"
    _seed_template(template_root)
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_BASE_TEMPLATE_PATH", str(template_root))

    request = _build_request(tmp_path)
    mcp.bootstrap_user_library({}, request)

    initial = mcp.get_onboarding_state({}, request)
    assert initial["ok"] is True
    assert initial["data"]["state"]["starter_topics"]["finances"] == "not_started"
    assert "topic_progress" in initial["data"]["state"]
    assert initial["data"]["state"]["topic_progress"]["finances"]["phase"] == "not_started"
    assert isinstance(initial["data"]["state"].get("topic_queue"), list)

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
            "question": "What blockers are slowing progress?",
            "answer": "My spending tracking is inconsistent.",
            "context": "Budget baseline and debt plan.",
            "approved": True,
            "phase": "opening",
            "question_index": 1,
            "question_total": 6,
        },
        request,
    )
    assert saved["ok"] is True
    assert saved["data"]["status"] == "in_progress"
    assert saved["data"]["phase"] == "opening"
    assert len(saved["data"]["commitSha"]) == 40

    interview_content = (
        _scoped_root(tmp_path) / "life" / "finances" / "interview.md"
    ).read_text(encoding="utf-8")
    assert "Budget baseline and debt plan." in interview_content
    assert "What blockers are slowing progress?" in interview_content
    assert "My spending tracking is inconsistent." in interview_content

    agent_content = (
        _scoped_root(tmp_path) / "life" / "finances" / "AGENT.md"
    ).read_text(encoding="utf-8")
    assert "Approved User Context" in agent_content
    assert "Budget baseline and debt plan." in agent_content
    assert "What blockers are slowing progress?" in agent_content
    assert "My spending tracking is inconsistent." in agent_content

    completed = mcp.complete_topic_onboarding(
        {
            "topic": "finances",
            "summary": "Weekly budget review every Monday.",
            "next_followup_due_at_utc": "2026-03-01T00:00:00+00:00",
        },
        request,
    )
    assert completed["ok"] is True
    assert completed["data"]["status"] == "complete"
    assert completed["data"]["phase"] == "complete"
    assert completed["data"]["next_topic"] == "fitness"
    assert len(completed["data"]["commitSha"]) == 40

    final_state = mcp.get_onboarding_state({}, request)
    assert final_state["data"]["state"]["starter_topics"]["finances"] == "complete"
    progress = final_state["data"]["state"]["topic_progress"]["finances"]
    assert progress["phase"] == "complete"
    assert progress["next_followup_due_at_utc"] == "2026-03-01T00:00:00+00:00"
    assert final_state["data"]["state"]["recommended_next_topic"] == "fitness"

    action_plan = (
        _scoped_root(tmp_path) / "life" / "finances" / "action-plan.md"
    ).read_text(encoding="utf-8")
    assert "Onboarding Summary" in action_plan


def test_save_goals_phase_updates_current_goals_section(tmp_path, monkeypatch):
    template_root = tmp_path / "template"
    _seed_template(template_root)
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_BASE_TEMPLATE_PATH", str(template_root))

    request = _build_request(tmp_path)
    mcp.bootstrap_user_library({}, request)

    saved = mcp.save_topic_onboarding_context(
        {
            "topic": "finances",
            "question": "What initial goals or tasks do you want to set now?",
            "answer": "Goal: Pay $400 toward card balance by 2026-03-01. Task: track spending nightly.",
            "context": "Goal: Pay $400 toward card balance by 2026-03-01. Task: track spending nightly.",
            "approved": True,
            "phase": "goals_tasks",
            "question_index": 6,
            "question_total": 6,
        },
        request,
    )

    assert saved["ok"] is True
    goals_content = (
        _scoped_root(tmp_path) / "life" / "finances" / "goals.md"
    ).read_text(encoding="utf-8")
    assert "(to be populated during onboarding)" not in goals_content
    assert "- [ ] Goal: Pay $400 toward card balance by 2026-03-01" in goals_content
    assert "- [ ] Task: track spending nightly" in goals_content
    assert "## Approved Goals Context" in goals_content
