"""Onboarding and library bootstrap MCP endpoints."""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import re
from pathlib import Path
from typing import Any

from fastapi import Request

from app.errors import McpError, success_response
from app.mcp_activity import _append_activity_log, _build_activity_entry
from app.mcp_git import _commit_markdown_changes, _ensure_git_repo
from app.mcp_payload import _ensure_payload_dict, _reject_unknown_fields
from app.mcp_router import mcp_router
from app.mcp_utils import _atomic_write, _join_with_newline
from app.user_scope import get_request_library_root

ENV_BASE_TEMPLATE_PATH = "BRAINDRIVE_LIBRARY_BASE_TEMPLATE_PATH"
TOPIC_ORDER = ("finances", "fitness", "relationships", "career", "whyfinder")
TOPIC_TITLES = {
    "finances": "Finances",
    "fitness": "Fitness",
    "relationships": "Relationships",
    "career": "Career",
    "whyfinder": "WhyFinder",
}

REQUIRED_DIRS = (
    "capture/inbox",
    "projects/active",
    "projects/archived",
    "digest/daily",
    "digest/weekly",
    "digest/monthly",
    "digest/yearly",
    "digest/_meta",
    "transcripts",
    "share/templates",
    "share/exports",
)

REQUIRED_TEXT_FILES = {
    "me/profile.md": "# Profile\n\n## Identity\n\n## Goals\n\n## Constraints\n\n## Preferences\n\n## Last Updated\n",
    "capture/agents.md": "# Capture Agent\n\nWrite quick captures to this domain before routing.\n",
    "life/agents.md": "# Life Agent\n\nLife-domain context lives under `life/<topic>`.\n",
    "projects/agents.md": "# Projects Agent\n\nUse `projects/active` for current work and `projects/archived` for completed work.\n",
    "pulse/agents.md": "# Pulse Agent\n\nPulse tracks tasks and completion history.\n",
    "pulse/index.md": "# Pulse Index\n",
    "pulse/archive.md": "# Pulse Archive\n",
    "digest/agents.md": "# Digest Agent\n\nCanonical source is `digest/daily`; rollups derive from daily entries.\n",
    "share/agents.md": "# Share Agent\n\nShare templates and exports live here.\n",
}

GITKEEP_FILES = (
    "capture/inbox/.gitkeep",
    "projects/active/.gitkeep",
    "projects/archived/.gitkeep",
    "digest/daily/.gitkeep",
    "digest/weekly/.gitkeep",
    "digest/monthly/.gitkeep",
    "digest/yearly/.gitkeep",
    "transcripts/.gitkeep",
    "share/templates/.gitkeep",
    "share/exports/.gitkeep",
)


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

    current_status = state["starter_topics"].get(topic, "not_started")
    if current_status != "complete" and current_status != "in_progress":
        state["starter_topics"][topic] = "in_progress"

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
    _reject_unknown_fields(payload, {"topic", "context", "approved"})

    missing = [field for field in ("topic", "context", "approved") if field not in payload]
    if missing:
        raise McpError("MISSING_FIELDS", "topic, context, and approved are required.", {"fields": missing})

    topic = _validate_topic(payload["topic"])
    context = payload["context"]
    approved = payload["approved"]

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

    library_root = get_request_library_root(request)
    changed_paths = _bootstrap_user_library(library_root)

    interview_path = _topic_file_path(library_root, topic, "interview.md")
    existing = interview_path.read_text(encoding="utf-8")
    stamp = dt.datetime.now(dt.timezone.utc).isoformat()
    section = f"## Approved Context {stamp}\n\n{context.strip()}\n"
    updated = _join_with_newline(existing, section)
    _atomic_write(interview_path, updated)
    changed_paths.append(interview_path.relative_to(library_root))

    state = _read_onboarding_state(library_root)
    if state["starter_topics"].get(topic) != "complete":
        state["starter_topics"][topic] = "in_progress"
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
            "commitSha": commit_sha,
        }
    )


