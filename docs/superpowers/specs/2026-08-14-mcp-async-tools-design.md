# MCP 工具接入与多智能体异步化设计规格

> 日期: 2026-08-14 | 状态: 已确认 | 关联: [design.md](../../design.md) §10、[multi-agent-design.md](../../multi-agent-design.md)

## 1. 目标与范围

### 1.1 目标

1. 通过配置连接外部 MCP Server，动态发现工具并转换为内部工具描述（LangChain `BaseTool`），以服务器命名空间命名（如 `knowledge/search`）。
2. MCP 工具**只在异步 agent 图里使用**（方案 B），即把 `SubAgent` 从同步图执行改为 `await self._graph.ainvoke(...)`。
3. MCP 默认关闭；连接失败、工具调用失败均不阻断普通对话与知识库问答。

### 1.2 首版范围

- MCP 适配器：配置加载、传输层（stdio / streamable-http）、连接管理、工具发现与转换、白名单、超时与熔断。
- `SubAgent` 异步化：图节点改 `async def`，模型调用改 `await *.ainvoke()`，`ToolNode` 改 `await *.ainvoke()`。
- **级联** `MainAgent` 异步化（见 §2）。
- **级联** SQLite 持久化切换异步实现（见 §2）。
- `MultiAgentService` 全链路异步化。
- MCP 工具注入到 SubAgent 的 `ToolRegistry`。

### 1.3 不在首版范围

- MCP Server 侧的动态重连 / 工具列表热刷新（启动时发现一次，失败熔断后按冷却时间重试）。
- MCP 资源（`resources/list`）与提示词（`prompts/list`）适配，首版只做 `tools/list` + `tools/call`。
- `ChatAgent`（受保护文件）不做任何改动。

---

## 2. 现状与级联分析

### 2.1 当前执行模型

当前 `MainAgent` 与 `SubAgent` 的图节点**全部是同步函数**：

