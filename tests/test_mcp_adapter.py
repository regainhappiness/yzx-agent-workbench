from types import SimpleNamespace
import asyncio

import pytest
from mcp.types import Tool
from PIL import Image

from src.tools.mcp.adapter import (
    McpAdapter,
    McpConnection,
    _extract_text,
    _prepare_vision_image,
)
from src.tools.mcp.config import McpConfig, McpServerConfig
from src.tools.mcp.transport import (
    StdioTransport,
    StreamableHttpTransport,
    build_transport,
)


# ── Task 3: 传输层 ──

def test_build_transport_dispatch():
    assert isinstance(
        build_transport(McpServerConfig(name="x", transport="stdio", command="python")),
        StdioTransport,
    )
    assert isinstance(
        build_transport(McpServerConfig(name="x", transport="streamable-http", url="http://x")),
        StreamableHttpTransport,
    )


def test_http_transport_requires_url():
    with pytest.raises(ValueError):
        build_transport(McpServerConfig(name="x", transport="streamable-http"))


# ── Task 4: 连接管理 + 熔断 ──

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


class _SequencedSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        text = self.responses.pop(0)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
        )


def test_extract_text():
    result = SimpleNamespace(content=[
        SimpleNamespace(type="text", text="hello"),
        SimpleNamespace(type="image", text=None),
        SimpleNamespace(type="text", text="world"),
    ])
    assert _extract_text(result) == "hello\nworld"


def test_prepare_vision_image_downscales_oversized_input(tmp_path):
    source = tmp_path / "large.png"
    Image.new("RGB", (2848, 1600), "white").save(source)
    cfg = McpServerConfig(
        name="eyes",
        transport="stdio",
        command="python",
        subagents=["vision_agent"],
    )

    arguments, temporary_paths = _prepare_vision_image(
        cfg, {"image_path": str(source)},
    )
    temporary_path = temporary_paths[0]
    try:
        assert arguments["image_path"] == str(temporary_path)
        assert temporary_path != source
        with Image.open(temporary_path) as resized:
            assert resized.width <= 1280
            assert resized.height <= 1280
    finally:
        temporary_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_call_succeeds():
    conn = McpConnection(McpServerConfig(name="k", transport="stdio", command="python"))
    conn._session = _FakeSession()
    conn.available = True
    assert await conn.call("search", {"q": "x"}) == "ok"


@pytest.mark.asyncio
async def test_call_retries_timeout_result_without_replanning_subagent():
    session = _SequencedSession(["错误: Request timed out.", "vision result"])
    conn = McpConnection(McpServerConfig(
        name="eyes",
        transport="stdio",
        command="python",
        env={"MKA_MCP_RESULT_RETRIES": "1"},
    ))
    conn._session = session
    conn.available = True

    result = await conn.call("analyze_image", {"image_path": "image.png"})

    assert result == "vision result"
    assert len(session.calls) == 2


@pytest.mark.asyncio
async def test_call_marks_timeout_result_non_retryable_after_retry_limit():
    session = _SequencedSession([
        "错误: Request timed out.",
        "错误: Request timed out.",
    ])
    conn = McpConnection(McpServerConfig(
        name="eyes",
        transport="stdio",
        command="python",
        env={"MKA_MCP_RESULT_RETRIES": "1"},
    ))
    conn._session = session
    conn.available = True

    result = await conn.call("analyze_image", {"image_path": "image.png"})

    assert result.startswith("[MCP] 工具结果重试已耗尽:")
    assert len(session.calls) == 2


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


@pytest.mark.asyncio
async def test_call_reconnects_a_previously_connected_server():
    conn = McpConnection(
        McpServerConfig(name="k", transport="stdio", command="python"),
    )
    session = _FakeSession()
    conn._ever_connected = True
    conn.available = False

    async def fake_close_transport():
        conn.available = False
        conn._session = None

    async def fake_connect():
        conn._session = session
        conn.available = True
        conn._failures = 0

    conn._close_transport = fake_close_transport
    conn.connect = fake_connect

    assert await conn.call("search", {"q": "x"}) == "ok"
    assert session.calls == [("search", {"q": "x"})]


# ── Task 5: 发现编排 ──

class _FakeMcpConnection:
    def __init__(self, cfg):
        self.cfg = cfg
        self.available = True

    async def connect(self):
        pass

    async def list_tools(self):
        return [
            Tool(name="search", description="s",
                 input_schema={"type": "object", "properties": {}}),
            Tool(name="delete", description="d",
                 input_schema={"type": "object", "properties": {}}),
        ]

    async def call(self, name, args):
        return "x"

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_discover_namespaces_and_whitelist(monkeypatch):
    monkeypatch.setattr("src.tools.mcp.adapter.McpConnection", _FakeMcpConnection)
    cfg = McpConfig(enabled=True, servers=[
        McpServerConfig(name="knowledge", transport="stdio",
                        command="python", allowed_tools=["search"]),
    ])
    tools, metas = await McpAdapter(cfg).discover()
    assert [t.name for t in tools] == ["knowledge_search"]   # 白名单过滤掉 delete
    assert metas["knowledge_search"]["category"] == "mcp"
    assert metas["knowledge_search"]["tags"] == ["mcp", "knowledge"]


@pytest.mark.asyncio
async def test_discover_disabled_returns_empty():
    tools, metas = await McpAdapter(McpConfig(enabled=False)).discover()
    assert tools == [] and metas == {}


@pytest.mark.asyncio
async def test_discover_respects_current_empty_session_tool_blocklist(monkeypatch):
    class VisionConnection(_FakeMcpConnection):
        async def list_tools(self):
            return [
                Tool(
                    name="analyze_clipboard",
                    description="read OS clipboard",
                    input_schema={"type": "object", "properties": {}},
                ),
                Tool(
                    name="analyze_image",
                    description="analyze image path",
                    input_schema={
                        "type": "object",
                        "properties": {"image_path": {"type": "string"}},
                        "required": ["image_path"],
                    },
                ),
            ]

    monkeypatch.setattr("src.tools.mcp.adapter.McpConnection", VisionConnection)
    cfg = McpConfig(enabled=True, servers=[
        McpServerConfig(
            name="eyes",
            transport="stdio",
            command="python",
            allowed_tools=["*"],
            subagents=["vision_agent"],
        ),
    ])

    tools, _ = await McpAdapter(cfg).discover()

    assert [tool.name for tool in tools] == [
        "eyes_analyze_clipboard", "eyes_analyze_image",
    ]


@pytest.mark.asyncio
async def test_discover_times_out_and_closes_partial_connection(monkeypatch):
    class SlowConnection(_FakeMcpConnection):
        closed = False

        async def connect(self):
            await asyncio.sleep(1)

        async def close(self):
            self.__class__.closed = True

    monkeypatch.setattr("src.tools.mcp.adapter.McpConnection", SlowConnection)
    cfg = McpConfig(enabled=True, servers=[
        McpServerConfig(
            name="slow",
            transport="stdio",
            command="python",
            timeout_seconds=0.01,
        ),
    ])

    adapter = McpAdapter(cfg)
    tools, metas = await adapter.discover()

    assert tools == [] and metas == {}
    assert adapter.server_statuses["slow"]["status"] == "error"
    assert SlowConnection.closed is True