@mcp_router.post("/tool:complete_topic_onboarding")
def complete_topic_onboarding(
    payload: dict[str, Any], request: Request
) -> dict[str, Any]:
    """Mark a topic onboarding flow complete and recommend the next topic."""
    payload = _ensure_payload_dict(payload)
    _reject_unknown_fields(payload, {"topic", "summary"})

    if "topic" not in payload:
        raise McpError("MISSING_TOPIC", "topic is required.", {"fields": ["topic"]})

    topic = _validate_topic(payload["topic"])
    summary_value = payload.get("summary")
    if summary_value is not None and not isinstance(summary_value, str):
        raise McpError(
            "INVALID_TYPE",
            "summary must be a string.",
            {"type": type(summary_value).__name__},
        )

    library_root = get_request_library_root(request)
    changed_paths = _bootstrap_user_library(library_root)

    state = _read_onboarding_state(library_root)
    state["starter_topics"][topic] = "complete"
    state.setdefault("completed_at", {})[topic] = dt.datetime.now(dt.timezone.utc).isoformat()
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
            "next_topic": _next_incomplete_topic(state),
            "commitSha": commit_sha,
        }
    )



APPROVED_CONTEXT_BLOCK_PATTERN = re.compile(
    r"^## Approved Context[^\n]*\n(?P<body>.*?)(?=^## |\Z)",
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

    changed_paths.extend(_ensure_required_structure(library_root))
    changed_paths.extend(_ensure_digest_period_files(library_root))

    # Keep relative paths stable and unique for commit staging/reporting.
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

    fallback = Path(__file__).resolve().parents[3] / "library_templates" / "Base_Library"
    if fallback.is_dir():
        return fallback
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


def _ensure_required_structure(library_root: Path) -> list[Path]:
    changed: list[Path] = []

    for relative_dir in REQUIRED_DIRS:
        (library_root / relative_dir).mkdir(parents=True, exist_ok=True)

    for relative_path, content in REQUIRED_TEXT_FILES.items():
        changed_path = _write_text_if_missing(library_root, relative_path, content)
        if changed_path is not None:
            changed.append(changed_path)

    for topic in TOPIC_ORDER:
        changed.extend(_ensure_topic_scaffold(library_root, topic))

    for gitkeep_path in GITKEEP_FILES:
        changed_path = _write_text_if_missing(library_root, gitkeep_path, "")
        if changed_path is not None:
            changed.append(changed_path)

    rollup_path = library_root / "digest" / "_meta" / "rollup-state.json"
    if not rollup_path.exists():
        rollup_state = {
            "version": 1,
            "last_daily_ingest": None,
            "last_weekly_rollup": None,
            "last_monthly_rollup": None,
            "last_yearly_rollup": None,
        }
        _atomic_write(rollup_path, json.dumps(rollup_state, indent=2) + "\n")
        changed.append(rollup_path.relative_to(library_root))

    state = _read_onboarding_state(library_root)
    state_changed = _persist_onboarding_state(library_root, state)
    if state_changed is not None:
        changed.append(state_changed)

    return changed


def _ensure_topic_scaffold(library_root: Path, topic: str) -> list[Path]:
    title = TOPIC_TITLES[topic]
    base_dir = library_root / "life" / topic
    base_dir.mkdir(parents=True, exist_ok=True)

    changed: list[Path] = []
    topic_files = {
        "agents.md": f"# {title} Agent\n\nUse this folder for {title.lower()} context and plans.\n",
        "interview.md": (
            f"# {title} Interview\n\n"
            f"- What matters most in {title.lower()} right now?\n"
            "- What constraints are currently blocking progress?\n"
            "- What result would make the next 30 days successful?\n"
        ),
        "goals.md": f"# {title} Goals\n\n## Current Goals\n\n",
        "action-plan.md": f"# {title} Action Plan\n\n## Immediate Actions\n\n",
    }
    for filename, content in topic_files.items():
        relative = f"life/{topic}/{filename}"
        changed_path = _write_text_if_missing(library_root, relative, content)
        if changed_path is not None:
            changed.append(changed_path)
    return changed


def _ensure_digest_period_files(library_root: Path) -> list[Path]:
    today = dt.date.today()
    iso_year, iso_week, _ = today.isocalendar()

    starters: list[tuple[Path, str]] = [
        (
            library_root
            / "digest"
            / "daily"
            / f"{today.year:04d}"
            / f"{today.month:02d}"
            / f"{today.isoformat()}.md",
            f"# Daily Digest {today.isoformat()}\n\n",
        ),
        (
            library_root
            / "digest"
            / "weekly"
            / f"{iso_year:04d}"
            / f"{iso_year:04d}-W{iso_week:02d}.md",
            f"# Weekly Digest {iso_year:04d}-W{iso_week:02d}\n\n",
        ),
        (
            library_root
            / "digest"
            / "monthly"
            / f"{today.year:04d}"
            / f"{today.year:04d}-{today.month:02d}.md",
            f"# Monthly Digest {today.year:04d}-{today.month:02d}\n\n",
        ),
        (
            library_root / "digest" / "yearly" / f"{today.year:04d}.md",
            f"# Yearly Digest {today.year:04d}\n\n",
        ),
    ]

    changed: list[Path] = []
    for file_path, content in starters:
        if file_path.exists():
            continue
        file_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(file_path, content)
        changed.append(file_path.relative_to(library_root))
    return changed


def _state_path(library_root: Path) -> Path:
    return library_root / ".braindrive" / "onboarding_state.json"


def _default_onboarding_state() -> dict[str, Any]:
    return {
        "version": 1,
        "starter_topics": {topic: "not_started" for topic in TOPIC_ORDER},
        "completed_at": {},
    }


def _read_onboarding_state(library_root: Path) -> dict[str, Any]:
    path = _state_path(library_root)
    if not path.exists():
        return _default_onboarding_state()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_onboarding_state()

    state = _default_onboarding_state()
    if isinstance(raw, dict):
        version = raw.get("version")
        if isinstance(version, int):
            state["version"] = version

        starter_topics = raw.get("starter_topics")
        if isinstance(starter_topics, dict):
            for topic in TOPIC_ORDER:
                candidate = starter_topics.get(topic)
                if candidate in {"not_started", "in_progress", "complete"}:
                    state["starter_topics"][topic] = candidate

        completed_at = raw.get("completed_at")
        if isinstance(completed_at, dict):
            state["completed_at"] = {
                topic: value
                for topic, value in completed_at.items()
                if isinstance(topic, str) and isinstance(value, str)
            }

    return state


def _persist_onboarding_state(library_root: Path, state: dict[str, Any]) -> Path | None:
    path = _state_path(library_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    normalized = _read_onboarding_state(library_root)
    normalized["version"] = int(state.get("version", normalized["version"]))

    starter_topics = state.get("starter_topics") if isinstance(state.get("starter_topics"), dict) else {}
    for topic in TOPIC_ORDER:
        value = starter_topics.get(topic)
        if value in {"not_started", "in_progress", "complete"}:
            normalized["starter_topics"][topic] = value

    completed_at = state.get("completed_at") if isinstance(state.get("completed_at"), dict) else {}
    normalized["completed_at"] = {
        topic: value
        for topic, value in completed_at.items()
        if isinstance(topic, str) and isinstance(value, str)
    }

    existing = None
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = None

    if existing == normalized:
        return None

    _atomic_write(path, json.dumps(normalized, indent=2) + "\n")
    return path.relative_to(library_root)


def _topic_file_path(library_root: Path, topic: str, filename: str) -> Path:
    return library_root / "life" / topic / filename


def _validate_topic(value: Any) -> str:
    if not isinstance(value, str):
        raise McpError(
            "INVALID_TYPE",
            "topic must be a string.",
            {"type": type(value).__name__},
        )
    topic = value.strip().lower()
    if topic not in TOPIC_ORDER:
        raise McpError(
            "INVALID_TOPIC",
            "Unsupported onboarding topic.",
            {"topic": value, "allowed": list(TOPIC_ORDER)},
        )
    return topic


def _next_incomplete_topic(state: dict[str, Any]) -> str | None:
    starter_topics = state.get("starter_topics")
    if not isinstance(starter_topics, dict):
        return TOPIC_ORDER[0]

    for topic in TOPIC_ORDER:
        if starter_topics.get(topic) != "complete":
            return topic
    return None


def _write_text_if_missing(
    library_root: Path, relative_path: str, content: str
) -> Path | None:
    target_path = library_root / relative_path
    if target_path.exists():
        return None
    target_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(target_path, content)
    return target_path.relative_to(library_root)


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
