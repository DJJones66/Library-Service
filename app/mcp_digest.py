"""Digest helper endpoints."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Request

from app.errors import McpError, success_response
from app.mcp_activity import (
    _append_activity_log,
    _build_activity_entry,
    _read_activity_entries,
)
from app.mcp_git import _commit_markdown_changes, _ensure_git_repo
from app.mcp_payload import _ensure_payload_dict, _reject_unknown_fields
from app.mcp_router import mcp_router
from app.mcp_tasks import _filter_tasks, _load_completed_tasks, _load_tasks
from app.mcp_utils import _atomic_write
from app.user_scope import get_request_library_root


@mcp_router.post("/tool:digest_snapshot")
def digest_snapshot(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Return tasks, recent completions, and activity entries for digests."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(
        payload,
        {
            "owner",
            "priority",
            "tag",
            "project",
            "include_completed",
            "completed_limit",
            "activity_since",
            "activity_limit",
        },
    )

    owner = payload.get("owner")
    priority = payload.get("priority")
    tag = payload.get("tag")
    project = payload.get("project")

    include_completed = payload.get("include_completed", True)
    if not isinstance(include_completed, bool):
        raise McpError(
            "INVALID_TYPE",
            "include_completed must be a boolean.",
            {"include_completed": str(include_completed)},
        )

    completed_limit = payload.get("completed_limit", 10)
    if not isinstance(completed_limit, int) or completed_limit <= 0:
        raise McpError(
            "INVALID_TYPE",
            "completed_limit must be a positive integer.",
            {"completed_limit": str(completed_limit)},
        )

    activity_limit = payload.get("activity_limit", 50)
    if not isinstance(activity_limit, int) or activity_limit <= 0:
        raise McpError(
            "INVALID_TYPE",
            "activity_limit must be a positive integer.",
            {"activity_limit": str(activity_limit)},
        )

    activity_since_value = payload.get("activity_since")
    activity_since = None
    if activity_since_value is not None:
        try:
            activity_since = datetime.fromisoformat(str(activity_since_value))
        except ValueError:
            raise McpError(
                "INVALID_DATE",
                "activity_since must be ISO date-time.",
                {"activity_since": activity_since_value},
            )

    library_root = get_request_library_root(request)
    tasks = _filter_tasks(
        _load_tasks(library_root, "open"),
        owner,
        priority,
        tag,
        project,
    )

    completed: list[dict[str, Any]] = []
    if include_completed:
        completed_tasks = _load_completed_tasks(library_root, activity_since)
        completed = _filter_tasks(
            completed_tasks,
            owner,
            priority,
            tag,
            project,
        )[:completed_limit]

    activity_entries = _read_activity_entries(
        library_root, activity_since, activity_limit
    )

    return success_response(
        {
            "tasks": tasks,
            "completed": completed,
            "activity": activity_entries,
        }
    )


@mcp_router.post("/tool:score_digest_tasks")
def score_digest_tasks(
    payload: dict[str, Any], request: Request
) -> dict[str, Any]:
    """Score and rank tasks for digest display."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"tasks", "focus_project", "now"})

    if "tasks" not in payload:
        raise McpError(
            "MISSING_TASKS",
            "tasks is required.",
            {"fields": ["tasks"]},
        )

    tasks = payload["tasks"]
    if not isinstance(tasks, list):
        raise McpError(
            "INVALID_TYPE",
            "tasks must be a list.",
            {"tasks": str(tasks)},
        )

    focus_project = payload.get("focus_project")
    now_value = payload.get("now")
    now = datetime.now(timezone.utc)
    if now_value is not None:
        try:
            now = datetime.fromisoformat(str(now_value))
        except ValueError:
            raise McpError(
                "INVALID_DATE",
                "now must be ISO date-time.",
                {"now": now_value},
            )

    scored: list[dict[str, Any]] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        score, reasons = _score_task(task, focus_project, now)
        scored.append(
            {"task": task, "score": score, "reasons": reasons}
        )

    scored.sort(key=lambda item: item["score"], reverse=True)
    return success_response({"tasks": scored})


