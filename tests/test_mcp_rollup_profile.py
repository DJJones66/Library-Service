from datetime import date
from types import SimpleNamespace

from app import mcp

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
    (template_root / "me" / "profile.md").write_text("# Profile\n", encoding="utf-8")
    (template_root / ".braindrive").mkdir(parents=True, exist_ok=True)
    (template_root / ".braindrive" / "onboarding_state.json").write_text("{}\n", encoding="utf-8")


def test_rollup_digest_period_rebuilds_from_daily_entries(tmp_path, monkeypatch):
    template_root = tmp_path / "template"
    _seed_template(template_root)
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_BASE_TEMPLATE_PATH", str(template_root))

    request = _build_request(tmp_path)
    mcp.bootstrap_user_library({}, request)

    scoped_root = _scoped_root(tmp_path)
    target = date(2026, 2, 12)

    for day in (10, 12):
        entry_date = date(2026, 2, day)
        daily_path = (
            scoped_root
            / "digest"
            / "daily"
            / f"{entry_date.year:04d}"
            / f"{entry_date.month:02d}"
            / f"{entry_date.isoformat()}.md"
        )
        daily_path.parent.mkdir(parents=True, exist_ok=True)
        daily_path.write_text(
            f"# Daily Digest {entry_date.isoformat()}\n\nEntry {day}\n",
            encoding="utf-8",
        )

    weekly = mcp.rollup_digest_period(
        {"period": "week", "target_date": target.isoformat()}, request
    )
    assert weekly["ok"] is True
    assert weekly["data"]["period"] == "week"
    assert len(weekly["data"]["commitSha"]) == 40

    iso_year, iso_week, _ = target.isocalendar()
    weekly_path = (
        scoped_root
        / "digest"
        / "weekly"
        / f"{iso_year:04d}"
        / f"{iso_year:04d}-W{iso_week:02d}.md"
    )
    weekly_content = weekly_path.read_text(encoding="utf-8")
    assert "Entry 10" in weekly_content
    assert "Entry 12" in weekly_content

    monthly = mcp.rollup_digest_period(
        {"period": "month", "target_date": target.isoformat()}, request
    )
    assert monthly["ok"] is True
    assert len(monthly["data"]["commitSha"]) == 40

    yearly = mcp.rollup_digest_period(
        {"period": "year", "target_date": target.isoformat()}, request
    )
    assert yearly["ok"] is True
    assert len(yearly["data"]["commitSha"]) == 40


def test_rebuild_profile_context_uses_onboarding_facts(tmp_path, monkeypatch):
    template_root = tmp_path / "template"
    _seed_template(template_root)
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_BASE_TEMPLATE_PATH", str(template_root))

    request = _build_request(tmp_path)
    mcp.bootstrap_user_library({}, request)

    mcp.save_topic_onboarding_context(
        {
            "topic": "finances",
            "context": "Budget baseline and debt payoff strategy.",
            "approved": True,
        },
        request,
    )

    rebuilt = mcp.rebuild_profile_context(
        {"facts": ["Prefer morning workouts"]},
        request,
    )

    assert rebuilt["ok"] is True
    assert rebuilt["data"]["fact_count"] >= 2
    assert len(rebuilt["data"]["commitSha"]) == 40

    profile_content = (_scoped_root(tmp_path) / "me" / "profile.md").read_text(
        encoding="utf-8"
    )
    assert "Prefer morning workouts" in profile_content
    assert "Budget baseline and debt payoff strategy." in profile_content
