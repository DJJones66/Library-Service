"""Onboarding and library bootstrap MCP endpoints."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from fastapi import Request

from app.errors import McpError, success_response
from app.library_schema import (
    TOPIC_ORDER,
    TOPIC_TITLES,
    ensure_scoped_library_structure,
    next_incomplete_topic as schema_next_incomplete_topic,
    persist_onboarding_state as schema_persist_onboarding_state,
    read_onboarding_state as schema_read_onboarding_state,
    topic_file_path as schema_topic_file_path,
    validate_topic as schema_validate_topic,
)
from app.mcp_activity import _append_activity_log, _build_activity_entry
from app.mcp_git import _commit_markdown_changes, _ensure_git_repo
from app.mcp_payload import _ensure_payload_dict, _reject_unknown_fields
from app.mcp_router import mcp_router
from app.mcp_utils import _atomic_write, _join_with_newline
from app.user_scope import get_request_library_root

ENV_BASE_TEMPLATE_PATH = "BRAINDRIVE_LIBRARY_BASE_TEMPLATE_PATH"
ONBOARDING_PHASE_VALUES = {
    "not_started",
    "opening",
    "goals_tasks",
    "followup",
    "complete",
}


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _normalize_phase(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in ONBOARDING_PHASE_VALUES:
        return normalized
    return None


def _normalize_nonempty_timestamp(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_future_topics(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    parsed: list[str] = []
    for item in values:
        if not isinstance(item, str):
            continue
        normalized = item.strip().lower()
        if normalized in TOPIC_ORDER and normalized not in parsed:
            parsed.append(normalized)
    return parsed


def _extract_goals_context_entries(context_text: str) -> list[str]:
    if not isinstance(context_text, str):
        return []
    text = context_text.strip()
    if not text:
        return []

    entries: list[str] = []
    labeled = re.findall(
        r"(?is)\b(goal|task)\s*:\s*(.+?)(?=(?:\bgoal\b\s*:|\btask\b\s*:)|$)",
        text,
    )
    if labeled:
        for kind, raw_value in labeled:
            cleaned = " ".join(raw_value.split()).strip(" .;,-")
            if cleaned:
                entries.append(f"{kind.capitalize()}: {cleaned}")
        return entries

    for raw_line in text.splitlines():
        cleaned = re.sub(r"^[\-\*\d\.\)\s]+", "", raw_line.strip())
        cleaned = " ".join(cleaned.split()).strip(" .;,-")
        if cleaned:
            entries.append(cleaned)
    if entries:
        return entries

    return [text]


def _upsert_current_goals_markdown(existing_markdown: str, entries: list[str]) -> str:
    if not entries:
        return existing_markdown

    lines = existing_markdown.splitlines()
    placeholder_pattern = re.compile(
        r"^\s*-\s*\(to be populated during onboarding\)\s*$",
        flags=re.IGNORECASE,
    )
    lines = [line for line in lines if not placeholder_pattern.match(line)]

    current_goals_index: int | None = None
    for idx, line in enumerate(lines):
        if line.strip().lower() == "## current goals":
            current_goals_index = idx
            break

    if current_goals_index is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("## Current Goals")
        lines.append("")
        current_goals_index = len(lines) - 3

    insertion_index = current_goals_index + 1
    if insertion_index < len(lines) and lines[insertion_index].strip():
        lines.insert(insertion_index, "")
        insertion_index += 1
    while insertion_index < len(lines) and lines[insertion_index].strip() == "":
        insertion_index += 1

    existing_set = {line.strip() for line in lines if line.strip().startswith("- [ ] ")}
    new_lines: list[str] = []
    for entry in entries:
        bullet = f"- [ ] {entry}"
        if bullet in existing_set:
            continue
        existing_set.add(bullet)
        new_lines.append(bullet)

    if not new_lines:
        return "\n".join(lines).rstrip() + "\n"

    lines[insertion_index:insertion_index] = new_lines + [""]
    return "\n".join(lines).rstrip() + "\n"


def _ensure_topic_progress(state: dict[str, Any], topic: str) -> dict[str, Any]:
    progress_map = state.setdefault("topic_progress", {})
    if not isinstance(progress_map, dict):
        progress_map = {}
        state["topic_progress"] = progress_map
    existing = progress_map.get(topic)
    if isinstance(existing, dict):
        return existing

    initialized = {
        "status": state.get("starter_topics", {}).get(topic, "not_started"),
        "phase": "not_started",
        "started_at_utc": None,
        "last_interview_at_utc": None,
        "completed_at_utc": None,
        "next_followup_due_at_utc": None,
        "question_total": 0,
        "question_index": 0,
        "followup_cycles": 0,
        "future_interview_topics": [],
        "last_updated_at_utc": _utc_now_iso(),
    }
    progress_map[topic] = initialized
    return initialized


def _append_topic_history(
    state: dict[str, Any],
    *,
    topic: str,
    event: str,
    from_status: str | None = None,
    to_status: str | None = None,
    detail: str | None = None,
) -> None:
    history = state.setdefault("topic_history", [])
    if not isinstance(history, list):
        history = []
        state["topic_history"] = history

    entry: dict[str, Any] = {
        "topic": topic,
        "event": event,
        "at_utc": _utc_now_iso(),
    }
    if isinstance(from_status, str) and from_status:
        entry["from_status"] = from_status
    if isinstance(to_status, str) and to_status:
        entry["to_status"] = to_status
    if isinstance(detail, str) and detail.strip():
        entry["detail"] = detail.strip()
    history.append(entry)
    if len(history) > 200:
        del history[:-200]


def _refresh_onboarding_summary_fields(state: dict[str, Any]) -> None:
    starter_topics = state.get("starter_topics")
    if not isinstance(starter_topics, dict):
        starter_topics = {}
        state["starter_topics"] = starter_topics

    completed = state.get("completed_at")
    if not isinstance(completed, dict):
        completed = {}
        state["completed_at"] = completed

    progress_map = state.get("topic_progress")
    if not isinstance(progress_map, dict):
        progress_map = {}
        state["topic_progress"] = progress_map

    for topic in TOPIC_ORDER:
        progress = _ensure_topic_progress(state, topic)
        status = progress.get("status")
        if status not in {"not_started", "in_progress", "complete"}:
            status = starter_topics.get(topic, "not_started")
        if status not in {"not_started", "in_progress", "complete"}:
            status = "not_started"
        starter_topics[topic] = status
        progress["status"] = status

        if status == "complete":
            completed_stamp = progress.get("completed_at_utc")
            if isinstance(completed_stamp, str) and completed_stamp:
                completed[topic] = completed_stamp
            elif topic not in completed:
                completed[topic] = _utc_now_iso()
        else:
            completed.pop(topic, None)

    state["recommended_next_topic"] = _next_incomplete_topic(state)
    state["topic_queue"] = [topic for topic in TOPIC_ORDER if starter_topics.get(topic) != "complete"]
    state["active_topic"] = (
        state["active_topic"]
        if isinstance(state.get("active_topic"), str) and state["active_topic"] in TOPIC_ORDER
        else None
    )
    state.setdefault("created_at_utc", _utc_now_iso())
    state["updated_at_utc"] = _utc_now_iso()


@mcp_router.post("/tool:bootstrap_user_library")
def bootstrap_user_library(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Ensure the scoped user library has the onboarding scaffold."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, set())

    library_root = get_request_library_root(request)
    changed_paths = _bootstrap_user_library(library_root)
    commit_sha = _commit_mutation(
        library_root,
        changed_paths,
        operation="bootstrap_user_library",
        target_path=Path(".braindrive/onboarding_state.json"),
        summary="bootstrap user library",
    )

    return success_response(
        {
            "changed": bool(changed_paths),
            "changed_paths": [path.as_posix() for path in changed_paths],
            "commitSha": commit_sha,
        }
    )


@mcp_router.post("/tool:get_onboarding_state")
def get_onboarding_state(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Return the current onboarding status by starter topic."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, set())

    library_root = get_request_library_root(request)
    state = _read_onboarding_state(library_root)
    return success_response(
        {
            "state": state,
            "next_topic": _next_incomplete_topic(state),
        }
    )


@mcp_router.post("/tool:start_topic_onboarding")
def start_topic_onboarding(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Mark a topic onboarding flow as in-progress and return interview seed."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"topic"})

    if "topic" not in payload:
        raise McpError("MISSING_TOPIC", "topic is required.", {"fields": ["topic"]})

    topic = _validate_topic(payload["topic"])
    library_root = get_request_library_root(request)

    changed_paths = _bootstrap_user_library(library_root)
    state = _read_onboarding_state(library_root)

    current_status = state.get("starter_topics", {}).get(topic, "not_started")
    progress = _ensure_topic_progress(state, topic)
    now_iso = _utc_now_iso()

    if current_status != "complete":
        if current_status != "in_progress":
            _append_topic_history(
                state,
                topic=topic,
                event="start_onboarding",
                from_status=current_status,
                to_status="in_progress",
            )
        state.setdefault("starter_topics", {})[topic] = "in_progress"
        progress["status"] = "in_progress"
        progress["phase"] = "opening"
        progress["started_at_utc"] = progress.get("started_at_utc") or now_iso
    progress["last_interview_at_utc"] = now_iso
    progress["last_updated_at_utc"] = now_iso
    state["active_topic"] = topic
    _refresh_onboarding_summary_fields(state)

    state_changed = _persist_onboarding_state(library_root, state)
    if state_changed is not None:
        changed_paths.append(state_changed)

    interview_path = _topic_file_path(library_root, topic, "interview.md")
    interview_seed = interview_path.read_text(encoding="utf-8")

    commit_sha = _commit_mutation(
        library_root,
        changed_paths,
        operation="start_topic_onboarding",
        target_path=interview_path.relative_to(library_root),
        summary=f"start topic onboarding ({topic})",
    )

    state = _read_onboarding_state(library_root)
    return success_response(
        {
            "topic": topic,
            "status": state["starter_topics"][topic],
            "interview_seed": interview_seed,
            "next_topic": _next_incomplete_topic(state),
            "commitSha": commit_sha,
        }
    )


@mcp_router.post("/tool:save_topic_onboarding_context")
def save_topic_onboarding_context(
    payload: dict[str, Any], request: Request
) -> dict[str, Any]:
    """Persist approved onboarding interview context into topic docs."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(
        payload,
        {
            "topic",
            "context",
            "approved",
            "question",
            "answer",
            "phase",
            "question_index",
            "question_total",
            "next_followup_due_at_utc",
            "future_interview_topics",
        },
    )

    missing = [field for field in ("topic", "context", "approved") if field not in payload]
    if missing:
        raise McpError("MISSING_FIELDS", "topic, context, and approved are required.", {"fields": missing})

    topic = _validate_topic(payload["topic"])
    context = payload["context"]
    approved = payload["approved"]
    question = payload.get("question")
    answer = payload.get("answer")
    phase_value = payload.get("phase")
    question_index = payload.get("question_index")
    question_total = payload.get("question_total")
    next_followup_due_at = payload.get("next_followup_due_at_utc")
    future_interview_topics = payload.get("future_interview_topics")

    if not isinstance(context, str) or not context.strip():
        raise McpError(
            "INVALID_TYPE",
            "context must be a non-empty string.",
            {"type": type(context).__name__},
        )
    if not isinstance(approved, bool):
        raise McpError(
            "INVALID_TYPE",
            "approved must be a boolean.",
            {"type": type(approved).__name__},
        )
    if not approved:
        raise McpError(
            "APPROVAL_REQUIRED",
            "approved=true is required for mutating onboarding context writes.",
            {"topic": topic},
        )

    if question is not None and (not isinstance(question, str) or not question.strip()):
        raise McpError(
            "INVALID_TYPE",
            "question must be a non-empty string when provided.",
            {"type": type(question).__name__},
        )
    if answer is not None and (not isinstance(answer, str) or not answer.strip()):
        raise McpError(
            "INVALID_TYPE",
            "answer must be a non-empty string when provided.",
            {"type": type(answer).__name__},
        )
    if question_index is not None and (not isinstance(question_index, int) or question_index < 0):
        raise McpError(
            "INVALID_TYPE",
            "question_index must be a non-negative integer when provided.",
            {"type": type(question_index).__name__},
        )
    if question_total is not None and (not isinstance(question_total, int) or question_total < 0):
        raise McpError(
            "INVALID_TYPE",
            "question_total must be a non-negative integer when provided.",
            {"type": type(question_total).__name__},
        )
    normalized_phase = _normalize_phase(phase_value) if phase_value is not None else None
    if phase_value is not None and normalized_phase is None:
        raise McpError(
            "INVALID_TYPE",
            "phase must be one of: not_started, opening, goals_tasks, followup, complete.",
            {"phase": phase_value},
        )
    normalized_followup_due = (
        _normalize_nonempty_timestamp(next_followup_due_at)
        if next_followup_due_at is not None
        else None
    )
    if next_followup_due_at is not None and normalized_followup_due is None:
        raise McpError(
            "INVALID_TYPE",
            "next_followup_due_at_utc must be a non-empty timestamp string when provided.",
            {"type": type(next_followup_due_at).__name__},
        )
    normalized_future_topics = _normalize_future_topics(future_interview_topics)
    if future_interview_topics is not None and not isinstance(future_interview_topics, list):
        raise McpError(
            "INVALID_TYPE",
            "future_interview_topics must be a list of topic slugs when provided.",
            {"type": type(future_interview_topics).__name__},
        )

    has_question = isinstance(question, str) and bool(question.strip())
    has_answer = isinstance(answer, str) and bool(answer.strip())
    if has_question != has_answer:
        missing_pair = ["answer"] if has_question else ["question"]
        raise McpError(
            "MISSING_FIELDS",
            "question and answer must be provided together when logging interview Q/A.",
            {"fields": missing_pair},
        )

    context_text = context.strip()
    question_text = question.strip() if has_question else None
    answer_text = answer.strip() if has_answer else None

    library_root = get_request_library_root(request)
    changed_paths = _bootstrap_user_library(library_root)

    interview_path = _topic_file_path(library_root, topic, "interview.md")
    existing = interview_path.read_text(encoding="utf-8")
    stamp = dt.datetime.now(dt.timezone.utc).isoformat()

    if question_text and answer_text:
        interview_section = (
            f"## Approved Interview Turn {stamp}\n\n"
            f"- Question: {question_text}\n"
            f"- Answer: {answer_text}\n"
            f"- Context Summary: {context_text}\n"
        )
    else:
        interview_section = f"## Approved Context {stamp}\n\n{context_text}\n"

    updated = _join_with_newline(existing, interview_section)
    _atomic_write(interview_path, updated)
    changed_paths.append(interview_path.relative_to(library_root))

    agent_path = _topic_file_path(library_root, topic, "AGENT.md")
    agent_existing = (
        agent_path.read_text(encoding="utf-8")
        if agent_path.exists()
        else f"# {TOPIC_TITLES[topic]} Agent\n\n"
    )

    if question_text and answer_text:
        agent_section = (
            f"## Approved User Context {stamp}\n\n"
            f"- Question: {question_text}\n"
            f"- Answer: {answer_text}\n"
            f"- Context Summary: {context_text}\n"
        )
    else:
        agent_section = f"## Approved User Context {stamp}\n\n{context_text}\n"

    agent_updated = _join_with_newline(agent_existing, agent_section)
    _atomic_write(agent_path, agent_updated)
    changed_paths.append(agent_path.relative_to(library_root))

    # Legacy compatibility: keep legacy agents.md in sync when it already exists.
    legacy_agent_path = _topic_file_path(library_root, topic, "agents.md")
    if legacy_agent_path.exists():
        _atomic_write(legacy_agent_path, agent_updated)
        changed_paths.append(legacy_agent_path.relative_to(library_root))

    if normalized_phase == "goals_tasks":
        goals_path = _topic_file_path(library_root, topic, "goals.md")
        goals_existing = goals_path.read_text(encoding="utf-8")
        goals_entries = _extract_goals_context_entries(context_text)
        goals_updated = _upsert_current_goals_markdown(goals_existing, goals_entries)
        goals_section = (
            f"## Approved Goals Context {stamp}\n\n"
            f"{context_text}\n"
        )
        _atomic_write(goals_path, _join_with_newline(goals_updated, goals_section))
        changed_paths.append(goals_path.relative_to(library_root))

        action_plan_path = _topic_file_path(library_root, topic, "action-plan.md")
        action_existing = action_plan_path.read_text(encoding="utf-8")
        action_section = (
            f"## Approved Onboarding Goals/Tasks Context {stamp}\n\n"
            f"{context_text}\n"
        )
        _atomic_write(action_plan_path, _join_with_newline(action_existing, action_section))
        changed_paths.append(action_plan_path.relative_to(library_root))

    state = _read_onboarding_state(library_root)
    progress = _ensure_topic_progress(state, topic)
    previous_status = state.get("starter_topics", {}).get(topic, "not_started")
    if previous_status != "complete":
        state.setdefault("starter_topics", {})[topic] = "in_progress"
        progress["status"] = "in_progress"
        if previous_status != "in_progress":
            _append_topic_history(
                state,
                topic=topic,
                event="context_status_progressed",
                from_status=previous_status,
                to_status="in_progress",
            )
    progress["phase"] = normalized_phase or progress.get("phase") or "opening"
    progress["last_interview_at_utc"] = _utc_now_iso()
    progress["last_updated_at_utc"] = _utc_now_iso()
    if question_index is not None:
        progress["question_index"] = question_index
    if question_total is not None:
        progress["question_total"] = question_total
    if normalized_followup_due is not None:
        progress["next_followup_due_at_utc"] = normalized_followup_due
    if normalized_future_topics:
        progress["future_interview_topics"] = normalized_future_topics
    state["active_topic"] = topic
    _append_topic_history(
        state,
        topic=topic,
        event="approved_context_saved",
        detail=normalized_phase or "opening",
    )
    _refresh_onboarding_summary_fields(state)
    state_changed = _persist_onboarding_state(library_root, state)
    if state_changed is not None:
        changed_paths.append(state_changed)

    commit_sha = _commit_mutation(
        library_root,
        changed_paths,
        operation="save_topic_onboarding_context",
        target_path=interview_path.relative_to(library_root),
        summary=f"save onboarding context ({topic})",
    )

    return success_response(
        {
            "topic": topic,
            "path": interview_path.relative_to(library_root).as_posix(),
            "status": state["starter_topics"][topic],
            "phase": progress.get("phase"),
            "commitSha": commit_sha,
        }
    )


