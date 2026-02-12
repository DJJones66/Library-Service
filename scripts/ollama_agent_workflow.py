from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.mcp_tools import ToolSchemaError, load_tool_definitions

ENV_PATH = Path(".env")
TOOLS_PATH = Path("tools/mcp_tools.json")
DEFAULT_LOG_PATH = Path("logs/ollama_agent_workflow.jsonl")


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].strip()
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


@dataclass
class ToolResult:
    ok: bool
    payload: dict[str, Any]


@dataclass
class StepOutcome:
    prompt: str
    success: bool
    errors: list[str]
    warnings: list[str]


@dataclass
class OutputConfig:
    mode: str = "human"  # "human" or "json"


class JsonlLogger:
    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._handle = None
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self._path.open("a", encoding="utf-8")

    def log(self, event: str, payload: dict[str, Any]) -> None:
        if self._handle is None:
            return
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "payload": payload,
        }
        self._handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
        self._handle.flush()

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()


class OllamaClient:
    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._http = httpx.Client(timeout=30.0)

    def close(self) -> None:
        self._http.close()

    def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        response = self._http.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._model,
                "messages": messages,
                "tools": tools,
                "stream": False,
            },
        )
        response.raise_for_status()
        return response.json()


class McpClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.Client(timeout=30.0)

    def close(self) -> None:
        self._http.close()

    def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        response = self._http.post(
            f"{self._base_url}/tool:{name}", json=args
        )
        try:
            body = response.json()
        except ValueError:
            return {
                "ok": False,
                "error": {
                    "code": "NON_JSON_RESPONSE",
                    "message": f"Non-JSON response ({response.status_code}).",
                    "details": {},
                },
            }
        if response.status_code != 200:
            return body
        return body


MUTATING_TOOLS = {
    "create_project",
    "create_markdown",
    "write_markdown",
    "edit_markdown",
    "delete_markdown",
}


SYSTEM_PROMPT = (
    "You are a tool-using assistant for the BrainDrive Library. "
    "Use the provided tools to read, create, and edit markdown content. "
    "If a task requires changing files, you MUST call the appropriate tool "
    "with all required arguments BEFORE responding. "
    "Tool calls must be returned via tool_calls only; do not print tool calls "
    "as text. "
    "For project existence or listing questions, you MUST call the "
    "corresponding tool and do not answer unless tool_calls are emitted; "
    "leave content empty and return only tool_calls. "
    "Do not emit <think> or <tool_call> tags in content. "
    "For projects, use paths like 'projects/active/<project-name>'. "
    "Routing rules: "
    "project listing -> list_projects; "
    "project existence -> project_exists (never read_markdown); "
    "create project -> create_project; "
    "append/prepend text -> write_markdown; "
    "section edits -> edit_markdown (replace_section). "
    "For create_project, always provide path or name and (if files is provided) "
    "each file entry must include {path, content}. "
    "Examples: "
    "project_exists {\"name\":\"Library\"}; "
    "list_projects {}; "
    "create_project {\"path\":\"projects/active/Library\",\"files\":["
    "{\"path\":\"spec.md\",\"content\":\"# Library\\n\"},"
    "{\"path\":\"notes.md\",\"content\":\"\\n\"}]}; "
    "create_markdown {\"path\":\"projects/active/Library/ideas.md\","
    "\"content\":\"# Ideas\\n\"}; "
    "write_markdown {\"path\":\"projects/active/Library/notes.md\","
    "\"operation\":{\"type\":\"append\",\"content\":\"First note\\n\"}}; "
    "edit_markdown {\"path\":\"projects/active/Library/spec.md\","
    "\"operation\":{\"type\":\"replace_section\",\"target\":\"## Scope\","
    "\"content\":\"## Scope\\nUpdated\\n\"}}; "
    "delete_markdown {\"path\":\"projects/active/Library/notes.md\","
    "\"confirm\":true}. "
    "Invalid example: create_project {\"files\":[\"spec.md\"]}. "
    "Corrected: create_project {\"path\":\"projects/active/Library\","
    "\"files\":[{\"path\":\"spec.md\",\"content\":\"# Library\\n\"}]}. "
    "Keep responses concise."
)


def _emit_event(output: OutputConfig, event: str, payload: dict[str, Any]) -> None:
    if output.mode == "json":
        print(json.dumps({"event": event, "payload": payload}, ensure_ascii=True))


def _prompt_approval(
    tool_name: str,
    args: dict[str, Any],
    auto: bool,
    output: OutputConfig,
) -> bool:
    if auto:
        _emit_event(
            output,
            "approval_result",
            {"tool": tool_name, "approved": True, "auto": True},
        )
        return True
    _emit_event(
        output,
        "approval_request",
        {"tool": tool_name, "args": args},
    )
    if output.mode == "human":
        print("\nApproval required:")
        print(f"  Tool: {tool_name}")
        print(f"  Args: {json.dumps(args, indent=2, ensure_ascii=True)}")
        response = input("Approve? [y/N]: ").strip().lower()
    else:
        response = input("").strip().lower()
    approved = response in {"y", "yes"}
    _emit_event(
        output,
        "approval_result",
        {"tool": tool_name, "approved": approved, "auto": False},
    )
    return approved


