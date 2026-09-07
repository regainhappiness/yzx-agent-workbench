# Multi-Agent 请求全链路梳理

从 `POST /api/v1/multi-agent/chat/stream` 发起请求到返回完整 SSE 事件流的全链路，**含动态修改 LLM 模型选择与 MCP 服务配置**。

> 本文描述的是当前实际实现（异步化 + 多轮会话上下文 + 运行时配置热更新）。
> 关联文档：[mcp-tool-discovery-flow.md](mcp-tool-discovery-flow.md)（MCP 工具发现细节）。

---

## 0. 总览（一图流）

```
浏览器 (MultiAgentView.vue)
   │  POST /api/v1/multi-agent/chat/stream  {query, session_id?}
   ▼
FastAPI API 层 (api/multi_agent.py)
   │  AuthMiddleware → Identity → 会话校验/创建 → EventSourceResponse
   ▼
MultiAgentService.chat_stream()  (services/multi_agent_service.py)
   │  1. 取/建 MainAgent（按 user 缓存）
   │  2. 组装多轮上下文（历史消息 + 摘要 + 上轮产物）
   │  3. 建 Turn / 用户消息 → yield turn_started
   │  4. agent.arun_stream() → 逐事件转发
   ▼
MainAgent (agents/multi_agent/main_agent.py)  — LangGraph
   │  analyze → (respond | plan → execute → synthesize)
   │  execute 内按需 sub.arun() 调度 SubAgent
   ▼
SubAgent (agents/multi_agent/sub_agent.py)  — LangGraph Plan-and-Solve
   │  plan → agent → (tools→advance_step) → evaluate → report
   │  工具 = L1 内置 + L4 专属 API + MCP 外部工具
   ▼
模型 get_model()  +  MCP 工具（运行时配置注入）
```

配置来源：**SQLite 运行时配置**（`RuntimeConfigService`）为运行期唯一真相，`.env` / `mcp.json` 仅作启动种子。

---

## 1. 请求入口 — API 层

**文件:** [src/server/api/multi_agent.py](src/server/api/multi_agent.py)

```
POST /api/v1/multi-agent/chat/stream
Body:    { "query": "帮我分析销售数据", "session_id": null }
Headers: Authorization: Bearer sk-xxx
```

处理步骤：

1. **认证**：`AuthMiddleware` 提取 Bearer token → `request.state.user_id / role / api_key_prefix`；`get_identity` 组装成 `Identity`。
2. **会话**：
   - `session_id` 已传 → `session_service.require_session(user_id, session_id, "multi_agent")` 校验存在与所有权；
   - 为空 → `create_session(session_type="multi_agent", title=query[:50])`。
3. **SSE 生成器 `event_generator()`**：
   - `yield start`（含 `session_id`）；
   - 转发 `multi_agent_service.chat_stream(...)` 的每个事件（记录是否已发过 `done`）；
   - 客户端断开 → `cancel_run(...)` 并返回；
   - 异常 → `yield error`；
   - 若服务层未发过 `done`，补发 `yield done`。
4. 返回 `EventSourceResponse(event_generator())`。

---

## 2. 服务层 — MultiAgentService

**文件:** [src/server/services/multi_agent_service.py](src/server/services/multi_agent_service.py)

### 2.1 构造与注入

构造时注入（见 [main.py](src/server/main.py) lifespan）：

- `sub_agent_registry`：由 `RuntimeConfigService.registry` 提供（含 MCP 工具 + 运行时模型配置）；
- `model_kwargs`：`RuntimeConfigService.model_config`（动态模型配置）；
- `message_repo / turn_repo / summary_repo`：多轮会话持久化；
- `session_service`、`max_context_tokens`（默认 6000）、`max_history_turns`（默认 10）。

### 2.2 Agent 缓存

`_get_or_create_agent(user_id)` 按 user 缓存 `MainAgent`，创建时传入 `model_kwargs=self._model_kwargs`。

`thread_id = "ma:v2:{user_id}:{session_id}"`（LangGraph checkpoint 隔离键）。

### 2.3 chat_stream() 执行流程

