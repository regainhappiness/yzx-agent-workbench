# MCP 工具动态发现与注册全链路

> 从「本地子进程启动命令」到「注册为工具供 agent 使用」的完整流程梳理。
> 关联：[design.md](design.md) §10、[2026-08-14-mcp-async-tools-design.md](superpowers/specs/2026-08-14-mcp-async-tools-design.md)

---

## 1. 总览（一图流）

```
┌─────────────── 配置 ───────────────┐
│  mcp.json / mcp.json.example        │  用户声明外部 MCP Server
│  { enabled, servers[] }             │
└────────────────┬───────────────────┘
                 │  load_mcp_config()          [src/tools/mcp/config.py]
                 ▼
         McpConfig（Pydantic）
                 │  McpAdapter(config)          [src/tools/mcp/adapter.py]
                 ▼
         await adapter.discover()               [server/main.py lifespan]
                 │  对每个 server：
                 │    McpConnection(cfg)
                 │      ├─ transport.open()     [src/tools/mcp/transport.py]
                 │      │    ├─ stdio: 启动本地子进程（command + args + env）
                 │      │    └─ streamable-http: httpx2.AsyncClient 连接 URL
                 │      ├─ ClientSession(read, write)   [mcp SDK v2]
                 │      ├─ await session.initialize()   # 协议版本协商
                 │      └─ await session.list_tools()   # → MCP tools/list → Tool[]
                 │    to_langchain_tool(conn, tool)     [src/tools/mcp/convert.py]
                 │      ├─ json_schema_to_pydantic(input_schema)  # JSON Schema → Pydantic
                 │      └─ name = f"{server}_{tool}"              # 下划线命名空间
                 ▼
         (tools: list[BaseTool], metas: dict)
                 │  create_default_registry(mcp_tools=...) [multi_agent/__init__.py]
                 ▼
         SubAgent(mcp_tools=...)  →  ToolRegistry.register_with_meta(category="mcp")
                 │                                     [multi_agent/sub_agent.py]
                 ▼
         异步 agent 图（ToolNode.ainvoke）执行时
                 │  conn.call(tool, args) → session.call_tool()
                 ▼
             工具结果文本 → 回填 ToolMessage → 继续 ReAct 循环
```

---

## 2. 配置：`mcp.json`

配置文件路径由环境变量 `MCP_CONFIG_PATH` 指定，默认 `./mcp.json`。

```jsonc
{
  "enabled": false,                 // 总开关；false 时零连接、零工具
  "servers": [
    {
      "name": "knowledge",          // 命名空间前缀 → 工具名 knowledge_search
      "transport": "stdio",         // stdio（本地子进程）| streamable-http（远程）
      "enabled": true,              // 本 server 开关；false 时跳过该 server
      "command": "python",          // stdio 专用：启动命令
      "args": ["-m", "knowledge_mcp_server"],  // stdio 专用：启动参数
      "env": {"KNOWLEDGE_API_KEY": "..."},     // stdio 专用：子进程环境变量
      "timeout_seconds": 30,        // 单次工具调用超时
      "allowed_tools": ["*"],       // 白名单："*" 全放行，或列出工具名
      "subagents": ["general_assistant"]  // 分配给哪些子 agent；"*"=全部
    },
    {
      "name": "web",
      "transport": "streamable-http",
      "url": "http://localhost:3000/mcp",      // streamable-http 专用：服务地址
      "headers": {"Authorization": "Bearer ..."}, // streamable-http 专用：请求头
      "timeout_seconds": 30,
      "allowed_tools": ["fetch"]
    }
  ]
}
```

对应 Pydantic 模型在 [src/tools/mcp/config.py](src/tools/mcp/config.py)：

- `McpServerConfig`：单个 Server（`name` / `transport` / `enabled` / `command` / `args` / `env` / `url` / `headers` / `timeout_seconds` / `allowed_tools` / `subagents`）。
- `enabled`：本 server 开关（默认 `true`；`false` 时跳过该 server，其余 server 不受影响）。
- `subagents`：server 级工具分配，声明这个 server 的工具归哪些子 agent 使用（默认 `["*"]` 全部；写 `["general_assistant"]` 则只有该子 agent 能加载）。
- `McpConfig`：`enabled` + `servers[]`。
- `load_mcp_config(path)`：读 JSON 文件，**文件缺失或解析失败时返回 `McpConfig(enabled=False)`**（静默降级，不抛异常）。

> 注意：`transport` 目前只有 `stdio` 和 `streamable-http` 两种（MCP 2.0 废弃了 legacy SSE）。

---

