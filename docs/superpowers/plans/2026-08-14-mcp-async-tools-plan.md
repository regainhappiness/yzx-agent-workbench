# MCP 工具接入与多智能体异步化 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 通过配置连接外部 MCP Server、动态发现并转换为内部工具，并把多智能体执行链路（MainAgent/SubAgent/MultiAgentService + SQLite 持久化）整体异步化，使 MCP 工具（async-only）能在图里正确执行。

**Architecture:** 三个独立阶段。阶段一新增 `src/tools/mcp/` 适配器（纯新代码，用 fake MCP server 测试，不碰现有系统）；阶段二把多智能体图从同步 `.invoke` 改为异步 `.ainvoke`/`.astream`，SQLite 持久化切 `AsyncSqliteSaver`/`AsyncSqliteStore`，取消信号 `threading.Event` → `asyncio.Event`；阶段三把 MCP 工具注入 SubAgent 的 `ToolRegistry` 并在 lifespan 接线。

**Tech Stack:** LangGraph / LangChain（`ainvoke`/`astream`/`ToolNode`）、`mcp` Python SDK **v2**（2026-07-28 spec）、httpx、Pydantic v2、aiosqlite、pytest + pytest-asyncio。

**关联 spec:** [2026-08-14-mcp-async-tools-design.md](../specs/2026-08-14-mcp-async-tools-design.md)

---

## 文件结构（锁定）

### 阶段一新增

| 文件 | 职责 |
|------|------|
| `src/tools/mcp/config.py` | `McpConfig`/`McpServerConfig`（Pydantic）+ `load_mcp_config` |
| `src/tools/mcp/transport.py` | `McpTransport` 协议 + `StdioTransport`/`StreamableHttpTransport`（v2 `streamable_http_client` + httpx）+ `build_transport` |
| `src/tools/mcp/convert.py` | `json_schema_to_pydantic` + `to_langchain_tool`（MCP Tool → `StructuredTool`） |
| `src/tools/mcp/adapter.py` | `McpConnection`（连接/发现/调用/熔断）+ `McpAdapter`（编排多 server） |
| `src/tools/mcp/__init__.py` | 导出 |
| `tests/test_mcp_config.py` | 配置加载单测 |
| `tests/test_mcp_convert.py` | `json_schema_to_pydantic` + `to_langchain_tool` 单测 |
| `tests/test_mcp_adapter.py` | `McpAdapter.discover` / `McpConnection` 熔断测试（fake session） |

### 阶段二修改

| 文件 | 职责 |
|------|------|
| `src/agents/base.py` | 增加 `ainitialize`/`aclose` 默认实现 |
| `src/agents/multi_agent/sub_agent.py` | 节点 async 化、`arun`/`arun_stream` 原生 async、`asyncio.Event` 取消、`mcp_tools` 注入、异步 store |
| `src/agents/multi_agent/main_agent.py` | 同上 + `execute_node` `await sub.arun` |
| `src/server/services/multi_agent_service.py` | 全链路 async、`asyncio.Event`、`await agent.ainitialize/arun_stream` |
| `tests/test_multi_agent_sqlite.py` | `run()`→`await arun()`，fake model 补 `ainvoke`，取消事件改 `asyncio.Event` |

### 阶段三修改

| 文件 | 职责 |
|------|------|
| `src/agents/multi_agent/__init__.py` | `create_default_registry` 透传 mcp_tools |
| `src/server/main.py` | lifespan 里 `load_mcp_config` + `mcp_adapter.discover()` + 关闭 |
| `requirements.txt` | 新增 `mcp>=2.0` |

---

# 阶段一：MCP 适配器（独立、零风险）

> 本阶段产物可独立测试，不依赖阶段二。命名决策已锁定：`StructuredTool.name` 用 `{server}_{tool}`（下划线，满足 `^[a-zA-Z0-9_-]{1,64}$`），`server/tool` 形式放入 `ToolMeta.tags`。

## Task 1: 配置模型与加载

**Files:**
- Create: `src/tools/mcp/config.py`
- Create: `src/tools/mcp/__init__.py`（先建空导出，后续补齐）
- Test: `tests/test_mcp_config.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_mcp_config.py
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
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/test_mcp_config.py -v`
Expected: 全部 FAIL（`ModuleNotFoundError: src.tools.mcp`）

- [ ] **Step 3: 实现配置模型与加载**

```python
# src/tools/mcp/config.py
"""MCP 配置模型与加载。"""
from typing import Literal
from pathlib import Path
from pydantic import BaseModel, Field


class McpServerConfig(BaseModel):
    name: str
    transport: Literal["stdio", "streamable-http"]
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = 30.0
    allowed_tools: list[str] = Field(default_factory=lambda: ["*"])


class McpConfig(BaseModel):
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
```

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/test_mcp_config.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/tools/mcp/config.py src/tools/mcp/__init__.py tests/test_mcp_config.py
git commit -m "feat(mcp): add MCP config models and loader"
```

---

## Task 2: JSON Schema → Pydantic 转换（纯函数，核心）

**Files:**
- Create: `src/tools/mcp/convert.py`
- Test: `tests/test_mcp_convert.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_mcp_convert.py
from typing import get_origin
from pydantic import BaseModel
from src.tools.mcp.convert import json_schema_to_pydantic


def test_scalar_and_required_optional():
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索词"},
            "limit": {"type": "integer", "description": "条数"},
        },
        "required": ["query"],
    }
    M = json_schema_to_pydantic(schema, "Search")
    assert issubclass(M, BaseModel)
    # required 字段无默认值
    assert "query" in M.model_fields
    assert M.model_fields["query"].is_required()
    # optional 字段默认 None
    assert not M.model_fields["limit"].is_required()


def test_nested_object_and_array():
    schema = {
        "type": "object",
        "properties": {
            "filter": {
                "type": "object",
                "properties": {"min": {"type": "number"}},
                "required": ["min"],
            },
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["filter", "tags"],
    }
    M = json_schema_to_pydantic(schema, "Complex")
    assert M.model_fields["filter"].annotation.__name__ == "Complex_filter"
    assert get_origin(M.model_fields["tags"].annotation) is list


def test_enum_and_unknown_fallback():
    schema = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["a", "b"]},
            "opaque": {"$ref": "#/defs/X"},
        },
        "required": ["kind", "opaque"],
    }
    M = json_schema_to_pydantic(schema, "EnumCase")
    assert M.model_fields["kind"].annotation.__name__ == "Literal"
    # $ref 未实现 → Any 兜底（不抛异常）
    assert M.model_fields["opaque"].annotation is not None
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/test_mcp_convert.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现转换函数**