@mcp_router.post("/tool:complete_topic_onboarding")
def complete_topic_onboarding(
    payload: dict[str, Any], request: Request
) -> dict[str, Any]:
    """Mark a topic onboarding flow complete and recommend the next topic."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(
        payload,
        {"topic", "summary", "next_followup_due_at_utc", "future_interview_topics"},
    )

    if "topic" not in payload:
        raise McpError("MISSING_TOPIC", "topic is required.", {"fields": ["topic"]})

    topic = _validate_topic(payload["topic"])
    summary_value = payload.get("summary")
    next_followup_due_at = payload.get("next_followup_due_at_utc")
    future_interview_topics = payload.get("future_interview_topics")
    if summary_value is not None and not isinstance(summary_value, str):
        raise McpError(
            "INVALID_TYPE",
            "summary must be a string.",
            {"type": type(summary_value).__name__},
        )
    normalized_followup_due = (
        _normalize_nonempty_timestamp(next_followup_due_at)
        if next_followup_due_at is not None
        else None
    )
    if next_followup_due_at is not None and normalized_followup_due is None:
        raise McpError(
            "INVALID_TYPE",
            "next_followup_due_at_utc must be a non-empty timestamp string when provided.",
            {"type": type(next_followup_due_at).__name__},
        )
    if future_interview_topics is not None and not isinstance(future_interview_topics, list):
        raise McpError(
            "INVALID_TYPE",
            "future_interview_topics must be a list of topic slugs when provided.",
            {"type": type(future_interview_topics).__name__},
        )
    normalized_future_topics = _normalize_future_topics(future_interview_topics)

    library_root = get_request_library_root(request)
    changed_paths = _bootstrap_user_library(library_root)

    state = _read_onboarding_state(library_root)
    previous_status = state.get("starter_topics", {}).get(topic, "not_started")
    now_iso = _utc_now_iso()
    state.setdefault("starter_topics", {})[topic] = "complete"
    state.setdefault("completed_at", {})[topic] = now_iso
    progress = _ensure_topic_progress(state, topic)
    progress["status"] = "complete"
    progress["phase"] = "complete"
    progress["completed_at_utc"] = now_iso
    progress["last_interview_at_utc"] = now_iso
    progress["last_updated_at_utc"] = now_iso
    progress["question_index"] = max(progress.get("question_index") or 0, progress.get("question_total") or 0)
    if normalized_followup_due is not None:
        progress["next_followup_due_at_utc"] = normalized_followup_due
    if normalized_future_topics:
        progress["future_interview_topics"] = normalized_future_topics
    state["active_topic"] = None
    _append_topic_history(
        state,
        topic=topic,
        event="complete_onboarding",
        from_status=previous_status,
        to_status="complete",
    )
    _refresh_onboarding_summary_fields(state)
    state_changed = _persist_onboarding_state(library_root, state)
    if state_changed is not None:
        changed_paths.append(state_changed)

    action_plan_path = _topic_file_path(library_root, topic, "action-plan.md")
    if isinstance(summary_value, str) and summary_value.strip():
        current = action_plan_path.read_text(encoding="utf-8")
        summary_block = (
            f"## Onboarding Summary {dt.datetime.now(dt.timezone.utc).date().isoformat()}\n\n"
            f"{summary_value.strip()}\n"
        )
        _atomic_write(action_plan_path, _join_with_newline(current, summary_block))
        changed_paths.append(action_plan_path.relative_to(library_root))

    commit_sha = _commit_mutation(
        library_root,
        changed_paths,
        operation="complete_topic_onboarding",
        target_path=action_plan_path.relative_to(library_root),
        summary=f"complete topic onboarding ({topic})",
    )

    state = _read_onboarding_state(library_root)
    return success_response(
        {
            "topic": topic,
            "status": state["starter_topics"][topic],
            "phase": progress.get("phase"),
            "next_topic": _next_incomplete_topic(state),
            "commitSha": commit_sha,
        }
    )


APPROVED_CONTEXT_BLOCK_PATTERN = re.compile(
    r"^## Approved (?:Context|Interview Turn|User Context)[^\n]*\n(?P<body>.*?)(?=^## |\Z)",
    flags=re.MULTILINE | re.DOTALL,
)


@mcp_router.post("/tool:rebuild_profile_context")
def rebuild_profile_context(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Rebuild `me/profile.md` from approved onboarding facts."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"facts", "topics"})

    raw_facts = payload.get("facts")
    if raw_facts is not None and not isinstance(raw_facts, list):
        raise McpError(
            "INVALID_TYPE",
            "facts must be a list of strings.",
            {"type": type(raw_facts).__name__},
        )

    topics_filter = payload.get("topics")
    if topics_filter is not None:
        if not isinstance(topics_filter, list) or any(
            not isinstance(item, str) for item in topics_filter
        ):
            raise McpError(
                "INVALID_TYPE",
                "topics must be a list of topic strings.",
                {"type": type(topics_filter).__name__},
            )
        topics = [_validate_topic(item) for item in topics_filter]
    else:
        topics = list(TOPIC_ORDER)

    library_root = get_request_library_root(request)
    changed_paths = _bootstrap_user_library(library_root)

    extracted_facts = _extract_profile_facts_from_topics(library_root, topics)
    explicit_facts = _normalize_fact_list(raw_facts or [])

    merged_facts: list[str] = []
    for fact in explicit_facts + extracted_facts:
        if fact not in merged_facts:
            merged_facts.append(fact)

    profile_path = library_root / "me" / "profile.md"
    rendered_profile = _render_profile_context(merged_facts)
    existing_profile = profile_path.read_text(encoding="utf-8") if profile_path.exists() else None
    if existing_profile != rendered_profile:
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(profile_path, rendered_profile)
        changed_paths.append(profile_path.relative_to(library_root))

    commit_sha = _commit_mutation(
        library_root,
        changed_paths,
        operation="rebuild_profile_context",
        target_path=Path("me/profile.md"),
        summary="rebuild profile context",
    )

    return success_response(
        {
            "path": "me/profile.md",
            "fact_count": len(merged_facts),
            "facts": merged_facts,
            "changed": bool(changed_paths),
            "commitSha": commit_sha,
        }
    )


def _extract_profile_facts_from_topics(
    library_root: Path, topics: list[str]
) -> list[str]:
    facts: list[str] = []
    for topic in topics:
        interview_path = _topic_file_path(library_root, topic, "interview.md")
        if not interview_path.exists():
            continue
        try:
            content = interview_path.read_text(encoding="utf-8")
        except OSError:
            continue

        for match in APPROVED_CONTEXT_BLOCK_PATTERN.finditer(content):
            body = match.group("body").strip()
            if not body:
                continue
            normalized = " ".join(line.strip() for line in body.splitlines() if line.strip())
            if not normalized:
                continue
            facts.append(f"[{TOPIC_TITLES[topic]}] {normalized}")
    return facts


def _normalize_fact_list(raw_facts: list[Any]) -> list[str]:
    facts: list[str] = []
    for value in raw_facts:
        if not isinstance(value, str):
            continue
        normalized = value.strip()
        if not normalized:
            continue
        facts.append(normalized)
    return facts


def _render_profile_context(facts: list[str]) -> str:
    lines = [
        "# Profile",
        "",
        "## Identity",
        "",
        "## Goals",
        "",
        "## Constraints",
        "",
        "## Preferences",
        "",
        "## Onboarding Facts",
        "",
    ]

    if not facts:
        lines.append("- (no approved onboarding facts yet)")
    else:
        for fact in facts:
            lines.append(f"- {fact}")

    lines.extend(
        [
            "",
            "## Last Updated",
            "",
            f"- {dt.datetime.now(dt.timezone.utc).isoformat()}",
            "",
        ]
    )
    return "\n".join(lines)


def _bootstrap_user_library(library_root: Path) -> list[Path]:
    changed_paths: list[Path] = []

    template_root = _resolve_template_root()
    if template_root is not None:
        changed_paths.extend(_copy_template_idempotent(template_root, library_root))

    schema_result = ensure_scoped_library_structure(library_root)
    changed_paths.extend(schema_result.changed_paths)

    unique: dict[str, Path] = {}
    for path in changed_paths:
        unique[path.as_posix()] = path
    return [unique[key] for key in sorted(unique.keys())]


def _resolve_template_root() -> Path | None:
    raw = os.environ.get(ENV_BASE_TEMPLATE_PATH, "").strip()
    if raw:
        candidate = Path(raw).expanduser().resolve()
        if not candidate.is_dir():
            raise McpError(
                "INVALID_TEMPLATE_PATH",
                "Configured base template path does not exist.",
                {"path": raw},
            )
        return candidate
    service_fallback = (
        Path(__file__).resolve().parents[1]
        / "library_templates"
        / "Base_Library"
    )
    if service_fallback.is_dir():
        return service_fallback

    legacy_fallback = Path(__file__).resolve().parents[3] / "library_templates" / "Base_Library"
    if legacy_fallback.is_dir():
        return legacy_fallback
    return None


def _copy_template_idempotent(source_root: Path, destination_root: Path) -> list[Path]:
    changed: list[Path] = []
    for source in sorted(source_root.rglob("*")):
        relative = source.relative_to(source_root)
        target = destination_root / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if not source.is_file():
            continue
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        changed.append(relative)
    return changed


def _read_onboarding_state(library_root: Path) -> dict[str, Any]:
    return schema_read_onboarding_state(library_root)


def _persist_onboarding_state(library_root: Path, state: dict[str, Any]) -> Path | None:
    return schema_persist_onboarding_state(library_root, state)


def _topic_file_path(library_root: Path, topic: str, filename: str) -> Path:
    return schema_topic_file_path(library_root, topic, filename)


def _validate_topic(value: Any) -> str:
    try:
        return schema_validate_topic(value)
    except ValueError as exc:
        if not isinstance(value, str):
            raise McpError(
                "INVALID_TYPE",
                "topic must be a string.",
                {"type": type(value).__name__},
            ) from exc
        raise McpError(
            "INVALID_TOPIC",
            "Unsupported onboarding topic.",
            {"topic": value, "allowed": list(TOPIC_ORDER)},
        ) from exc


def _next_incomplete_topic(state: dict[str, Any]) -> str | None:
    return schema_next_incomplete_topic(state)


def _commit_mutation(
    library_root: Path,
    changed_paths: list[Path],
    *,
    operation: str,
    target_path: Path,
    summary: str,
) -> str | None:
    if not changed_paths:
        return None

    unique: dict[str, Path] = {}
    for path in changed_paths:
        unique[path.as_posix()] = path
    staged_paths = [unique[key] for key in sorted(unique.keys())]

    repo = _ensure_git_repo(library_root)
    try:
        commit_sha = _commit_markdown_changes(
            repo,
            staged_paths,
            operation,
            target_path,
        )
    except Exception as exc:
        raise McpError(
            "GIT_ERROR",
            "Git commit failed for onboarding mutation.",
            {"operation": operation},
        ) from exc

    entry = _build_activity_entry(operation, target_path, summary, commit_sha)
    _append_activity_log(library_root, entry)
    return commit_sha