## 3. 启动：lifespan 加载与发现

在 [src/server/main.py](src/server/main.py) 的 `lifespan` startup 中：

```python
mcp_cfg = load_mcp_config(os.getenv("MCP_CONFIG_PATH", "./mcp.json"))
mcp_adapter = McpAdapter(mcp_cfg)
mcp_tools, mcp_tools_meta = await mcp_adapter.discover()
logger.info("MCP 工具: enabled=%s, tools=%d", mcp_cfg.enabled, len(mcp_tools))
```

关键点：

- `enabled=false`（或 mcp.json 不存在）时，`discover()` 直接返回 `([], {})`，**不会建立任何连接**。
- 每个 Server 的连接/发现都包在 `try/except` 里，单个失败只 `logger.warning` 并跳过，**不会阻断整个应用启动**。

---

## 4. 传输层：本地子进程 / 远程 HTTP

[src/tools/mcp/transport.py](src/tools/mcp/transport.py) 定义 `McpTransport` 协议 + 两种实现，由 `build_transport(cfg)` 按 `transport` 字段分发。

### 4.1 stdio（本地子进程）

```python
class StdioTransport:
    def __init__(self, cfg):
        self._params = StdioServerParameters(command=cfg.command, args=cfg.args, env=cfg.env or None)

    @asynccontextmanager
    async def open(self):
        async with stdio_client(self._params) as (read, write):
            yield read, write
```

- `stdio_client` 会**启动一个本地子进程**（如 `python -m knowledge_mcp_server`），通过 stdin/stdout 与它通信。
- 这是「从本地子进程启动命令」这一步的落点：`command` + `args` + `env` 就是进程的启动命令。

### 4.2 streamable-http（远程服务）

```python
class StreamableHttpTransport:
    @asynccontextmanager
    async def open(self):
        async with httpx2.AsyncClient(headers=self._headers, timeout=...) as client:
            async with streamable_http_client(self._url, http_client=client) as (read, write):
                yield read, write
```

- MCP 2.0（SDK v2）下，`streamable_http_client` 需要自建 `httpx2.AsyncClient`（注意是 `httpx2`，不是 `httpx`），返回 `(read, write)` 二元组。

两种传输都统一 yield `(read_stream, write_stream)`，上层 `McpConnection` 不感知差异。

---

## 5. 连接与工具发现

[src/tools/mcp/adapter.py](src/tools/mcp/adapter.py) 的 `McpConnection`：

```python
async def connect(self):
    self._stack = AsyncExitStack()
    read, write = await self._stack.enter_async_context(self._transport.open())
    self._session = await self._stack.enter_async_context(ClientSession(read, write))
    # v2: initialize() 用于自动向下协商协议版本
    await self._session.initialize()
    self.available = True

async def list_tools(self) -> list[Tool]:
    result = await self._session.list_tools()   # MCP 协议 tools/list
    return list(result.tools)
```

- `ClientSession` 是 MCP SDK 的客户端会话对象，封装了 JSON-RPC 通信。
- `session.initialize()` 完成协议握手/协商（MCP 2.0 会自动向下兼容旧版服务器）。
- `session.list_tools()` 对应 MCP 协议的 `tools/list` 方法，返回 `ListToolsResult`，其中 `.tools` 是 `Tool[]` 列表。

`Tool` 的关键字段（MCP 2.0 是 **snake_case**）：

| 字段 | 说明 |
|---|---|
| `name` | 工具名 |
| `description` | 工具描述（LLM 决策依据） |
| `input_schema` | 参数 JSON Schema（注意不是 `inputSchema`，那是别名） |

---

## 6. 转换：MCP Tool → LangChain `StructuredTool`

[src/tools/mcp/convert.py](src/tools/mcp/convert.py) 的 `to_langchain_tool`：

```python
def to_langchain_tool(conn, mcp_tool) -> BaseTool:
    full_name = f"{conn.cfg.name}_{mcp_tool.name}"     # 下划线命名空间
    model_name = "".join(c if c.isalnum() else "_" for c in full_name)
    args_model = json_schema_to_pydantic(mcp_tool.input_schema or {}, model_name)

    async def _arun(**kwargs) -> str:
        return await conn.call(mcp_tool.name, kwargs)   # 回调 MCP tools/call

    return StructuredTool(
        name=full_name,
        description=mcp_tool.description or "",
        args_schema=args_model,
        coroutine=_arun,          # 只给 coroutine → async-only，仅异步图可用
    )
```

三个关键点：