```
chat_stream(user_id, session_id, query)
│
├─ agent = _get_or_create_agent(user_id)          # 按 user 缓存 MainAgent
├─ tid = "ma:v2:{user_id}:{session_id}"
├─ session_lock（同一会话串行）
│
├─ 组装多轮上下文:
│   ├─ existing_messages = message_repo.list_by_session(session_id)
│   ├─ summary, conversation_context = _prepare_conversation_context(...)
│   │     └→ 按 Token 预算裁剪最近消息 + 增量更新较早历史摘要(agent.summarize_conversation)
│   ├─ previous_turns = turn_repo.list_by_session(session_id)
│   └─ previous_artifacts = [最近 3 个 turn 的产物快照]
│
├─ 建 Turn: turn_repo.create(status="running", resolved_task=query)
├─ 存用户消息: message_repo.create(role="user", content=query)
├─ _sync_message_count(session_id)
│
├─ yield turn_started {turn_id, session_id}
│
├─ async for event in agent.arun_stream(
│       query, thread_id=tid, cancellation_event=..., turn_id=...,
│       conversation_context=..., conversation_summary=..., previous_artifacts=...
│   ):
│     └→ 跳过 event=="done"，其余 yield
│
├─ snapshot = agent.get_run_snapshot(tid)        # 读最终 state
├─ _finalize_turn(... status="completed")        # 更新 Turn + 存 assistant 消息
└─ yield done {session_id, turn_id}
```

异常分支：`cancelled` / `error`，并 `_finalize_interrupted_turn(...)` 落库（含中止时保留未完成步骤，支持「继续」恢复）。

### 2.4 多轮上下文与断点续跑

- **上下文裁剪**：`_prepare_conversation_context` 按 `max_context_tokens` 预算选择最近消息；超出部分交给 `agent.summarize_conversation` 增量压缩为摘要，存 `summary_repo`。
- **产物复用**：`_turn_to_artifact` 把上一轮 `MultiAgentTurn` 的 `plan/results/step_statuses/final_answer` 等快照传给本轮 `previous_artifacts`。
- **断点续跑**：MainAgent 的 `analyze_node` 输出 `intent=continue_task` + `reuse_previous_artifacts=true` 时，`_resume_previous_plan` 从上一次 `cancelled/failed` 轮次恢复未完成步骤。

### 2.5 热更新 reconfigure()

```
reconfigure(*, sub_agent_registry, model_kwargs):
    self._registry = sub_agent_registry
    self._model_kwargs = dict(model_kwargs)
    self._retired_agents += 旧的 _agents
    self._agents = {}            # 下次请求用新配置重建 MainAgent
```

退役的旧 MainAgent 在 `close_all` 时统一 `aclose()`（异步关闭 SQLite 连接）。

---

## 3. 编排引擎 — MainAgent

**文件:** [src/agents/multi_agent/main_agent.py](src/agents/multi_agent/main_agent.py)

### 3.1 初始化

`_setup()` → `self.model = get_model(**self._model_kwargs)`（动态模型配置在此落地）；`ainitialize()` 在 `store_type="sqlite"` 时用 `AsyncSqliteSaver` / `AsyncSqliteStore`（aiosqlite）。

### 3.2 LangGraph 状态图（异步）

```
                    ┌─────────┐
                    │ analyze │  ← 入口
                    └────┬────┘
                after_analyze(state)
                 /             \
      needs_subagents=False    needs_subagents=True / 可续跑
               │                      │
               ▼                      ▼
        ┌─────────┐            ┌──────────┐
        │ respond │            │   plan   │
        └────┬────┘            └────┬─────┘
             │                      │
             │                      ▼
             │               ┌───────────┐
             │               │  execute  │ ← 内部按步骤重试
             │               └─────┬─────┘
             │        after_execute(state)
             │         /             \
             │    还有步骤(重试)    全部完成
             │         │              │
             │         ▼              ▼
             │    ┌─────────┐   ┌────────────┐
             │    │ execute │   │ synthesize │
             │    │(循环)   │   └─────┬──────┘
             │    └─────────┘         │
             │                        ▼
             ▼                       END
           END
```

无 `replan` 节点——步骤失败在 `execute_node` 内部按 `_max_step_retries`（默认 2）重试同一执行步骤，重试耗尽则带着失败继续下一步。

### 3.3 五个节点详解

#### analyze_node — 任务分析 + 意图识别

输入 `state.current_input`（本轮用户输入）+ 历史上下文。调用 `analyze_user_task(...)` 注入 L2 分析模板，`with_structured_output(TaskAnalysisOutput)` 输出：

