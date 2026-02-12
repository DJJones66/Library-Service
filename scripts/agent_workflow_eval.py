from __future__ import annotations

import argparse
import io
import json
import os
import sys
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ollama_agent_workflow import (
    MUTATING_TOOLS,
    McpClient,
    OllamaClient,
    OutputConfig,
    SYSTEM_PROMPT,
    _load_dotenv,
    run_scripted_session,
)
from tools.mcp_tools import ToolSchemaError, load_tool_definitions


DEFAULT_PROMPTS = [
    "Does the project Library exist?",
    "What projects do exist?",
    "Create a new project called Library with a spec and notes file.",
    "Append a note 'First note' to notes.md in the Library project.",
    "Update the Scope section in spec.md for Library to say 'Updated scope'.",
    "Delete notes.md in the Library project.",
    "List all projects.",
]


def _load_prompts(path: Path | None) -> list[str]:
    if path is None:
        return DEFAULT_PROMPTS
    if not path.is_file():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    lines = [
        line.strip() for line in path.read_text(encoding="utf-8").splitlines()
    ]
    return [line for line in lines if line and not line.startswith("#")]


def _apply_project_name(prompts: list[str], project_name: str) -> list[str]:
    updated: list[str] = []
    for prompt in prompts:
        updated.append(
            prompt.replace("Library", project_name).replace(
                "library", project_name
            )
        )
    return updated


def _parse_event_lines(raw: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _build_steps(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for event in events:
        name = event.get("event")
        payload = event.get("payload", {})
        if name == "user_input":
            if current is not None:
                steps.append(current)
            current = {
                "prompt": payload.get("content", ""),
                "assistant_messages": [],
                "tool_calls": [],
                "tool_responses": [],
                "approval_requests": [],
                "approval_results": [],
                "policy_retries": [],
                "policy_errors": [],
                "policy_autofix": [],
                "outcome": None,
            }
            continue
        if current is None:
            continue
        if name == "assistant_message":
            current["assistant_messages"].append(payload)
        elif name == "tool_call":
            current["tool_calls"].append(payload)
        elif name == "tool_response":
            current["tool_responses"].append(payload)
        elif name == "approval_request":
            current["approval_requests"].append(payload)
        elif name == "approval_result":
            current["approval_results"].append(payload)
        elif name == "policy_retry":
            current["policy_retries"].append(payload)
        elif name == "policy_error":
            current["policy_errors"].append(payload)
        elif name == "policy_autofix":
            current["policy_autofix"].append(payload)
        elif name == "step_outcome":
            current["outcome"] = payload
    if current is not None:
        steps.append(current)
    return steps


def _summarize_step(step: dict[str, Any]) -> dict[str, Any]:
    tool_calls = step["tool_calls"]
    tool_responses = step["tool_responses"]
    approvals = step["approval_results"]
    approval_requests = step["approval_requests"]
    policy_retries = step["policy_retries"]
    policy_errors = step["policy_errors"]
    outcome = step["outcome"] or {}

    approval_required = any(
        call.get("tool") in MUTATING_TOOLS for call in tool_calls
    )
    approval_requested = bool(approval_requests)
    approval_auto = any(result.get("auto") for result in approvals)
    approval_mode = "none"
    if approval_required:
        approval_mode = "auto" if approval_auto else "prompted"

    unexpected: list[str] = []
    for entry in outcome.get("errors", []):
        unexpected.append(entry)
    for entry in outcome.get("warnings", []):
        unexpected.append(entry)
    for entry in policy_errors:
        reason = entry.get("reason")
        if reason:
            unexpected.append(f"policy_error: {reason}")

    deduped_unexpected: list[str] = []
    for entry in unexpected:
        if entry not in deduped_unexpected:
            deduped_unexpected.append(entry)

    attempts = {
        "assistant_messages": len(step["assistant_messages"]),
        "tool_calls": len(tool_calls),
        "policy_retries": len(policy_retries),
    }

    return {
        "prompt": step["prompt"],
        "project_name": step.get("project_name", ""),
        "attempts": attempts,
        "approval_required": approval_required,
        "approval_requested": approval_requested,
        "approval_mode": approval_mode,
        "tool_calls": tool_calls,
        "tool_responses": tool_responses,
        "completed": bool(outcome.get("success", False)),
        "unexpected": deduped_unexpected,
    }


def main() -> int:
    _load_dotenv(Path(".env"))

    parser = argparse.ArgumentParser(
        description="Evaluate each workflow step and report outcomes."
    )
    parser.add_argument(
        "--tools",
        type=Path,
        default=Path("tools/mcp_tools.json"),
        help="Path to MCP tool definitions JSON.",
    )
    parser.add_argument(
        "--ollama-base-url",
        default=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        help="Ollama base URL (default: env OLLAMA_BASE_URL).",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OLLAMA_MODEL", "functiongemma"),
        help="Ollama model name (default: env OLLAMA_MODEL).",
    )
    parser.add_argument(
        "--mcp-base-url",
        default=os.environ.get("MCP_BASE_URL", "http://127.0.0.1:8000"),
        help="MCP server base URL.",
    )
    parser.add_argument(
        "--prompts",
        type=Path,
        help="Optional text file of prompts (one per line).",
    )
    parser.add_argument(
        "--project-name",
        help="Override the project name used in the workflow prompts.",
    )
    parser.add_argument(
        "--require-approval",
        action="store_true",
        help="Prompt for approval (disables auto-approve).",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=8,
        help="Max tool-call steps per user message.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Include raw assistant content in JSON capture.",
    )
    parser.add_argument(
        "--no-auto-repair",
        action="store_false",
        dest="auto_repair",
        default=True,
        help="Disable rule-based fallback tool calls.",
    )
    parser.add_argument(
        "--strict-tool-calls",
        action="store_true",
        help="Fail if no tool_calls are produced and skip auto-repair.",
    )
    args = parser.parse_args()

    try:
        tools = load_tool_definitions(args.tools)
    except ToolSchemaError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        prompts = _load_prompts(args.prompts)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.project_name:
        project_name = args.project_name
    else:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        project_name = f"Library-{timestamp}"
    prompts = _apply_project_name(prompts, project_name)

    output = OutputConfig(mode="json")
    ollama = OllamaClient(args.ollama_base_url, args.model)
    mcp = McpClient(args.mcp_base_url)

    try:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            run_scripted_session(
                ollama,
                mcp,
                tools,
                prompts,
                auto_approve=not args.require_approval,
                max_steps=args.max_steps,
                system_prompt=SYSTEM_PROMPT,
                debug=args.debug,
                auto_repair=args.auto_repair,
                strict_tool_calls=args.strict_tool_calls,
                logger=None,
                output=output,
            )
    finally:
        ollama.close()
        mcp.close()

    events = _parse_event_lines(buffer.getvalue())
    steps = _build_steps(events)
    for step in steps:
        step["project_name"] = project_name

    separator = "*" * 60
    for step in steps:
        summary = _summarize_step(step)
        print(separator)
        print(json.dumps(summary, indent=2, ensure_ascii=True))
    print(separator)
    return 0


if __name__ == "__main__":
    sys.exit(main())