1. **命名空间**：工具名用 `{server}_{tool}`（下划线），例如 `knowledge_search`。原因：OpenAI/DeepSeek 的函数调用 `name` 只允许 `^[a-zA-Z0-9_-]{1,64}$`，`/` 不允许。
2. **JSON Schema → Pydantic**：`json_schema_to_pydantic()` 把 MCP 的 `input_schema`（JSON Schema）映射成 Pydantic 模型，供 `bind_tools` 生成参数 schema。不支持的构造（`$ref`/`anyOf`/未知 type）降级为 `Any` 兜底，保证不抛异常。
3. **async-only**：`coroutine=_arun` 且不设 `func`，意味着工具只能在异步图里正确执行（`ToolNode.ainvoke` 会 `await` 它）。这也是「MCP 工具只在异步 agent 图里使用」的落点。

---

## 7. 注册注入链路

`discover()` 返回 `(tools, metas)`，其中 `metas` 形如：

```python
{"knowledge_search": {"category": "mcp", "tags": ["mcp", "knowledge"], "version": "1.0.0"}}
```

注入链路（设计意图）：

```
main.py lifespan
  → mcp_tools, mcp_tools_meta = await mcp_adapter.discover()
  → create_default_registry(mcp_tools=mcp_tools, mcp_tools_meta=mcp_tools_meta)
        [src/agents/multi_agent/__init__.py]
  → SubAgentMeta.factory = lambda: SubAgent(..., mcp_tools=mcp_tools, mcp_tools_meta=mcp_tools_meta)
  → SubAgent._setup():
        if self._mcp_tools:
            self.tool_registry.register_with_meta(self._mcp_tools, self._mcp_tools_meta)
        [src/agents/multi_agent/sub_agent.py]
```

`SubAgent._setup()` 里 MCP 工具被注册进该 SubAgent 独立的 `ToolRegistry`，之后：

- `_build_graph()` 里 `model.bind_tools(tools)` 会把 MCP 工具绑给模型（`agent_node` 的 ReAct 循环）。
- `_format_available_tools()` 会把 MCP 工具名+描述注入 plan 提示词。

> ⚠️ **已知问题（当前实现）**：`MainAgent._get_or_create_subagent()`（[main_agent.py](src/agents/multi_agent/main_agent.py) 第 681-682 行）会无条件执行 `sub._mcp_tools = self._mcp_tools`，而 `MultiAgentService._get_or_create_agent()` 创建 `MainAgent` 时**没有传 `mcp_tools`**，所以 `MainAgent._mcp_tools == []`，会把 factory 注入的 MCP 工具清空。
>
> 结果：启动时发现的 MCP 工具实际上没有注册进 SubAgent。见 §11。

---

## 8. 执行：agent 调用 MCP 工具

运行时（异步 SubAgent 图）：

```
agent_node（ReAct）
  → model_with_tools.ainvoke(messages)        # LLM 决定调用 knowledge_search
  → 产生 tool_calls
  → tools_node：ToolNode(tools).ainvoke(...)  # 异步执行工具
        → StructuredTool._arun(**kwargs)
            → conn.call("search", kwargs)
                → 超时控制（asyncio.timeout）
                → session.call_tool("search", kwargs)   # MCP tools/call
                → 提取 result.content 里的 text → 拼接为字符串
  → ToolMessage(工具结果) 回填
  → 回到 agent_node 继续 / advance_step
```

`McpConnection.call()` 的容错（[adapter.py](src/tools/mcp/adapter.py)）：

- `asyncio.timeout(cfg.timeout_seconds)` 包裹调用。
- 连续失败 ≥3 次 → `available=False`（熔断），之后调用直接返回错误文本，不抛异常。
- 成功一次 → 清零失败计数。

---

## 9. 降级与容错

| 场景 | 行为 |
|---|---|
| `enabled=false` / mcp.json 不存在 | `discover()` 返回空，零连接、零工具 |
| 单个 Server 连接失败 | `logger.warning` + 跳过该 Server，其余继续 |
| 单个 Server `list_tools` 失败 | `logger.warning` + 跳过该 Server 的工具 |
| 工具调用超时 | 返回 `[MCP] 工具调用失败: ...` 错误文本 |
| 连续 3 次调用失败 | 熔断，该 Server 后续调用直接返回「不可用」 |
| 白名单 `allowed_tools` | 只放行列表内工具（`"*"` 表示全放行） |

核心保证：**MCP 未配置 / 连接失败 / 工具调用失败，都不阻断普通对话和知识库问答**。

---

## 10. 关键文件索引