- `intent`（chat/new_task/follow_up/revise_task/continue_task）
- `resolved_task`（上下文消解后的可执行任务）
- `referenced_turn_ids` / `reuse_previous_artifacts`
- `needs_subagents` / `task_summary` / `complexity` / `suggested_approach`

`user_task` 被更新为 `resolved_task`。

#### after_analyze — 路由

可续跑（`_resume_previous_plan` 非空）→ `plan`；`needs_subagents=True` → `plan`；否则 → `respond`。

#### respond_node — 简单任务直接回答

`self.model.ainvoke(_build_context_messages(...))`，返回 `synthesized_answer` + `synthesis_confidence="high"`。

#### plan_node — 生成执行计划

`match_subagents(...)` → `with_structured_output(SubagentMatchOutput)` → `plan[]`（`step_id/description/subagent_type/input_summary/depends_on`）。校验 `subagent_type` 必须已注册。**可续跑时直接 `_resume_previous_plan` 返回旧计划**。

#### execute_node — 逐步骤调度

每个步骤：
- `subagent_type == None` → MainAgent 直接 `self.model.ainvoke`；
- 否则 `sub = await _get_or_create_subagent(type)` → `await sub.arun(delegation_task, context=..., cancellation_event=...)`。

> 注意：当前调用的是 `sub.arun()`（**非流式**），因此 SubAgent 内部的 `subagent_*`/`tool_call` 等事件**不会**回传（见 §7 说明）。

失败重试：`step_retry_counts` 记录每步骤失败次数，≤`_max_step_retries` 则 `current_step_index` 不回退（原地重试），否则 `+1` 继续。

#### synthesize_node — 综合结果

`aggregate_results(...)` → `with_structured_output(AggregationOutput)` → `{answer, sources, confidence}`。

### 3.4 上下文消息构造

`_build_context_messages`：`SystemMessage(主提示)` →（可选）较早摘要 → 最近对话上下文（user/assistant）→（可选）相关历史成果 → 当前指令。**只注入用户可见对话，不注入编排内部消息**。

### 3.5 结构化输出重试

`_ainvoke_structured`：`include_raw=True`，解析失败（空/校验错）最多重试 `_max_structured_retries`（默认 1）次；请求类异常（鉴权/限流/网络）不吞、直接抛出。

---

## 4. 执行引擎 — SubAgent

**文件:** [src/agents/multi_agent/sub_agent.py](src/agents/multi_agent/sub_agent.py)

### 4.1 工具注册（隔离）

`_setup()` 创建独立 `ToolRegistry`：

| 层 | 来源 | 说明 |
|---|---|---|
| L1 | `BUILTIN_TOOLS` | 内置通用工具（如 `get_current_time`） |
| L4 | `api_tools` | 本 subagent 专属 API 工具（Tavily / 遥感） |
| MCP | `mcp_tools` | 外部 MCP Server 发现的工具（async-only） |

`mcp_tools` 由 factory 注入（`create_default_registry` 按 `subagents` 字段过滤），MainAgent 不再覆盖。

### 4.2 LangGraph 状态图（异步）

```
      ┌──────┐
      │ plan │ ← 入口（分解任务为子步骤）
      └──┬───┘
         ▼
      ┌───────┐   ┌───────┐   ┌──────────────┐
      │ agent │ → │ tools │ → │ advance_step │   （每个子步骤原子执行）
      └───┬───┘   └───────┘   └──────┬───────┘
          │ 无 tool_calls → advance   │
          └──────────────────────────┘
                 after_advance_step: 还有步骤? → agent | 否则 → evaluate
      ┌──────────┐
      │ evaluate │ ← 自评
      └────┬─────┘
    after_evaluate: needs_revision 且 <3 次 → plan | 否则 → report
      ┌────────┐
      │ report │ ← 格式化最终结果
      └────┬───┘
          END
```

关键点：

- `agent_node`：`model_with_tools = self.model.bind_tools(tools)`；首个进入时注入步骤指令（`build_subagent_step_prompt`）。
- `tools_node`：`ToolNode(tools).ainvoke(...)` → MCP 工具在此异步执行。
- `tools → advance_step` 直接推进（不是 tools→agent 循环），避免同一步骤重复调用。
- `advance_step`：`_latest_execution_result` 提取最近有用输出存入 `step_results`，`current_step_index+1`。
- `evaluate_node`：`evaluate_result(...)` → `EvaluationOutput{needs_revision, feedback, ...}`。
- `report_node`：按 step_id 排序拼接 `final_result`。