```python
# src/tools/mcp/convert.py
"""MCP Tool → LangChain BaseTool 转换。"""
from typing import Any, Literal
from pydantic import BaseModel, Field, create_model
from langchain_core.tools import BaseTool, StructuredTool

_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def json_schema_to_pydantic(schema: dict, name: str) -> type[BaseModel]:
    """把 JSON Schema 映射为 Pydantic 模型（供 bind_tools 生成参数 schema）。

    不支持的构造（$ref / anyOf / 未知 type）降级为 Any，保证不抛异常。
    """
    props = schema.get("properties", {})
    required = set(schema.get("required") or [])
    fields: dict[str, tuple] = {}
    for key, prop in props.items():
        t = prop.get("type")
        if t == "object" and "properties" in prop:
            py = json_schema_to_pydantic(prop, f"{name}_{key}")
        elif t == "array" and isinstance(prop.get("items"), dict) \
                and prop["items"].get("type") == "object":
            item = json_schema_to_pydantic(prop["items"], f"{name}_{key}Item")
            py = list[item]
        elif "enum" in prop:
            enum_vals = tuple(prop["enum"])
            if enum_vals and all(isinstance(v, str) for v in enum_vals):
                py = Literal[enum_vals]
            else:
                py = str
        else:
            py = _TYPE_MAP.get(t, Any)
        desc = prop.get("description")
        if key in required:
            fields[key] = (py, Field(description=desc))
        else:
            fields[key] = (py | None, Field(default=None, description=desc))
    return create_model(name, **fields)
```

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/test_mcp_convert.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/tools/mcp/convert.py tests/test_mcp_convert.py
git commit -m "feat(mcp): add JSON Schema to Pydantic converter"
```

---

## Task 3: 传输层协议与三种实现

**Files:**
- Create: `src/tools/mcp/transport.py`
- Test: `tests/test_mcp_adapter.py`（先建，本 task 只测 build_transport）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_mcp_adapter.py
import pytest
from src.tools.mcp.config import McpServerConfig
from src.tools.mcp.transport import build_transport, StdioTransport, StreamableHttpTransport


def test_build_transport_dispatch():
    assert isinstance(build_transport(McpServerConfig(name="x", transport="stdio", command="python")), StdioTransport)
    assert isinstance(build_transport(McpServerConfig(name="x", transport="streamable-http", url="http://x")), StreamableHttpTransport)


def test_http_transport_requires_url():
    with pytest.raises(ValueError):
        build_transport(McpServerConfig(name="x", transport="streamable-http"))
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/test_mcp_adapter.py::test_build_transport_dispatch -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现传输层**

```python
# src/tools/mcp/transport.py
"""MCP 传输层：协议 + 两种传输实现（MCP 2.0 / SDK v2）。"""
from contextlib import asynccontextmanager
from typing import Protocol

import httpx2
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from .config import McpServerConfig


class McpTransport(Protocol):
    def open(self):
        """异步上下文管理器，yield (read_stream, write_stream)。"""
        ...


class StdioTransport:
    def __init__(self, cfg: McpServerConfig):
        if not cfg.command:
            raise ValueError("stdio 传输需要 command")
        self._params = StdioServerParameters(
            command=cfg.command, args=cfg.args, env=cfg.env or None)

    @asynccontextmanager
    async def open(self):
        async with stdio_client(self._params) as (read, write):
            yield read, write


class StreamableHttpTransport:
    """v2：`streamable_http_client`（正确拼写）需自建 httpx2.AsyncClient，返回 2 元组。"""
    def __init__(self, cfg: McpServerConfig):
        if not cfg.url:
            raise ValueError("streamable-http 传输需要 url")
        self._url = cfg.url
        self._headers = cfg.headers or None
        self._timeout = httpx2.Timeout(cfg.timeout_seconds)

    @asynccontextmanager
    async def open(self):
        async with httpx2.AsyncClient(headers=self._headers, timeout=self._timeout) as client:
            async with streamable_http_client(self._url, http_client=client) as (read, write):
                yield read, write


def build_transport(cfg: McpServerConfig) -> McpTransport:
    if cfg.transport == "stdio":
        return StdioTransport(cfg)
    if cfg.transport == "streamable-http":
        return StreamableHttpTransport(cfg)
    raise ValueError(f"未知 MCP 传输类型: {cfg.transport}")
```

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/test_mcp_adapter.py::test_build_transport_dispatch tests/test_mcp_adapter.py::test_http_transport_requires_url -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/tools/mcp/transport.py tests/test_mcp_adapter.py
git commit -m "feat(mcp): add transport protocol and stdio/http/sse impls"
```

---

## Task 4: 连接管理 + 工具发现 + 熔断

**Files:**
- Create: `src/tools/mcp/adapter.py`
- Test: `tests/test_mcp_adapter.py`（追加）

- [ ] **Step 1: 写失败测试（用 fake session 测熔断与调用）**

```python
# tests/test_mcp_adapter.py 追加
import asyncio
from types import SimpleNamespace
from src.tools.mcp.adapter import McpConnection, _extract_text
from src.tools.mcp.config import McpServerConfig


class _FakeSession:
    def __init__(self, fail_times=0):
        self.fail_times = fail_times
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("boom")
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="ok")])


def test_extract_text():
    result = SimpleNamespace(content=[
        SimpleNamespace(type="text", text="hello"),
        SimpleNamespace(type="image", text=None),
        SimpleNamespace(type="text", text="world"),
    ])
    assert _extract_text(result) == "hello\nworld"


@pytest.mark.asyncio
async def test_call_succeeds():
    conn = McpConnection(McpServerConfig(name="k", transport="stdio", command="python"))
    conn._session = _FakeSession()
    conn.available = True
    assert await conn.call("search", {"q": "x"}) == "ok"


@pytest.mark.asyncio
async def test_call_circuit_breaker_opens_after_3_failures():
    conn = McpConnection(McpServerConfig(name="k", transport="stdio", command="python"))
    conn._session = _FakeSession(fail_times=99)
    conn.available = True
    for _ in range(3):
        await conn.call("search", {"q": "x"})
    assert conn.available is False
    # 熔断后调用直接返回错误文本，不再抛异常
    assert "不可用" in await conn.call("search", {"q": "x"})


@pytest.mark.asyncio
async def test_call_returns_error_text_when_unavailable():
    conn = McpConnection(McpServerConfig(name="k", transport="stdio", command="python"))
    conn.available = False
    assert "不可用" in await conn.call("search", {})
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/test_mcp_adapter.py -v`
Expected: 新用例 FAIL（`ModuleNotFoundError: adapter`）

