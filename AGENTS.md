# AGENTS

## Setup

```bash
pip install fastapi uvicorn pytest ruff dulwich httpx
```

## Environment

```bash
cat <<'EOF' > .env
BRAINDRIVE_LIBRARY_PATH="/path/to/library"
EOF
```

## Run

```bash
uvicorn app.main:app --reload
```

## Verification

```bash
python -m pytest
python -m ruff check .
```