---

## 5. 模型注入链路（动态 LLM）

**文件:** [src/models/llm.py](src/models/llm.py)

`get_model()` 签名已扩展：

```python
get_model(provider="auto", temperature=0.3, api_key=None, base_url=None, **kwargs)
```

- `provider`：`auto` 时先读 `LLM_PROVIDER` 环境变量，再按 `openai → deepseek → anthropic` 检测。
- `api_key`：**运行时 Key 优先**，缺省回退 `os.getenv(env_key)`。
- `base_url`：运行时地址优先，缺省用 `PROVIDER_CONFIG[provider]["base_url"]`。

注入链路：

```
RuntimeConfigService.model_config (dict)
  → ChatService(model_kwargs=...) / MultiAgentService(model_kwargs=...)
      → MainAgent(model_kwargs=...)           → get_model(**kwargs)
      → create_default_registry(model_kwargs=...) → SubAgent(model_kwargs=...) → get_model(**kwargs)
```

`model_config` 形如：`{"provider": "deepseek", "model": "deepseek-chat", "api_key": "sk-...", "base_url": "...", "temperature": 0.3, ...}`。

---

## 6. MCP 工具发现与注入（运行时）

**文件:** [src/tools/mcp/](src/tools/mcp/) + [src/server/services/runtime_config_service.py](src/server/services/runtime_config_service.py)

MCP 配置现在存于 **运行时配置库**（`RuntimeConfigRecord`，`category="mcp"`，payload 为加密的 `McpServerConfig`），不再直接依赖 `mcp.json`（仅作启动种子）。

```
RuntimeConfigService._reload_mcp()
  ├─ 读所有 category=mcp 记录 → 解密 payload → McpServerConfig 列表
  ├─ McpAdapter(McpConfig(enabled=any(...), servers=...))
  ├─ await adapter.discover()
  │     ├─ 对每个 enabled server: connect() → list_tools() → to_langchain_tool()
  │     ├─ 每个工具命名空间 {server}_{tool}，meta 带 subagents 字段
  │     └─ 记录 server_statuses（connected/error/disabled + tool_count）
  ├─ 更新每个 server 的 status/last_error/tool_count（写回 DB）
  └─ self._registry = create_default_registry(
          mcp_tools=tools, mcp_tools_meta=metas, model_kwargs=model_config)
```

`create_default_registry` 用 `_filter_mcp` 按 server 的 `subagents` 字段，把工具分配到 `general_assistant` / `remote_sensing` 的 factory，再随 `SubAgent._setup()` 注册进各自 ToolRegistry。

---

## 7. SSE 事件流

### 7.1 事件词汇表（定义于 [events.py](src/agents/multi_agent/events.py)）

生命周期：`start` / `turn_started` / `done` / `cancelled`
主智能体：`analyzing` / `analysis_done` / `status` / `plan_created` / `dispatching` / `synthesizing` / `synthesis_done`
子智能体：`subagent_start` / `subagent_plan` / `subagent_step` / `subagent_progress` / `subagent_done`
工具/文本：`tool_call` / `tool_result` / `token`
错误：`error`

### 7.2 当前链路**实际发射**的事件序列

**复杂任务（needs_subagents=true）：**

```
start → turn_started → analyzing → status(plan) → dispatching
      → [execute 内部 sub.arun() 静默执行]
      → synthesizing → synthesis_done → done
```

**简单任务（needs_subagents=false）：**

```
start → turn_started → analyzing → token(respond, agent=main) → status(respond)
      → synthesis_done → done
```

**中止 / 失败：** 最后以 `cancelled` 或 `error` 结尾（替代 `done`）。

### 7.3 定义但当前未发射的事件

`analysis_done`、`plan_created`、`subagent_*`、`tool_call`、`tool_result` 已定义、前端也已预留处理，但当前代码**不会发射**，原因是：

- `execute_node` 调用的是 `sub.arun()`（非 `sub.arun_stream()`），SubAgent 的流式事件（`subagent_plan/subagent_step/subagent_done/token`）不会回传；
- MainAgent `arun_stream` 只发射节点过渡事件（`_node_to_event` 把 plan/respond 映射为 `status`，execute→`dispatching`，synthesize→`synthesizing`）+ `synthesis_done` + `done`。