- [ ] **Step 3: 实现连接管理与熔断**

```python
# src/tools/mcp/adapter.py
"""MCP 连接管理、工具发现与熔断。"""
import asyncio
import logging
from contextlib import AsyncExitStack

from mcp import ClientSession
from mcp.types import Tool
from langchain_core.tools import BaseTool

from .config import McpConfig, McpServerConfig
from .transport import build_transport
from .convert import to_langchain_tool

logger = logging.getLogger(__name__)


def _extract_text(result) -> str:
    parts = []
    for block in getattr(result, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", ""))
    return "\n".join(parts)


class McpConnection:
    def __init__(self, cfg: McpServerConfig):
        self.cfg = cfg
        self._transport = build_transport(cfg)
        self._session: ClientSession | None = None
        self._stack: AsyncExitStack | None = None
        self.available = False
        self._failures = 0

    async def connect(self):
        self._stack = AsyncExitStack()
        read, write = await self._stack.enter_async_context(self._transport.open())
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        # v2: initialize() 用于自动向下协商；纯无状态服务器可改用 discover()/adopt()
        await self._session.initialize()
        self.available = True

    async def list_tools(self) -> list[Tool]:
        result = await self._session.list_tools()
        return list(result.tools)

    async def call(self, tool_name: str, arguments: dict) -> str:
        if not self.available:
            return f"[MCP] 服务器 {self.cfg.name} 当前不可用"
        try:
            async with asyncio.timeout(self.cfg.timeout_seconds):
                result = await self._session.call_tool(tool_name, arguments)
            self._failures = 0
            return _extract_text(result)
        except Exception as e:
            self._failures += 1
            if self._failures >= 3:
                self.available = False
            return f"[MCP] 工具调用失败: {e}"

    async def close(self):
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
            self._session = None
            self.available = False


def _allowed(allowed: list[str], name: str) -> bool:
    return "*" in allowed or name in allowed


class McpAdapter:
    def __init__(self, config: McpConfig):
        self.config = config
        self._connections: list[McpConnection] = []

    async def discover(self) -> tuple[list[BaseTool], dict[str, dict]]:
        if not self.config.enabled:
            return [], {}
        tools: list[BaseTool] = []
        metas: dict[str, dict] = {}
        for server_cfg in self.config.servers:
            conn = McpConnection(server_cfg)
            try:
                await conn.connect()
            except Exception as e:
                logger.warning("MCP '%s' 连接失败，已跳过: %s", server_cfg.name, e)
                continue
            self._connections.append(conn)
            try:
                for t in await conn.list_tools():
                    if not _allowed(server_cfg.allowed_tools, t.name):
                        continue
                    tool = to_langchain_tool(conn, t)
                    tools.append(tool)
                    metas[tool.name] = {"category": "mcp",
                                        "tags": ["mcp", server_cfg.name],
                                        "version": "1.0.0"}
            except Exception as e:
                logger.warning("MCP '%s' 工具发现失败: %s", server_cfg.name, e)
        return tools, metas

    async def close(self):
        for conn in self._connections:
            await conn.close()
        self._connections = []
```

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/test_mcp_adapter.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/tools/mcp/adapter.py tests/test_mcp_adapter.py
git commit -m "feat(mcp): add connection management, discovery, and circuit breaker"
```

---

## Task 5: `to_langchain_tool` 转换 + 适配器编排测试

**Files:**
- Modify: `src/tools/mcp/convert.py`（补 `to_langchain_tool`）
- Modify: `src/tools/mcp/__init__.py`
- Test: `tests/test_mcp_convert.py`（追加）、`tests/test_mcp_adapter.py`（追加 discover 编排测试）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_mcp_convert.py 追加
import asyncio
from types import SimpleNamespace
from mcp.types import Tool
from src.tools.mcp.convert import to_langchain_tool


class _FakeConn:
    cfg = SimpleNamespace(name="knowledge")
    def __init__(self): self.calls = []
    async def call(self, name, args): self.calls.append((name, args)); return "hit"


def test_to_langchain_tool_namespace_and_invoke():
    mcp_tool = Tool(name="search", description="搜索知识库",
                    input_schema={"type": "object",
                                 "properties": {"q": {"type": "string"}},
                                 "required": ["q"]})
    lt = to_langchain_tool(_FakeConn(), mcp_tool)
    assert lt.name == "knowledge_search"          # 下划线命名空间，满足模型名约束
    result = asyncio.run(lt.ainvoke({"q": "x"}))
    assert result == "hit"
```

```python
# tests/test_mcp_adapter.py 追加
import pytest
from mcp.types import Tool
from src.tools.mcp.adapter import McpAdapter
from src.tools.mcp.config import McpConfig, McpServerConfig


class _FakeMcpConnection:
    def __init__(self, cfg):
        self.cfg = cfg
        self.available = True
    async def connect(self): pass
    async def list_tools(self):
        return [Tool(name="search", description="s", input_schema={"type": "object", "properties": {}}),
                Tool(name="delete", description="d", input_schema={"type": "object", "properties": {}})]
    async def call(self, name, args): return "x"
    async def close(self): pass


@pytest.mark.asyncio
async def test_discover_namespaces_and_whitelist(monkeypatch):
    monkeypatch.setattr("src.tools.mcp.adapter.McpConnection", _FakeMcpConnection)
    cfg = McpConfig(enabled=True, servers=[
        McpServerConfig(name="knowledge", transport="stdio", command="python", allowed_tools=["search"]),
    ])
    tools, metas = await McpAdapter(cfg).discover()
    assert [t.name for t in tools] == ["knowledge_search"]   # 白名单过滤掉 delete
    assert metas["knowledge_search"]["category"] == "mcp"
    assert metas["knowledge_search"]["tags"] == ["mcp", "knowledge"]


@pytest.mark.asyncio
async def test_discover_disabled_returns_empty():
    tools, metas = await McpAdapter(McpConfig(enabled=False)).discover()
    assert tools == [] and metas == []
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/test_mcp_convert.py tests/test_mcp_adapter.py -v`
Expected: `to_langchain_tool` 未定义 → FAIL

- [ ] **Step 3: 实现 `to_langchain_tool` + 导出**

在 `src/tools/mcp/convert.py` 末尾追加：

