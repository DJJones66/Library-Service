from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_LOG_PATH = Path("logs/ollama_agent_workflow.jsonl")


def _load_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Log file not found: {path}")
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _print_inputs_only(events: list[dict[str, Any]]) -> None:
    for event in events:
        if event.get("event") == "user_input":
            payload = event.get("payload", {})
            content = payload.get("content", "")
            print(content)
    print("exit")


def _print_conversation(
    events: list[dict[str, Any]], include_tools: bool
) -> None:
    for event in events:
        event_type = event.get("event")
        payload = event.get("payload", {})
        if event_type == "user_input":
            print(f"user> {payload.get('content', '')}")
        elif event_type == "assistant_message":
            content = payload.get("content", "")
            if content:
                print(f"assistant> {content}")
            if include_tools:
                tool_calls = payload.get("tool_calls") or []
                if tool_calls:
                    print("assistant> [tool_calls]")
                    print(json.dumps(tool_calls, indent=2, ensure_ascii=True))
        elif include_tools and event_type == "tool_response":
            tool = payload.get("tool")
            response = payload.get("response")
            print(f"tool_response ({tool}):")
            print(json.dumps(response, indent=2, ensure_ascii=True))


def _print_summary(events: list[dict[str, Any]]) -> None:
    counts: dict[str, int] = {}
    for event in events:
        event_type = event.get("event", "unknown")
        counts[event_type] = counts.get(event_type, 0) + 1
    for key in sorted(counts):
        print(f"{key}: {counts[key]}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replay or inspect Ollama agent JSONL logs."
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help="Path to the JSONL log file.",
    )
    parser.add_argument(
        "--inputs-only",
        action="store_true",
        help="Print only user inputs (suitable for piping into the agent).",
    )
    parser.add_argument(
        "--include-tools",
        action="store_true",
        help="Include tool calls and tool responses in output.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print event counts summary.",
    )
    args = parser.parse_args()

    try:
        events = _load_events(args.log_file)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.inputs_only:
        _print_inputs_only(events)
    else:
        _print_conversation(events, args.include_tools)

    if args.summary:
        print("\nSummary:")
        _print_summary(events)

    return 0


if __name__ == "__main__":
    sys.exit(main())
