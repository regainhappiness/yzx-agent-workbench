import json

from src.tools.mcp.config import McpConfig, McpServerConfig, load_mcp_config


def test_load_mcp_config_parses_servers(tmp_path):
    cfg_file = tmp_path / "mcp.json"
    cfg_file.write_text(json.dumps({
        "enabled": True,
        "servers": [
            {"name": "knowledge", "transport": "stdio",
             "command": "python", "args": ["-m", "kmcp"]},
            {"name": "web", "transport": "streamable-http",
             "url": "http://localhost:3000/mcp"},
        ],
    }), encoding="utf-8")
    cfg = load_mcp_config(str(cfg_file))
    assert cfg.enabled is True
    assert len(cfg.servers) == 2
    assert cfg.servers[0].name == "knowledge"
    assert cfg.servers[1].transport == "streamable-http"


def test_load_mcp_config_missing_file_defaults_disabled(tmp_path):
    cfg = load_mcp_config(str(tmp_path / "nope.json"))
    assert cfg.enabled is False
    assert cfg.servers == []


def test_server_config_defaults():
    s = McpServerConfig(name="x", transport="stdio", command="python")
    assert s.timeout_seconds == 30.0
    assert s.allowed_tools == ["*"]
    assert s.args == []
    assert s.env == {}
