"""Canonical BrainDrive library schema helpers."""

from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from app.mcp_utils import _atomic_write as _shared_atomic_write
except ModuleNotFoundError:
    _shared_atomic_write = None


def _atomic_write(target_path: Path, content: str) -> None:
    if _shared_atomic_write is not None:
        _shared_atomic_write(target_path, content)
        return

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=target_path.parent, delete=False
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, target_path)
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass

SCHEMA_VERSION = "2026-02-17-v2"
TOPIC_ORDER = ("finances", "fitness", "relationships", "career", "whyfinder")
TOPIC_TITLES = {
    "finances": "Finances",
    "fitness": "Fitness",
    "relationships": "Relationships",
    "career": "Career",
    "whyfinder": "WhyFinder",
}

TOPIC_STATUS_VALUES = {"not_started", "in_progress", "complete"}
TOPIC_PHASE_VALUES = {
    "not_started",
    "opening",
    "goals_tasks",
    "followup",
    "complete",
}

ROOT_AGENT_TEMPLATE = (
    "# BrainDrive Library Agent\n\n"
    "You are working in a user-scoped BrainDrive library.\n"
    "Read this contract before mutating files.\n\n"
    "## Priorities\n"
    "1. Preserve user data.\n"
    "2. Keep paths canonical.\n"
    "3. Require explicit approval before mutating writes.\n"
)

LIFE_DOMAIN_AGENT_TEMPLATE = (
    "# Life Domain Agent\n\n"
    "Life-domain context lives under `life/<topic>`.\n"
    "Each topic must include AGENT.md, spec.md, and build-plan.md.\n"
)

PROJECTS_AGENT_TEMPLATE = (
    "# Projects Domain Agent\n\n"
    "Use `projects/active` for active projects and `projects/archived` for archived work.\n"
    "Each project must include AGENT.md, spec.md, build-plan.md, decisions.md, and ideas.md.\n"
)

CAPTURE_AGENT_TEMPLATE = (
    "# Capture Agent\n\n"
    "Capture raw input in `capture/inbox` and then route it intentionally.\n"
)

PULSE_AGENT_TEMPLATE = (
    "# Pulse Agent\n\n"
    "Pulse tracks active tasks in `pulse/index.md` and completed tasks in `pulse/completed/YYYY-MM.md`.\n"
)

DIGEST_AGENT_TEMPLATE = (
    "# Digest Agent\n\n"
    "Digest rollups derive from `digest/daily` entries.\n"
)

SHARE_AGENT_TEMPLATE = (
    "# Share Agent\n\n"
    "Share templates in `share/templates` and exports in `share/exports`.\n"
)

REQUIRED_DIRECTORIES = (
    ".braindrive",
    "me",
    "capture",
    "capture/inbox",
    "life",
    "projects",
    "projects/active",
    "projects/archived",
    "pulse",
    "pulse/completed",
    "digest",
    "digest/daily",
    "digest/weekly",
    "digest/monthly",
    "digest/yearly",
    "digest/_meta",
    "transcripts",
    "share",
    "share/templates",
    "share/exports",
)