def _extract_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    tool_calls = message.get("tool_calls")
    if not tool_calls:
        return []
    if isinstance(tool_calls, list):
        return tool_calls
    return []


def _strip_think_blocks(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL)

def _strip_tool_call_blocks(text: str) -> str:
    if not text:
        return ""
    return re.sub(
        r"<tool_call>.*?</tool_call>", "", text, flags=re.IGNORECASE | re.DOTALL
    )


def _clean_display_content(text: str) -> str:
    cleaned = _strip_think_blocks(text)
    cleaned = _strip_tool_call_blocks(cleaned)
    cleaned = re.sub(
        r"</?(think|assistant|assistance)[^>]*>",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip()


def _extract_braced_json(text: str, start_index: int = 0) -> str | None:
    brace_start = text.find("{", start_index)
    if brace_start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for idx in range(brace_start, len(text)):
        char = text[idx]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[brace_start : idx + 1]
    return None


def _parse_json_like(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        normalized = raw
        normalized = re.sub(
            r'([{\[,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)',
            r'\1"\2"\3',
            normalized,
        )
        normalized = re.sub(r",\s*([}\]])", r"\1", normalized)
        if "'" in normalized and '"' not in normalized:
            normalized = normalized.replace("'", '"')
        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError:
            return None
    if isinstance(parsed, dict):
        return parsed
    return None


def _extract_tool_call_from_text(
    content: str, tool_names: list[str]
) -> tuple[str, dict[str, Any]] | None:
    if not content:
        return None
    cleaned = _strip_think_blocks(content)
    if not cleaned.strip():
        return None

    tag_match = re.search(
        r"<tool_call>(.*?)</tool_call>",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if tag_match:
        inner = tag_match.group(1).strip()
        if inner:
            parsed = _parse_json_like(inner)
            if parsed:
                name = parsed.get("name")
                args = parsed.get("arguments")
                if (
                    isinstance(name, str)
                    and name in tool_names
                    and isinstance(args, dict)
                ):
                    return (name, args)
                function = parsed.get("function")
                if isinstance(function, dict):
                    name = function.get("name")
                    args = function.get("arguments")
                    if (
                        isinstance(name, str)
                        and name in tool_names
                        and isinstance(args, dict)
                    ):
                        return (name, args)

    json_block = _extract_braced_json(cleaned)
    if json_block:
        parsed = _parse_json_like(json_block)
        if parsed:
            name = parsed.get("name")
            args = parsed.get("arguments")
            if (
                isinstance(name, str)
                and name in tool_names
                and isinstance(args, dict)
            ):
                return (name, args)

    for tool_name in tool_names:
        match = re.search(rf"\b{re.escape(tool_name)}\b", cleaned)
        if not match:
            continue
        args_block = _extract_braced_json(cleaned, match.end())
        if not args_block:
            continue
        args = _parse_json_like(args_block)
        if args is None:
            continue
        return (tool_name, args)
    return None


def _normalize_args(raw_args: Any) -> dict[str, Any]:
    if isinstance(raw_args, dict):
        return raw_args
    if isinstance(raw_args, str):
        try:
            parsed = json.loads(raw_args)
        except json.JSONDecodeError:
            raise ValueError("Tool arguments must be valid JSON.")
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("Tool arguments must decode to an object.")
    raise ValueError("Tool arguments must be an object.")


def _tool_message(tool_name: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_name": tool_name,
        "content": json.dumps(result, ensure_ascii=True),
    }


def _requires_list_projects(user_input: str) -> bool:
    lowered = user_input.lower()
    if "project" not in lowered:
        return False
    triggers = [
        "list projects",
        "what projects",
        "which projects",
        "projects do exist",
        "projects exist",
        "list all projects",
    ]
    return any(trigger in lowered for trigger in triggers)


def _requires_project_exists(user_input: str) -> bool:
    lowered = user_input.lower()
    if "project" not in lowered or "exist" not in lowered:
        return False
    if _requires_list_projects(user_input):
        return False
    return True


def _explicit_list_path_in_prompt(user_input: str) -> bool:
    lowered = user_input.lower()
    if "projects/" in lowered or "/" in lowered:
        return True
    if "path" in lowered or "directory" in lowered or "folder" in lowered:
        return True
    if "projects" in lowered and re.search(
        r"\b(in|under|within|inside)\b", lowered
    ):
        return True
    return False


def _tool_hint_for_query(user_input: str) -> str | None:
    lowered = user_input.lower()
    if "project" in lowered and "exist" in lowered:
        return (
            "Tool hint: you must respond ONLY with tool_calls. "
            "Call project_exists with the project name from the prompt "
            "(use the name field, not a markdown file). "
            "Content must be empty; do not print tool names or JSON."
        )
    if "list projects" in lowered or "what projects" in lowered:
        return (
            "Tool hint: you must respond ONLY with tool_calls. "
            "Call list_projects with no arguments to list project directories. "
            "Content must be empty; do not print tool names or JSON."
        )
    if "projects do exist" in lowered or "which projects" in lowered:
        return (
            "Tool hint: you must respond ONLY with tool_calls. "
            "Call list_projects with no arguments to list project directories. "
            "Content must be empty; do not print tool names or JSON."
        )
    if "list all projects" in lowered:
        return (
            "Tool hint: you must respond ONLY with tool_calls. "
            "Call list_projects with no arguments to list project directories. "
            "Content must be empty; do not print tool names or JSON."
        )
    return None


def _routing_hint_for_prompt(user_input: str) -> str | None:
    if _requires_project_exists(user_input):
        return (
            "ROUTING (STRICT): TOOL_CALLS_ONLY. "
            "The assistant content must be empty. "
            "Do not output tool names, JSON, analysis text, or tags. "
            "Call only project_exists with the project name from the prompt."
        )
    if _requires_list_projects(user_input):
        return (
            "ROUTING (STRICT): TOOL_CALLS_ONLY. "
            "The assistant content must be empty. "
            "Do not output tool names, JSON, analysis text, or tags. "
            "Call only list_projects with no arguments."
        )

    fallback = _fallback_tool_from_prompt(user_input)
    if fallback:
        tool_name, args = fallback
        return (
            "ROUTING (STRICT): Output only tool_calls. "
            "Do not answer in text. "
            f"Call exactly: {tool_name} {json.dumps(args)}"
        )
    lowered = user_input.lower()
    if "create a new project" in lowered or "create project" in lowered:
        return (
            "ROUTING (STRICT): DO NOT answer unless you emit a tool call. "
            "Call create_project with name or path. If the user mentions "
            "spec/notes, include files entries with {path, content}."
        )
    if "append a note" in lowered and "notes.md" in lowered:
        return (
            "ROUTING (STRICT): DO NOT answer unless you emit a tool call. "
            "Call write_markdown with "
            "{\"operation\":{\"type\":\"append\",\"content\":\"...\"}}."
        )
    if "update the scope section" in lowered and "spec.md" in lowered:
        return (
            "ROUTING (STRICT): DO NOT answer unless you emit a tool call. "
            "Call edit_markdown with "
            "{\"operation\":{\"type\":\"replace_section\","
            "\"target\":\"## Scope\",\"content\":\"...\"}}."
        )
    if "delete notes.md" in lowered:
        return (
            "ROUTING (STRICT): DO NOT answer unless you emit a tool call. "
            "Call delete_markdown with {\"confirm\":true}."
        )
    return None


def _normalize_project_name(value: str) -> str:
    cleaned = value.strip().strip(" .?")
    cleaned = cleaned.strip('"').strip("'")
    return cleaned


def _extract_quoted_value(text: str) -> str | None:
    match = re.search(r"['\"]([^'\"]+)['\"]", text)
    if not match:
        return None
    return match.group(1).strip()


def _fallback_tool_from_prompt(
    user_input: str,
) -> tuple[str, dict[str, Any]] | None:
    lowered = user_input.lower()

    if _requires_list_projects(user_input):
        return ("list_projects", {})

    if _requires_project_exists(user_input):
        match = re.search(
            r"project\s+(.+?)\s+exist", user_input, re.IGNORECASE
        )
        if match:
            name = _normalize_project_name(match.group(1))
            if name:
                return ("project_exists", {"name": name})

    if "create a new project called" in lowered:
        match = re.search(
            r"project\s+called\s+(.+?)(?:\s+with|$)",
            user_input,
            re.IGNORECASE,
        )
        if match:
            name = _normalize_project_name(match.group(1))
            if name:
                return (
                    "create_project",
                    {
                        "name": name,
                        "files": [
                            {
                                "path": "spec.md",
                                "content": "\n".join(
                                    [
                                        f"# {name}",
                                        "",
                                        "## Scope",
                                        "Initial scope.",
                                        "",
                                    ]
                                )
                                + "\n",
                            },
                            {"path": "notes.md", "content": "\n"},
                        ],
                    },
                )

    if "append a note" in lowered and "notes.md" in lowered:
        note = _extract_quoted_value(user_input)
        project_match = re.search(
            r"in\s+the\s+(.+?)\s+project", user_input, re.IGNORECASE
        )
        if note and project_match:
            project = _normalize_project_name(project_match.group(1))
            return (
                "write_markdown",
                {
                    "path": f"projects/active/{project}/notes.md",
                    "operation": {
                        "type": "append",
                        "content": f"{note}\n",
                    },
                },
            )

    if "update the scope section" in lowered and "spec.md" in lowered:
        scope = _extract_quoted_value(user_input)
        project_match = re.search(
            r"spec\.md\s+for\s+(.+?)\s+to\s+say",
            user_input,
            re.IGNORECASE,
        )
        if scope and project_match:
            project = _normalize_project_name(project_match.group(1))
            return (
                "edit_markdown",
                {
                    "path": f"projects/active/{project}/spec.md",
                    "operation": {
                        "type": "replace_section",
                        "target": "## Scope",
                        "content": f"## Scope\n{scope}\n",
                    },
                },
            )

    if "delete notes.md" in lowered:
        project_match = re.search(
            r"in\s+the\s+(.+?)\s+project", user_input, re.IGNORECASE
        )
        if project_match:
            project = _normalize_project_name(project_match.group(1))
            return (
                "delete_markdown",
                {
                    "path": f"projects/active/{project}/notes.md",
                    "confirm": True,
                },
            )

    return None


def _build_tool_index(
    tools: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for tool in tools:
        function = tool.get("function", {})
        name = function.get("name")
        if isinstance(name, str):
            index[name] = function.get("parameters", {})
    return index


def _build_tool_definition_index(
    tools: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for tool in tools:
        function = tool.get("function", {})
        name = function.get("name")
        if isinstance(name, str):
            index[name] = tool
    return index


def _validate_tool_call_args(
    tool_name: str,
    args: dict[str, Any],
    schema: dict[str, Any],
) -> None:
    required = schema.get("required", [])
    if isinstance(required, list):
        missing = [key for key in required if key not in args]
        if missing:
            raise ValueError(
                f"Missing required fields: {', '.join(missing)}"
            )

    one_of = schema.get("oneOf", [])
    if isinstance(one_of, list) and one_of:
        satisfied = False
        for entry in one_of:
            required_set = entry.get("required", [])
            if (
                isinstance(required_set, list)
                and required_set
                and all(field in args for field in required_set)
            ):
                satisfied = True
                break
        if not satisfied:
            raise ValueError("Arguments do not satisfy oneOf requirements.")

    if tool_name == "create_project" and "files" in args:
        files = args.get("files")
        if not isinstance(files, list):
            raise ValueError("files must be a list.")
        for index, item in enumerate(files):
            if not isinstance(item, dict):
                raise ValueError(
                    f"files[{index}] must be an object with path and content."
                )
            if "path" not in item or "content" not in item:
                raise ValueError(
                    f"files[{index}] must include path and content."
                )
            if not isinstance(item["path"], str) or not isinstance(
                item["content"], str
            ):
                raise ValueError(
                    f"files[{index}] path/content must be strings."
                )

    if tool_name in {"write_markdown", "edit_markdown", "preview_markdown_change"}:
        operation = args.get("operation")
        if not isinstance(operation, dict):
            raise ValueError("operation must be an object.")
        op_type = operation.get("type")
        content = operation.get("content")
        if not isinstance(op_type, str) or not op_type.strip():
            raise ValueError("operation.type must be a non-empty string.")
        if not isinstance(content, str):
            raise ValueError("operation.content must be a string.")
        if tool_name == "edit_markdown":
            target = operation.get("target")
            if not isinstance(target, str) or not target.strip():
                raise ValueError("operation.target must be a non-empty string.")

    if tool_name == "delete_markdown":
        confirm = args.get("confirm")
        if not isinstance(confirm, bool):
            raise ValueError("confirm must be a boolean.")

    if tool_name == "create_markdown":
        path = args.get("path")
        content = args.get("content")
        if not isinstance(path, str) or not path.strip():
            raise ValueError("path must be a non-empty string.")
        if not isinstance(content, str):
            raise ValueError("content must be a string.")

    if tool_name == "project_exists":
        if "path" in args and not isinstance(args["path"], str):
            raise ValueError("path must be a string.")
        if "name" in args and not isinstance(args["name"], str):
            raise ValueError("name must be a string.")


def _process_user_input(
    user_input: str,
    messages: list[dict[str, Any]],
    ollama: OllamaClient,
    mcp: McpClient,
    tools: list[dict[str, Any]],
    tool_index: dict[str, dict[str, Any]],
    tool_def_index: dict[str, dict[str, Any]],
    auto_approve: bool,
    max_steps: int,
    debug: bool,
    auto_repair: bool,
    strict_tool_calls: bool,
    logger: JsonlLogger | None,
    output: OutputConfig,
) -> StepOutcome:
    errors: list[str] = []
    warnings: list[str] = []
    success = True
    fallback = _fallback_tool_from_prompt(user_input) if auto_repair else None
    require_list_projects = _requires_list_projects(user_input)
    require_project_exists = _requires_project_exists(user_input)
    hint_message = None
    hint = _tool_hint_for_query(user_input)
    if hint:
        hint_message = {"role": "system", "content": hint}
        messages.append(hint_message)

    routing_message = None
    routing_hint = _routing_hint_for_prompt(user_input)
    if routing_hint:
        routing_message = {"role": "system", "content": routing_hint}
        messages.append(routing_message)

    tool_only_message = None
    allowed_tool_names: set[str] | None = None
    if require_project_exists:
        allowed_tool_names = {"project_exists"}
        tool_only_message = {
            "role": "system",
            "content": (
                "TOOL-ONLY MODE: Respond only with tool_calls (content empty). "
                "Only allowed tool this turn: project_exists. "
                "Do not include <think> or <tool_call> tags in content."
            ),
        }
        messages.append(tool_only_message)
    elif require_list_projects:
        allowed_tool_names = {"list_projects"}
        tool_only_message = {
            "role": "system",
            "content": (
                "TOOL-ONLY MODE: Respond only with tool_calls (content empty). "
                "Only allowed tool this turn: list_projects. "
                "Do not include <think> or <tool_call> tags in content."
            ),
        }
        messages.append(tool_only_message)

    messages.append({"role": "user", "content": user_input})
    if logger:
        logger.log("user_input", {"content": user_input})
    if output.mode == "json":
        _emit_event(output, "user_input", {"content": user_input})

    enforcement_message = None
    retries = 0
    tool_calls_observed = False
    require_tool_calls = bool(routing_hint)
    tool_only_mode = require_list_projects or require_project_exists
    tools_for_turn = tools
    if require_project_exists and "project_exists" in tool_def_index:
        tools_for_turn = [tool_def_index["project_exists"]]
    if require_list_projects and "list_projects" in tool_def_index:
        tools_for_turn = [tool_def_index["list_projects"]]

    for step in range(max_steps):
        response = ollama.chat(messages, tools_for_turn)
        message = response.get("message", {})
        content = message.get("content", "") or ""
        tool_calls = _extract_tool_calls(message)
        text_tool_call_detected = False
        parsed_text_call = None
        if content and not tool_calls:
            parsed_text_call = _extract_tool_call_from_text(
                content, list(tool_index.keys())
            )
            if parsed_text_call:
                tool_name, args = parsed_text_call
                tool_calls = [
                    {
                        "function": {
                            "name": tool_name,
                            "arguments": args,
                        }
                    }
                ]
                if logger:
                    logger.log(
                        "policy_autofix",
                        {
                            "reason": "text_tool_call_extracted",
                            "tool": tool_name,
                            "args": args,
                        },
                    )
            else:
                for tool_name in tool_index:
                    if content.strip().startswith(f"{tool_name} "):
                        text_tool_call_detected = True
                        break

        assistant_message: dict[str, Any] = {
            "role": "assistant",
            "content": content,
        }
        if tool_calls:
            assistant_message["tool_calls"] = tool_calls
            tool_calls_observed = True
        messages.append(assistant_message)

        display_content = ""
        if not tool_only_mode:
            display_content = _clean_display_content(content)
        if display_content and output.mode == "human":
            print(f"\nassistant: {display_content}")
        if output.mode == "json":
            payload = {
                "content": display_content,
            }
            if debug:
                payload["raw_content"] = content
                payload["tool_calls_raw"] = tool_calls
            _emit_event(output, "assistant_message", payload)
        if logger:
            logger.log(
                "assistant_message",
                {"content": content, "tool_calls": tool_calls},
            )

        if text_tool_call_detected:
            warning = (
                "assistant: Plain-text tool call detected. "
                "Please emit tool_calls instead."
            )
            if output.mode == "human":
                print(f"\n{warning}")
            _emit_event(
                output,
                "policy_retry",
                {"reason": "plain_text_tool_call"},
            )
            if logger:
                logger.log(
                    "policy_retry",
                    {"reason": "plain_text_tool_call"},
                )
            if step < max_steps - 1:
                enforcement_message = {
                    "role": "system",
                    "content": (
                        "You must emit tool calls using tool_calls only. "
                        "Do not print tool calls as text or include tags."
                    ),
                }
                messages.append(enforcement_message)
                continue
            errors.append("policy_error: plain_text_tool_call")
            success = False
            break

        if allowed_tool_names and tool_calls:
            invalid_calls = [
                call.get("function", {}).get("name")
                for call in tool_calls
                if call.get("function", {}).get("name") not in allowed_tool_names
            ]
            if invalid_calls:
                retries += 1
                warning = (
                    "assistant: Tool policy allows only "
                    f"{', '.join(sorted(allowed_tool_names))}. "
                    "Retrying tool selection."
                )
                if output.mode == "human":
                    print(f"\n{warning}")
                _emit_event(
                    output,
                    "policy_retry",
                    {"reason": "tool_not_allowed"},
                )
                if logger:
                    logger.log(
                        "policy_retry",
                        {"reason": "tool_not_allowed"},
                    )
                if retries <= 1 and step < max_steps - 1:
                    enforcement_message = {
                        "role": "system",
                        "content": (
                            "Tool-only mode: call only the allowed tool "
                            "for this prompt. Do not call any other tools."
                        ),
                    }
                    messages.append(enforcement_message)
                    continue
                if output.mode == "human":
                    print("\nassistant: Policy error: tool_not_allowed.")
                _emit_event(
                    output,
                    "policy_error",
                    {"reason": "tool_not_allowed"},
                )
                if logger:
                    logger.log(
                        "policy_error",
                        {"reason": "tool_not_allowed"},
                    )
                errors.append("policy_error: tool_not_allowed")
                success = False
                break

        if require_list_projects:
            has_required = any(
                call.get("function", {}).get("name") == "list_projects"
                for call in tool_calls
            )
            if not has_required:
                retries += 1
                warning = (
                    "assistant: Tool policy requires list_projects. "
                    "Retrying tool selection."
                )
                if output.mode == "human":
                    print(f"\n{warning}")
                _emit_event(
                    output,
                    "policy_retry",
                    {"reason": "list_projects_required"},
                )
                if logger:
                    logger.log(
                        "policy_retry",
                        {"reason": "list_projects_required"},
                    )
                if retries <= 1 and step < max_steps - 1:
                    enforcement_message = {
                        "role": "system",
                        "content": (
                            "You must call list_projects to answer "
                            "project listing questions before responding."
                        ),
                    }
                    messages.append(enforcement_message)
                    continue
                if output.mode == "human":
                    print("\nassistant: Policy error: list_projects not called.")
                _emit_event(
                    output,
                    "policy_error",
                    {"reason": "list_projects_required"},
                )
                if logger:
                    logger.log(
                        "policy_error",
                        {"reason": "list_projects_required"},
                    )
                errors.append("policy_error: list_projects_required")
                success = False
                break

        if require_project_exists:
            has_required = any(
                call.get("function", {}).get("name") == "project_exists"
                for call in tool_calls
            )
            if not has_required:
                retries += 1
                warning = (
                    "assistant: Tool policy requires project_exists. "
                    "Retrying tool selection."
                )
                if output.mode == "human":
                    print(f"\n{warning}")
                _emit_event(
                    output,
                    "policy_retry",
                    {"reason": "project_exists_required"},
                )
                if logger:
                    logger.log(
                        "policy_retry",
                        {"reason": "project_exists_required"},
                    )
                if retries <= 1 and step < max_steps - 1:
                    enforcement_message = {
                        "role": "system",
                        "content": (
                            "You must call project_exists to answer "
                            "project existence questions before responding."
                        ),
                    }
                    messages.append(enforcement_message)
                    continue
                if output.mode == "human":
                    print("\nassistant: Policy error: project_exists not called.")
                _emit_event(
                    output,
                    "policy_error",
                    {"reason": "project_exists_required"},
                )
                if logger:
                    logger.log(
                        "policy_error",
                        {"reason": "project_exists_required"},
                    )
                errors.append("policy_error: project_exists_required")
                success = False
                break

        if not tool_calls:
            break

        if debug:
            if output.mode == "human":
                print(
                    f"\n[debug] tool_calls: {json.dumps(tool_calls, indent=2)}"
                )
            else:
                _emit_event(
                    output,
                    "debug_tool_calls",
                    {"tool_calls": tool_calls},
                )
        for call in tool_calls:
            function = call.get("function", {})
            tool_name = function.get("name")
            raw_args = function.get("arguments", {})

            if not tool_name:
                tool_result = ToolResult(
                    ok=False,
                    payload={
                        "ok": False,
                        "error": {
                            "code": "INVALID_TOOL_CALL",
                            "message": "Tool name missing.",
                            "details": {},
                        },
                    },
                )
                messages.append(_tool_message("unknown", tool_result.payload))
                errors.append("invalid_tool_call: missing_name")
                success = False
                continue

            try:
                args = _normalize_args(raw_args)
            except ValueError as exc:
                tool_result = ToolResult(
                    ok=False,
                    payload={
                        "ok": False,
                        "error": {
                            "code": "INVALID_TOOL_ARGS",
                            "message": str(exc),
                            "details": {"tool": tool_name},
                        },
                    },
                )
                messages.append(_tool_message(tool_name, tool_result.payload))
                errors.append(f"invalid_tool_args: {exc}")
                success = False
                continue

            if (
                tool_name == "list_projects"
                and require_list_projects
                and not _explicit_list_path_in_prompt(user_input)
            ):
                args = {}

            schema = tool_index.get(tool_name)
            if schema is None:
                tool_result = ToolResult(
                    ok=False,
                    payload={
                        "ok": False,
                        "error": {
                            "code": "UNKNOWN_TOOL",
                            "message": "Tool is not defined.",
                            "details": {"tool": tool_name},
                        },
                    },
                )
                messages.append(_tool_message(tool_name, tool_result.payload))
                errors.append(f"unknown_tool: {tool_name}")
                success = False
                continue

            try:
                _validate_tool_call_args(tool_name, args, schema)
            except ValueError as exc:
                tool_result = ToolResult(
                    ok=False,
                    payload={
                        "ok": False,
                        "error": {
                            "code": "INVALID_TOOL_ARGS",
                            "message": str(exc),
                            "details": {"tool": tool_name},
                        },
                    },
                )
                messages.append(_tool_message(tool_name, tool_result.payload))
                errors.append(f"invalid_tool_args: {exc}")
                success = False
                continue

            if tool_name in MUTATING_TOOLS:
                approved = _prompt_approval(
                    tool_name, args, auto_approve, output
                )
                if not approved:
                    tool_result = ToolResult(
                        ok=False,
                        payload={
                            "ok": False,
                            "error": {
                                "code": "USER_DECLINED",
                                "message": "User declined the action.",
                                "details": {"tool": tool_name},
                            },
                        },
                    )
                    messages.append(_tool_message(tool_name, tool_result.payload))
                    errors.append(f"user_declined: {tool_name}")
                    success = False
                    continue

            if logger:
                logger.log(
                    "tool_call",
                    {"tool": tool_name, "args": args},
                )
            if output.mode == "json":
                _emit_event(
                    output, "tool_call", {"tool": tool_name, "args": args}
                )
            tool_response = mcp.call_tool(tool_name, args)
            if debug:
                if output.mode == "human":
                    print(
                        f"[debug] tool_response ({tool_name}): "
                        f"{json.dumps(tool_response, indent=2)}"
                    )
                else:
                    _emit_event(
                        output,
                        "debug_tool_response",
                        {"tool": tool_name, "response": tool_response},
                    )
            if output.mode == "json":
                _emit_event(
                    output,
                    "tool_response",
                    {"tool": tool_name, "response": tool_response},
                )
            elif tool_name in {"project_exists", "list_projects"}:
                print("\nassistant (tool_result):")
                print(json.dumps(tool_response, indent=2))
            if logger:
                logger.log(
                    "tool_response",
                    {"tool": tool_name, "response": tool_response},
                )
            if isinstance(tool_response, dict) and not tool_response.get(
                "ok", True
            ):
                error = tool_response.get("error", {})
                code = error.get("code", "UNKNOWN_ERROR")
                message = error.get("message", "")
                errors.append(
                    f"tool_error: {tool_name} {code} {message}".strip()
                )
                success = False
            messages.append(_tool_message(tool_name, tool_response))
        if tool_only_mode:
            break
        continue

    else:
        if output.mode == "human":
            print("\nassistant: Max steps reached; stopping tool loop.")
        else:
            _emit_event(
                output,
                "notice",
                {"message": "Max steps reached; stopping tool loop."},
            )

    if hint_message and hint_message in messages:
        messages.remove(hint_message)
    if routing_message and routing_message in messages:
        messages.remove(routing_message)
    if tool_only_message and tool_only_message in messages:
        messages.remove(tool_only_message)
    if enforcement_message and enforcement_message in messages:
        messages.remove(enforcement_message)

    if not tool_calls_observed and require_tool_calls:
        errors.append("policy_error: tool_calls_required")
        success = False

    if strict_tool_calls and not tool_calls_observed:
        if "policy_error: tool_calls_required" not in errors:
            errors.append("policy_error: tool_calls_required")
        success = False
        fallback = None

    if not success and fallback:
        tool_name, args = fallback
        auto_repair_succeeded = False
        if logger:
            logger.log(
                "policy_autofix",
                {"tool": tool_name, "args": args},
            )
        if tool_name in MUTATING_TOOLS:
            approved = _prompt_approval(
                tool_name, args, auto_approve, output
            )
            if not approved:
                errors.append(f"user_declined: {tool_name}")
                success = False
                auto_repair_succeeded = False
                fallback = None
                outcome = StepOutcome(
                    prompt=user_input,
                    success=success,
                    errors=errors,
                    warnings=warnings,
                )
                if logger:
                    logger.log(
                        "step_outcome",
                        {
                            "prompt": outcome.prompt,
                            "success": outcome.success,
                            "errors": outcome.errors,
                            "warnings": outcome.warnings,
                        },
                    )
                return outcome
        if logger:
            logger.log("tool_call", {"tool": tool_name, "args": args})
        if output.mode == "json":
            _emit_event(
                output, "tool_call", {"tool": tool_name, "args": args}
            )
        tool_response = mcp.call_tool(tool_name, args)
        if isinstance(tool_response, dict) and not tool_response.get("ok", True):
            error = tool_response.get("error", {})
            code = error.get("code")
            if tool_name == "create_project" and code == "PROJECT_EXISTS":
                warnings.extend(errors)
                warnings.append("auto_repair: create_project (exists)")
                errors = []
                success = True
                auto_repair_succeeded = True
            if tool_name in {
                "write_markdown",
                "edit_markdown",
                "delete_markdown",
            }:
                if code == "FILE_NOT_FOUND":
                    path_value = args.get("path")
                    if isinstance(path_value, str) and path_value.startswith(
                        "projects/active/"
                    ):
                        alt_args = dict(args)
                        alt_args["path"] = path_value.replace(
                            "projects/active/", "projects/", 1
                        )
                        tool_response = mcp.call_tool(tool_name, alt_args)
                        error = (
                            tool_response.get("error", {})
                            if isinstance(tool_response, dict)
                            else {}
                        )
                        code = error.get("code")
                if tool_name == "write_markdown" and code == "FILE_NOT_FOUND":
                    content = ""
                    operation = args.get("operation")
                    if isinstance(operation, dict):
                        content = operation.get("content", "")
                    create_args = {"path": args.get("path"), "content": content}
                    tool_response = mcp.call_tool(
                        "create_markdown", create_args
                    )
                if tool_name == "delete_markdown" and code == "FILE_NOT_FOUND":
                    warnings.extend(errors)
                    warnings.append("auto_repair: delete_markdown (already gone)")
                    errors = []
                    success = True
                    auto_repair_succeeded = True
                if tool_name == "edit_markdown" and code in {
                    "SECTION_NOT_FOUND",
                    "FILE_NOT_FOUND",
                }:
                    operation = args.get("operation", {})
                    content = (
                        operation.get("content", "")
                        if isinstance(operation, dict)
                        else ""
                    )
                    append_args = {
                        "path": args.get("path"),
                        "operation": {"type": "append", "content": content},
                    }
                    tool_response = mcp.call_tool(
                        "write_markdown", append_args
                    )
        messages.append(_tool_message(tool_name, tool_response))
        if output.mode == "json":
            _emit_event(
                output,
                "tool_response",
                {"tool": tool_name, "response": tool_response},
            )
        elif tool_name in {"project_exists", "list_projects"}:
            print("\nassistant (tool_result):")
            print(json.dumps(tool_response, indent=2))
        if isinstance(tool_response, dict) and tool_response.get("ok"):
            warnings.extend(errors)
            warnings.append(f"auto_repair: {tool_name}")
            errors = []
            success = True
            auto_repair_succeeded = True
        if not auto_repair_succeeded:
            error = tool_response.get("error", {}) if isinstance(tool_response, dict) else {}
            code = error.get("code", "UNKNOWN_ERROR")
            message = error.get("message", "")
            errors.append(
                f"auto_repair_failed: {tool_name} {code} {message}".strip()
            )

    outcome = StepOutcome(
        prompt=user_input, success=success, errors=errors, warnings=warnings
    )
    if logger:
        logger.log(
            "step_outcome",
            {
                "prompt": outcome.prompt,
                "success": outcome.success,
                "errors": outcome.errors,
                "warnings": outcome.warnings,
            },
        )
    if output.mode == "json":
        _emit_event(
            output,
            "step_outcome",
            {
                "prompt": outcome.prompt,
                "success": outcome.success,
                "errors": outcome.errors,
                "warnings": outcome.warnings,
            },
        )
    return outcome


def run_loop(
    ollama: OllamaClient,
    mcp: McpClient,
    tools: list[dict[str, Any]],
    auto_approve: bool,
    max_steps: int,
    system_prompt: str,
    debug: bool,
    auto_repair: bool,
    strict_tool_calls: bool,
    logger: JsonlLogger | None,
    output: OutputConfig,
) -> None:
    tool_index = _build_tool_index(tools)
    tool_def_index = _build_tool_definition_index(tools)
    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    if output.mode == "human":
        print("Enter a request (type 'exit' to quit).")
    while True:
        try:
            prompt = "\nuser> " if output.mode == "human" else ""
            user_input = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            if output.mode == "human":
                print("\nExiting.")
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            break
        _process_user_input(
            user_input,
            messages,
            ollama,
            mcp,
            tools,
            tool_index,
            tool_def_index,
            auto_approve,
            max_steps,
            debug,
            auto_repair,
            strict_tool_calls,
            logger,
            output,
        )


def run_scripted_session(
    ollama: OllamaClient,
    mcp: McpClient,
    tools: list[dict[str, Any]],
    inputs: list[str],
    auto_approve: bool,
    max_steps: int,
    system_prompt: str,
    debug: bool,
    auto_repair: bool,
    strict_tool_calls: bool,
    logger: JsonlLogger | None,
    output: OutputConfig,
) -> list[StepOutcome]:
    tool_index = _build_tool_index(tools)
    tool_def_index = _build_tool_definition_index(tools)
    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    outcomes: list[StepOutcome] = []
    for user_input in inputs:
        user_input = user_input.strip()
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            break
        if output.mode == "human":
            print(f"\nuser> {user_input}")
        outcome = _process_user_input(
            user_input,
            messages,
            ollama,
            mcp,
            tools,
            tool_index,
            tool_def_index,
            auto_approve,
            max_steps,
            debug,
            auto_repair,
            strict_tool_calls,
            logger,
            output,
        )
        outcomes.append(outcome)
        if output.mode == "human":
            status = "PASS" if outcome.success else "FAIL"
            if outcome.errors or outcome.warnings:
                notes = outcome.errors + outcome.warnings
                print(f"{status}: {user_input} - {', '.join(notes)}")
            else:
                print(f"{status}: {user_input}")

    failures = [outcome for outcome in outcomes if not outcome.success]
    if output.mode == "human":
        if failures:
            print(
                f"\nWorkflow FAILED ({len(failures)}/{len(outcomes)} steps failed)."
            )
        else:
            print(f"\nWorkflow PASSED ({len(outcomes)} steps).")
    else:
        _emit_event(
            output,
            "workflow_summary",
            {
                "success": not failures,
                "total": len(outcomes),
                "failed": len(failures),
            },
        )
    return outcomes


def main() -> int:
    _load_dotenv(ENV_PATH)

    parser = argparse.ArgumentParser(
        description="Interactive Ollama agent for MCP workflow testing."
    )
    parser.add_argument(
        "--tools",
        type=Path,
        default=TOOLS_PATH,
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
        "--auto-approve",
        action="store_true",
        help="Auto-approve all mutating tool calls.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print tool calls and tool responses.",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help="Write JSONL logs to this file (set to '-' to disable).",
    )
    parser.add_argument(
        "--auto-repair",
        action="store_true",
        help="Attempt rule-based fallback tool calls when the model fails.",
    )
    parser.add_argument(
        "--strict-tool-calls",
        action="store_true",
        help="Fail if no tool_calls are produced and skip auto-repair.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=8,
        help="Max tool-call steps per user message.",
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

    log_path = None if str(args.log_file) == "-" else args.log_file
    logger = JsonlLogger(log_path)
    output = OutputConfig(mode=args.output)
    ollama = OllamaClient(args.ollama_base_url, args.model)
    mcp = McpClient(args.mcp_base_url)

    try:
        run_loop(
            ollama,
            mcp,
            tools,
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
