#!/bin/bash
# Forge loop — simple, portable, single-agent
# Usage:
#   ./.agents/forge/loop.sh                 # build mode, default iterations
#   ./.agents/forge/loop.sh build           # build mode
#   ./.agents/forge/loop.sh prd "request"   # generate PRD via agent
#   ./.agents/forge/loop.sh 10              # build mode, 10 iterations
#   ./.agents/forge/loop.sh build 1 --no-commit
#   ./.agents/forge/loop.sh sign "text"     # add formatted sign to guardrails.md
#   ./.agents/forge/loop.sh sign ls         # list all current signs
#   ./.agents/forge/loop.sh sign --clear    # reset guardrails to defaults

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${FORGE_ROOT:-${SCRIPT_DIR}/../..}" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/config.sh"

DEFAULT_PRD_PATH=".agents/tasks/prd.json"
DEFAULT_PROGRESS_PATH=".forge/progress.md"
DEFAULT_AGENTS_PATH="AGENTS.md"
DEFAULT_PROMPT_BUILD=".agents/forge/PROMPT_build.md"
DEFAULT_GUARDRAILS_PATH=".forge/guardrails.md"
DEFAULT_ERRORS_LOG_PATH=".forge/errors.log"
DEFAULT_ACTIVITY_LOG_PATH=".forge/activity.log"
DEFAULT_TMP_DIR=".forge/.tmp"
DEFAULT_RUNS_DIR=".forge/runs"
DEFAULT_GUARDRAILS_REF=".agents/forge/references/GUARDRAILS.md"
DEFAULT_CONTEXT_REF=".agents/forge/references/CONTEXT_ENGINEERING.md"
DEFAULT_ACTIVITY_CMD=".agents/forge/log-activity.sh"
DEFAULT_FORGE_DIR=".forge"
DEFAULT_FORGE_ITER_DIR=".forge/iterations"
DEFAULT_FORGE_LOGS_DIR=".forge/logs"
DEFAULT_FORGE_STORIES_DIR=".forge/stories"
DEFAULT_FORGE_EVENTS_PATH=".forge/events.jsonl"
DEFAULT_FORGE_PROJECT_PATH=".forge/project.json"
DEFAULT_FORGE_METRICS_PATH=".forge/metrics.json"
DEFAULT_FORGE_PAUSE_PATH=".forge/paused.json"
if [[ -n "${FORGE_ROOT:-}" ]]; then
  agents_path="$FORGE_ROOT/.agents/forge/agents.sh"
else
  agents_path="$SCRIPT_DIR/agents.sh"
fi
if [[ -f "$agents_path" ]]; then
  # shellcheck source=/dev/null
  source "$agents_path"
fi

DEFAULT_MAX_ITERATIONS=25
DEFAULT_NO_COMMIT=false
DEFAULT_STALE_SECONDS=0
DEFAULT_TIMEOUT_SECONDS=""
DEFAULT_TIMEOUT_KILL_AFTER=30
PRD_REQUEST_PATH=""
PRD_INLINE=""
PRD_FROM_FILE=0
SIGN_INLINE=""
SIGN_CLEAR=false
SIGN_LIST=false

# Optional config overrides (simple shell vars)
if [ -f "$CONFIG_FILE" ]; then
  # shellcheck source=/dev/null
  . "$CONFIG_FILE"
fi

DEFAULT_AGENT_NAME="${DEFAULT_AGENT:-codex}"
resolve_agent_cmd() {
  local name="$1"
  case "$name" in
    claude)
      echo "${AGENT_CLAUDE_CMD:-claude -p --dangerously-skip-permissions \"\$(cat {prompt})\"}"
      ;;
    droid)
      echo "${AGENT_DROID_CMD:-droid exec --skip-permissions-unsafe -f {prompt}}"
      ;;
    codex|"")
      echo "${AGENT_CODEX_CMD:-codex exec --yolo --skip-git-repo-check -}"
      ;;
    *)
      echo "${AGENT_CODEX_CMD:-codex exec --yolo --skip-git-repo-check -}"
      ;;
  esac
}
DEFAULT_AGENT_CMD="$(resolve_agent_cmd "$DEFAULT_AGENT_NAME")"

PRD_PATH="${PRD_PATH:-$DEFAULT_PRD_PATH}"
PROGRESS_PATH="${PROGRESS_PATH:-$DEFAULT_PROGRESS_PATH}"
AGENTS_PATH="${AGENTS_PATH:-$DEFAULT_AGENTS_PATH}"
PROMPT_BUILD="${PROMPT_BUILD:-$DEFAULT_PROMPT_BUILD}"
GUARDRAILS_PATH="${GUARDRAILS_PATH:-$DEFAULT_GUARDRAILS_PATH}"
ERRORS_LOG_PATH="${ERRORS_LOG_PATH:-$DEFAULT_ERRORS_LOG_PATH}"
ACTIVITY_LOG_PATH="${ACTIVITY_LOG_PATH:-$DEFAULT_ACTIVITY_LOG_PATH}"
TMP_DIR="${TMP_DIR:-$DEFAULT_TMP_DIR}"
RUNS_DIR="${RUNS_DIR:-$DEFAULT_RUNS_DIR}"
GUARDRAILS_REF="${GUARDRAILS_REF:-$DEFAULT_GUARDRAILS_REF}"
CONTEXT_REF="${CONTEXT_REF:-$DEFAULT_CONTEXT_REF}"
ACTIVITY_CMD="${ACTIVITY_CMD:-$DEFAULT_ACTIVITY_CMD}"
FORGE_DIR="${FORGE_DIR:-$DEFAULT_FORGE_DIR}"
FORGE_ITER_DIR="${FORGE_ITER_DIR:-$DEFAULT_FORGE_ITER_DIR}"
FORGE_LOGS_DIR="${FORGE_LOGS_DIR:-$DEFAULT_FORGE_LOGS_DIR}"
FORGE_STORIES_DIR="${FORGE_STORIES_DIR:-$DEFAULT_FORGE_STORIES_DIR}"
FORGE_EVENTS_PATH="${FORGE_EVENTS_PATH:-$DEFAULT_FORGE_EVENTS_PATH}"
FORGE_PROJECT_PATH="${FORGE_PROJECT_PATH:-$DEFAULT_FORGE_PROJECT_PATH}"
FORGE_METRICS_PATH="${FORGE_METRICS_PATH:-$DEFAULT_FORGE_METRICS_PATH}"
FORGE_PAUSE_PATH="${FORGE_PAUSE_PATH:-$DEFAULT_FORGE_PAUSE_PATH}"
AGENT_CMD="${AGENT_CMD:-$DEFAULT_AGENT_CMD}"
MAX_ITERATIONS="${MAX_ITERATIONS:-$DEFAULT_MAX_ITERATIONS}"
NO_COMMIT="${NO_COMMIT:-$DEFAULT_NO_COMMIT}"
STALE_SECONDS="${STALE_SECONDS:-$DEFAULT_STALE_SECONDS}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-$DEFAULT_TIMEOUT_SECONDS}"
TIMEOUT_KILL_AFTER="${TIMEOUT_KILL_AFTER:-$DEFAULT_TIMEOUT_KILL_AFTER}"
DRY_RUN="${FORGE_DRY_RUN:-0}"

