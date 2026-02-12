from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ollama_agent_workflow import (
    JsonlLogger,
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
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return [line for line in lines if line and not line.startswith("#")]


def main() -> int:
    _load_dotenv(Path(".env"))

    parser = argparse.ArgumentParser(
        description="Run a scripted natural-language workflow against the agent."
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
        "--auto-approve",
        action="store_true",
        help="Auto-approve all mutating tool calls.",
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
        help="Print tool calls and tool responses.",
    )
    parser.add_argument(
        "--no-auto-repair",
        action="store_false",
        dest="auto_repair",
        default=True,
        help="Disable rule-based fallback tool calls.",
    )
    parser.add_argument(
        "--auto-repair",
        action="store_true",
        dest="auto_repair",
        help="Enable rule-based fallback tool calls (default).",
    )
    parser.add_argument(
        "--strict-tool-calls",
        action="store_true",
        help="Fail if no tool_calls are produced and skip auto-repair.",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=Path("logs/ollama_agent_workflow.jsonl"),
        help="Write JSONL logs to this file (set to '-' to disable).",
    )
    parser.add_argument(
        "--output",
        choices=["human", "json"],
        default="json",
        help="Output format (default: json).",
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

    log_path = None if str(args.log_file) == "-" else args.log_file
    logger = JsonlLogger(log_path)
    output = OutputConfig(mode=args.output)
    ollama = OllamaClient(args.ollama_base_url, args.model)
    mcp = McpClient(args.mcp_base_url)

    try:
        outcomes = run_scripted_session(
            ollama,
            mcp,
            tools,
            prompts,
            args.auto_approve,
            args.max_steps,
            SYSTEM_PROMPT,
            args.debug,
            args.auto_repair,
            args.strict_tool_calls,
            logger,
            output,
        )
    finally:
        ollama.close()
        mcp.close()
        if logger:
            logger.close()
    failures = [outcome for outcome in outcomes if not outcome.success]
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