@mcp_router.post("/tool:rollup_digest_period")
def rollup_digest_period(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Rebuild a digest rollup period from daily canonical entries."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"period", "target_date"})

    if "period" not in payload:
        raise McpError(
            "MISSING_PERIOD",
            "period is required.",
            {"fields": ["period"]},
        )

    period = payload["period"]
    if not isinstance(period, str):
        raise McpError(
            "INVALID_TYPE",
            "period must be a string.",
            {"type": type(period).__name__},
        )
    period = period.strip().lower()
    if period not in {"week", "month", "year"}:
        raise McpError(
            "INVALID_PERIOD",
            "period must be one of week, month, or year.",
            {"period": period},
        )

    target_value = payload.get("target_date")
    target_date = date.today()
    if target_value is not None:
        if not isinstance(target_value, str):
            raise McpError(
                "INVALID_TYPE",
                "target_date must be a string in YYYY-MM-DD format.",
                {"type": type(target_value).__name__},
            )
        try:
            target_date = date.fromisoformat(target_value)
        except ValueError:
            raise McpError(
                "INVALID_DATE",
                "target_date must use YYYY-MM-DD format.",
                {"target_date": target_value},
            )

    library_root = get_request_library_root(request)
    result = _rollup_digest_period(library_root, period, target_date)
    return success_response(result)


def _score_task(
    task: dict[str, Any],
    focus_project: str | None,
    now: datetime,
) -> tuple[int, list[str]]:
    reasons: list[str] = []
    score = 0

    priority = task.get("priority") or "p2"
    priority_map = {"p0": 100, "p1": 70, "p2": 40, "p3": 20}
    priority_score = priority_map.get(priority, 10)
    score += priority_score
    reasons.append(f"priority:{priority}")

    project = task.get("project")
    if focus_project and project == focus_project:
        score += 10
        reasons.append("focus_project")

    tags = task.get("tags") or []
    if "blocked" in tags:
        score -= 100
        reasons.append("blocked")

    due = task.get("due")
    if due:
        try:
            due_date = datetime.fromisoformat(str(due))
            delta_days = (due_date - now).days
            if delta_days <= 0:
                score += 30
                reasons.append("due_overdue")
            elif delta_days <= 1:
                score += 25
                reasons.append("due_1d")
            elif delta_days <= 3:
                score += 20
                reasons.append("due_3d")
            elif delta_days <= 7:
                score += 10
                reasons.append("due_7d")
        except ValueError:
            reasons.append("due_invalid")

    return score, reasons


def _rollup_digest_period(
    library_root: Path, period: str, target_date: date
) -> dict[str, Any]:
    entries = _collect_daily_entries(library_root)
    period_entries = _filter_period_entries(entries, period, target_date)
    output_path, label = _period_output_path(library_root, period, target_date)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rendered = _render_rollup_content(period, label, period_entries, library_root)
    changed_paths: list[Path] = []

    previous = output_path.read_text(encoding="utf-8") if output_path.exists() else None
    if previous != rendered:
        _atomic_write(output_path, rendered)
        changed_paths.append(output_path.relative_to(library_root))

    state_path = library_root / "digest" / "_meta" / "rollup-state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = _read_rollup_state(state_path)

    now_iso = datetime.now(timezone.utc).isoformat()
    key_by_period = {
        "week": "last_weekly_rollup",
        "month": "last_monthly_rollup",
        "year": "last_yearly_rollup",
    }
    state[key_by_period[period]] = now_iso
    if period_entries:
        state["last_daily_ingest"] = period_entries[-1][0].isoformat()

    state_before = state_path.read_text(encoding="utf-8") if state_path.exists() else None
    state_after = json.dumps(state, indent=2) + "\n"
    if state_before != state_after:
        _atomic_write(state_path, state_after)
        changed_paths.append(state_path.relative_to(library_root))

    commit_sha = None
    if changed_paths:
        repo = _ensure_git_repo(library_root)
        try:
            commit_sha = _commit_markdown_changes(
                repo,
                changed_paths,
                "rollup_digest_period",
                output_path.relative_to(library_root),
            )
        except Exception as exc:
            raise McpError(
                "GIT_ERROR",
                "Git commit failed for digest rollup.",
                {"period": period, "path": output_path.relative_to(library_root).as_posix()},
            ) from exc

        entry = _build_activity_entry(
            "rollup_digest_period",
            output_path.relative_to(library_root),
            f"rollup digest {period}",
            commit_sha,
        )
        _append_activity_log(library_root, entry)

    return {
        "period": period,
        "label": label,
        "path": output_path.relative_to(library_root).as_posix(),
        "daily_count": len(period_entries),
        "changed": bool(changed_paths),
        "commitSha": commit_sha,
    }


def _collect_daily_entries(
    library_root: Path,
) -> list[tuple[date, Path, str]]:
    daily_root = library_root / "digest" / "daily"
    if not daily_root.exists():
        return []

    entries: list[tuple[date, Path, str]] = []
    for file_path in sorted(daily_root.rglob("*.md")):
        try:
            entry_date = date.fromisoformat(file_path.stem)
        except ValueError:
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError:
            continue
        entries.append((entry_date, file_path, content))

    entries.sort(key=lambda item: item[0])
    return entries


def _filter_period_entries(
    entries: list[tuple[date, Path, str]], period: str, target_date: date
) -> list[tuple[date, Path, str]]:
    if period == "week":
        target_year, target_week, _ = target_date.isocalendar()
        return [
            item
            for item in entries
            if item[0].isocalendar()[:2] == (target_year, target_week)
        ]

    if period == "month":
        return [
            item
            for item in entries
            if item[0].year == target_date.year and item[0].month == target_date.month
        ]

    return [item for item in entries if item[0].year == target_date.year]


def _period_output_path(
    library_root: Path, period: str, target_date: date
) -> tuple[Path, str]:
    if period == "week":
        year, week, _ = target_date.isocalendar()
        label = f"{year:04d}-W{week:02d}"
        return (
            library_root / "digest" / "weekly" / f"{year:04d}" / f"{label}.md",
            label,
        )

    if period == "month":
        label = f"{target_date.year:04d}-{target_date.month:02d}"
        return (
            library_root
            / "digest"
            / "monthly"
            / f"{target_date.year:04d}"
            / f"{label}.md",
            label,
        )

    label = f"{target_date.year:04d}"
    return (library_root / "digest" / "yearly" / f"{label}.md", label)


def _render_rollup_content(
    period: str,
    label: str,
    entries: list[tuple[date, Path, str]],
    library_root: Path,
) -> str:
    header_by_period = {
        "week": "Weekly",
        "month": "Monthly",
        "year": "Yearly",
    }
    lines = [f"# {header_by_period[period]} Digest {label}", ""]
    lines.append("## Source Daily Entries")
    if not entries:
        lines.extend(["", "- (none)", ""])
        return "\n".join(lines).rstrip() + "\n"

    for entry_date, entry_path, content in entries:
        relative = entry_path.relative_to(library_root).as_posix()
        lines.append("")
        lines.append(f"### {entry_date.isoformat()} ({relative})")
        lines.append("")
        body = content.strip()
        if not body:
            lines.append("_empty_")
            continue
        lines.append(body)

    return "\n".join(lines).rstrip() + "\n"


def _read_rollup_state(state_path: Path) -> dict[str, Any]:
    default_state = {
        "version": 1,
        "last_daily_ingest": None,
        "last_weekly_rollup": None,
        "last_monthly_rollup": None,
        "last_yearly_rollup": None,
    }
    if not state_path.exists():
        return default_state

    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_state

    if not isinstance(raw, dict):
        return default_state

    for key in default_state:
        if key == "version":
            if isinstance(raw.get(key), int):
                default_state[key] = raw[key]
            continue
        value = raw.get(key)
        default_state[key] = value if isinstance(value, str) or value is None else None

    return default_state