> 若要让编排过程更细粒度可见（子智能体进度、工具调用），需要把 `execute_node` 的 `sub.arun()` 换成 `sub.arun_stream()` 并转发其事件——当前是刻意简化为「子智能体内部不逐事件回传」。

### 7.4 前端消费（[MultiAgentView.vue](front/src/views/MultiAgentView.vue)）

- `start` → 记录 `session_id`；`turn_started` → 记录 `turn_id`；
- `token` / `synthesis_done` → 最终交付面板；其余事件进「执行追踪」时间线；
- `done`/`error` 视为终结事件，随后 `getMessages` 拉取完整历史。

---

## 8. 动态配置（LLM + MCP）全链路

**核心文件:** [src/server/services/runtime_config_service.py](src/server/services/runtime_config_service.py)、[src/server/api/runtime_config.py](src/server/api/runtime_config.py)、[src/server/services/secret_cipher.py](src/server/services/secret_cipher.py)、[src/server/repositories/base.py](src/server/repositories/base.py)

### 8.1 持久化与加密

- 存储：`RuntimeConfigRecord`（`config_id / category / name / enabled / payload / revision / status / last_error`），SQLite 走 `SqliteRuntimeConfigRepo`，内存走 `InMemoryRuntimeConfigRepo`。
- 加密：`SecretCipher`（Fernet）加密 `payload`。密钥来源：`CONFIG_ENCRYPTION_KEY` 环境变量，否则在数据目录生成 `.runtime-config.key`（0600）。内存仓库用临时密钥。
- 脱敏：读取接口不返回明文——`api_key_hint`（`sk-***xxxx` 尾部提示）、`env`/`headers` 显示为 `••••••••`。

### 8.2 启动初始化（lifespan）

```
runtime_config_service = RuntimeConfigService(
    repository=RuntimeConfigRepo, cipher=SecretCipher, mcp_adapter_factory=McpAdapter)
await runtime_config_service.initialize(load_mcp_config(MCP_CONFIG_PATH))
   ├─ _seed_llm_from_environment(): DB 无 LLM 记录 → 从 .env 种子（LLM_PROVIDER/LLM_MODEL/LLM_BASE_URL/对应 API Key）
   ├─ _seed_mcp_from_file(mcp_cfg):     DB 无 MCP 记录 → 从 mcp.json 种子
   ├─ _load_llm_config():              读 LLM 记录 → self._model_config
   └─ _reload_mcp():                   读 MCP 记录 → discover → 建 registry
```

随后 `ChatService(model_kwargs=model_config)`、`MultiAgentService(sub_agent_registry=registry, model_kwargs=model_config)`，并 `bind_services(chat_service, multi_agent_service)`。

### 8.3 Admin API（`/api/v1/admin/config`，`require_admin`）

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/llm` | 读当前模型配置（脱敏） |
| PUT | `/llm` | 保存模型配置（探测→加密入库→热更新） |
| POST | `/llm/test` | 测试模型连接（不保存） |
| GET | `/mcp` | 列出 MCP 服务 |
| POST | `/mcp` | 新增 MCP（校验→入库→重载） |
| PUT | `/mcp/{id}` | 更新 MCP |
| PATCH | `/mcp/{id}/enabled` | 启停单个 MCP |
| POST | `/mcp/{id}/test` | 测试单个 MCP 连接 |
| DELETE | `/mcp/{id}` | 删除 MCP |

### 8.4 模型热更新流程（PUT `/llm`）

```
save_llm(values)
  ├─ 锁；读现有 payload；api_key 留空则复用旧 Key
  ├─ 校验 provider；组装 payload；_create_model() + _probe_model()（30s 探测）
  ├─ 加密 upsert 记录（status=active）
  ├─ self._model_config = _to_model_kwargs(payload)
  └─ _publish_model_change()
        ├─ 重建 registry（create_default_registry 带新 model_kwargs）
        ├─ chat_service.reconfigure_model(model_config)
        └─ multi_agent_service.reconfigure(registry, model_kwargs)
              └→ 退役旧 MainAgent、清空 _agents，下次请求用新模型重建
