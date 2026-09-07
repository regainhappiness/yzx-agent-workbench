"""MCP 配置模型与加载。"""
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class McpServerConfig(BaseModel):
    """单个外部 MCP Server 的连接配置。"""
    name: str
    transport: Literal["stdio", "streamable-http"]
    enabled: bool = True
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = 30.0
    allowed_tools: list[str] = Field(default_factory=lambda: ["*"])
    subagents: list[str] = Field(default_factory=lambda: ["*"])


class McpConfig(BaseModel):
    """MCP 适配器总配置。"""
    enabled: bool = False
    servers: list[McpServerConfig] = Field(default_factory=list)


def load_mcp_config(path: str | None = None) -> McpConfig:
    """从 JSON 文件加载配置；文件不存在或不可解析时返回禁用配置。"""
    path = path or "./mcp.json"
    p = Path(path)
    if not p.is_file():
        return McpConfig()
    try:
        return McpConfig.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception:
        return McpConfig()
