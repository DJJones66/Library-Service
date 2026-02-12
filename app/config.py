"""Configuration loading for the MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class AppConfig:
    library_path: Path
    require_user_header: bool
    service_token: str | None


def _read_dotenv_value(dotenv_path: Path, key: str) -> str | None:
    """Read a single key from a .env file without mutating the environment."""
    if not dotenv_path.is_file():
        return None
    try:
        content = dotenv_path.read_text(encoding="utf-8")
    except OSError:
        return None

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].strip()
        if "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        name = name.strip()
        if name != key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        return value or None
    return None


def _read_bool(raw_value: str | None, *, default: bool, key: str) -> bool:
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if not normalized:
        return default
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{key} must be a boolean value.")


def load_config() -> AppConfig:
    """Load required configuration from the environment."""
    dotenv_path = Path.cwd() / ".env"

    env_key = "BRAINDRIVE_LIBRARY_PATH"
    raw_path = os.environ.get(env_key, "").strip()
    if not raw_path:
        raw_path = _read_dotenv_value(dotenv_path, env_key) or ""
        raw_path = raw_path.strip()
    if not raw_path:
        raise ConfigError(
            "BRAINDRIVE_LIBRARY_PATH is required; set it to the library root path."
        )

    require_user_key = "BRAINDRIVE_LIBRARY_REQUIRE_USER_HEADER"
    require_user_raw = os.environ.get(require_user_key)
    if require_user_raw is None:
        require_user_raw = _read_dotenv_value(dotenv_path, require_user_key)
    require_user_header = _read_bool(
        require_user_raw, default=True, key=require_user_key
    )

    service_token_key = "BRAINDRIVE_LIBRARY_SERVICE_TOKEN"
    service_token = os.environ.get(service_token_key)
    if service_token is None:
        service_token = _read_dotenv_value(dotenv_path, service_token_key)
    service_token = service_token.strip() if isinstance(service_token, str) else None
    if not service_token:
        service_token = None

    return AppConfig(
        library_path=Path(raw_path),
        require_user_header=require_user_header,
        service_token=service_token,
    )