```python
def to_langchain_tool(conn, mcp_tool) -> BaseTool:
    """把 MCP Tool 转成 async-only 的 LangChain StructuredTool。

    工具名用 `{server}_{tool}`（下划线）：OpenAI/DeepSeek 函数名不允许 `/`。
    """
    full_name = f"{conn.cfg.name}_{mcp_tool.name}"
    model_name = "".join(c if c.isalnum() else "_" for c in full_name)
    args_model = json_schema_to_pydantic(mcp_tool.input_schema or {}, model_name)

    async def _arun(**kwargs) -> str:
        return await conn.call(mcp_tool.name, kwargs)

    return StructuredTool(
        name=full_name,
        description=mcp_tool.description or "",
        args_schema=args_model,
        coroutine=_arun,
    )
```

`src/tools/mcp/__init__.py`：

```python
"""工具层 — MCP 适配器。"""
from .config import McpConfig, McpServerConfig, load_mcp_config
from .adapter import McpAdapter, McpConnection

__all__ = ["McpConfig", "McpServerConfig", "load_mcp_config", "McpAdapter", "McpConnection"]
```

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/test_mcp_convert.py tests/test_mcp_adapter.py tests/test_mcp_config.py -v`
Expected: 全 PASS

- [ ] **Step 5: 提交**

```bash
git add src/tools/mcp/ tests/test_mcp_convert.py tests/test_mcp_adapter.py
git commit -m "feat(mcp): complete MCP adapter with tool conversion"
```

> **阶段一自检**：`pytest tests/test_mcp_config.py tests/test_mcp_convert.py tests/test_mcp_adapter.py -v` 全绿；`src/tools/mcp/` 未引用任何 agent 代码。阶段一可独立交付。

---

# 阶段二：多智能体异步化（高风险，先迁移测试）

> TDD 顺序：先迁移测试到异步（此时会失败），再改 `BaseAgent`/`SubAgent`/`MainAgent`/`MultiAgentService`，最后 SQLite 异步持久化。`store_type="memory"` 默认（`MemorySaver`/`InMemoryStore`）天然支持异步，先跑通，SQLite 单独一 task。

## Task 6: BaseAgent 增加 `ainitialize` / `aclose`

**Files:**
- Modify: `src/agents/base.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_multi_agent_sqlite.py 追加
import pytest


class _AsyncInitAgent(BaseAgent):
    def _setup(self, **kwargs):
        self.setup_called = True

    async def ainitialize(self):
        await super().ainitialize()


@pytest.mark.asyncio
async def test_base_agent_ainitialize_delegates_to_setup():
    a = _AsyncInitAgent(name="t")
    await a.ainitialize()
    assert a.setup_called is True
    assert a.is_initialized
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/test_multi_agent_sqlite.py::test_base_agent_ainitialize_delegates_to_setup -v`
Expected: FAIL（`AttributeError: 'BaseAgent' object has no attribute 'ainitialize'`）

- [ ] **Step 3: 实现**

在 [src/agents/base.py](../../src/agents/base.py) 的 `initialize()` 之后追加：

```python
    async def ainitialize(self):
        """异步初始化（默认等价于同步 initialize；子类可为异步 store 覆盖）。"""
        if self._initialized:
            return
        self.initialize()

    async def aclose(self):
        """异步关闭（默认等价于同步 close，若子类实现了 close）。"""
        close = getattr(self, "close", None)
        if callable(close):
            close()
```

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/test_multi_agent_sqlite.py::test_base_agent_ainitialize_delegates_to_setup -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/agents/base.py tests/test_multi_agent_sqlite.py
git commit -m "feat(agents): add ainitialize/aclose to BaseAgent"
```

---

## Task 7: SubAgent 异步化

**Files:**
- Modify: `src/agents/multi_agent/sub_agent.py`
- Test: `tests/test_multi_agent_sqlite.py`（迁移）

**要点（把同步图换成异步图）：**
1. 6 个节点 `def` → `async def`，内部 `.invoke` → `await *.ainvoke`，`ToolNode.invoke` → `await ToolNode.ainvoke`，`self._raise_if_cancelled(config)` → `await self._check_cancelled(config)`。
2. `_cancellation_events` 类型 `threading.Event` → `asyncio.Event`，`_raise_if_cancelled` 改 `async def _check_cancelled`。
3. 删除 `run`/`run_stream` 同步方法；`arun`/`arun_stream` 改为原生 async（`ainvoke`/`astream`，去 `asyncio.to_thread`）。
4. 新增 `mcp_tools`/`mcp_tools_meta` 构造参数，`_setup` 里注册。
5. store 创建从 `_setup` 抽到 `ainitialize`（memory 同步 / sqlite 异步）。

- [ ] **Step 1: 迁移测试到异步（先让它失败）**

把 `tests/test_multi_agent_sqlite.py` 里的三个同步图测试改为异步，并给 fake model 补 `ainvoke`：

```python
class _StructuredModel:
    def __init__(self, schema): self.schema = schema
    async def ainvoke(self, _messages):
        if self.schema.__name__ == "DecompositionOutput":
            return SimpleNamespace(
                strategy="two steps",
                sub_plan=[
                    SimpleNamespace(step_id=1, description="first", tool_hint=None),
                    SimpleNamespace(step_id=2, description="second", tool_hint=None),
                ],
            )
        return SimpleNamespace(needs_revision=False, completeness="complete",
                               accuracy="accurate", feedback="ok", ready_for_main_agent=True)


class _SubAgentModel:
    def __init__(self): self.agent_calls = 0
    def bind_tools(self, _tools): return self
    def with_structured_output(self, schema): return _StructuredModel(schema)
    async def ainvoke(self, _messages):
        self.agent_calls += 1
        return AIMessage(content=f"result-{self.agent_calls}")


@pytest.mark.asyncio
async def test_subagent_persists_each_planned_step_before_evaluation():
    agent = SubAgent()
    agent.model = _SubAgentModel()
    agent.tool_registry = ToolRegistry()
    agent._checkpointer = MemorySaver()
    agent._store = InMemoryStore()
    agent._initialized = True
    agent._build_graph()

    result = await agent.arun("do two things", thread_id="two-steps")

    assert "result-1" in result
    assert "result-2" in result
    assert agent.model.agent_calls == 2
```