REQUIRED_TEXT_FILES = {
    "AGENT.md": ROOT_AGENT_TEMPLATE,
    "activity.log": "",
    "me/profile.md": (
        "# Profile\n\n"
        "## Identity\n\n"
        "## Goals\n\n"
        "## Constraints\n\n"
        "## Preferences\n\n"
        "## Last Updated\n"
    ),
    "capture/AGENT.md": CAPTURE_AGENT_TEMPLATE,
    "life/AGENT.md": LIFE_DOMAIN_AGENT_TEMPLATE,
    "projects/AGENT.md": PROJECTS_AGENT_TEMPLATE,
    "pulse/AGENT.md": PULSE_AGENT_TEMPLATE,
    "pulse/index.md": "# Pulse Index\n",
    "digest/AGENT.md": DIGEST_AGENT_TEMPLATE,
    "share/AGENT.md": SHARE_AGENT_TEMPLATE,
    "digest/_meta/rollup-state.json": json.dumps(
        {
            "version": 1,
            "last_daily_ingest": None,
            "last_weekly_rollup": None,
            "last_monthly_rollup": None,
            "last_yearly_rollup": None,
        },
        indent=2,
    )
    + "\n",
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

AGENT_MIGRATION_DIRECTORIES = (
    ".",
    "capture",
    "life",
    "projects",
    "pulse",
    "digest",
    "share",
    "life/finances",
    "life/fitness",
    "life/relationships",
    "life/career",
    "life/whyfinder",
)


@dataclass(frozen=True)
class LibrarySchemaApplyResult:
    """Describes canonical structure updates for a scoped library root."""

    changed_paths: tuple[Path, ...]
    created_paths: tuple[Path, ...]
    migrated_paths: tuple[Path, ...]


def _schema_version_path(library_root: Path) -> Path:
    return library_root / ".braindrive" / "schema-version.json"


def _state_path(library_root: Path) -> Path:
    return library_root / ".braindrive" / "onboarding_state.json"


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _normalize_timestamp(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _default_topic_progress(*, created_at: str | None = None) -> dict[str, Any]:
    timestamp = created_at or _utc_now_iso()
    return {
        topic: {
            "status": "not_started",
            "phase": "not_started",
            "started_at_utc": None,
            "last_interview_at_utc": None,
            "completed_at_utc": None,
            "next_followup_due_at_utc": None,
            "question_total": 0,
            "question_index": 0,
            "followup_cycles": 0,
            "future_interview_topics": [],
            "last_updated_at_utc": timestamp,
        }
        for topic in TOPIC_ORDER
    }


def default_onboarding_state() -> dict[str, Any]:
    created_at = _utc_now_iso()
    topic_progress = _default_topic_progress(created_at=created_at)
    return {
        "version": 2,
        "starter_topics": {topic: "not_started" for topic in TOPIC_ORDER},
        "completed_at": {},
        "created_at_utc": created_at,
        "updated_at_utc": created_at,
        "active_topic": None,
        "topic_queue": list(TOPIC_ORDER),
        "recommended_next_topic": TOPIC_ORDER[0],
        "topic_progress": topic_progress,
        "topic_history": [],
    }


def read_onboarding_state(library_root: Path) -> dict[str, Any]:
    state_path = _state_path(library_root)
    if not state_path.exists():
        return default_onboarding_state()

    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_onboarding_state()

    normalized = default_onboarding_state()
    if not isinstance(raw, dict):
        return normalized

    version = raw.get("version")
    if isinstance(version, int):
        normalized["version"] = version

    created_at = _normalize_timestamp(raw.get("created_at_utc"))
    updated_at = _normalize_timestamp(raw.get("updated_at_utc"))
    if created_at:
        normalized["created_at_utc"] = created_at
    if updated_at:
        normalized["updated_at_utc"] = updated_at

    active_topic = raw.get("active_topic")
    if isinstance(active_topic, str):
        topic = active_topic.strip().lower()
        if topic in TOPIC_ORDER:
            normalized["active_topic"] = topic

    topic_queue = raw.get("topic_queue")
    if isinstance(topic_queue, list):
        queue: list[str] = []
        for item in topic_queue:
            if not isinstance(item, str):
                continue
            topic = item.strip().lower()
            if topic in TOPIC_ORDER and topic not in queue:
                queue.append(topic)
        if queue:
            normalized["topic_queue"] = queue

    recommended_next_topic = raw.get("recommended_next_topic")
    if isinstance(recommended_next_topic, str):
        topic = recommended_next_topic.strip().lower()
        if topic in TOPIC_ORDER:
            normalized["recommended_next_topic"] = topic

    starter_topics = raw.get("starter_topics")
    if isinstance(starter_topics, dict):
        for topic in TOPIC_ORDER:
            value = starter_topics.get(topic)
            if value in TOPIC_STATUS_VALUES:
                normalized["starter_topics"][topic] = value

    completed_at = raw.get("completed_at")
    if isinstance(completed_at, dict):
        normalized["completed_at"] = {
            topic: value
            for topic, value in completed_at.items()
            if isinstance(topic, str) and isinstance(value, str)
        }

    progress = raw.get("topic_progress")
    if isinstance(progress, dict):
        for topic in TOPIC_ORDER:
            raw_progress = progress.get(topic)
            if not isinstance(raw_progress, dict):
                continue

            target = normalized["topic_progress"][topic]
            status = raw_progress.get("status")
            if status in TOPIC_STATUS_VALUES:
                target["status"] = status
                normalized["starter_topics"][topic] = status

            phase = raw_progress.get("phase")
            if phase in TOPIC_PHASE_VALUES:
                target["phase"] = phase

            for key in (
                "started_at_utc",
                "last_interview_at_utc",
                "completed_at_utc",
                "next_followup_due_at_utc",
                "last_updated_at_utc",
            ):
                value = _normalize_timestamp(raw_progress.get(key))
                if value is not None:
                    target[key] = value

            for key in ("question_total", "question_index", "followup_cycles"):
                value = raw_progress.get(key)
                if isinstance(value, int) and value >= 0:
                    target[key] = value

            future_topics = raw_progress.get("future_interview_topics")
            if isinstance(future_topics, list):
                parsed_future: list[str] = []
                for item in future_topics:
                    if not isinstance(item, str):
                        continue
                    candidate = item.strip().lower()
                    if candidate in TOPIC_ORDER and candidate not in parsed_future:
                        parsed_future.append(candidate)
                target["future_interview_topics"] = parsed_future

    history = raw.get("topic_history")
    if isinstance(history, list):
        parsed_history: list[dict[str, Any]] = []
        for item in history:
            if not isinstance(item, dict):
                continue
            event = item.get("event")
            topic = item.get("topic")
            timestamp = _normalize_timestamp(item.get("at_utc"))
            if not isinstance(event, str) or not event.strip():
                continue
            if not isinstance(topic, str) or topic.strip().lower() not in TOPIC_ORDER:
                continue
            if not timestamp:
                continue
            entry: dict[str, Any] = {
                "event": event.strip(),
                "topic": topic.strip().lower(),
                "at_utc": timestamp,
            }
            from_status = item.get("from_status")
            to_status = item.get("to_status")
            if from_status in TOPIC_STATUS_VALUES:
                entry["from_status"] = from_status
            if to_status in TOPIC_STATUS_VALUES:
                entry["to_status"] = to_status
            detail = item.get("detail")
            if isinstance(detail, str) and detail.strip():
                entry["detail"] = detail.strip()
            parsed_history.append(entry)
        normalized["topic_history"] = parsed_history[-200:]

    for topic in TOPIC_ORDER:
        if normalized["starter_topics"][topic] == "complete":
            if topic not in normalized["completed_at"]:
                completed_stamp = normalized["topic_progress"][topic].get("completed_at_utc")
                if isinstance(completed_stamp, str) and completed_stamp:
                    normalized["completed_at"][topic] = completed_stamp
        else:
            normalized["completed_at"].pop(topic, None)

    if normalized.get("recommended_next_topic") not in TOPIC_ORDER:
        normalized["recommended_next_topic"] = next_incomplete_topic(normalized)
    if not normalized.get("topic_queue"):
        normalized["topic_queue"] = [topic for topic in TOPIC_ORDER]

    return normalized


def persist_onboarding_state(library_root: Path, state: dict[str, Any]) -> Path | None:
    path = _state_path(library_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    normalized = read_onboarding_state(library_root)
    try:
        normalized["version"] = int(state.get("version", normalized["version"]))
    except (TypeError, ValueError):
        pass

    incoming_created_at = _normalize_timestamp(state.get("created_at_utc"))
    if incoming_created_at:
        normalized["created_at_utc"] = incoming_created_at

    incoming_updated_at = _normalize_timestamp(state.get("updated_at_utc"))
    if incoming_updated_at:
        normalized["updated_at_utc"] = incoming_updated_at

    incoming_topics = (
        state.get("starter_topics") if isinstance(state.get("starter_topics"), dict) else {}
    )
    for topic in TOPIC_ORDER:
        value = incoming_topics.get(topic)
        if value in TOPIC_STATUS_VALUES:
            normalized["starter_topics"][topic] = value
            normalized["topic_progress"][topic]["status"] = value

    incoming_completed = (
        state.get("completed_at") if isinstance(state.get("completed_at"), dict) else {}
    )
    normalized["completed_at"] = {
        topic: value
        for topic, value in incoming_completed.items()
        if isinstance(topic, str) and isinstance(value, str)
    }

    incoming_active_topic = state.get("active_topic")
    if isinstance(incoming_active_topic, str):
        topic = incoming_active_topic.strip().lower()
        normalized["active_topic"] = topic if topic in TOPIC_ORDER else None
    elif incoming_active_topic is None:
        normalized["active_topic"] = None

    incoming_queue = state.get("topic_queue")
    if isinstance(incoming_queue, list):
        queue: list[str] = []
        for item in incoming_queue:
            if not isinstance(item, str):
                continue
            topic = item.strip().lower()
            if topic in TOPIC_ORDER and topic not in queue:
                queue.append(topic)
        if queue:
            normalized["topic_queue"] = queue

    incoming_recommended = state.get("recommended_next_topic")
    if isinstance(incoming_recommended, str):
        topic = incoming_recommended.strip().lower()
        normalized["recommended_next_topic"] = topic if topic in TOPIC_ORDER else None
    elif incoming_recommended is None:
        normalized["recommended_next_topic"] = None

    incoming_progress = state.get("topic_progress")
    if isinstance(incoming_progress, dict):
        for topic in TOPIC_ORDER:
            raw_progress = incoming_progress.get(topic)
            if not isinstance(raw_progress, dict):
                continue
            target = normalized["topic_progress"][topic]

            status = raw_progress.get("status")
            if status in TOPIC_STATUS_VALUES:
                target["status"] = status
                normalized["starter_topics"][topic] = status

            phase = raw_progress.get("phase")
            if phase in TOPIC_PHASE_VALUES:
                target["phase"] = phase

            for key in (
                "started_at_utc",
                "last_interview_at_utc",
                "completed_at_utc",
                "next_followup_due_at_utc",
                "last_updated_at_utc",
            ):
                value = _normalize_timestamp(raw_progress.get(key))
                if value is not None:
                    target[key] = value

            for key in ("question_total", "question_index", "followup_cycles"):
                value = raw_progress.get(key)
                if isinstance(value, int) and value >= 0:
                    target[key] = value

            future_topics = raw_progress.get("future_interview_topics")
            if isinstance(future_topics, list):
                parsed_future: list[str] = []
                for item in future_topics:
                    if not isinstance(item, str):
                        continue
                    candidate = item.strip().lower()
                    if candidate in TOPIC_ORDER and candidate not in parsed_future:
                        parsed_future.append(candidate)
                target["future_interview_topics"] = parsed_future

    incoming_history = state.get("topic_history")
    if isinstance(incoming_history, list):
        parsed_history: list[dict[str, Any]] = []
        for item in incoming_history:
            if not isinstance(item, dict):
                continue
            event = item.get("event")
            topic = item.get("topic")
            at_utc = _normalize_timestamp(item.get("at_utc"))
            if not isinstance(event, str) or not event.strip():
                continue
            if not isinstance(topic, str):
                continue
            normalized_topic = topic.strip().lower()
            if normalized_topic not in TOPIC_ORDER:
                continue
            if not at_utc:
                continue
            record: dict[str, Any] = {
                "event": event.strip(),
                "topic": normalized_topic,
                "at_utc": at_utc,
            }
            from_status = item.get("from_status")
            to_status = item.get("to_status")
            if from_status in TOPIC_STATUS_VALUES:
                record["from_status"] = from_status
            if to_status in TOPIC_STATUS_VALUES:
                record["to_status"] = to_status
            detail = item.get("detail")
            if isinstance(detail, str) and detail.strip():
                record["detail"] = detail.strip()
            parsed_history.append(record)
        normalized["topic_history"] = parsed_history[-200:]

    for topic in TOPIC_ORDER:
        if normalized["starter_topics"][topic] == "complete":
            completed_stamp = normalized["topic_progress"][topic].get("completed_at_utc")
            if isinstance(completed_stamp, str) and completed_stamp:
                normalized["completed_at"][topic] = completed_stamp
            elif topic not in normalized["completed_at"]:
                normalized["completed_at"][topic] = _utc_now_iso()
        else:
            normalized["completed_at"].pop(topic, None)
            normalized["topic_progress"][topic]["completed_at_utc"] = None

    if not isinstance(normalized.get("created_at_utc"), str) or not normalized["created_at_utc"]:
        normalized["created_at_utc"] = _utc_now_iso()
    normalized["updated_at_utc"] = _utc_now_iso()

    if normalized.get("recommended_next_topic") not in TOPIC_ORDER:
        normalized["recommended_next_topic"] = next_incomplete_topic(normalized)
    if not isinstance(normalized.get("topic_queue"), list) or not normalized["topic_queue"]:
        normalized["topic_queue"] = [topic for topic in TOPIC_ORDER]

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


def topic_file_path(library_root: Path, topic: str, filename: str) -> Path:
    return library_root / "life" / topic / filename


def validate_topic(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Topic must be a string, received: {type(value).__name__}")

    topic = value.strip().lower()
    if topic not in TOPIC_ORDER:
        raise ValueError(f"Unsupported topic '{value}'. Allowed: {', '.join(TOPIC_ORDER)}")
    return topic


def next_incomplete_topic(state: dict[str, Any]) -> str | None:
    starter_topics = state.get("starter_topics")
    if not isinstance(starter_topics, dict):
        return TOPIC_ORDER[0]
    for topic in TOPIC_ORDER:
        if starter_topics.get(topic) != "complete":
            return topic
    return None


def required_scope_files(page_kind: str) -> tuple[str, ...]:
    normalized = str(page_kind or "").strip().lower()
    if normalized == "project":
        return ("AGENT.md", "spec.md", "build-plan.md", "decisions.md", "ideas.md")
    if normalized == "life":
        return (
            "AGENT.md",
            "spec.md",
            "build-plan.md",
            "interview.md",
            "goals.md",
            "action-plan.md",
        )
    if normalized == "capture":
        return ("AGENT.md",)
    return ("AGENT.md", "spec.md", "build-plan.md")


def _topic_seed_files(topic: str) -> dict[str, str]:
    title = TOPIC_TITLES[topic]
    lowered = title.lower()
    if topic == "finances":
        return {
            "AGENT.md": (
                "# Finances Agent\n\n"
                "This topic helps the user build financial clarity, consistency, and confidence.\n\n"
                "## Focus Description\n\n"
                "Prioritize practical money management and steady progress.\n\n"
                "## Interview Focus\n\n"
                "- Income and cash-flow stability\n"
                "- Budget consistency and spending awareness\n"
                "- Debt payoff priorities\n"
                "- Savings and emergency buffer goals\n"
                "- Near-term milestones (30/60/90 days)\n"
                "- Constraints and tradeoffs\n"
            ),
            "interview.md": (
                "# Finances Interview\n\n"
                "## Opening Interview Policy\n\n"
                "- Ask one question at a time.\n"
                "- Opening set should be high-level and capped at 6 questions.\n"
                "- Require approval before each write.\n"
                "- Convert relative dates to explicit dates before final save.\n\n"
                "## Seed Questions (Fallback)\n"
                "1. What matters most in finances over the next 90 days?\n"
                "2. What is working well today, and what is not?\n"
                "3. Which constraints are blocking progress?\n"
                "4. What would make the next 30 days successful?\n"
            ),
            "spec.md": (
                "# Finances Spec\n\n"
                "## Current Reality\n\n"
                "## Desired Outcomes\n\n"
                "## Constraints\n\n"
                "## Success Criteria\n"
            ),
            "build-plan.md": (
                "# Finances Build Plan\n\n"
                "## Phase 1\n\n"
                "## Phase 2\n\n"
                "## Risks\n\n"
                "## Next Review\n"
            ),
            "goals.md": (
                "# Finances Goals\n\n"
                "## Current Goals\n\n"
                "- (to be populated during onboarding)\n"
            ),
            "action-plan.md": (
                "# Finances Action Plan\n\n"
                "## Immediate Actions\n\n"
                "- (to be populated during onboarding)\n"
            ),
        }
    return {
        "AGENT.md": f"# {title} Agent\n\nUse this folder for {lowered} planning and execution.\n",
        "interview.md": (
            f"# {title} Interview\n\n"
            f"## Seed Questions\n"
            f"1. What matters most in {lowered} right now?\n"
            "2. What is working and what is not?\n"
            "3. What constraints are blocking progress?\n"
            "4. What would make the next 30 days successful?\n"
        ),
        "spec.md": (
            f"# {title} Spec\n\n"
            "## Current Reality\n\n"
            "## Desired Outcomes\n\n"
            "## Constraints\n\n"
            "## Success Criteria\n"
        ),
        "build-plan.md": (
            f"# {title} Build Plan\n\n"
            "## Phase 1\n\n"
            "## Phase 2\n\n"
            "## Risks\n\n"
            "## Next Review\n"
        ),
        "goals.md": f"# {title} Goals\n\n## Current Goals\n\n",
        "action-plan.md": f"# {title} Action Plan\n\n## Immediate Actions\n\n",
    }


def _digest_starter_paths(library_root: Path, today: dt.date) -> list[tuple[Path, str]]:
    iso_year, iso_week, _ = today.isocalendar()
    return [
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


def _write_text_if_missing(library_root: Path, relative_path: str, content: str) -> Path | None:
    target = library_root / relative_path
    if target.exists():
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(target, content)
    return target.relative_to(library_root)


def _ensure_schema_version(library_root: Path) -> Path | None:
    version_path = _schema_version_path(library_root)
    version_path.parent.mkdir(parents=True, exist_ok=True)
    desired = {"schema_version": SCHEMA_VERSION}

    existing = None
    if version_path.exists():
        try:
            existing = json.loads(version_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = None

    if existing == desired:
        return None

    _atomic_write(version_path, json.dumps(desired, indent=2) + "\n")
    return version_path.relative_to(library_root)


def _migrate_legacy_agents(library_root: Path) -> list[Path]:
    changed: list[Path] = []
    for relative_dir in AGENT_MIGRATION_DIRECTORIES:
        directory = library_root if relative_dir == "." else library_root / relative_dir
        if not directory.exists() or not directory.is_dir():
            continue

        canonical_agent = directory / "AGENT.md"
        legacy_agent = directory / "agents.md"
        if canonical_agent.exists() or not legacy_agent.exists():
            continue

        try:
            content = legacy_agent.read_text(encoding="utf-8")
        except OSError:
            continue

        _atomic_write(canonical_agent, content)
        changed.append(canonical_agent.relative_to(library_root))
    return changed


def ensure_scoped_library_structure(
    library_root: Path,
    *,
    include_digest_period_files: bool = True,
    today: dt.date | None = None,
) -> LibrarySchemaApplyResult:
    """Ensure canonical user-scoped structure exists without destructive writes."""
    scoped_root = Path(library_root).expanduser().resolve()
    scoped_root.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []
    migrated: list[Path] = []
    changed: dict[str, Path] = {}

    for relative_dir in REQUIRED_DIRECTORIES:
        target = scoped_root / relative_dir
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
            relative = target.relative_to(scoped_root)
            created.append(relative)
            changed[relative.as_posix()] = relative
        else:
            target.mkdir(parents=True, exist_ok=True)

    legacy_migrations = _migrate_legacy_agents(scoped_root)
    for migrated_path in legacy_migrations:
        migrated.append(migrated_path)
        changed[migrated_path.as_posix()] = migrated_path

    for relative_path, content in REQUIRED_TEXT_FILES.items():
        maybe = _write_text_if_missing(scoped_root, relative_path, content)
        if maybe is not None:
            created.append(maybe)
            changed[maybe.as_posix()] = maybe

    for topic in TOPIC_ORDER:
        topic_root = scoped_root / "life" / topic
        if not topic_root.exists():
            topic_root.mkdir(parents=True, exist_ok=True)
            relative = topic_root.relative_to(scoped_root)
            created.append(relative)
            changed[relative.as_posix()] = relative

        for filename, content in _topic_seed_files(topic).items():
            maybe = _write_text_if_missing(
                scoped_root,
                f"life/{topic}/{filename}",
                content,
            )
            if maybe is not None:
                created.append(maybe)
                changed[maybe.as_posix()] = maybe

    for relative_path in GITKEEP_FILES:
        maybe = _write_text_if_missing(scoped_root, relative_path, "")
        if maybe is not None:
            created.append(maybe)
            changed[maybe.as_posix()] = maybe

    if include_digest_period_files:
        marker_day = today or dt.date.today()
        for digest_path, content in _digest_starter_paths(scoped_root, marker_day):
            if digest_path.exists():
                continue
            digest_path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(digest_path, content)
            relative = digest_path.relative_to(scoped_root)
            created.append(relative)
            changed[relative.as_posix()] = relative

    schema_path = _ensure_schema_version(scoped_root)
    if schema_path is not None:
        changed[schema_path.as_posix()] = schema_path

    state = read_onboarding_state(scoped_root)
    state_path = persist_onboarding_state(scoped_root, state)
    if state_path is not None:
        changed[state_path.as_posix()] = state_path
        if state_path not in created:
            created.append(state_path)

    changed_paths = tuple(changed[key] for key in sorted(changed.keys()))
    return LibrarySchemaApplyResult(
        changed_paths=changed_paths,
        created_paths=tuple(created),
        migrated_paths=tuple(migrated),
    )