| 文件 | 职责 |
|---|---|
| [src/tools/mcp/config.py](src/tools/mcp/config.py) | `McpConfig`/`McpServerConfig` + `load_mcp_config` |
| [src/tools/mcp/transport.py](src/tools/mcp/transport.py) | `McpTransport` 协议 + stdio / streamable-http 实现 |
| [src/tools/mcp/adapter.py](src/tools/mcp/adapter.py) | `McpConnection`（连接/发现/调用/熔断）+ `McpAdapter`（编排） |
| [src/tools/mcp/convert.py](src/tools/mcp/convert.py) | `to_langchain_tool` + `json_schema_to_pydantic` |
| [src/server/main.py](src/server/main.py) | lifespan 里 `load_mcp_config` + `discover()` + 注入 + 关闭 |
| [src/agents/multi_agent/__init__.py](src/agents/multi_agent/__init__.py) | `create_default_registry(mcp_tools=...)` |
| [src/agents/multi_agent/sub_agent.py](src/agents/multi_agent/sub_agent.py) | `_setup()` 里把 `mcp_tools` 注册进 `ToolRegistry` |
| [src/agents/multi_agent/main_agent.py](src/agents/multi_agent/main_agent.py) | `_get_or_create_subagent()` 注入 MCP 工具（⚠️ 见 §11） |
| [mcp.json.example](mcp.json.example) | 配置模板 |

---

## 11. 注入链路说明（已修复）

曾有一个注入断裂问题：`MainAgent._get_or_create_subagent()` 会无条件用 `MainAgent._mcp_tools`（空列表，因为 `MultiAgentService` 创建 `MainAgent` 时未传 `mcp_tools`）覆盖 factory 注入的 MCP 工具，导致工具被清空、未真正注册。

已按「统一由 factory 注入」修复：`_get_or_create_subagent()` 中那两行覆盖代码已注释掉，MCP 工具完全由 `create_default_registry(mcp_tools=...)` 通过 factory 注入，`MainAgent` 不再覆盖。



核心点先说清楚：stdio 传输不是「连接一个已经在跑的服务」，而是「启动一个子进程，然后接管它的 stdin/stdout 管道」。所以配置里只有「怎么启动」的信息（command/args/env），没有 url/端口——因为根本不走网络。

为什么 command + args + env 就够了
StdioServerParameters(command, args, env) 这三个字段，正好就是操作系统启动一个进程所需的全部信息：

command：可执行程序/启动器（python、npx、uvx、或某个二进制路径）
args：传给它的参数（如 ["-m", "knowledge_mcp_server"]）
env：注入给这个子进程的环境变量（通常是 API Key 之类的凭据）
MCP SDK 的 stdio_client 内部做的事：

用 command + args + env spawn 一个子进程；
把子进程的 stdin/stdout 包成 read/write 流；
之后所有 MCP 协议消息（JSON-RPC）就在这两条管道上收发。
对应你项目里的 transport.py 的 StdioTransport——它只做 stdio_client(StdioServerParameters(...))，后面的 ClientSession(read, write) 就是在跟这个子进程「对话」。

那 MCP server 的代码从哪来？
command 只是「启动器」，它本身不携带 MCP server 的代码。 真正的代码必须已经在本机，或由包管理器在首次运行时自动拉取：

启动命令	代码来源
python -m xxx	xxx 这个 Python 包必须已经 pip install 进当前 Python 环境
npx -y @scope/server	npx 检查本地 node_modules，没有就从 npm 自动下载后运行
uvx xxx	uv 会自动下载并运行 xxx 这个 Python 包
/usr/local/bin/xxx	已编译好的可执行文件，路径必须存在
以你 mcp.json.example 里的例子：


{"command": "python", "args": ["-m", "knowledge_mcp_server"], "env": {"KNOWLEDGE_API_KEY": "..."}}
这等价于你手动在终端敲 python -m knowledge_mcp_server——前提是 knowledge-mcp-server 这个包已经 pip install 进你跑客户端用的那个 Python 环境。客户端「启动服务」的本质，就是帮你执行这条命令，然后接管它的 stdin/stdout。

env 的作用：MCP server 是独立进程，它自己要调外部 API（比如知识库），所以需要凭据——客户端通过 env 把 KNOWLEDGE_API_KEY 传进子进程环境，这样 server 才有 key 可用。

对比 streamable-http
stdio	streamable-http
通信方式	子进程 stdin/stdout 管道	网络 HTTP
「连接」含义	启动一个本地子进程	连一个已经在跑的远程服务
需要 url 吗	不需要	需要
代码在哪	本机（已安装）	远端
一句话总结：stdio = 帮你起一个本地子进程并接管它的输入输出；streamable-http = 连一个已存在的远程服务地址。