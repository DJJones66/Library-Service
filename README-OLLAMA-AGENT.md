# Ollama Agent Workflow Notes

This repo includes an interactive agent that uses Ollama tool calling to drive
the MCP server with natural language. The tool schemas live in
`tools/mcp_tools.json`, and the agent consumes those schemas at runtime via the
loader in `tools/mcp_tools.py`. The MCP server exposes the current tool
definitions at `GET /tools`, which always re-reads the JSON file so updates
are picked up without a restart (useful during testing).

## When You Add or Change MCP Tools

Update **all** of the following so the agent stays reliable:

1. **Tool schema**
   - Add or edit the tool entry in `tools/mcp_tools.json`.

2. **System prompt**
   - Update the prompt in `scripts/ollama_agent_workflow.py` with:
     - The new tool name and required arguments.
     - One concrete example of a valid tool call.
     - If the tool is easy to misuse, include an invalid → corrected example.

3. **Validation (optional but recommended)**
   - If the tool has non-obvious constraints, add a validator in
     `scripts/ollama_agent_workflow.py` so malformed tool calls are rejected
     before they hit MCP.

4. **Routing hints & fallbacks**
   - Add or update routing hints in `scripts/ollama_agent_workflow.py`:
     - `_tool_hint_for_query` (lightweight hint)
     - `_routing_hint_for_prompt` (explicit routing rules per prompt)
   - If needed, extend `_fallback_tool_from_prompt` for auto-repair.
   - Keep the per-turn tool subsetting in `_process_user_input` aligned with any
     new “must-call” tools (the agent can pass only the required tool to the
     model for those prompts).

## Log Replay

The agent writes JSONL logs to `logs/ollama_agent_workflow.jsonl`. You can
replay or inspect them with:

```bash
python scripts/replay_ollama_agent_logs.py
```

Print only the original user inputs (for piping back into the agent):

```bash
python scripts/replay_ollama_agent_logs.py --inputs-only
```

Include tool calls and tool responses:

```bash
python scripts/replay_ollama_agent_logs.py --include-tools
```

## Scripted User Workflow

To simulate a user running common Library interactions, use:

```bash
python scripts/run_common_workflow.py --mcp-base-url http://127.0.0.1:8000
```

The script prints PASS/FAIL per prompt and exits non-zero if any step fails.

Strict mode (fail if the model does not emit tool_calls and skip auto-repair):

```bash
python scripts/run_common_workflow.py --strict-tool-calls --no-auto-repair
```

Override prompts with a text file (one prompt per line):

```bash
python scripts/run_common_workflow.py --prompts prompts.txt
```

## Common Prompt Enhancement Patterns

Use one (or more) of these patterns when a tool is mis-called:

- **Golden path example**
  - One clear, minimal example showing correct arguments.
- **Invalid → Corrected**
  - Show a common mistake and the corrected call.
- **Argument constraints**
  - Explicitly state required fields and their types.
- **Path hints**
  - E.g. "project paths should look like `projects/active/<name>`".

These adjustments make the model more stable without changing MCP code.