并把 [test_multi_agent_sqlite.py](../../tests/test_multi_agent_sqlite.py) 里 `_MainAgentModel`/`_MainAgentStructuredModel`/`_FlakySubAgent`/`_FailingSubAgent` 一并补 `ainvoke`/`async def arun`（见 Task 8 的完整 fake 定义）。

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/test_multi_agent_sqlite.py::test_subagent_persists_each_planned_step_before_evaluation -v`
Expected: FAIL（`AttributeError: 'SubAgent' object has no attribute 'arun'`）

- [ ] **Step 3: 实现 SubAgent 异步化**

按顺序改 [sub_agent.py](../../src/agents/multi_agent/sub_agent.py)：

**(a) 顶部 import 增补：**

```python
import asyncio
# 移除 threading（不再用跨线程 Event）；保留 sqlite3 仅当 sqlite store 用不到时也保留
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver   # 延迟 import 放在 try 内
from langgraph.store.sqlite.aio import AsyncSqliteStore        # 以已安装版本路径为准
```

**(b) `__init__` 增补 mcp_tools 参数：**

```python
def __init__(self, ..., mcp_tools: list | None = None,
             mcp_tools_meta: dict[str, dict] | None = None, **kwargs):
    ...
    self._mcp_tools = mcp_tools or []
    self._mcp_tools_meta = mcp_tools_meta or {}
    self._cancellation_events: dict[str, asyncio.Event] = {}
```

**(c) `_setup` 里注册 mcp_tools（放在 L4 之后）：**

```python
        if self._mcp_tools:
            self.tool_registry.register_with_meta(self._mcp_tools, self._mcp_tools_meta)
```

并把 store 创建逻辑从 `_setup` 抽走：`_setup` 只保留 model + tool_registry + `_build_graph()`。

**(d) 新增 `ainitialize`：**

```python
    async def ainitialize(self):
        if self._initialized:
            return
        if self._store_type == "sqlite":
            await self._setup_async_store()
        else:
            self._checkpointer = MemorySaver()
            self._store = InMemoryStore()
        self._setup()
        self._initialized = True
```

**(e) 新增 `_setup_async_store`（Task 9 前先抛 NotImplemented，Task 9 落地）：**

```python
    async def _setup_async_store(self):
        raise NotImplementedError("SQLite 异步持久化在 Task 9 实现")
```

**(f) 节点 async 化示例（`agent_node` + `tools_node`，其余节点同构）：**

```python
        async def agent_node(state: SubAgentState, config: RunnableConfig) -> dict:
            await self._check_cancelled(config)
            ...
            response = await model_with_tools.ainvoke(messages)
            await self._check_cancelled(config)
            return {"messages": [response], ...}

        async def tools_node(state: SubAgentState, config: RunnableConfig) -> dict:
            await self._check_cancelled(config)
            result = await ToolNode(tools).ainvoke({"messages": state["messages"]})
            await self._check_cancelled(config)
            return result
```

`plan_node`/`evaluate_node` 里的 `structured_model.invoke(messages)` → `await structured_model.ainvoke(messages)`。

**(g) `_check_cancelled`：**

```python
    async def _check_cancelled(self, config: RunnableConfig) -> None:
        tid = config.get("configurable", {}).get("thread_id")
        event = self._cancellation_events.get(tid)
        if event is not None and event.is_set():
            raise AgentRunCancelled("任务已由用户中止")
```

**(h) 删除 `run`/`run_stream`，重写 `arun`/`arun_stream`：**

```python
    async def arun(self, assigned_task, thread_id=None, context="",
                   cancellation_event: asyncio.Event | None = None) -> str:
        await self.ainitialize()
        tid = thread_id or str(uuid.uuid4())[:12]
        if cancellation_event is not None:
            self._cancellation_events[tid] = cancellation_event
        config = {"configurable": {"thread_id": tid},
                  "recursion_limit": GRAPH_RECURSION_LIMIT}
        initial_state = {
            "assigned_task": assigned_task, "subagent_type": self.subagent_type,
            "step_results": {"_context": context}, "iteration_count": 0,
            "react_iteration_count": 0,
            "messages": [SystemMessage(content=SUBAGENT_SYSTEM_PROMPT.format(
                subagent_type=self.subagent_type, description=self.description,
                capabilities=", ".join(self.capabilities)))],
        }
        try:
            result = await self._graph.ainvoke(initial_state, config)
            return result.get("final_result", "")
        finally:
            self._cancellation_events.pop(tid, None)

    async def arun_stream(self, assigned_task, thread_id=None, context="",
                          cancellation_event: asyncio.Event | None = None):
        await self.ainitialize()
        tid = thread_id or str(uuid.uuid4())[:12]
        if cancellation_event is not None:
            self._cancellation_events[tid] = cancellation_event
        config = {"configurable": {"thread_id": tid},
                  "recursion_limit": GRAPH_RECURSION_LIMIT}
        initial_state = {  # 同 arun
            "assigned_task": assigned_task, "subagent_type": self.subagent_type,
            "step_results": {"_context": context}, "iteration_count": 0,
            "react_iteration_count": 0,
            "messages": [SystemMessage(content=SUBAGENT_SYSTEM_PROMPT.format(
                subagent_type=self.subagent_type, description=self.description,
                capabilities=", ".join(self.capabilities)))],
        }
        final_result = ""
        try:
            async for chunk, metadata in self._graph.astream(
                    initial_state, config, stream_mode="messages"):
                node_name = metadata.get("langgraph_node", "")
                if isinstance(chunk, AIMessage) and chunk.content:
                    text = self._message_chunk_text(chunk.content)
                    if text:
                        yield {"event": "token", "data": {"text": text, "agent": self.subagent_type}}
                if node_name == "plan" and not final_result:
                    yield {"event": "subagent_plan", "data": {"subagent_type": self.subagent_type, "plan": []}}
                elif node_name == "evaluate":
                    yield {"event": "subagent_step", "data": {"subagent_type": self.subagent_type, "status": "evaluating"}}
            final_state = await self._graph.aget_state(config)
            if final_state and final_state.values:
                final_result = final_state.values.get("final_result", "")
            yield {"event": "subagent_done", "data": {
                "subagent_type": self.subagent_type,
                "result_summary": final_result[:200] if final_result else "",
                "success": bool(final_result)}}
        finally:
            if cancellation_event is not None:
                cancellation_event.set()
            self._cancellation_events.pop(tid, None)
```

**(i) 删除 `_raise_if_cancelled` 与旧 `arun`/`arun_stream` 的 `to_thread` 包装。**

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/test_multi_agent_sqlite.py::test_subagent_persists_each_planned_step_before_evaluation tests/test_multi_agent_sqlite.py::test_subagent_async_stream_uses_one_generator_and_propagates_cancel -v`
Expected: PASS（注意 `test_subagent_async_stream_uses_one_generator_and_propagates_cancel` 需把 `fake_run_stream` 改为 async generator、`cancellation_event` 改 `asyncio.Event`，见 Step 1）

