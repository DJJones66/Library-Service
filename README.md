# Library Service

FastAPI-based scaffold for the BrainDrive Markdown MCP server.

## Setup

Install dependencies (includes dulwich for git-backed mutation commits):

```bash
pip install fastapi uvicorn pytest ruff dulwich httpx
```

## Configuration

Set the library root and strict request identity controls:

```bash
cat <<'EOF' > .env
BRAINDRIVE_LIBRARY_PATH="./library"
BRAINDRIVE_LIBRARY_BASE_TEMPLATE_PATH="./library_templates/Base_Library"
BRAINDRIVE_LIBRARY_REQUIRE_USER_HEADER="true"
BRAINDRIVE_LIBRARY_SERVICE_TOKEN="dev-library-token"
EOF
```

`BRAINDRIVE_LIBRARY_PATH` and `BRAINDRIVE_LIBRARY_BASE_TEMPLATE_PATH` can still be provided via the environment; those values take precedence over `.env`.
Starting without `BRAINDRIVE_LIBRARY_PATH` raises a clear config error and prevents startup.
`BRAINDRIVE_LIBRARY_REQUIRE_USER_HEADER` defaults to `true`.
If `BRAINDRIVE_LIBRARY_SERVICE_TOKEN` is set, callers must include `X-BrainDrive-Service-Token`.

## Bootstrap user-scoped directories

Create development directories for one or more users before testing tool calls:

```bash
python backend/scripts/bootstrap_library_user_scope.py \
  --library-root "/path/to/library" \
  --user-id "dev-user-123" \
  --user-id "dev-user-456"
```

This creates:
- `users/<user_id>/projects/active`
- `users/<user_id>/transcripts`
- `users/<user_id>/pulse`
- `users/<user_id>/docs`
- `users/<user_id>/activity.log`

## Run locally

Use the standard dev command (reload is intentional for fast iteration):

```bash
uvicorn app.main:app --reload
```

## Health check

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status": "ok"}
```

## Tool call example (strict mode)

```bash
curl -X POST "http://127.0.0.1:8000/tool:list_projects" \
  -H "Content-Type: application/json" \
  -H "X-BrainDrive-User-Id: dev-user-123" \
  -H "X-BrainDrive-Service-Token: dev-library-token" \
  -d '{"path":"projects/active"}'
```

## Verification

These checks confirm config loading and the health endpoint behavior:

```bash
python -m pytest
python -m ruff check .
```
