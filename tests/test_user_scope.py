from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.errors import McpError
from app.main import create_app
from app.user_scope import (
    SERVICE_TOKEN_HEADER,
    USER_ID_HEADER,
    get_request_library_root,
    normalize_user_id,
    resolve_user_library_root,
)


def test_normalize_user_id_removes_dashes():
    assert normalize_user_id("abc-def-123") == "abcdef123"


def test_normalize_user_id_rejects_empty():
    with pytest.raises(McpError) as excinfo:
        normalize_user_id("   ")
    assert excinfo.value.error.code == "AUTH_REQUIRED"


def test_resolve_user_library_root_scopes_under_users(tmp_path):
    root = resolve_user_library_root(tmp_path, "test-user-123")
    assert root == tmp_path / "users" / "testuser123"


def test_get_request_library_root_uses_request_state_user_id(tmp_path):
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(config=SimpleNamespace(library_path=tmp_path))),
        state=SimpleNamespace(user_id="user-123"),
        headers={},
    )
    scoped_root = get_request_library_root(request)
    assert scoped_root == tmp_path / "users" / "user123"
    assert scoped_root.exists()


def test_middleware_allows_health_without_identity(monkeypatch, tmp_path):
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_PATH", str(tmp_path))
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_REQUIRE_USER_HEADER", "true")
    monkeypatch.delenv("BRAINDRIVE_LIBRARY_SERVICE_TOKEN", raising=False)

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200


def test_middleware_requires_user_header_for_tools(monkeypatch, tmp_path):
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_PATH", str(tmp_path))
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_REQUIRE_USER_HEADER", "true")
    monkeypatch.delenv("BRAINDRIVE_LIBRARY_SERVICE_TOKEN", raising=False)

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/tools")

    assert response.status_code == 401
    payload = response.json()
    assert payload["error"]["code"] == "AUTH_REQUIRED"


def test_middleware_requires_service_token_when_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_PATH", str(tmp_path))
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_REQUIRE_USER_HEADER", "true")
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_SERVICE_TOKEN", "expected-token")

    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            "/tools",
            headers={USER_ID_HEADER: "test-user-123"},
        )

    assert response.status_code == 403
    payload = response.json()
    assert payload["error"]["code"] == "AUTH_FORBIDDEN"


def test_middleware_allows_tools_with_identity_and_service_token(monkeypatch, tmp_path):
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_PATH", str(tmp_path))
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_REQUIRE_USER_HEADER", "true")
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_SERVICE_TOKEN", "expected-token")

    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            "/tools",
            headers={
                USER_ID_HEADER: "test-user-123",
                SERVICE_TOKEN_HEADER: "expected-token",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True


def test_multi_user_project_isolation(monkeypatch, tmp_path):
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_PATH", str(tmp_path))
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_REQUIRE_USER_HEADER", "true")
    monkeypatch.delenv("BRAINDRIVE_LIBRARY_SERVICE_TOKEN", raising=False)

    app = create_app()
    with TestClient(app) as client:
        create_response = client.post(
            "/tool:create_project",
            headers={USER_ID_HEADER: "user-a-123"},
            json={
                "path": "projects/active/alpha",
                "files": [{"path": "spec.md", "content": "# alpha\n"}],
            },
        )
        assert create_response.status_code == 200

        list_user_a = client.post(
            "/tool:list_projects",
            headers={USER_ID_HEADER: "user-a-123"},
            json={"path": "projects/active"},
        )
        assert list_user_a.status_code == 200
        names_user_a = [item["name"] for item in list_user_a.json()["data"]["projects"]]
        assert "alpha" in names_user_a

        list_user_b = client.post(
            "/tool:list_projects",
            headers={USER_ID_HEADER: "user-b-123"},
            json={"path": "projects/active"},
        )
        assert list_user_b.status_code == 400
        payload_user_b = list_user_b.json()
        assert payload_user_b["error"]["code"] == "FILE_NOT_FOUND"


def test_multi_user_file_isolation(monkeypatch, tmp_path):
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_PATH", str(tmp_path))
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_REQUIRE_USER_HEADER", "true")
    monkeypatch.delenv("BRAINDRIVE_LIBRARY_SERVICE_TOKEN", raising=False)

    app = create_app()
    with TestClient(app) as client:
        create_file = client.post(
            "/tool:create_markdown",
            headers={USER_ID_HEADER: "user-a-123"},
            json={"path": "docs/private.md", "content": "private\n"},
        )
        assert create_file.status_code == 200

        read_file_user_a = client.post(
            "/tool:read_markdown",
            headers={USER_ID_HEADER: "user-a-123"},
            json={"path": "docs/private.md"},
        )
        assert read_file_user_a.status_code == 200

        read_file_user_b = client.post(
            "/tool:read_markdown",
            headers={USER_ID_HEADER: "user-b-123"},
            json={"path": "docs/private.md"},
        )
        assert read_file_user_b.status_code == 400
        payload_user_b = read_file_user_b.json()
        assert payload_user_b["error"]["code"] == "FILE_NOT_FOUND"