- [ ] **Step 5: 提交**

```bash
git add src/agents/multi_agent/sub_agent.py tests/test_multi_agent_sqlite.py
git commit -m "refactor(multi-agent): async-ify SubAgent graph and execution"
```

---

## Task 8: MainAgent 异步化

**Files:**
- Modify: `src/agents/multi_agent/main_agent.py`
- Test: `tests/test_multi_agent_sqlite.py`（迁移）

- [ ] **Step 1: 迁移测试（先失败）**

```python
class _MainAgentStructuredModel:
    def __init__(self, schema): self.schema = schema
    async def ainvoke(self, _messages):
        if self.schema.__name__ == "TaskAnalysisOutput":
            return SimpleNamespace(needs_subagents=True, task_summary="delegate one step",
                                   complexity="simple", suggested_subagents=["worker"], reason="test")
        if self.schema.__name__ == "SubagentMatchOutput":
            return SimpleNamespace(overall_strategy="one step",
                                   plan=[SimpleNamespace(step_id=1, description="flaky work",
                                                         subagent_type="worker", input_summary="", depends_on=[])])
        if self.schema.__name__ == "AggregationOutput":
            return SimpleNamespace(answer="aggregated success", sources=["worker:1"],
                                   confidence="high", missing_info="")
        raise AssertionError(f"unexpected schema: {self.schema.__name__}")


class _MainAgentModel:
    def with_structured_output(self, schema):
        return _MainAgentStructuredModel(schema)
    async def ainvoke(self, _messages):
        return AIMessage(content="direct")


class _FlakySubAgent:
    def __init__(self): self.calls = 0
    async def arun(self, *_args, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary failure")
        return "recovered result"


class _FailingSubAgent:
    def __init__(self): self.calls = 0
    async def arun(self, *_args, **_kwargs):
        self.calls += 1
        raise RuntimeError("persistent failure")


@pytest.mark.asyncio
async def test_main_agent_retries_failed_execute_step_without_replanning():
    agent = MainAgent(max_step_retries=2)
    agent.model = _MainAgentModel()
    agent._checkpointer = MemorySaver()
    agent._store = InMemoryStore()
    agent._initialized = True
    flaky_subagent = _FlakySubAgent()
    agent._get_or_create_subagent = lambda _t: flaky_subagent
    agent._build_graph()

    result = await agent.arun("delegate this", thread_id="execute-retry")
    final_state = await agent._graph.aget_state({"configurable": {"thread_id": "execute-retry"}})

    assert result == "aggregated success"
    assert flaky_subagent.calls == 2
    assert final_state.values["current_step_index"] == 1
```

`test_main_agent_stops_retrying_step_after_configured_limit` 同构改为 `await agent.arun(...)`。

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/test_multi_agent_sqlite.py::test_main_agent_retries_failed_execute_step_without_replanning -v`
Expected: FAIL（`AttributeError: 'MainAgent' object has no attribute 'arun'`）

- [ ] **Step 3: 实现 MainAgent 异步化**

对称改 [main_agent.py](../../src/agents/multi_agent/main_agent.py)：

**(a)** `_cancellation_events` → `dict[str, asyncio.Event]`；新增 `mcp_tools`/`mcp_tools_meta` 构造参数（透传给 `_get_or_create_subagent`）。

**(b)** 5 个节点**全部** `async def`，每个节点开头 `self._raise_if_cancelled(config)` → `await self._check_cancelled(config)`，内部模型调用 `.invoke` → `await *.ainvoke`。逐节点：

| 节点 | 关键改动 |
|------|----------|
| `analyze_node` | `structured_model.invoke(messages)` → `await structured_model.ainvoke(messages)` |
| `respond_node` | `self.model.invoke(messages)` → `await self.model.ainvoke(messages)` |
| `plan_node` | `structured_model.invoke(messages)` → `await structured_model.ainvoke(messages)` |
| `execute_node`（direct 分支） | `self.model.invoke(messages)` → `await self.model.ainvoke(messages)` |
| `execute_node`（subagent 分支） | `sub.run(...)` → `await sub.arun(...)`（见 (c)） |
| `synthesize_node` | `structured_model.invoke(messages)` → `await structured_model.ainvoke(messages)` |

**(c) `execute_node` 里 subagent 分支关键改动：**

```python
            else:
                try:
                    sub = self._get_or_create_subagent(subagent_type)
                    context = self._build_context_for_step(step, results)
                    delegation_task = build_delegation_task_prompt(
                        step["description"], context, state.get("user_task", ""))
                    result = await sub.arun(
                        delegation_task, context=context,
                        cancellation_event=self._cancellation_events.get(
                            config.get("configurable", {}).get("thread_id")))
                    await self._check_cancelled(config)
                    results[step_id] = result
                    statuses[step_id] = "success"
```

**(d)** 删除 `run`/`run_stream`；`arun`/`arun_stream` 原生 async（`ainvoke`/`astream` + `aget_state`），`finally` 里 `event.set()`。

**(e) `_get_or_create_subagent` 注入 mcp_tools：**

```python
    def _get_or_create_subagent(self, subagent_type: str) -> SubAgent:
        if subagent_type not in self._sub_agents_cache:
            meta = self.sub_agent_registry.get(subagent_type)
            if meta is None:
                raise ValueError(f"未知的 SubAgent 类型: {subagent_type}")
            sub = None
            if meta.factory is not None:
                sub = meta.factory()
            if sub is None:
                sub = SubAgent(
                    name=meta.display_name, subagent_type=meta.subagent_type,
                    description=meta.description, capabilities=meta.capabilities,
                    store_type=self._store_type,
                    sqlite_path=self._subagent_sqlite_path(meta.subagent_type))
            # 在 initialize 之前注入 MCP 工具（覆盖自定义 factory 的场景）
            sub._mcp_tools = self._mcp_tools
            sub._mcp_tools_meta = self._mcp_tools_meta
            sub.initialize()
            self._sub_agents_cache[subagent_type] = sub
        return self._sub_agents_cache[subagent_type]
```

> 注意：`sub.initialize()` 是同步的（memory 场景）；SQLite 场景在 Task 9 后改为 `await sub.ainitialize()`。

**(f) 新增 `ainitialize`/`_setup_async_store`（同 SubAgent，SQLite 先 `NotImplementedError`）。**

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/test_multi_agent_sqlite.py -k "main_agent" -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/agents/multi_agent/main_agent.py tests/test_multi_agent_sqlite.py
git commit -m "refactor(multi-agent): async-ify MainAgent graph and execution"
```