- 节点内调用 `self.model.invoke(...)`、`structured_model.invoke(...)`（同步）。
- `SubAgent` 的 `run()` = `self._graph.invoke(...)`，`run_stream()` = `self._graph.stream(...)`。
- `MainAgent.execute_node` 里**同步调用** `sub.run(...)`（[main_agent.py:343](../../src/agents/multi_agent/main_agent.py#L343)）。
- 所谓「异步」入口 `arun()`/`arun_stream()` 只是 `asyncio.to_thread(self.run, ...)` 的包装（[main_agent.py:587](../../src/agents/multi_agent/main_agent.py#L587)、[sub_agent.py:577](../../src/agents/multi_agent/sub_agent.py#L577)），图本身在 worker 线程里同步跑。

### 2.2 三个硬约束

1. **异步 MCP 工具只能在 async 图里执行**：MCP `ClientSession` 是绑定事件循环的长连接，`StructuredTool(coroutine=...)` 只有在图走 `ainvoke`/`astream` 时才会被 `ToolNode` 正确地 `await`；同步 `.invoke()` 会因「当前线程无运行中的 event loop」失败。
2. **SubAgent 异步化必然牵动 MainAgent**：`MainAgent.execute_node` 同步调 `sub.run()`，一旦 SubAgent 只有 `arun()`，MainAgent 节点必须 `await sub.arun()`，MainAgent 图也必须异步化。
3. **SQLite 持久化不支持同步 checkpointer 跑 async 图**：`ChatAgent` 代码注释已明确「同步 `SqliteSaver`/`SqliteStore` 不实现 LangGraph 的异步接口」，所以 `store_type="sqlite"` 时必须切换为 `AsyncSqliteSaver`/`AsyncSqliteStore`（基于 `aiosqlite`，已在 requirements 中）。

### 2.3 级联结论

方案 B 的最小完整改动面是 **`MainAgent` + `SubAgent` + `MultiAgentService` + SQLite 持久化** 四者一起异步化，缺一不可。`store_type="memory"`（`MemorySaver`/`InMemoryStore`）天然支持异步，无需替换，仅 SQLite 路径需要换异步实现。

---

## 3. MCP 适配器

沿用项目「协议 + 实现」的风格（同 `ObjectStorage`/`Parser`）。

### 3.1 配置

```jsonc
// mcp.json（MCP_CONFIG_PATH 指定，默认 ./mcp.json）
{
  "enabled": false,                // 默认关闭；false 时零连接、零工具
  "servers": [
    {
      "name": "knowledge",          // 命名空间 → knowledge/<tool>
      "transport": "stdio",         // stdio | streamable-http
      "command": "python",
      "args": ["-m", "knowledge_mcp_server"],
      "env": {"KNOWLEDGE_API_KEY": "${KNOWLEDGE_API_KEY}"},
      "timeout_seconds": 30,
      "allowed_tools": ["*"]        // 白名单；或 ["search", "get_doc"]
    },
    {
      "name": "web",
      "transport": "streamable-http",
      "url": "http://localhost:3000/mcp",
      "headers": {"Authorization": "Bearer ..."},
      "timeout_seconds": 30,
      "allowed_tools": ["fetch"]
    }
  ]
}
```

### 3.2 包结构

```
src/tools/mcp/
├── __init__.py        # McpAdapter, McpConfig, load_mcp_config
├── config.py          # Pydantic 配置模型 + JSON 加载
├── transport.py       # McpTransport 协议 + Stdio/StreamableHttp（v2 streamable_http_client + httpx）实现
├── adapter.py         # McpConnection(连接/发现/执行/熔断) + McpAdapter(编排)
└── convert.py         # MCP Tool → LangChain BaseTool（含 json_schema_to_pydantic）
```

依赖新增 `mcp>=2.0`（官方 Python SDK，2026-07-28 spec；`httpx` 已在 requirements）。

### 3.3 发现与转换

```python
# convert.py —— 核心：MCP Tool 转成 async-only 的 BaseTool
def to_langchain_tool(conn: McpConnection, mcp_tool: Tool) -> BaseTool:
    full_name = f"{conn.cfg.name}_{mcp_tool.name}"   # 下划线命名空间（模型函数名不允许 /）
    args_model = json_schema_to_pydantic(mcp_tool.input_schema, full_name)

    async def _arun(**kwargs) -> str:
        return await conn.call(mcp_tool.name, kwargs)   # 内部走 session.call_tool

    # 只给 coroutine，不给 func —— 强制 async-only（方案 B 的约束落点）
    return StructuredTool(name=full_name, description=mcp_tool.description or "",
                          args_schema=args_model, coroutine=_arun)
```

`json_schema_to_pydantic`：把 `inputSchema`（JSON Schema）映射成 Pydantic 模型供 `bind_tools` 用。映射 `string/integer/number/boolean/array/object/enum`，`$ref`/`anyOf`/未知构造降级为 `Any`/`dict` 兜底，`description` 必须透传（LLM 依赖它决策）。这是纯函数，优先级最高、最好测。

`McpConnection.call`：`asyncio.timeout(cfg.timeout_seconds)` 包裹 `session.call_tool`；连续失败 ≥3 次熔断（`available=False` + 冷却时间），调用失败返回错误文本而非抛异常。

### 3.4 异步执行约束

- 适配器本身全异步（`async def connect/list_tools/call`），在 `lifespan` 主循环里创建、在 `finally` 里 `await conn.close()`。
- 生成的工具是 `StructuredTool(coroutine=...)`，只能被 async 图正确执行——这正是 §2.2 约束 1 的来源。

---

## 4. SubAgent 异步化

### 4.1 图节点 async 化

[sub_agent.py](../../src/agents/multi_agent/sub_agent.py) 的 6 个节点全部 `def` → `async def`，模型调用同步转异步：

| 节点 | 改动 |
|------|------|
| `plan_node` | `structured_model.invoke` → `await structured_model.ainvoke` |
| `agent_node` | `model_with_tools.invoke` → `await model_with_tools.ainvoke` |
| `tools_node` | `ToolNode(tools).invoke` → `await ToolNode(tools).ainvoke` |
| `evaluate_node` | `structured_model.invoke` → `await structured_model.ainvoke` |
| `report_node` / `advance_step_node` | 纯状态处理，仅加 `async` |

路由函数（`should_continue` 等）保持同步（LangGraph 条件边支持同步函数）。

### 4.2 执行入口

`arun()` / `arun_stream()` 改为**原生异步实现**，删除 `asyncio.to_thread` 包装：

```python
async def arun(self, assigned_task, thread_id=None, context="",
               cancellation_event=None) -> str:
    await self.ainitialize()
    ...
    result = await self._graph.ainvoke(initial_state, config)
    return result.get("final_result", "")

async def arun_stream(self, ...) -> AsyncGenerator[dict, None]:
    ...
    async for chunk, metadata in self._graph.astream(initial_state, config,
                                                     stream_mode="messages"):
        ...
```

同步 `run()`/`run_stream()` 移除（见 §11）。

### 4.3 取消机制

`threading.Event` → `asyncio.Event`（图已回到主循环，无 worker 线程，跨线程信号不再需要）：

- `self._cancellation_events: dict[str, asyncio.Event]`。
- `_raise_if_cancelled` 改为 `async def _check_cancelled(config)`，节点开头 `await self._check_cancelled(config)`；`event.is_set()` 时抛 `AgentRunCancelled`。
- `arun`/`arun_stream` 的 `finally` 里 `event.set()` + `pop`，语义不变。

### 4.4 持久化

- `store_type="memory"`：`MemorySaver`/`InMemoryStore` 天然支持异步，无需改。
- `store_type="sqlite"`：换 `AsyncSqliteSaver` + `AsyncSqliteStore`（`langgraph.checkpoint.sqlite.aio` / `langgraph.store.sqlite.aio`，**以已安装版本导入路径为准**）。它们基于 `aiosqlite`，需要异步创建与关闭：

```python
self._checkpointer = AsyncSqliteSaver(conn)      # aiosqlite 连接
await self._checkpointer.setup()
self._store = AsyncSqliteStore(store_conn)
await self._store.setup()
# 关闭时：
await self._checkpointer.aclose()
await self._store.aclose()
```

因此 `_setup()` 拆出异步路径（见 §7 的 `ainitialize` 设计）。

---

## 5. MainAgent 异步化（级联）

[main_agent.py](../../src/agents/multi_agent/main_agent.py) 的改动与 SubAgent 对称：

| 节点 | 改动 |
|------|------|
| `analyze_node` / `plan_node` / `synthesize_node` | `structured_model.invoke` → `await *.ainvoke` |
| `respond_node` | `model.invoke` → `await model.ainvoke` |
| `execute_node`（direct 分支） | `model.invoke` → `await model.ainvoke` |
| `execute_node`（subagent 分支） | `sub.run(...)` → `result = await sub.arun(...)` |

其余：`arun`/`arun_stream` 原生 async（`ainvoke`/`astream`）、`threading.Event` → `asyncio.Event`、SQLite 换异步实现，均同 §4。

---

## 6. MultiAgentService 改造

[multi_agent_service.py](../../src/server/services/multi_agent_service.py)：

- `_active_runs: dict[str, asyncio.Event]`（原 `threading.Event`）。
- `_get_or_create_agent` 改为 `async def`，内部 `await agent.ainitialize()`。
- `chat_stream` 直接 `async for event in agent.arun_stream(...)`，**不再经过 `to_thread`**。
- `get_session_messages` 里 `agent._graph.get_state` → `await agent._graph.aget_state`。
- `close_all` / `close_user` 改为 `async def`，`await agent.aclose()`（异步关闭 checkpointer/store）。
- 同步 `chat()`：移除或改 `async def`（当前无路由调用，仅测试/演示用）。

取消路径不变：`AgentRunCancelled` 仍在 `chat_stream` 捕获；客户端断开由路由层调 `cancel_run` → `asyncio.Event.set()`。

---

## 7. 异步初始化与 MCP 工具注入链路

### 7.1 `ainitialize`

`BaseAgent.initialize()` 是同步的（[base.py:78](../../src/agents/base.py#L78)）。为支持异步 checkpointer 的创建，`MainAgent`/`SubAgent` 增加 `async def ainitialize()`，`MultiAgentService` 统一走它：

```python
# SubAgent / MainAgent
async def ainitialize(self):
    if self._initialized:
        return
    if self._store_type == "sqlite":
        await self._setup_async_store()      # 建 AsyncSqliteSaver/Store + await setup()
    self._setup(...)                          # 模型/工具/内存 store + _build_graph()
    self._initialized = True
```

`store_type="memory"` 时 `ainitialize()` 等价于同步初始化（MemorySaver 支持异步图）。同步 `initialize()` 保留但仅用于内存场景或测试。

### 7.2 MCP 工具注入

```
lifespan: mcp_adapter.discover() → (mcp_tools, mcp_metas)
  → MultiAgentService(mcp_tools=..., mcp_tools_meta=...)
    → MainAgent(mcp_tools=..., mcp_tools_meta=...)
      → SubAgent(mcp_tools=..., mcp_tools_meta=...)   # _get_or_create_subagent 传入
        → ToolRegistry.register_with_meta(mcp_tools, mcp_metas, category="mcp")
```

- `SubAgent.__init__` 新增 `mcp_tools=None, mcp_tools_meta=None`；`_setup` 里注册（放在 L1/L4 之后）。
- `MainAgent.__init__` 新增同名字段；`_get_or_create_subagent` 在调用 `sub.initialize()` 之前把 `mcp_tools` 写进实例（兼容自定义 `meta.factory` 返回的 SubAgent）。
- 命名空间冲突：注册前检查 `tool.name` 是否已在 `ToolRegistry`，冲突则告警跳过。
- 由于 SubAgent 的 `_format_available_tools()` 读取 `tool_registry.list_all()`，MCP 工具会自动进入 plan 提示词并被 `bind_tools` 绑定，无需额外改动。

---

## 8. 文件变更清单

### 新增

| 文件 | 说明 |
|------|------|
| `src/tools/mcp/__init__.py` | 导出 |
| `src/tools/mcp/config.py` | `McpConfig`/`McpServerConfig` + `load_mcp_config` |
| `src/tools/mcp/transport.py` | `McpTransport` 协议 + 两种传输实现（stdio / streamable-http） |
| `src/tools/mcp/adapter.py` | `McpConnection` + `McpAdapter`（发现/转换/熔断） |
| `src/tools/mcp/convert.py` | `to_langchain_tool` + `json_schema_to_pydantic` |
| `tests/test_mcp_adapter.py` | MCP 适配器契约测试（fake stdio server） |
| `tests/test_mcp_convert.py` | `json_schema_to_pydantic` 单测 |

### 修改

| 文件 | 改动 |
|------|------|
| `src/agents/base.py` | 增加 `async def ainitialize` / `async def aclose` 默认实现 |
| `src/agents/multi_agent/sub_agent.py` | 节点 async 化、`arun`/`arun_stream` 原生 async、`mcp_tools` 注入、取消机制、异步 store |
| `src/agents/multi_agent/main_agent.py` | 同上 + `execute_node` `await sub.arun` |
| `src/agents/multi_agent/__init__.py` | `create_default_registry` 可接收 mcp_tools（透传给 factory） |
| `src/server/services/multi_agent_service.py` | 全链路 async、`asyncio.Event`、`await agent.ainitialize/arun_stream` |
| `src/server/main.py` | lifespan 里 `load_mcp_config` + `mcp_adapter.discover()` + 关闭 |
| `requirements.txt` | 新增 `mcp>=2.0`（`aiosqlite`/`httpx` 已有） |
| `tests/test_multi_agent_sqlite.py` | `run()`→`await arun()`，fake model 补 `ainvoke`，取消事件改 `asyncio.Event` |

---

## 9. 测试策略

- **转换层单测**：`json_schema_to_pydantic` 覆盖标量/嵌套对象/数组/enum/可选字段/`$ref` 兜底。
- **适配器契约测试**：用一个进程内 fake MCP stdio server（或 mock `ClientSession.list_tools/call_tool`）验证「发现 → 转换 → 注册 → 调用」全链路，不依赖真实外部 Server（呼应 design.md §18.7）。
- **异步图测试**：`FakeAsyncSubAgentModel`/`FakeAsyncMainAgentModel`（提供 `ainvoke`）验证图能跑通；`FakeAsyncMcpTool`（`StructuredTool(coroutine=...)`）验证 async 图能正确 `await` 工具。
- **SQLite 异步持久化**：`AsyncSqliteSaver`/`AsyncSqliteStore` 的 setup/checkpoint/aclose 生命周期测试（替换现有同步 SQLite 回归测试的对应断言）。
- **迁移现有测试**：`test_multi_agent_sqlite.py` 三处 `agent.run(...)` 改 `await agent.arun(...)` 并加 `@pytest.mark.asyncio`；`_SubAgentModel`/`_MainAgentModel` 等 fake 补 `ainvoke`；取消机制相关测试改 `asyncio.Event`。
- **降级测试**：`mcp.enabled=false` 或连接失败时，多智能体问答仍正常（无 MCP 工具）。

---

## 10. 完成标准

- [ ] `mcp.json` 配置可加载，`enabled=false` 时零连接、零工具。
- [ ] 连接外部 MCP Server 后工具被命名空间化（`server/tool`）注册进 SubAgent `ToolRegistry`。
- [ ] `SubAgent`/`MainAgent` 图经 `ainvoke`/`astream` 执行，MCP 工具调用正确 `await`。
- [ ] `store_type="sqlite"` 下多智能体会话可持久化（异步 checkpointer/store）。
- [ ] 客户端断开时异步图协作取消，资源正确释放。
- [ ] MCP 未配置 / 连接失败 / 工具调用失败均不阻断普通问答。
- [ ] 原同步 SQLite 回归测试迁移为异步后全部通过；`tests/test_mcp_*.py` 通过。
- [ ] 受保护文件 `src/agents/chat_agent.py` 逐字节不变。

---

## 11. 风险与待确认决策点

1. **同步 `run()`/`run_stream()` 去留**：✅ 已决定**移除**（async-only）。同步调用方（`MultiAgentService.chat()`、测试、演示脚本）一律改 `await`，fake model 补 `ainvoke`。
2. **异步 checkpointer/store 导入路径**：`AsyncSqliteSaver` 位于 `langgraph.checkpoint.sqlite.aio`；异步 store 的路径与已安装 `langgraph` 版本相关，实现时先验证（`python -c "from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver"`）。
3. **`ainitialize` 的并发**：多个请求同时首次触达同一 user 时需保证 `ainitialize` 幂等且不重复建连接（沿用现有 `_get_or_create_agent` 缓存 + 必要时加锁）。
4. **MCP 工具注入范围**：默认注入所有 SubAgent；是否按 subagent 类型/白名单再细分，可在配置里加 `servers[].allowed_tools` 之外再按 `subagent_type` 过滤（首版不做）。