abs_path() {
  local p="$1"
  if [[ "$p" = /* ]]; then
    echo "$p"
  else
    echo "$ROOT_DIR/$p"
  fi
}

PRD_PATH="$(abs_path "$PRD_PATH")"
PROGRESS_PATH="$(abs_path "$PROGRESS_PATH")"
AGENTS_PATH="$(abs_path "$AGENTS_PATH")"
PROMPT_BUILD="$(abs_path "$PROMPT_BUILD")"
GUARDRAILS_PATH="$(abs_path "$GUARDRAILS_PATH")"
ERRORS_LOG_PATH="$(abs_path "$ERRORS_LOG_PATH")"
ACTIVITY_LOG_PATH="$(abs_path "$ACTIVITY_LOG_PATH")"
TMP_DIR="$(abs_path "$TMP_DIR")"
RUNS_DIR="$(abs_path "$RUNS_DIR")"
GUARDRAILS_REF="$(abs_path "$GUARDRAILS_REF")"
CONTEXT_REF="$(abs_path "$CONTEXT_REF")"
ACTIVITY_CMD="$(abs_path "$ACTIVITY_CMD")"
FORGE_DIR="$(abs_path "$FORGE_DIR")"
FORGE_ITER_DIR="$(abs_path "$FORGE_ITER_DIR")"
FORGE_LOGS_DIR="$(abs_path "$FORGE_LOGS_DIR")"
FORGE_STORIES_DIR="$(abs_path "$FORGE_STORIES_DIR")"
FORGE_EVENTS_PATH="$(abs_path "$FORGE_EVENTS_PATH")"
FORGE_PROJECT_PATH="$(abs_path "$FORGE_PROJECT_PATH")"
FORGE_METRICS_PATH="$(abs_path "$FORGE_METRICS_PATH")"
FORGE_PAUSE_PATH="$(abs_path "$FORGE_PAUSE_PATH")"

init_forge_state() {
  mkdir -p "$FORGE_DIR" "$FORGE_ITER_DIR" "$FORGE_LOGS_DIR" "$FORGE_STORIES_DIR"
  if [ ! -f "$FORGE_EVENTS_PATH" ]; then
    touch "$FORGE_EVENTS_PATH"
  fi
}

forge_emit_event() {
  local type="$1"
  local payload="${2:-}"
  local story_id="${3:-}"
  local iteration_id="${4:-}"
  python3 - "$FORGE_EVENTS_PATH" "$type" "$payload" "$story_id" "$iteration_id" "$RUN_TAG" "$MODE" <<'PY'
import json
import sys
from datetime import datetime, timezone

path = sys.argv[1]
event_type = sys.argv[2]
payload_raw = sys.argv[3] if len(sys.argv) > 3 else ""
story_id = sys.argv[4] if len(sys.argv) > 4 else ""
iteration_id = sys.argv[5] if len(sys.argv) > 5 else ""
run_id = sys.argv[6] if len(sys.argv) > 6 else ""
mode = sys.argv[7] if len(sys.argv) > 7 else ""

try:
    payload = json.loads(payload_raw) if payload_raw else {}
except Exception:
    payload = {"message": payload_raw} if payload_raw else {}

event = {
    "type": event_type,
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "payload": payload,
}
if story_id:
    event["story_id"] = story_id
if iteration_id:
    event["iteration_id"] = iteration_id
if run_id:
    event["run_id"] = run_id
if mode:
    event["mode"] = mode

with open(path, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(event) + "\n")
PY
}

json_escape() {
  python3 - "$1" <<'PY'
import json
import sys

print(json.dumps(sys.argv[1]))
PY
}

forge_sync_project() {
  python3 - "$PRD_PATH" "$FORGE_PROJECT_PATH" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

prd_path = Path(sys.argv[1])
project_path = Path(sys.argv[2])

data = {}
if prd_path.exists():
    try:
        data = json.loads(prd_path.read_text())
    except Exception:
        data = {}

project = {
    "project": data.get("project") if isinstance(data, dict) else None,
    "prdPath": str(prd_path),
    "qualityGates": data.get("qualityGates") if isinstance(data, dict) else [],
    "stories": [s.get("id") for s in (data.get("stories") or []) if isinstance(s, dict)],
    "updatedAt": datetime.now(timezone.utc).isoformat(),
}

project_path.parent.mkdir(parents=True, exist_ok=True)
project_path.write_text(json.dumps(project, indent=2) + "\n")
PY
}

forge_sync_stories() {
  python3 - "$PRD_PATH" "$FORGE_STORIES_DIR" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

prd_path = Path(sys.argv[1])
stories_dir = Path(sys.argv[2])
stories_dir.mkdir(parents=True, exist_ok=True)

if not prd_path.exists():
    sys.exit(0)

try:
    data = json.loads(prd_path.read_text())
except Exception:
    sys.exit(0)

stories = data.get("stories") if isinstance(data, dict) else None
if not isinstance(stories, list):
    sys.exit(0)

now = datetime.now(timezone.utc).isoformat()
for story in stories:
    if not isinstance(story, dict):
        continue
    story_id = story.get("id")
    if not story_id:
        continue
    payload = {
        "id": story_id,
        "title": story.get("title"),
        "status": story.get("status"),
        "description": story.get("description"),
        "dependsOn": story.get("dependsOn") or [],
        "acceptanceCriteria": story.get("acceptanceCriteria") or [],
        "startedAt": story.get("startedAt"),
        "completedAt": story.get("completedAt"),
        "updatedAt": story.get("updatedAt") or now,
    }
    (stories_dir / f"{story_id}.json").write_text(json.dumps(payload, indent=2) + "\n")
PY
}

forge_next_iteration_id() {
  python3 - "$FORGE_METRICS_PATH" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
data = {}
if path.exists():
    try:
        data = json.loads(path.read_text())
    except Exception:
        data = {}

count = int(data.get("iterationCount", 0)) + 1
iter_id = f"iter-{count:02d}"
data["iterationCount"] = count
data["lastIterationId"] = iter_id
data["updatedAt"] = datetime.now(timezone.utc).isoformat()
if "createdAt" not in data:
    data["createdAt"] = data["updatedAt"]

path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data, indent=2) + "\n")
print(iter_id)
PY
}

require_agent() {
  local agent_cmd="${1:-$AGENT_CMD}"
  local agent_bin
  agent_bin="${agent_cmd%% *}"
  if [ -z "$agent_bin" ]; then
    echo "AGENT_CMD is empty. Set it in config.sh."
    exit 1
  fi
  if ! command -v "$agent_bin" >/dev/null 2>&1; then
    echo "Agent command not found: $agent_bin"
    case "$agent_bin" in
      codex)
        echo "Install: npm i -g @openai/codex"
        ;;
      claude)
        echo "Install: curl -fsSL https://claude.ai/install.sh | bash"
        ;;
      droid)
        echo "Install: curl -fsSL https://app.factory.ai/cli | sh"
        ;;
      opencode)
        echo "Install: curl -fsSL https://opencode.ai/install.sh | bash"
        ;;
    esac
    echo "Then authenticate per the CLI's instructions."
    exit 1
  fi
}

run_agent() {
  local prompt_file="$1"
  local agent_cmd="${2:-$AGENT_CMD}"
  if [[ "$agent_cmd" == *"{prompt}"* ]]; then
    local escaped
    escaped=$(printf '%q' "$prompt_file")
    local cmd="${agent_cmd//\{prompt\}/$escaped}"
    run_cmd "$cmd"
  else
    local escaped
    escaped=$(printf '%q' "$prompt_file")
    run_cmd "cat $escaped | $agent_cmd"
  fi
}

run_agent_inline() {
  local prompt_file="$1"
  local prompt_content
  prompt_content="$(cat "$prompt_file")"
  local escaped
  escaped=$(printf '%q' "$prompt_content")
  local cmd="${PRD_AGENT_CMD:-$AGENT_CMD}"
  if [[ "$cmd" == *"{prompt}"* ]]; then
    cmd="${cmd//\{prompt\}/$escaped}"
  else
    cmd="$cmd $escaped"
  fi
  run_cmd "$cmd"
}

run_cmd() {
  local cmd="$1"
  if [ -n "${TIMEOUT_SECONDS:-}" ] && [ "${TIMEOUT_SECONDS}" -gt 0 ]; then
    if command -v timeout >/dev/null 2>&1; then
      timeout --preserve-status --kill-after="${TIMEOUT_KILL_AFTER}s" "${TIMEOUT_SECONDS}s" bash -c "$cmd"
    else
      echo "timeout not found; running without timeout" >&2
      bash -c "$cmd"
    fi
  else
    bash -c "$cmd"
  fi
}

MODE="build"
while [ $# -gt 0 ]; do
  case "$1" in
    build|prd|sign)
      MODE="$1"
      shift
      ;;
    --prompt)
      PRD_REQUEST_PATH="$2"
      PRD_FROM_FILE=1
      shift 2
      ;;
    --no-commit)
      NO_COMMIT=true
      shift
      ;;
    --clear)
      if [ "$MODE" = "sign" ]; then
        SIGN_CLEAR=true
        shift
      else
        echo "Unknown arg: $1"
        exit 1
      fi
      ;;
    ls)
      if [ "$MODE" = "sign" ]; then
        SIGN_LIST=true
        shift
      else
        echo "Unknown arg: $1"
        exit 1
      fi
      ;;
    *)
      if [ "$MODE" = "prd" ]; then
        PRD_INLINE="${PRD_INLINE:+$PRD_INLINE }$1"
        shift
      elif [ "$MODE" = "sign" ]; then
        SIGN_INLINE="${SIGN_INLINE:+$SIGN_INLINE }$1"
        shift
      elif [[ "$1" =~ ^[0-9]+$ ]]; then
        MAX_ITERATIONS="$1"
        shift
      else
        echo "Unknown arg: $1"
        exit 1
      fi
      ;;
  esac
done

PROMPT_FILE="$PROMPT_BUILD"

if [ "$MODE" = "prd" ]; then
  PRD_USE_INLINE=1
  if [ -z "${PRD_AGENT_CMD:-}" ]; then
    PRD_AGENT_CMD="$AGENT_CMD"
    PRD_USE_INLINE=0
  fi
  if [[ "${PRD_AGENT_CMD:-}" != *"{prompt}"* ]]; then
    PRD_USE_INLINE=0
  fi
  if [ "$DRY_RUN" != "1" ]; then
    require_agent "${PRD_AGENT_CMD:-$AGENT_CMD}"
  fi

  if [[ "$PRD_PATH" == *.json ]]; then
    mkdir -p "$(dirname "$PRD_PATH")" "$TMP_DIR"
  else
    mkdir -p "$PRD_PATH" "$TMP_DIR"
  fi

  if [ -z "$PRD_REQUEST_PATH" ] && [ -n "$PRD_INLINE" ]; then
    PRD_REQUEST_PATH="$TMP_DIR/prd-request-$(date +%Y%m%d-%H%M%S)-$$.txt"
    printf '%s\n' "$PRD_INLINE" > "$PRD_REQUEST_PATH"
  fi

  if [ -z "$PRD_REQUEST_PATH" ] || [ ! -f "$PRD_REQUEST_PATH" ]; then
    echo "PRD request missing. Provide a prompt string or --prompt <file>."
    exit 1
  fi

  if [ "$DRY_RUN" = "1" ]; then
    if [[ "$PRD_PATH" == *.json ]]; then
      if [ ! -f "$PRD_PATH" ]; then
        {
          echo '{'
          echo '  "version": 1,'
          echo '  "project": "braindrive-forge",'
          echo '  "qualityGates": [],'
          echo '  "stories": []'
          echo '}'
        } > "$PRD_PATH"
      fi
    else
      mkdir -p "$PRD_PATH"
      if [ ! -f "$PRD_PATH/prd.json" ]; then
        {
          echo '{'
          echo '  "version": 1,'
          echo '  "project": "braindrive-forge",'
          echo '  "qualityGates": [],'
          echo '  "stories": []'
          echo '}'
        } > "$PRD_PATH/prd.json"
      fi
    fi
    exit 0
  fi

  PRD_PROMPT_FILE="$TMP_DIR/prd-prompt-$(date +%Y%m%d-%H%M%S)-$$.md"
  {
    echo "You are an autonomous coding agent."
    echo "Use the \$prd skill to create a Product Requirements Document in JSON."
    if [[ "$PRD_PATH" == *.json ]]; then
      echo "Save the PRD to: $PRD_PATH"
    else
      echo "Save the PRD as JSON in directory: $PRD_PATH"
      echo "Filename rules: prd-<short-slug>.json using 1-3 meaningful words."
      echo "Examples: prd-workout-tracker.json, prd-usage-billing.json"
    fi
    if [ "$PRD_FROM_FILE" -eq 1 ]; then
      echo "The request is fully specified in the provided file. Do not ask clarifying questions; generate the PRD directly."
    fi
    echo "Do NOT implement anything."
    echo "After creating the PRD, end with:"
    echo "PRD JSON saved to <path>. Close this chat and run \`braindrive-forge build\`."
    echo ""
    echo "User request:"
    cat "$PRD_REQUEST_PATH"
  } > "$PRD_PROMPT_FILE"

  if [ "$PRD_USE_INLINE" -eq 1 ]; then
    run_agent_inline "$PRD_PROMPT_FILE"
  else
    run_agent "$PRD_PROMPT_FILE" "${PRD_AGENT_CMD:-$AGENT_CMD}"
  fi

  # Validate generated PRD JSON
  PRD_TARGET="$PRD_PATH"
  if [[ "$PRD_PATH" != *.json ]]; then
    PRD_TARGET="$(ls -t "$PRD_PATH"/*.json 2>/dev/null | head -n 1)"
  fi
  if [ -n "$PRD_TARGET" ] && [ -f "$PRD_TARGET" ]; then
    python3 -c "import json, sys; json.load(open('$PRD_TARGET'))" 2>&1 || {
      echo "ERROR: PRD JSON is invalid"
      python3 -c "import json, sys; json.load(open('$PRD_TARGET'))" 2>&1 | sed 's/^/  /'
      exit 1
    }
    echo "PRD JSON validated successfully: $PRD_TARGET"
  else
    echo "ERROR: PRD file not found in $PRD_PATH"
    exit 1
  fi

  exit 0
fi

# ─────────────────────────────────────────────────────────────────────────────
# Sign mode: Add runtime guidance to guardrails.md
# ─────────────────────────────────────────────────────────────────────────────

add_sign() {
  local text="$1"
  local timestamp
  timestamp=$(date '+%Y-%m-%d %H:%M:%S')
  local tmp_prompt="$TMP_DIR/sign-prompt-$$.md"
  local tmp_output="$TMP_DIR/sign-output-$$.md"

  mkdir -p "$TMP_DIR"

  # Create prompt for agent to format the sign
  cat > "$tmp_prompt" <<EOF
Format this operator guidance as a Sign for the Forge guardrails file.

Operator's input:
$text

Output ONLY a markdown Sign block in this exact format (no other text):

### Sign: [Short descriptive title, 3-6 words]
- **Trigger**: [When this applies, e.g., "Before running tests", "When implementing auth", or "Always apply"]
- **Instruction**: [The full guidance, can be multi-line]
- **Added**: $timestamp
EOF

  # Run agent to format
  if run_agent "$tmp_prompt" > "$tmp_output" 2>&1; then
    # Extract just the sign block (lines starting with ### Sign: through the Added: line)
    local sign_content
    sign_content=$(sed -n '/^### Sign:/,/^\- \*\*Added\*\*:/p' "$tmp_output")
    if [ -z "$sign_content" ]; then
      # Fallback: use entire output if no sign block found
      sign_content=$(cat "$tmp_output")
    fi
    echo "" >> "$GUARDRAILS_PATH"
    echo "$sign_content" >> "$GUARDRAILS_PATH"
    echo "Sign added to $GUARDRAILS_PATH:"
    echo "$sign_content"
  else
    echo "Agent formatting failed, using raw format"
    cat >> "$GUARDRAILS_PATH" <<EOF

### Sign: Operator Guidance
- **Trigger**: Always apply
- **Instruction**: $text
- **Added**: $timestamp
EOF
    echo "Sign added (raw format)"
  fi

  rm -f "$tmp_prompt" "$tmp_output"
}

reset_guardrails() {
  cat > "$GUARDRAILS_PATH" <<EOF
# Guardrails (Signs)

> Lessons learned from failures. Read before acting.

## Core Signs

### Sign: Read Before Writing
- **Trigger**: Before modifying any file
- **Instruction**: Read the file first
- **Added after**: Core principle

### Sign: Test Before Commit
- **Trigger**: Before committing changes
- **Instruction**: Run required tests and verify outputs
- **Added after**: Core principle

---

## Learned Signs

EOF
  echo "Guardrails reset to defaults: $GUARDRAILS_PATH"
}

list_signs() {
  if [ ! -f "$GUARDRAILS_PATH" ]; then
    echo "No guardrails file found at $GUARDRAILS_PATH"
    exit 1
  fi

  python3 - "$GUARDRAILS_PATH" <<'PY'
import sys
from pathlib import Path

content = Path(sys.argv[1]).read_text()
lines = content.split('\n')

current_section = None
signs = []
current_sign = None

for line in lines:
    stripped = line.strip()

    # Detect section headers
    if stripped == "## Core Signs":
        current_section = "core"
        continue
    elif stripped == "## Learned Signs":
        current_section = "learned"
        continue

    # Detect sign headers
    if stripped.startswith("### Sign:"):
        if current_sign:
            signs.append(current_sign)
        title = stripped.replace("### Sign:", "").strip()
        current_sign = {
            "section": current_section or "unknown",
            "title": title,
            "trigger": "",
            "instruction": "",
        }
        continue

    # Parse sign fields
    if current_sign:
        if stripped.startswith("- **Trigger**:"):
            current_sign["trigger"] = stripped.replace("- **Trigger**:", "").strip()
        elif stripped.startswith("- **Instruction**:"):
            current_sign["instruction"] = stripped.replace("- **Instruction**:", "").strip()

# Don't forget the last sign
if current_sign:
    signs.append(current_sign)

if not signs:
    print("No signs found.")
    sys.exit(0)

# Group by section
core_signs = [s for s in signs if s["section"] == "core"]
learned_signs = [s for s in signs if s["section"] == "learned"]

print("=" * 60)
print("  SIGNS")
print("=" * 60)

if core_signs:
    print("\n[CORE]")
    for i, sign in enumerate(core_signs, 1):
        print(f"  {i}. {sign['title']}")
        if sign['trigger']:
            print(f"     Trigger: {sign['trigger']}")

if learned_signs:
    print("\n[LEARNED]")
    for i, sign in enumerate(learned_signs, 1):
        print(f"  {i}. {sign['title']}")
        if sign['trigger']:
            print(f"     Trigger: {sign['trigger']}")

print()
print(f"Total: {len(core_signs)} core, {len(learned_signs)} learned")
PY
}

if [ "$MODE" = "sign" ]; then
  mkdir -p "$TMP_DIR" "$(dirname "$GUARDRAILS_PATH")"

  if [ "$SIGN_LIST" = "true" ]; then
    list_signs
    exit 0
  fi

  if [ "$SIGN_CLEAR" = "true" ]; then
    reset_guardrails
    exit 0
  fi

  if [ -z "$SIGN_INLINE" ]; then
    echo "Usage: $0 sign \"your guidance text\""
    echo "       $0 sign ls"
    echo "       $0 sign --clear"
    exit 1
  fi

  if [ "$DRY_RUN" != "1" ]; then
    require_agent
  fi

  add_sign "$SIGN_INLINE"
  exit 0
fi

if [ "$DRY_RUN" != "1" ]; then
  require_agent
fi

if [ ! -f "$PROMPT_FILE" ]; then
  echo "Prompt not found: $PROMPT_FILE"
  exit 1
fi

if [ "$MODE" != "prd" ] && [ "$MODE" != "sign" ] && [ ! -f "$PRD_PATH" ]; then
  echo "PRD not found: $PRD_PATH"
  exit 1
fi

init_forge_state
forge_sync_project
forge_sync_stories

mkdir -p "$(dirname "$PROGRESS_PATH")" "$TMP_DIR" "$RUNS_DIR"

if [ ! -f "$PROGRESS_PATH" ]; then
  {
    echo "# Progress Log"
    echo "Started: $(date)"
    echo ""
    echo "## Codebase Patterns"
    echo "- (add reusable patterns here)"
    echo ""
    echo "---"
  } > "$PROGRESS_PATH"
fi

if [ ! -f "$GUARDRAILS_PATH" ]; then
  {
    echo "# Guardrails (Signs)"
    echo ""
    echo "> Lessons learned from failures. Read before acting."
    echo ""
    echo "## Core Signs"
    echo ""
    echo "### Sign: Read Before Writing"
    echo "- **Trigger**: Before modifying any file"
    echo "- **Instruction**: Read the file first"
    echo "- **Added after**: Core principle"
    echo ""
    echo "### Sign: Test Before Commit"
    echo "- **Trigger**: Before committing changes"
    echo "- **Instruction**: Run required tests and verify outputs"
    echo "- **Added after**: Core principle"
    echo ""
    echo "---"
    echo ""
    echo "## Learned Signs"
    echo ""
  } > "$GUARDRAILS_PATH"
fi

if [ ! -f "$ERRORS_LOG_PATH" ]; then
  {
    echo "# Error Log"
    echo ""
    echo "> Failures and repeated issues. Use this to add guardrails."
    echo ""
  } > "$ERRORS_LOG_PATH"
fi

if [ ! -f "$ACTIVITY_LOG_PATH" ]; then
  {
    echo "# Activity Log"
    echo ""
    echo "## Run Summary"
    echo ""
    echo "## Events"
    echo ""
  } > "$ACTIVITY_LOG_PATH"
fi

RUN_TAG="$(date +%Y%m%d-%H%M%S)-$$"

render_prompt() {
  local src="$1"
  local dst="$2"
  local story_meta="$3"
  local story_block="$4"
  local run_id="$5"
  local iter="$6"
  local run_log="$7"
  local run_meta="$8"
  python3 - "$src" "$dst" "$PRD_PATH" "$AGENTS_PATH" "$PROGRESS_PATH" "$ROOT_DIR" "$GUARDRAILS_PATH" "$ERRORS_LOG_PATH" "$ACTIVITY_LOG_PATH" "$GUARDRAILS_REF" "$CONTEXT_REF" "$ACTIVITY_CMD" "$NO_COMMIT" "$story_meta" "$story_block" "$run_id" "$iter" "$run_log" "$run_meta" <<'PY'
import sys
from pathlib import Path

src = Path(sys.argv[1]).read_text()
prd, agents, progress, root = sys.argv[3:7]
guardrails = sys.argv[7]
errors_log = sys.argv[8]
activity_log = sys.argv[9]
guardrails_ref = sys.argv[10]
context_ref = sys.argv[11]
activity_cmd = sys.argv[12]
no_commit = sys.argv[13]
meta_path = sys.argv[14] if len(sys.argv) > 14 else ""
block_path = sys.argv[15] if len(sys.argv) > 15 else ""
run_id = sys.argv[16] if len(sys.argv) > 16 else ""
iteration = sys.argv[17] if len(sys.argv) > 17 else ""
run_log = sys.argv[18] if len(sys.argv) > 18 else ""
run_meta = sys.argv[19] if len(sys.argv) > 19 else ""
repl = {
    "PRD_PATH": prd,
    "AGENTS_PATH": agents,
    "PROGRESS_PATH": progress,
    "REPO_ROOT": root,
    "GUARDRAILS_PATH": guardrails,
    "ERRORS_LOG_PATH": errors_log,
    "ACTIVITY_LOG_PATH": activity_log,
    "GUARDRAILS_REF": guardrails_ref,
    "CONTEXT_REF": context_ref,
    "ACTIVITY_CMD": activity_cmd,
    "NO_COMMIT": no_commit,
    "RUN_ID": run_id,
    "ITERATION": iteration,
    "RUN_LOG_PATH": run_log,
    "RUN_META_PATH": run_meta,
}
story = {"id": "", "title": "", "block": ""}
quality_gates = []
if meta_path:
    try:
        import json
        meta = json.loads(Path(meta_path).read_text())
        story["id"] = meta.get("id", "") or ""
        story["title"] = meta.get("title", "") or ""
        quality_gates = meta.get("quality_gates", []) or []
    except Exception:
        pass
if block_path and Path(block_path).exists():
    story["block"] = Path(block_path).read_text()
repl["STORY_ID"] = story["id"]
repl["STORY_TITLE"] = story["title"]
repl["STORY_BLOCK"] = story["block"]
if quality_gates:
    repl["QUALITY_GATES"] = "\n".join([f"- {g}" for g in quality_gates])
else:
    repl["QUALITY_GATES"] = "- (none)"
for k, v in repl.items():
    src = src.replace("{{" + k + "}}", v)
Path(sys.argv[2]).write_text(src)
PY
}

select_story() {
  local meta_out="$1"
  local block_out="$2"
  python3 - "$PRD_PATH" "$meta_out" "$block_out" "$STALE_SECONDS" <<'PY'
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
try:
    import fcntl
except Exception:
    fcntl = None

prd_path = Path(sys.argv[1])
meta_out = Path(sys.argv[2])
block_out = Path(sys.argv[3])
stale_seconds = 0
if len(sys.argv) > 4:
    try:
        stale_seconds = int(sys.argv[4])
    except Exception:
        stale_seconds = 0

if not prd_path.exists():
    meta_out.write_text(json.dumps({"ok": False, "error": "PRD not found"}, indent=2) + "\n")
    block_out.write_text("")
    sys.exit(0)

def normalize_status(value):
    if value is None:
        return "open"
    return str(value).strip().lower()

def parse_ts(value):
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None

def now_iso():
    return datetime.now(timezone.utc).isoformat()

with prd_path.open("r+", encoding="utf-8") as fh:
    if fcntl is not None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
    try:
        try:
            data = json.load(fh)
        except Exception as exc:
            meta_out.write_text(json.dumps({"ok": False, "error": f"Invalid PRD JSON: {exc}"}, indent=2) + "\n")
            block_out.write_text("")
            sys.exit(0)

        stories = data.get("stories") if isinstance(data, dict) else None
        if not isinstance(stories, list) or not stories:
            meta_out.write_text(json.dumps({"ok": False, "error": "No stories found in PRD"}, indent=2) + "\n")
            block_out.write_text("")
            sys.exit(0)

        story_index = {s.get("id"): s for s in stories if isinstance(s, dict)}

        def is_done(story_id: str) -> bool:
            target = story_index.get(story_id)
            if not isinstance(target, dict):
                return False
            return normalize_status(target.get("status")) == "done"

        if stale_seconds > 0:
            now = datetime.now(timezone.utc)
            for story in stories:
                if not isinstance(story, dict):
                    continue
                if normalize_status(story.get("status")) != "in_progress":
                    continue
                started = parse_ts(story.get("startedAt"))
                if started is None or (now - started).total_seconds() > stale_seconds:
                    story["status"] = "open"
                    story["startedAt"] = None
                    story["completedAt"] = None
                    story["updatedAt"] = now_iso()

        candidate = None
        candidate_index = None
        for idx, story in enumerate(stories, start=1):
            if not isinstance(story, dict):
                continue
            if normalize_status(story.get("status")) != "open":
                continue
            deps = story.get("dependsOn") or []
            if not isinstance(deps, list):
                deps = []
            if all(is_done(dep) for dep in deps):
                candidate = story
                candidate_index = idx
                break

        remaining = sum(
            1 for story in stories
            if isinstance(story, dict) and normalize_status(story.get("status")) != "done"
        )

        def to_list(value):
            return value if isinstance(value, list) else []

        global_gates = to_list(data.get("qualityGates"))
        early_gates = to_list(data.get("qualityGatesEarly"))
        start_index = data.get("qualityGatesStartIndex")
        try:
            start_index = int(start_index) if start_index is not None else None
        except Exception:
            start_index = None

        selected_gates = global_gates
        if candidate is not None:
            story_gates = candidate.get("qualityGates")
            if isinstance(story_gates, list):
                selected_gates = story_gates
            elif start_index is not None and candidate_index is not None and candidate_index < start_index:
                selected_gates = early_gates

        meta = {
            "ok": True,
            "total": len(stories),
            "remaining": remaining,
            "quality_gates": selected_gates,
        }

        if candidate:
            candidate["status"] = "in_progress"
            if not candidate.get("startedAt"):
                candidate["startedAt"] = now_iso()
            candidate["completedAt"] = None
            candidate["updatedAt"] = now_iso()
            meta.update({
                "id": candidate.get("id", ""),
                "title": candidate.get("title", ""),
            })

            depends = candidate.get("dependsOn") or []
            if not isinstance(depends, list):
                depends = []
            acceptance = candidate.get("acceptanceCriteria") or []
            if not isinstance(acceptance, list):
                acceptance = []

            description = candidate.get("description") or ""
            block_lines = []
            block_lines.append(f"### {candidate.get('id', '')}: {candidate.get('title', '')}")
            block_lines.append(f"Status: {candidate.get('status', 'open')}")
            block_lines.append(
                f"Depends on: {', '.join(depends) if depends else 'None'}"
            )
            block_lines.append("")
            block_lines.append("Description:")
            block_lines.append(description if description else "(none)")
            block_lines.append("")
            block_lines.append("Acceptance Criteria:")
            if acceptance:
                block_lines.extend([f"- [ ] {item}" for item in acceptance])
            else:
                block_lines.append("- (none)")
            block_out.write_text("\n".join(block_lines).rstrip() + "\n")
        else:
            block_out.write_text("")

        fh.seek(0)
        fh.truncate()
        json.dump(data, fh, indent=2)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    finally:
        if fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

meta_out.write_text(json.dumps(meta, indent=2) + "\n")
PY
}

remaining_stories() {
  local meta_file="$1"
  python3 - "$meta_file" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text())
print(data.get("remaining", "unknown"))
PY
}

remaining_from_prd() {
  python3 - "$PRD_PATH" <<'PY'
import json
import sys
from pathlib import Path

prd_path = Path(sys.argv[1])
if not prd_path.exists():
    print("unknown")
    sys.exit(0)

try:
    data = json.loads(prd_path.read_text())
except Exception:
    print("unknown")
    sys.exit(0)

stories = data.get("stories") if isinstance(data, dict) else None
if not isinstance(stories, list):
    print("unknown")
    sys.exit(0)

def normalize_status(value):
    if value is None:
        return "open"
    return str(value).strip().lower()

remaining = sum(
    1 for story in stories
    if isinstance(story, dict) and normalize_status(story.get("status")) != "done"
)
print(remaining)
PY
}

story_field() {
  local meta_file="$1"
  local field="$2"
  python3 - "$meta_file" "$field" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text())
field = sys.argv[2]
print(data.get(field, ""))
PY
}

update_story_status() {
  local story_id="$1"
  local new_status="$2"
  python3 - "$PRD_PATH" "$story_id" "$new_status" <<'PY'
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
try:
    import fcntl
except Exception:
    fcntl = None

prd_path = Path(sys.argv[1])
story_id = sys.argv[2]
new_status = sys.argv[3]

if not story_id:
    sys.exit(0)

if not prd_path.exists():
    sys.exit(0)

def now_iso():
    return datetime.now(timezone.utc).isoformat()

with prd_path.open("r+", encoding="utf-8") as fh:
    if fcntl is not None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
    try:
        data = json.load(fh)
        stories = data.get("stories") if isinstance(data, dict) else None
        if not isinstance(stories, list):
            sys.exit(0)
        for story in stories:
            if isinstance(story, dict) and story.get("id") == story_id:
                story["status"] = new_status
                story["updatedAt"] = now_iso()
                if new_status == "in_progress":
                    if not story.get("startedAt"):
                        story["startedAt"] = now_iso()
                    story["completedAt"] = None
                elif new_status == "done":
                    story["completedAt"] = now_iso()
                    if not story.get("startedAt"):
                        story["startedAt"] = now_iso()
                elif new_status == "open":
                    story["startedAt"] = None
                    story["completedAt"] = None
                break
        fh.seek(0)
        fh.truncate()
        json.dump(data, fh, indent=2)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    finally:
        if fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
PY
}

log_activity() {
  local message="$1"
  local timestamp
  timestamp=$(date '+%Y-%m-%d %H:%M:%S')
  echo "[$timestamp] $message" >> "$ACTIVITY_LOG_PATH"
}

log_error() {
  local message="$1"
  local timestamp
  timestamp=$(date '+%Y-%m-%d %H:%M:%S')
  echo "[$timestamp] $message" >> "$ERRORS_LOG_PATH"
}

append_run_summary() {
  local line="$1"
  python3 - "$ACTIVITY_LOG_PATH" "$line" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
line = sys.argv[2]
text = path.read_text().splitlines()
out = []
inserted = False
for l in text:
    out.append(l)
    if not inserted and l.strip() == "## Run Summary":
        out.append(f"- {line}")
        inserted = True
if not inserted:
    out = [
        "# Activity Log",
        "",
        "## Run Summary",
        f"- {line}",
        "",
        "## Events",
        "",
    ] + text
Path(path).write_text("\n".join(out).rstrip() + "\n")
PY
}

write_run_meta() {
  local path="$1"
  local mode="$2"
  local iter="$3"
  local run_id="$4"
  local story_id="$5"
  local story_title="$6"
  local started="$7"
  local ended="$8"
  local duration="$9"
  local status="${10}"
  local log_file="${11}"
  local head_before="${12}"
  local head_after="${13}"
  local commit_list="${14}"
  local changed_files="${15}"
  local dirty_files="${16}"
  python3 - "$path" "$mode" "$iter" "$run_id" "$story_id" "$story_title" "$started" "$ended" "$duration" "$status" "$log_file" "$head_before" "$head_after" "$commit_list" "$changed_files" "$dirty_files" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
mode = sys.argv[2]
iteration = sys.argv[3]
run_id = sys.argv[4]
story_id = sys.argv[5]
story_title = sys.argv[6]
started = sys.argv[7]
ended = sys.argv[8]
duration = sys.argv[9]
status = sys.argv[10]
log_file = sys.argv[11]
head_before = sys.argv[12]
head_after = sys.argv[13]
commit_list_raw = sys.argv[14]
changed_files_raw = sys.argv[15]
dirty_files_raw = sys.argv[16]

def parse_lines(value):
    if not value:
        return []
    lines = []
    for line in value.splitlines():
        cleaned = line.strip()
        if cleaned.startswith("- "):
            cleaned = cleaned[2:]
        if cleaned:
            lines.append(cleaned)
    return lines

payload = {
    "runId": run_id,
    "iteration": iteration,
    "mode": mode,
    "story": {
        "id": story_id or None,
        "title": story_title or None,
    },
    "started": started,
    "ended": ended,
    "durationSeconds": int(duration) if str(duration).isdigit() else duration,
    "status": status,
    "log": log_file,
    "git": {
        "headBefore": head_before or None,
        "headAfter": head_after or None,
        "commits": parse_lines(commit_list_raw),
        "changedFiles": parse_lines(changed_files_raw),
        "dirtyFiles": parse_lines(dirty_files_raw),
    },
    "updatedAt": datetime.now(timezone.utc).isoformat(),
}

path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(payload, indent=2) + "\n")
PY
}

git_head() {
  if git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$ROOT_DIR" rev-parse HEAD 2>/dev/null || true
  else
    echo ""
  fi
}

git_commit_list() {
  local before="$1"
  local after="$2"
  if [ -n "$before" ] && [ -n "$after" ] && [ "$before" != "$after" ]; then
    git -C "$ROOT_DIR" log --oneline "$before..$after" | sed 's/^/- /'
  else
    echo ""
  fi
}

git_changed_files() {
  local before="$1"
  local after="$2"
  if [ -n "$before" ] && [ -n "$after" ] && [ "$before" != "$after" ]; then
    git -C "$ROOT_DIR" diff --name-only "$before" "$after" | sed 's/^/- /'
  else
    echo ""
  fi
}

git_dirty_files() {
  if git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$ROOT_DIR" status --porcelain | awk '{print "- " $2}'
  else
    echo ""
  fi
}

echo "Forge mode: $MODE"
echo "Max iterations: $MAX_ITERATIONS"
echo "PRD: $PRD_PATH"
HAS_ERROR="false"
PRD_JSON="$(json_escape "$PRD_PATH")"
forge_emit_event "loop_started" "{\"max_iterations\": $MAX_ITERATIONS, \"prd\": ${PRD_JSON}}"

for i in $(seq 1 "$MAX_ITERATIONS"); do
  echo ""
  echo "═══════════════════════════════════════════════════════"
  echo "  Forge Iteration $i of $MAX_ITERATIONS"
  echo "═══════════════════════════════════════════════════════"

  STORY_META=""
  STORY_BLOCK=""
  if [ -f "$FORGE_PAUSE_PATH" ]; then
    forge_emit_event "loop_paused" "{\"reason\": \"pause requested\"}"
    echo "Loop paused. Remove $FORGE_PAUSE_PATH or run braindrive-forge resume."
    exit 0
  fi
  ITERATION_ID="$(forge_next_iteration_id)"
  ITER_START=$(date +%s)
  ITER_START_FMT=$(date '+%Y-%m-%d %H:%M:%S')
  if [ "$MODE" = "build" ]; then
    STORY_META="$TMP_DIR/story-$RUN_TAG-$i.json"
    STORY_BLOCK="$TMP_DIR/story-$RUN_TAG-$i.md"
    select_story "$STORY_META" "$STORY_BLOCK"
    REMAINING="$(remaining_stories "$STORY_META")"
    if [ "$REMAINING" = "unknown" ]; then
      echo "Could not parse stories from PRD: $PRD_PATH"
      exit 1
    fi
    if [ "$REMAINING" = "0" ]; then
      echo "No remaining stories."
      exit 0
    fi
    STORY_ID="$(story_field "$STORY_META" "id")"
    STORY_TITLE="$(story_field "$STORY_META" "title")"
    if [ -z "$STORY_ID" ]; then
      echo "No actionable open stories (all blocked or in progress). Remaining: $REMAINING"
      exit 0
    fi
    forge_sync_stories
    TITLE_JSON="$(json_escape "$STORY_TITLE")"
    forge_emit_event "story_selected" "{\"title\": ${TITLE_JSON}, \"remaining\": ${REMAINING}}" "$STORY_ID" "$ITERATION_ID"
  fi

  HEAD_BEFORE="$(git_head)"
  PROMPT_RENDERED="$TMP_DIR/prompt-$RUN_TAG-$i.md"
  LOG_FILE="$FORGE_LOGS_DIR/${ITERATION_ID}.raw.txt"
  RUN_META="$FORGE_ITER_DIR/${ITERATION_ID}.json"
  render_prompt "$PROMPT_FILE" "$PROMPT_RENDERED" "$STORY_META" "$STORY_BLOCK" "$RUN_TAG" "$i" "$LOG_FILE" "$RUN_META"

  if [ "$MODE" = "build" ] && [ -n "${STORY_ID:-}" ]; then
    log_activity "ITERATION $i start (mode=$MODE story=$STORY_ID)"
  else
    log_activity "ITERATION $i start (mode=$MODE)"
  fi
  forge_emit_event "agent_started" "{\"prompt\": $(json_escape "$PROMPT_RENDERED")}" "${STORY_ID:-}" "$ITERATION_ID"
  set +e
  if [ "$DRY_RUN" = "1" ]; then
    echo "[FORGE_DRY_RUN] Skipping agent execution." | tee "$LOG_FILE"
    CMD_STATUS=0
  else
    run_agent "$PROMPT_RENDERED" 2>&1 | tee "$LOG_FILE"
    CMD_STATUS=$?
  fi
  set -e
  forge_emit_event "agent_output_saved" "{\"log\": $(json_escape "$LOG_FILE")}" "${STORY_ID:-}" "$ITERATION_ID"
  if [ "$CMD_STATUS" -eq 130 ] || [ "$CMD_STATUS" -eq 143 ]; then
    echo "Interrupted."
    exit "$CMD_STATUS"
  fi
  ITER_END=$(date +%s)
  ITER_END_FMT=$(date '+%Y-%m-%d %H:%M:%S')
  ITER_DURATION=$((ITER_END - ITER_START))
  HEAD_AFTER="$(git_head)"
  forge_emit_event "validation_started" "{}" "${STORY_ID:-}" "$ITERATION_ID"
  if [ "$CMD_STATUS" -ne 0 ]; then
    forge_emit_event "validation_failed" "{\"status\": $CMD_STATUS}" "${STORY_ID:-}" "$ITERATION_ID"
  else
    forge_emit_event "validation_passed" "{}" "${STORY_ID:-}" "$ITERATION_ID"
  fi
  log_activity "ITERATION $i end (duration=${ITER_DURATION}s)"
  if [ "$CMD_STATUS" -ne 0 ]; then
    log_error "ITERATION $i command failed (status=$CMD_STATUS)"
    HAS_ERROR="true"
  fi
  COMMIT_LIST="$(git_commit_list "$HEAD_BEFORE" "$HEAD_AFTER")"
  CHANGED_FILES="$(git_changed_files "$HEAD_BEFORE" "$HEAD_AFTER")"
  DIRTY_FILES="$(git_dirty_files)"
  if [ -n "$CHANGED_FILES" ]; then
    while IFS= read -r line; do
      [ -z "$line" ] && continue
      file="${line#- }"
      forge_emit_event "file_modified" "{\"path\": $(json_escape "$file"), \"source\": \"commit\"}" "${STORY_ID:-}" "$ITERATION_ID"
    done <<< "$CHANGED_FILES"
  fi
  if [ -n "$DIRTY_FILES" ]; then
    while IFS= read -r line; do
      [ -z "$line" ] && continue
      file="${line#- }"
      forge_emit_event "file_modified" "{\"path\": $(json_escape "$file"), \"source\": \"working_tree\"}" "${STORY_ID:-}" "$ITERATION_ID"
    done <<< "$DIRTY_FILES"
  fi
  STATUS_LABEL="success"
  if [ "$CMD_STATUS" -ne 0 ]; then
    STATUS_LABEL="error"
  fi
  if [ "$MODE" = "build" ] && [ "$NO_COMMIT" = "false" ] && [ -n "$DIRTY_FILES" ]; then
    log_error "ITERATION $i left uncommitted changes; review run summary at $RUN_META"
  fi
  write_run_meta "$RUN_META" "$MODE" "$i" "$RUN_TAG" "${STORY_ID:-}" "${STORY_TITLE:-}" "$ITER_START_FMT" "$ITER_END_FMT" "$ITER_DURATION" "$STATUS_LABEL" "$LOG_FILE" "$HEAD_BEFORE" "$HEAD_AFTER" "$COMMIT_LIST" "$CHANGED_FILES" "$DIRTY_FILES"
  if [ "$MODE" = "build" ] && [ -n "${STORY_ID:-}" ]; then
    append_run_summary "$(date '+%Y-%m-%d %H:%M:%S') | run=$RUN_TAG | iter=$i | iter_id=$ITERATION_ID | mode=$MODE | story=$STORY_ID | duration=${ITER_DURATION}s | status=$STATUS_LABEL"
  else
    append_run_summary "$(date '+%Y-%m-%d %H:%M:%S') | run=$RUN_TAG | iter=$i | iter_id=$ITERATION_ID | mode=$MODE | duration=${ITER_DURATION}s | status=$STATUS_LABEL"
  fi

  if [ "$MODE" = "build" ]; then
    if [ "$CMD_STATUS" -ne 0 ]; then
      log_error "ITERATION $i exited non-zero; review $LOG_FILE"
      update_story_status "$STORY_ID" "open"
      forge_sync_stories
      forge_emit_event "iteration_completed" "{\"status\": \"error\"}" "${STORY_ID:-}" "$ITERATION_ID"
      echo "Iteration failed; story reset to open."
    elif grep -q "<promise>COMPLETE</promise>" "$LOG_FILE"; then
      update_story_status "$STORY_ID" "done"
      forge_sync_stories
      forge_emit_event "story_completed" "{\"status\": \"done\"}" "${STORY_ID:-}" "$ITERATION_ID"
      forge_emit_event "iteration_completed" "{\"status\": \"success\"}" "${STORY_ID:-}" "$ITERATION_ID"
      echo "Completion signal received; story marked done."
    else
      update_story_status "$STORY_ID" "open"
      forge_sync_stories
      forge_emit_event "iteration_completed" "{\"status\": \"incomplete\"}" "${STORY_ID:-}" "$ITERATION_ID"
      echo "No completion signal; story reset to open."
    fi
    REMAINING="$(remaining_from_prd)"
    echo "Iteration $i complete. Remaining stories: $REMAINING"
    if [ "$REMAINING" = "0" ]; then
      echo "No remaining stories."
      exit 0
    fi
  else
    forge_emit_event "iteration_completed" "{\"status\": \"success\"}" "" "$ITERATION_ID"
    echo "Iteration $i complete."
  fi
  sleep 2

done

echo "Reached max iterations ($MAX_ITERATIONS)."
if [ "$HAS_ERROR" = "true" ]; then
  exit 1
fi
exit 0