---

## Task 9: MultiAgentService 异步化 + SQLite 异步持久化

**Files:**
- Modify: `src/server/services/multi_agent_service.py`
- Modify: `src/agents/multi_agent/sub_agent.py`（`_setup_async_store` 落地）
- Modify: `src/agents/multi_agent/main_agent.py`（同上 + `await sub.ainitialize()`）
- Test: `tests/test_multi_agent_sqlite.py`（追加 SQLite async 生命周期测试）

- [ ] **Step 1: 写 SQLite 异步生命周期失败测试（先钉 API）**

```python
@pytest.mark.asyncio
async def test_async_sqlite_checkpoint_roundtrip(tmp_path):
    """钉住 AsyncSqliteSaver 的 API：connect → setup → ainvoke → aget_state → aclose。"""
    from langgraph.graph import StateGraph, END
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from langchain_core.messages import HumanMessage

    db = tmp_path / "ckpt.db"
    async with AsyncSqliteSaver.from_conn_string(str(db)) as saver:
        g = StateGraph(dict)
        g.add_node("n", lambda s: {"messages": s.get("messages", []) + [HumanMessage(content="hi")]})
        g.set_entry_point("n"); g.add_edge("n", END)
        graph = g.compile(checkpointer=saver)
        await graph.ainvoke({"messages": []}, {"configurable": {"thread_id": "t1"}})
        state = await graph.aget_state({"configurable": {"thread_id": "t1"}})
        assert len(state.values["messages"]) == 1
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/test_multi_agent_sqlite.py::test_async_sqlite_checkpoint_roundtrip -v`
Expected: 若导入路径/构造签名与已安装版本不符，这里 FAIL 并给出准确报错 → 据此修正 `_setup_async_store` 的写法。

- [ ] **Step 3: 落地 SubAgent/MainAgent 的 `_setup_async_store`**

以测试通过的 API 为准（下为参考写法）：

```python
    async def _setup_async_store(self):
        try:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
            from langgraph.store.sqlite.aio import AsyncSqliteStore
        except ImportError:
            self._checkpointer = MemorySaver()
            self._store = InMemoryStore()
            return
        db_path = Path(self._sqlite_path or "./data/subagent.db").expanduser()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._checkpointer = AsyncSqliteSaver.from_conn_string(str(db_path))
        await self._checkpointer.setup()
        self._store = AsyncSqliteStore.from_conn_string(str(db_path))
        await self._store.setup()
        self._sqlite_path = str(db_path)
```

（MainAgent 的 `_get_or_create_subagent` 里把 `sub.initialize()` 改为 `await sub.ainitialize()`。）

- [ ] **Step 4: MultiAgentService 全链路异步化**

改 [multi_agent_service.py](../../src/server/services/multi_agent_service.py)：

**(a)** `_active_runs: dict[str, asyncio.Event]`。

**(b)** `_get_or_create_agent` → `async def`，`await agent.ainitialize()`。

**(c)** `chat_stream`：

```python
    async def chat_stream(self, user_id, session_id, query):
        agent = await self._get_or_create_agent(user_id)
        tid = self._make_tid(user_id, session_id)
        session_lock = self._session_locks.setdefault(tid, asyncio.Lock())
        async with session_lock:
            cancellation_event = asyncio.Event()
            self._active_runs[tid] = cancellation_event
            try:
                async for event in agent.arun_stream(query, thread_id=tid,
                                                     cancellation_event=cancellation_event):
                    yield event
            except (asyncio.CancelledError, GeneratorExit):
                cancellation_event.set()
                raise
            except AgentRunCancelled:
                logger.info("Multi-agent run cancelled for user=%s", user_id[:8])
            except Exception as e:
                logger.exception("Multi-agent stream error for user=%s", user_id[:8])
                yield {"event": "error", "data": {"code": "AGENT_ERROR", "message": str(e), "agent": "main"}}
            finally:
                cancellation_event.set()
                if self._active_runs.get(tid) is cancellation_event:
                    self._active_runs.pop(tid, None)
```

**(d)** 删除同步 `chat()`（已决定移除）。

**(e)** `get_session_messages` 里 `agent._graph.get_state` → `await agent._graph.aget_state`。

**(f)** `close_user`/`close_all` → `async def`，`await agent.aclose()`；`close_all` 里循环 `await self.close_user(uid)`。

- [ ] **Step 5: 运行验证通过**

Run: `pytest tests/test_multi_agent_sqlite.py -v`
Expected: 全 PASS（含 `test_async_sqlite_checkpoint_roundtrip` 与 `test_service_derives_stable_isolated_database_per_user`——后者 `_get_or_create_agent` 已 async，测试需改为 `await service._get_or_create_agent("user-a")` 并加 `@pytest.mark.asyncio`）

- [ ] **Step 6: 提交**

```bash
git add src/agents/multi_agent/sub_agent.py src/agents/multi_agent/main_agent.py src/server/services/multi_agent_service.py tests/test_multi_agent_sqlite.py
git commit -m "refactor(multi-agent): async-ify service and SQLite persistence"
```

---

## Task 10: 全量回归（同步调用方清零）

**Files:** 全部已改文件；`tests/test_server.py` 中涉 `multi_agent_service` 的用例。

- [ ] **Step 1: 跑全量测试找出遗漏的同步调用方**

Run: `pytest tests/test_multi_agent_sqlite.py tests/test_server.py -v`
Expected: 若 `test_server.py` 有 `app.state.multi_agent_service` 相关用例用了同步 `chat()` 或直接访问 `_active_runs` 为 `threading.Event`，此处暴露；逐处修正为 `asyncio.Event` / `await`。

- [ ] **Step 2: 修正后全绿**

Run: `pytest tests/test_multi_agent_sqlite.py tests/test_server.py -v`
Expected: 全 PASS

- [ ] **Step 3: 提交**

```bash
git add -A
git commit -m "test(multi-agent): migrate all callers to async execution"
```

---

# 阶段三：MCP 工具注入与接线

## Task 11: 注入 MCP 工具 + lifespan 接线

**Files:**
- Modify: `src/agents/multi_agent/__init__.py`
- Modify: `src/agents/multi_agent/sub_agent.py`（若 `_setup` 尚未注册 mcp_tools，补上——已在 Task 7 完成，此处核对）
- Modify: `src/agents/multi_agent/main_agent.py`（`__init__` 接收并透传 mcp_tools）
- Modify: `src/server/main.py`
- Modify: `requirements.txt`

