from pathlib import Path

import pytest

from app.config import ConfigError, load_config


def test_load_config_requires_env(monkeypatch, tmp_path):
    monkeypatch.delenv("BRAINDRIVE_LIBRARY_PATH", raising=False)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ConfigError) as excinfo:
        load_config()

    assert "BRAINDRIVE_LIBRARY_PATH" in str(excinfo.value)


def test_load_config_reads_env(monkeypatch, tmp_path):
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_PATH", str(tmp_path))

    config = load_config()

    assert config.library_path == tmp_path.resolve()
    assert config.require_user_header is True
    assert config.service_token is None


def test_load_config_reads_dotenv(monkeypatch, tmp_path):
    monkeypatch.delenv("BRAINDRIVE_LIBRARY_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    (tmp_path / ".env").write_text(
        f'BRAINDRIVE_LIBRARY_PATH="{library_root}"\n', encoding="utf-8"
    )

    config = load_config()

    assert config.library_path == library_root.resolve()
    assert config.require_user_header is True
    assert config.service_token is None


def test_load_config_reads_dotenv_relative_path(monkeypatch, tmp_path):
    monkeypatch.delenv("BRAINDRIVE_LIBRARY_PATH", raising=False)
    service_root = tmp_path / "service"
    service_root.mkdir()
    (service_root / ".env").write_text(
        'BRAINDRIVE_LIBRARY_PATH="./library"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(service_root)

    config = load_config()

    assert config.library_path == (service_root / "library").resolve()


def test_load_config_prefers_env_over_dotenv(monkeypatch, tmp_path):
    env_root = tmp_path / "env"
    env_root.mkdir()
    dotenv_root = tmp_path / "dotenv"
    dotenv_root.mkdir()
    (tmp_path / ".env").write_text(
        f"BRAINDRIVE_LIBRARY_PATH={dotenv_root}\n", encoding="utf-8"
    )
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_PATH", str(env_root))
    monkeypatch.chdir(tmp_path)

    config = load_config()

    assert config.library_path == env_root.resolve()


def test_load_config_reads_auth_flags(monkeypatch, tmp_path):
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_PATH", str(tmp_path))
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_REQUIRE_USER_HEADER", "false")
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_SERVICE_TOKEN", "test-token")

    config = load_config()

    assert config.require_user_header is False
    assert config.service_token == "test-token"


def test_load_config_rejects_invalid_bool(monkeypatch, tmp_path):
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_PATH", str(tmp_path))
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_REQUIRE_USER_HEADER", "not-a-bool")

    with pytest.raises(ConfigError) as excinfo:
        load_config()

    assert "BRAINDRIVE_LIBRARY_REQUIRE_USER_HEADER" in str(excinfo.value)