```

### 8.5 MCP 热更新流程（POST/PUT/PATCH/DELETE `/mcp`）

```
create/update/set_enabled/delete_mcp
  ├─ 锁；校验（名称唯一、stdio 需 command、http 需 url）
  ├─ 加密 upsert（enabled 时 status="applying"）
  └─ _reload_mcp_and_publish()
        ├─ _reload_mcp()（§6：重连→发现→更新 server 状态→换 registry）
        └─ multi_agent_service.reconfigure(registry, model_kwargs)
```

- 失败不阻断：单个 server 连接失败只标记 `status=error` + `last_error`，其余继续。
- 旧 `McpAdapter` 进入 `_retired_mcp_adapters`，在 `close()` 统一关闭子进程/连接。

### 8.6 前端配置页

[SettingsView.vue](front/src/views/SettingsView.vue)（`/settings`，`adminOnly`）：

- 「模型配置」：provider 下拉 / 模型名 / API Key（脱敏回显）/ Base URL / temperature / max_tokens，支持「测试连接」与「保存并应用」。
- 「MCP 服务」：列表（状态徽标 + 工具数）、启停开关、测试、编辑/新增/删除（支持 stdio 的 command/args/env 与 streamable-http 的 url/headers，以及 `subagents`/`allowed_tools` 分配）。

保存后**新请求立即使用最新配置**，无需重启（reconfigure 使旧 agent 退役，下次请求重建）。

---

## 9. 关键数据结构

### 9.1 MainAgentState（[states.py](src/agents/multi_agent/states.py)）

| 字段 | 说明 |
|---|---|
| `turn_id` / `current_input` | 本轮标识 / 原始输入 |
| `conversation_context` / `conversation_summary` | 历史对话 + 摘要 |
| `previous_artifacts` | 上几轮产物快照 |
| `resolved_task` / `intent` / `referenced_turn_ids` / `reuse_previous_artifacts` | 意图与上下文消解 |
| `needs_subagents` / `task_summary` | 分析结果 |
| `plan` / `plan_raw` / `current_step_index` | 计划 |
| `subagent_results` / `subagent_statuses` / `step_retry_counts` | 执行状态 |
| `synthesized_answer` / `synthesis_sources` / `synthesis_confidence` | 综合结果 |

### 9.2 存储记录（[repositories/base.py](src/server/repositories/base.py)）

| 记录 | 用途 |
|---|---|
| `SessionMessage` | 用户可见对话（role=user/assistant） |
| `MultiAgentTurn` | 每轮编排快照（intent/resolved_task/plan/results/step_statuses/sources/resume_step/final_answer/status） |
| `ConversationSummary` | 会话历史摘要（含 covered_message_count） |
| `RuntimeConfigRecord` | 运行时配置（llm / mcp） |

---

## 10. 关键文件索引

| 文件 | 职责 |
|---|---|
| [src/server/api/multi_agent.py](src/server/api/multi_agent.py) | SSE 路由、会话校验、取消 |
| [src/server/services/multi_agent_service.py](src/server/services/multi_agent_service.py) | 服务包装、多轮上下文、Turn 落库、reconfigure |
| [src/agents/multi_agent/main_agent.py](src/agents/multi_agent/main_agent.py) | 编排图（analyze/plan/execute/synthesize） |
| [src/agents/multi_agent/sub_agent.py](src/agents/multi_agent/sub_agent.py) | 子执行器（Plan-and-Solve + 工具） |
| [src/agents/multi_agent/__init__.py](src/agents/multi_agent/__init__.py) | `create_default_registry`（MCP 过滤 + model_kwargs） |
| [src/models/llm.py](src/models/llm.py) | `get_model`（provider/api_key/base_url 运行时注入） |
| [src/server/services/runtime_config_service.py](src/server/services/runtime_config_service.py) | 动态配置中心（LLM + MCP 热更新） |
| [src/server/api/runtime_config.py](src/server/api/runtime_config.py) | `/admin/config` 管理接口 |
| [src/server/services/secret_cipher.py](src/server/services/secret_cipher.py) | 配置密钥加密 |
| [src/tools/mcp/](src/tools/mcp/) | MCP 配置/传输/连接/发现/转换 |
| [src/server/main.py](src/server/main.py) | lifespan 装配与热更新接线 |
| [front/src/views/MultiAgentView.vue](front/src/views/MultiAgentView.vue) | SSE 消费前端 |
| [front/src/views/SettingsView.vue](front/src/views/SettingsView.vue) | 动态配置前端 |
