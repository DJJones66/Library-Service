import pytest

from tools.mcp_tools import ToolSchemaError, load_tool_definitions


def test_load_tool_definitions_rejects_missing_file(tmp_path):
    missing = tmp_path / "missing.json"
    with pytest.raises(ToolSchemaError):
        load_tool_definitions(missing)


def test_load_tool_definitions_rejects_invalid_json(tmp_path):
    path = tmp_path / "tools.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ToolSchemaError):
        load_tool_definitions(path)


def test_load_tool_definitions_rejects_non_list(tmp_path):
    path = tmp_path / "tools.json"
    path.write_text("{\"type\":\"function\"}", encoding="utf-8")
    with pytest.raises(ToolSchemaError):
        load_tool_definitions(path)


def test_load_tool_definitions_validates_schema(tmp_path):
    path = tmp_path / "tools.json"
    path.write_text(
        '[{"type":"function","function":{"name":"ping","parameters":{}}}]',
        encoding="utf-8",
    )
    tools = load_tool_definitions(path)
    assert isinstance(tools, list)
    assert tools[0]["function"]["name"] == "ping"