- [ ] **Step 1: 写失败测试（lifespan 接线）**

```python
# tests/test_server.py 追加
from src.tools.mcp.config import McpConfig


@pytest.mark.asyncio
async def test_lifespan_wires_mcp_tools_when_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("REPOSITORY_BACKEND", "memory")
    monkeypatch.setenv("MCP_CONFIG_PATH", str(tmp_path / "mcp.json"))
    (tmp_path / "mcp.json").write_text(
        '{"enabled": true, "servers": [{"name": "k", "transport": "stdio", "command": "python"}]}',
        encoding="utf-8")
    monkeypatch.setattr("src.server.main.McpAdapter", _FakeMcpAdapter)

    from src.server.main import app
    # 通过 lifespan 触发 startup
    async with app.router.lifespan_context(app):
        assert len(app.state.mcp_tools) == 1
        assert app.state.multi_agent_service is not None
```

其中 `_FakeMcpAdapter`：

```python
class _FakeMcpAdapter:
    def __init__(self, config): self.config = config
    async def discover(self):
        if not self.config.enabled:
            return [], {}
        from langchain_core.tools import tool
        @tool
        async def k_search(q: str) -> str:
            """fake mcp tool"""
            return "x"
        k_search.name = "k_search"
        return [k_search], {"k_search": {"category": "mcp", "tags": ["mcp", "k"], "version": "1.0.0"}}
    async def close(self): pass
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/test_server.py::test_lifespan_wires_mcp_tools_when_configured -v`
Expected: FAIL（`AttributeError: module 'src.server.main' has no attribute 'McpAdapter'`）

- [ ] **Step 3: 实现接线**

**(a) `src/agents/multi_agent/__init__.py`** — `create_default_registry` 增加参数：

```python
def create_default_registry(mcp_tools: list | None = None,
                            mcp_tools_meta: dict[str, dict] | None = None) -> SubAgentRegistry:
    registry = SubAgentRegistry()
    registry.register(SubAgentMeta(
        subagent_type="general_assistant", display_name="通用子智能体",
        description="获取当前日期和时间，返回 ISO 格式的时间字符串。",
        capabilities=["get_current_time"],
        factory=lambda: SubAgent(name="GeneralAssistant", subagent_type="general_assistant",
                                 description="通用子智能体", capabilities=["get_current_time"],
                                 mcp_tools=mcp_tools, mcp_tools_meta=mcp_tools_meta)))
    registry.register(SubAgentMeta(
        subagent_type="remote_sensing", display_name="遥感中心",
        description=REMOTE_SENSING_DESCRIPTION, capabilities=REMOTE_SENSING_CAPABILITIES,
        factory=lambda: SubAgent(name="RemoteSensingCenter", subagent_type="remote_sensing",
                                 description=REMOTE_SENSING_DESCRIPTION,
                                 capabilities=REMOTE_SENSING_CAPABILITIES,
                                 api_tools=REMOTE_SENSING_TOOLS,
                                 mcp_tools=mcp_tools, mcp_tools_meta=mcp_tools_meta)))
    return registry
```

**(b) `MainAgent.__init__` 接收 `mcp_tools`/`mcp_tools_meta`（Task 8 已加字段，此处确保 `__init__` 签名包含并在 `MultiAgentService` 传入）。**

**(c) `src/server/main.py` lifespan：**

```python
# startup（multi_agent_service 之前）
from ..tools.mcp import load_mcp_config, McpAdapter
mcp_cfg = load_mcp_config(os.getenv("MCP_CONFIG_PATH", "./mcp.json"))
mcp_adapter = McpAdapter(mcp_cfg)
mcp_tools, mcp_tools_meta = await mcp_adapter.discover()
logger.info("MCP 工具: enabled=%s, tools=%d", mcp_cfg.enabled, len(mcp_tools))

sub_agent_registry = create_default_registry(mcp_tools=mcp_tools, mcp_tools_meta=mcp_tools_meta)
multi_agent_service = MultiAgentService(
    sub_agent_registry=sub_agent_registry, store_type=repo_backend,
    sqlite_path=os.path.join(storage_sqlite_dir, "multi_agent.db") if repo_backend == "sqlite" else None)
app.state.mcp_tools = mcp_tools

# shutdown（finally 块）
if mcp_adapter:
    await mcp_adapter.close()
```

**(d) `requirements.txt` 增加 `mcp>=2.0`（`httpx` 已在测试依赖里，若运行环境未显式引入则补 `httpx>=0.27`）。**

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/test_server.py::test_lifespan_wires_mcp_tools_when_configured -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/agents/multi_agent/__init__.py src/agents/multi_agent/main_agent.py src/server/main.py requirements.txt tests/test_server.py
git commit -m "feat(mcp): wire MCP tools into SubAgent via lifespan"
```

---

## 全量验收

- [ ] `pytest tests/test_mcp_config.py tests/test_mcp_convert.py tests/test_mcp_adapter.py tests/test_multi_agent_sqlite.py tests/test_server.py -v` 全绿。
- [ ] `python -c "import src.agents.chat_agent"` 可正常导入（受保护文件未改）。
- [ ] `git diff --stat HEAD~n -- src/agents/chat_agent.py` 为空（逐字节不变）。

---

## 自检记录

**Spec 覆盖**：spec §3（MCP 适配器）→ Task 1–5；§4（SubAgent）→ Task 7；§5（MainAgent）→ Task 8；§6（MultiAgentService）→ Task 9；§7（注入链路）→ Task 11；§2 级联约束（异步 store）→ Task 9。§9 测试策略 → 各 Task 的 Step 1；§10 完成标准 → 全量验收。无遗漏。

**命名一致性**：`McpConnection.call(name, arguments)` / `to_langchain_tool(conn, mcp_tool)` / `McpAdapter.discover() -> (tools, metas)` / `SubAgent.arun` / `MainAgent.arun` / `ainitialize` / `_check_cancelled` 在所有 task 中一致。

**待实现时核对（版本相关外部 API，非占位）**：`AsyncSqliteSaver`/`AsyncSqliteStore` 的导入路径与 `from_conn_string` 签名，已由 Task 9 Step 1 的钉 API 测试强制验证；v2 的 `streamable_http_client`（正确拼写）需自建 `httpx2.AsyncClient` 且返回 2 元组（已按此在 `StreamableHttpTransport.open` 落地）；`ClientSession.initialize()` 仍用于自动向下协商，纯无状态服务器的原生 `discover()`/`adopt()` 或统一 `Client` 对象路径留作后续。
