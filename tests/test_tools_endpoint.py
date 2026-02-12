from fastapi.testclient import TestClient

from app.main import create_app


def test_tools_endpoint_returns_tool_definitions(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_PATH", str(tmp_path))

    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            "/tools", headers={"X-BrainDrive-User-Id": "test-user-123"}
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    tools = payload["data"]["tools"]
    assert isinstance(tools, list)
    names = {
        tool.get("function", {}).get("name") for tool in tools if tool
    }
    assert "read_markdown" in names
    assert "create_project" in names
