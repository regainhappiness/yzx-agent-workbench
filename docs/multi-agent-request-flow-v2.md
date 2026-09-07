# Multi-Agent 请求全链路梳理（v2 · 工作区模式 + 事件透传）

从 `POST /api/v1/multi-agent/chat/stream` 发起请求到返回完整 SSE 事件流的全链路。

> 本文基于**当前实际实现**重写，覆盖与 v1 文档相比的几个结构性变更：
> 1. **强制工作区**：请求必须携带已配置工作区的 `session_id`，否则直接 409；
> 2. **文件作用域沙箱**：本轮执行被绑定到一个 `ExecutionFileScope`，MCP 工具据此执行只读/读写权限校验；
> 3. **资源上下文注入**：工作区路径与附件清单以可信 SystemMessage 注入 MainAgent 并透传给 SubAgent；
> 4. **事件透传机制重写**：从“节点序列推断事件”改为 **ContextVar 事件汇（event sink）**，SubAgent 内层图与 ToolNode 的事件现在能真正透传到 SSE；
> 5. **SubAgent 出厂类型调整**：`general_assistant` / `workspace_file_agent` / `vision_agent`。
>
> 关联文档：[mcp-tool-discovery-flow.md](mcp-tool-discovery-flow.md)（MCP 工具发现细节）。

---

## 0. 总览（一图流）

```
浏览器 (MultiAgentView.vue)
   │  POST /api/v1/multi-agent/chat/stream
   │     {query, session_id(必填), attachment_ids[]}
   ▼
FastAPI API 层 (api/multi_agent.py)
   │  Auth → 会话校验 → 工作区校验(409) → EventSourceResponse
   ▼
MultiAgentService.chat_stream()  (services/multi_agent_service.py)
   │  1. 取/建 MainAgent(按 user 缓存)
   │  2. 工作区/附件校验 + 建 ExecutionFileScope
   │  3. set_file_scope(scope) —— 本轮文件权限生效
   │  4. 组装多轮上下文(历史+摘要+上轮产物) → 建 Turn → turn_started
   │  5. agent.arun_stream() 逐事件转发
   ▼
MainAgent (agents/multi_agent/main_agent.py) — LangGraph
   │  analyze → (respond | plan → execute → synthesize)
   │  set_agent_event_sink(enqueue) —— 事件汇绑定到本次流
   │  execute 内按需 sub.arun() 调度 SubAgent
   ▼
SubAgent (agents/multi_agent/sub_agent.py) — LangGraph Plan-and-Solve
   │  plan → agent → (tools→advance_step) → evaluate → report
   │  通过同一 ContextVar 事件汇把子级事件透传到 MainAgent 流
   ▼
模型 get_model()  +  MCP 工具（运行时配置 + ExecutionFileScope 权限门控）
```

配置来源：**SQLite 运行时配置**（`RuntimeConfigService`）为运行期唯一真相，`.env` / `mcp.json` 仅作启动种子。

关键机制：**事件透传不再依赖 `_node_to_event` 节点推断**。`MainAgent.arun_stream()` 在 `produce_events` 任务内先 `set_agent_event_sink()`，随后整个 LangGraph（含嵌套的 SubAgent 图与 ToolNode）通过 `emit_agent_event()` 把事件写入该汇；ContextVar 随任务继承，因此子级事件天然被收集到同一个流中。

---

## 1. 请求入口 — API 层

**文件:** [src/server/api/multi_agent.py](src/server/api/multi_agent.py)

```
POST /api/v1/multi-agent/chat/stream
Body:    { "query": "帮我分析销售数据",
          "session_id": "必填且已配置工作区",
          "attachment_ids": ["本轮引用的会话附件 id", ...] }
Headers: Authorization: Bearer sk-xxx
```

处理步骤：

1. **认证**：`AuthMiddleware` 提取 Bearer token → `request.state.user_id / role`；`get_identity` 组装成 `Identity`。
2. **会话强校验**（注意与 v1 不同）：`session_id` 为空 → **直接抛 `WORKSPACE_REQUIRED`(409)**，不再自动建会话；
   - `session_service.require_session(user_id, session_id, "multi_agent")` 校验存在与所有权；
   - `workspace_service.require_workspace(user_id, session_id)` 校验该会话已配置工作区。
3. **SSE 生成器 `event_generator()`**（由 `EventSourceResponse` 包装）：
   - 先 `yield start`（含 `session_id`）；
   - 逐条转发 `multi_agent_service.chat_stream(...)` 的事件；转发前检查 `request.is_disconnected()`，断连则 `cancel_run(_make_tid(...))` 并返回；
   - 记录是否已发过事件 `done`（`terminal_sent`）；
   - `GeneratorExit / CancelledError` → 同样 `cancel_run` 后 `raise`；
   - 其它异常 → `yield error`(`AGENT_ERROR`)；
   - 结尾若客户端仍在线且未发过 `done`，补发 `yield done`。

4. **取消端点**：`POST /multi-agent/chat/{session_id}/cancel` 调 `multi_agent_service.cancel_run(tid)`，返回 `{cancelled: bool}`。

---

## 2. 服务层 — MultiAgentService

**文件:** [src/server/services/multi_agent_service.py](src/server/services/multi_agent_service.py)

### 2.1 构造与注入

构造时注入（见 [main.py](src/server/main.py) lifespan）：

- `sub_agent_registry`：来自 `RuntimeConfigService.registry`（含运行时 MCP 工具 + 出厂三个 SubAgent 的 factory + `model_kwargs`）；
- `model_kwargs`：`RuntimeConfigService.model_config`；
- `MessageRepo / TurnRepo / SummaryRepo`：多轮会话持久化；
- `session_service`、`workspace_service`（新增）；
- `max_context_tokens`（默认 6000）、`max_history_turns`（默认 10）。

### 2.2 Agent / 会话锁 / 取消表

- `_get_or_create_agent(user_id)` 按 user 缓存 `MainAgent`，`store_type` 为 sqlite 时按 user 派生独立 DB（`_sqlite_path_for_user`）。
- `_session_locks[tid]`：同一会话 `asyncio.Lock` 串行，避免 checkpoint 写竞争。
- `_active_runs[tid]`：`asyncio.Event`，供 `cancel_run()` 协作取消。
- `tid = _make_tid(user_id, session_id) = "ma:v2:{user_id}:{session_id}"`。

### 2.3 chat_stream() 执行流程

```
chat_stream(user_id, session_id, query, attachment_ids)
│
├─ agent = await _get_or_create_agent(user_id)
├─ tid = _make_tid(user_id, session_id)
├─ async with session_lock(tid):                      # 同一会话串行
│   ├─ 工作区/附件（有 workspace_service 时）:
│   │   ├─ await workspace_service.require_workspace(...)
│   │   ├─ current_attachments = await validate_attachments(user_id, session_id, attachment_ids)
│   │   ├─ resource_context    = await build_resource_context(...)     # 可信资源清单文本
│   │   └─ execution_scope     = await execution_scope(...)            # ExecutionFileScope
│   │
│   ├─ existing_messages = message_repo.list_by_session(session_id)
│   ├─ summary, conversation_context = await _prepare_conversation_context(...)
│   ├─ previous_turns = turn_repo.list_by_session(session_id)
│   ├─ previous_artifacts = [最近 3 个 turn 快照]
│   ├─ 建 Turn: turn_repo.create(status="running") + 存 user 消息(带 attachments 元数据)
│   ├─ 若工作区: await bind_attachments_to_turn(attachments, turn_id)
│   ├─ _sync_message_count(session_id)
│   │
│   ├─ cancellation_event 建会话 run 项 → _active_runs[tid] = event
│   ├─ execution_scope 换成带 cancellation_event 的副本
│   ├─ scope_token = set_file_scope(execution_scope)   # ◀ 本轮文件权限生效
│   │
│   ├─ try:
│   │   ├─ yield turn_started {turn_id, session_id}
│   │   ├─ async for event in agent.arun_stream(query, thread_id=tid,
│   │   │       cancellation_event, turn_id,
│   │   │       conversation_context, conversation_summary,
│   │   │       previous_artifacts, resource_context):
│   │   │       └─ 跳过 event=="done"，其余 yield
│   │   ├─ snapshot = await agent.get_run_snapshot(tid)
│   │   ├─ await _finalize_turn(status="completed")
│   │   └─ yield done {session_id, turn_id}
│   │
│   ├─ except Cancelled/GeneratorExit:  set(cancel) → shield(_finalize_interrupted_turn(cancelled)) → raise
│   ├─ except AgentRunCancelled:        _finalize_interrupted_turn(cancelled) → yield cancelled
│   ├─ except Exception:                _finalize_interrupted_turn(failed)   → yield error(AGENT_ERROR)
│   └─ finally:
│       ├─ reset_file_scope(scope_token)               # ◀ 本轮文件权限回收
│       ├─ cancellation_event.set()  +  移除 _active_runs
```

### 2.4 文件作用域（新增关键点）

`execution_scope` 来自 `MultiAgentWorkspaceService.execution_scope()`，为 `ExecutionFileScope`：

- `workspace_root`（会话选择的工作区绝对路径）、`permission`（`read_only` / `read_write`）、`attachment_paths`（会话全部附件路径）、`cancellation_event`。
- `can_read(path)`：在工作区内**或**属于附件路径才可读；
- `can_write(path)`：仅当 `permission == "read_write"` **且**在工作区内。
- MCP 工具守卫通过 `current_file_scope()` 读取该 ContextVar 做权限门控。

> 该 scope 仅在 `chat_stream` 的 `async with` 体内通过 `set_file_scope` 生效，`finally` 中 `reset_file_scope` 回收，避免跨会话串权限。

### 2.5 多轮上下文与断点续跑

- **上下文裁剪**：`_prepare_conversation_context` 先按轮分组（`_select_recent_messages`，最多 `max_history_turns` 轮），再按 `max_context_tokens` 预算；被裁掉的较早消息交给 `agent.summarize_conversation` 增量压缩进摘要（存 `summary_repo`），否则 `_fit_messages_to_budget` 按 token 比例截断最近消息。
- **产物复用**：`_turn_to_artifact` 把上一轮 `MultiAgentTurn` 快照传给本轮 `previous_artifacts`（最近 3 轮）。
- **断点续跑**：MainAgent 的 `analyze_node` 输出 `intent=continue_task` 且 `reuse_previous_artifacts=true` 时，`plan_node` 的 `_resume_previous_plan` 从上一次 `cancelled/failed` 轮次恢复未完成步骤（`current_step_index` 定位第一个非 `success` 的步骤）。

### 2.6 热更新 reconfigure()

```
reconfigure(*, sub_agent_registry, model_kwargs):
    self._registry = sub_agent_registry
    self._model_kwargs = dict(model_kwargs)
    self._retired_agents += 旧的 _agents
    self._agents = {}            # 下次请求用新配置重建 MainAgent
```

退役的旧 MainAgent 在 `close_all` 时统一 `aclose()`（异步关闭 aiosqlite 连接）。

---

## 3. 编排引擎 — MainAgent

**文件:** [src/agents/multi_agent/main_agent.py](src/agents/multi_agent/main_agent.py)

### 3.1 初始化

`_setup()` → `self.model = get_model(**self._model_kwargs)`；`ainitialize()` 在 `store_type="sqlite"` 时用 `AsyncSqliteSaver / AsyncSqliteStore`（aiosqlite），否则 `MemorySaver + InMemoryStore`。

### 3.2 LangGraph 状态图（异步）

```
                    ┌─────────┐
                    │ analyze │  ← 入口
                    └────┬────┘
                after_analyze(state)
                 /             \
      可续跑(_resume) 或        needs_subagents=False
      needs_subagents=True             │
               │                       ▼
               ▼                 ┌─────────┐
         ┌──────────┐            │ respond │
         │   plan   │            └────┬────┘
         └────┬─────┘                 │
              │                       ▼
              ▼                      END
         ┌───────────┐
         │  execute  │ ◀─ after_execute: 还有步骤(retry) → execute | 否则 → synthesize
         └─────┬─────┘
               ▼
         ┌────────────┐
         │ synthesize │
         └─────┬──────┘
               ▼
              END
```

无独立 replan 节点——步骤失败在 `execute_node` 内部按 `_max_step_retries`（默认 2）重试同一执行步骤。

### 3.3 五个节点详解

事件全部通过 `emit_agent_event()` 写入事件汇（不在 `_node_to_event` 处发射）。

#### analyze_node — 任务分析 + 意图识别

- 首事件 `ANALYZING`（"正在分析任务..."）；
- 组装 prompt（注入会话上下文/历史摘要/上轮产物）；`resource_context` 非空时前置一条 SystemMessage；
- `_ainvoke_structured(TaskAnalysisOutput, strict=True)` 输出 `intent / resolved_task / referenced_turn_ids / reuse_previous_artifacts / needs_subagents / task_summary / complexity / suggested_subagents`；
- 完成后发射 `ANALYSIS_DONE`（含 task_summary/complexity/needs_subagents）。

#### after_analyze — 路由

`_resume_previous_plan(state)` 非空 → `plan`；`needs_subagents=True` → `plan`；否则 → `respond`。

#### respond_node — 简单任务直接回答

- 发射 `STATUS`（"正在生成回答..."）；
- `self.model.ainvoke(_build_context_messages(...))`；
- 返回 `synthesized_answer + synthesis_sources=[] + synthesis_confidence="high"`。
- 对应 token 由 `arun_stream` 的 `stream_mode="messages"` 流式输出（见 §3.5）。

#### plan_node — 生成执行计划

- 发射 `STATUS`（"正在生成执行计划..."）；可续跑时 `_resume_previous_plan` 直接返回旧计划并发射 `PLAN_CREATED`（含 `resumed_from_turn_id`）；
- 否则 `match_subagents(...)` → `_ainvoke_structured(SubagentMatchOutput)` → `plan[]`（`step_id/description/subagent_type/input_summary/depends_on`）；
- 校验：`subagent_type` 为空转为 direct 步骤；非空必须已注册（否则抛 ValueError）；
- 发射 `PLAN_CREATED`（含 plan + strategy）。

#### execute_node — 逐步骤调度

对每个 `plan[step_idx]`：

- 定位 `step_id`、`subagent_type`（`_normalize_subagent_type`），`effective_agent = subagent_type or "main"`，`attempt = retry_counts+1`；
- 依次发射 `DISPATCHING` → `SUBAGENT_START` → `SUBAGENT_STEP(running)`（均含 step_id/description/subagent_type/attempt/total_steps）；
- **direct 步骤**（`subagent_type is None`）：MainAgent `model.ainvoke` 直接处理，结果存 `results[step_id]`，`statuses="success"`；
- **subagent 步骤**：
  - `sub = await _get_or_create_subagent(subagent_type)`；
  - `context = _build_context_for_step(step, results)`（前置 `depends_on` 结果）→ 拼接 `resource_context` → 若复用上轮产物再拼 `_format_previous_artifacts`；
  - `delegation_task = build_delegation_task_prompt(...)`；
  - `result = await sub.arun(delegation_task, context=context, cancellation_event=本线程事件)`；
  - 空结果 → 抛 `SubAgentExecutionError(retryable=True)`；
  - 成功存入 `results/statuses`；
- 完成后发射 `SUBAGENT_DONE`（含 success/status/result_summary 前 400 字符）；
- **失败重试**：`retry_counts[step_id]+1`；`failure_retryable=False`（由 `SubAgentExecutionError.retryable` 决定）→ 直接推进；≤`_max_step_retries` → `current_step_index` 不回退（原地重试）；否则 `+1` 带失败继续。

> 注意：这里调用的是 `sub.arun()`（非流式），SubAgent 内部仍通过**同一 ContextVar 事件汇**把 `subagent_plan / subagent_step / tool_call / tool_result` 等透传回来（见 §4、§7）。与 v1「子事件不同传」的说法不同。

#### synthesize_node — 综合结果

- 发射 `SYNTHESIZING`；
- 把 plan 每个步骤的 `status/results` 格式化为 result_lines，`aggregate_results(...)` → `_ainvoke_structured(AggregationOutput)` → `{answer, sources, confidence}`；
- 发射 `SYNTHESIS_DONE`（含 answer/sources/confidence/turn_id）。

### 3.4 上下文消息构造

`_build_context_messages`：（System 主提示）→（resource_context SystemMessage）→（较早摘要 SystemMessage）→（最近对话 user/assistant）→（可选相关历史成果 SystemMessage）→（当前指令）。只注入用户可见对话，不注入编排内部消息。

### 3.5 arun_stream 流式实现（事件透传核心）

```
arun_stream(...):
  await ainitialize(); tid = thread_id or uuid
  若 cancellation_event: self._cancellation_events[tid] = event
  config = {configurable:{thread_id}, recursion_limit: 50}
  initial_state = _new_turn_state(...含 resource_context)

  event_queue = asyncio.Queue(); synthesis_emitted = False

  async def produce_events():
    sink_token = set_agent_event_sink(enqueue_event)     # ◀ 事件汇绑定
    try:
      async for chunk, metadata in self._graph.astream(initial_state, config, stream_mode="messages"):
        node = metadata["langgraph_node"]
        if node=="respond" and 是 AIMessage/AIMessageChunk 且有 content:
          text = _message_chunk_text(chunk.content)
          if text: enqueue(TOKEN {text, agent=main})      # respond 的 token 流式
      final = await self._graph.aget_state(config)
      answer = final.get("synthesized_answer","")
      if answer and not synthesis_emitted:                 # 兜底补发
        enqueue(SYNTHESIS_DONE {answer, sources, confidence, turn_id})
      enqueue(DONE {session_id: tid, turn_id})
    finally:
      reset_agent_event_sink(sink_token)
      queue.put(stream_closed)

  producer = create_task(produce_events())
  try:
    while True:
      e = await queue.get()
      if e is stream_closed: break
      yield e
    await producer
  finally:
    if not producer.done(): producer.cancel()
    if cancellation_event: cancellation_event.set()
    self._cancellation_events.pop(tid, None)
```

要点：

- **事件来源**：`produce_events` 任务内 `set_agent_event_sink(enqueue_event)`。整个图（含 SubAgent 嵌套图）的 `emit_agent_event` 都经此汇入队；ContextVar 任务继承保证子任务可见。
- **token 流式**：`stream_mode="messages"` 仅在 `respond` 节点把模型 token 转成 `TOKEN` 事件（`agent=main`）。SubAgent 在 execute 节点内的 token 不让 MainAgent 重复发射，而是由 SubAgent 自身 `tool_call / tool_result` 事件体现。
- **synthesis_done 幂等**：若节点已直接发射 `SYNTHESIS_DONE`，`synthesis_emitted` 置真，兜底不重复。

### 3.6 结构化输出重试

`_ainvoke_structured`：`include_raw=True`，仅解析/校验失败（`parsing_error` 或空结果）最多重试 `_max_structured_retries`（默认 1）次；请求类异常（鉴权/限流/网络）由 `ainvoke` 抛出，不当作格式失败吞掉。

---

## 4. 执行引擎 — SubAgent

**文件:** [src/agents/multi_agent/sub_agent.py](src/agents/multi_agent/sub_agent.py)

### 4.1 工具注册（隔离）

`_setup()` 创建独立 `ToolRegistry`：

| 层 | 来源 | 说明 |
|---|---|---|
| L1 | `BUILTIN_TOOLS` | 内置通用工具 |
| L4 | `api_tools` | 本 subagent 专属 API 工具（如 Tavily） |
| MCP | `mcp_tools` | 外部 MCP 工具（async-only），由 factory 按 `subagents` 字段过滤注入 |

MainAgent 不再覆盖 SubAgent 的 `_mcp_tools`（见 `_get_or_create_subagent` 注释）。

### 4.2 LangGraph 状态图（Plan-and-Solve，异步）

```
      ┌──────┐
      │ plan │ ← 入口（SUBPARENT_PLAN 事件）
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
    after_evaluate: needs_revision 且迭代<3 → plan | 否则 → report
      ┌────────┐
      │ report │ ← 格式化最终结果
      └────┬───┘
          END
```

- `plan_node`：`decompose_task(...)` → `DecompositionOutput` → `sub_plan[]`；校验每个 `tool_hint`（经 `_resolve_tool_hint` 解析）必须在可用工具名中，否则抛 `SubAgentExecutionError(retryable=False)`；发射 `SUBAGENT_PLAN`。
- `agent_node`：每步骤仅在 `react_iteration_count==0` 时注入一次 `build_subagent_step_prompt` 并发射 `SUBAGENT_STEP(running)`；若该步骤有 `tool_hint`，模型被 `bind_tools([该工具])` **限制只能调该工具**，否则抛 `SubAgentExecutionError(retryable=True)`。
- `tools_node`：`ToolNode(tools).ainvoke(...)`；对每个调用发射 `TOOL_CALL`，结果发射 `TOOL_RESULT`；`_tool_failure` 按返回文本分类 MCP 失败并映射 `retryable`；工具步骤完成后直接 `tools → advance_step`（不做 tools→agent 循环，避免同一步骤重复调用）。
- `advance_step_node`：`_latest_execution_result` 提取最近有用输出存入 `step_results`；发射 `SUBAGENT_STEP(completed)` + `SUBAGENT_PROGRESS(percent)`；`current_step_index + 1`。
- `evaluate_node`：`evaluate_result(...)` → `EvaluationOutput{needs_revision, feedback,...}`；发射 `SUBAGENT_STEP(evaluating)`。
- `report_node`：按 step_id 排序拼接 `final_result`，返回 MainAgent。

> **事件透传**：以上 `emit_agent_event` 依赖的正是 §3.5 绑定的事件汇 ContextVar。SubAgent 无论以 `arun()` 还是 `arun_stream()` 被调度，只要运行在 MainAgent 流上下文内，其子级事件都会被回传。`arun()` 本身也维护独立 `_cancellation_events` 响应取消。

---

## 5. 模型注入链路（动态 LLM）

**文件:** [src/models/llm.py](src/models/llm.py)

`get_model()` 签名：

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
      → MainAgent(model_kwargs=...)                → get_model(**kwargs)
      → create_default_registry(model_kwargs=...) → SubAgent(model_kwargs=...) → get_model(**kwargs)
```

`model_config` 形如 `{"provider": "deepseek", "model": "deepseek-chat", "api_key": "sk-...", "base_url": "...", "temperature": 0.3, ...}`。

---

## 6. MCP 工具发现注入与文件权限门控（运行时）

**文件:** [src/tools/mcp/](src/tools/mcp/)（含 [scope.py](src/tools/mcp/scope.py)）+ [src/server/services/runtime_config_service.py](src/server/services/runtime_config_service.py)

MCP 配置存于运行时配置库（`category="mcp"`，payload 加密），`mcp.json` 仅作启动种子。

```
RuntimeConfigService._reload_mcp()
  ├─ 读所有 category=mcp 记录 → 解密 → McpServerConfig 列表
  ├─ McpAdapter(McpConfig(...)) → await discover()
  │     ├─ 每 enabled server: connect() → list_tools() → to_langchain_tool()
  │     ├─ 命名空间 {server}_{tool}，meta 带 subagents / 权限字段
  │     └─ 记录 server_statuses 并写回 DB
  └─ self._registry = create_default_registry(mcp_tools=..., mcp_tools_meta=..., model_kwargs=...)
```

- `create_default_registry._filter_mcp` 按 meta 的 `subagents` 字段把工具分配到 `general_assistant` / `workspace_file_agent` / `vision_agent` 的 factory，再随 `SubAgent._setup()` 注册。
- **权限门控**：MCP 工具在执⾏文件类操作时调用 `current_file_scope()` 读取 `ExecutionFileScope`，命中 `can_read / can_write` 才放行，否则返回 `[MCP] 权限校验失败: ...`（SubAgent 将其判为 `retryable=False`）。

---

## 7. SSE 事件流

### 7.1 事件词汇表（定义于 [events.py](src/agents/multi_agent/events.py)）

生命周期：`start` / `turn_started` / `done` / `cancelled`
主智能体：`analyzing` / `analysis_done` / `status` / `plan_created` / `dispatching` / `synthesizing` / `synthesis_done`
子智能体：`subagent_start` / `subagent_plan` / `subagent_step` / `subagent_progress` / `subagent_done`
工具/文本：`tool_call` / `tool_result` / `token`
错误：`error`

### 7.2 当前链路实际发射的事件序列

**复杂任务（needs_subagents=true，含 SubAgent 内层事件透传）：**

```
start → turn_started
      → analyzing → analysis_done
      → status(plan) → plan_created
      → dispatching → subagent_start → subagent_step(running)
      → [sub.arun() 内层经事件会汇透传]
            subagent_plan → subagent_step(running) → tool_call → tool_result
            → subagent_step(completed) → subagent_progress → […循环…]
      → subagent_done (execute_node 收尾，每步骤一次)
      → synthesizing → synthesis_done → done
```

**简单任务（needs_subagents=false）：**

```
start → turn_started
      → analyzing → analysis_done
      → status(respond) → token(agent=main)…     # respond 模型 token 流式
      → synthesis_done → done
```

> 简单路径的 `synthesis_done` 由 `synthesis_emitted` 幂等兜底补发。

**中止 / 失败：** 最后以 `cancelled` 或 `error` 结尾（替代 `done`）。

### 7.3 事件是否发射——相对 v1 的变化

| 事件 | v1 状态 | v2 状态 |
|---|---|---|
| `analysis_done` | 未发射 | ✅ `analyze_node` 发射 |
| `plan_created` | 未发射 | ✅ `plan_node` 发射 |
| `subagent_start` / `subagent_step` | 未发射 | ✅ `execute_node` / `sub_agent` 节点发射 |
| `subagent_plan` | 未发射 | ✅ `sub_agent.plan_node` 透传 |
| `subagent_progress` | 未发射 | ✅ `sub_agent.advance_step_node` 透传 |
| `tool_call` / `tool_result` | 未发射 | ✅ `sub_agent.tools_node` 透传 |
| `token` | 仅 respond 相关？ | ✅ MainAgent `respond` 节点流式；SubAgent 内不重复 |
| MainAgent `_node_to_event` | 由它推断 | 仅保留为静态映射表，**事件不再由其发射** |

> 根因：v2 用 **ContextVar 事件汇**把整棵图（含嵌套 SubAgent）的事件统一收集，取代 v1 中 `execute_node` 静默执行 `sub.arun()` 导致子事件丢失的状况。

### 7.4 前端消费（[MultiAgentView.vue](front/src/views/MultiAgentView.vue)）

- `start` → 记录 `session_id`；`turn_started` → 记录 `turn_id`；
- `token` / `synthesis_done` → 最终交付面板；其余事件进「执行追踪」时间线（主智能体/子智能体/工具分级展示）；
- `done`/`error` 视为终结事件，随后 `getMessages` 拉取完整历史。

---

## 8. 动态配置（LLM + MCP）全链路

**核心文件:** [src/server/services/runtime_config_service.py](src/server/services/runtime_config_service.py)、[src/server/api/runtime_config.py](src/server/api/runtime_config.py)、[src/server/services/secret_cipher.py](src/server/services/secret_cipher.py)、[src/server/repositories/base.py](src/server/repositories/base.py)

### 8.1 持久化与加密

- 存储：`RuntimeConfigRecord`（`config_id / category / name / enabled / payload / revision / status / last_error`）；SQLite 走 `SqliteRuntimeConfigRepo`，内存走 `InMemoryRuntimeConfigRepo`。
- 加密：`SecretCipher`（Fernet）。密钥来自 `CONFIG_ENCRYPTION_KEY` 或数据目录 `.runtime-config.key`（0600），内存仓库用临时密钥。
- 脱敏：不返回明文——`api_key_hint`、`env/headers` 显示 `••••••••`。

### 8.2 启动初始化（lifespan）

```
runtime_config_service = RuntimeConfigService(repository, cipher, mcp_adapter_factory=McpAdapter)
await runtime_config_service.initialize(load_mcp_config(MCP_CONFIG_PATH))
   ├─ _seed_llm_from_environment()   DB 无 LLM 记录 → 从 .env 种子
   ├─ _seed_mcp_from_file(mcp_cfg)   DB 无 MCP 记录 → 从 mcp.json 种子
   ├─ _load_llm_config()             → self._model_config
   └─ _reload_mcp()                  → discover → 建 registry
```

随后 `ChatService(model_kwargs=model_config)`、`MultiAgentService(sub_agent_registry=registry, model_kwargs=model_config, workspace_service=…)`，并 `bind_services(chat_service, multi_agent_service)`。

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

- 失败不阻断：单个 server 失败仅标记 `status=error + last_error`。
- 旧 `McpAdapter` 进 `_retired_mcp_adapters`，`close()` 时关闭子进程/连接。

### 8.6 前端配置页

[SettingsView.vue](front/src/views/SettingsView.vue)（`/settings`，`adminOnly`）：

- 「模型配置」：provider 下拉 / 模型名 / API Key（脱敏回显）/ Base URL / temperature / max_tokens，支持「测试连接」与「保存并应用」。
- 「MCP 服务」：列表（状态徽标 + 工具数）、启停开关、测试、编辑/新增/删除，以及工具→SubAgent 的 `subagents` 分配。

保存后新请求立即生效（reconfigure 使旧 agent 退役，下次请求重建）。

---

## 9. 工作区 / 附件机制（v2 新增核心）

**文件:** [src/server/services/multi_agent_workspace_service.py](src/server/services/multi_agent_workspace_service.py)、[src/tools/mcp/scope.py](src/tools/mcp/scope.py)

- **工作区**：会话级配置 `root_path + permission(read_only/read_write)`，仅允许位于 `MULTI_AGENT_WORKSPACE_ROOTS` 白名单内；会话开始（message_count>0）后不可更换。附件文件存储于 `MULTI_AGENT_ATTACHMENT_DIR` 下的 `<user>/<session>/<attachment_id>-<name>`。
- **附件**：按 `attachment_ids` 校验归属与存在后绑定到本轮 turn；`build_resource_context` 汇总会话附件（标记本轮/历史、image/text/binary/pdf_office_unparsed）注入为可信上下文。
- **执行作用域**：`execution_scope()` 产出 `ExecutionFileScope`，经 `set_file_scope` 在 service 层绑定（§2.4），使工作区文件 agent 与 MCP 工具只能读写被授权的路径。
- **副作用清单**：`delete_attachment`（未发送前）、`delete_session_resources`（删除会话时清理附件文件与目录）。

---

## 10. 关键数据结构

### 10.1 MainAgentState（[states.py](src/agents/multi_agent/states.py)）

| 字段 | 说明 |
|---|---|
| `turn_id` / `current_input` | 本轮标识 / 原始输入 |
| `conversation_context` / `conversation_summary` / `resource_context` | 历史对话 / 摘要 / 工作区可信资源 |
| `previous_artifacts` / `resumed_from_turn_id` | 上几轮产物快照 / 续跑来源轮次 |
| `resolved_task` / `intent` / `referenced_turn_ids` / `reuse_previous_artifacts` | 意图与上下文消解 |
| `needs_subagents` / `task_summary` | 分析结果 |
| `plan` / `plan_raw` / `current_step_index` | 计划 |
| `subagent_results` / `subagent_statuses` / `step_retry_counts` | 执行状态与重试计数 |
| `synthesized_answer` / `synthesis_sources` / `synthesis_confidence` | 综合结果 |
| `iteration_count` | 安全计数器 |

### 10.2 存储记录（[repositories/base.py](src/server/repositories/base.py)）

| 记录 | 用途 |
|---|---|
| `SessionMessage` | 用户可见对话（role=user/assistant，assistant 带 sources/confidence 元数据） |
| `MultiAgentTurn` | 每轮编排快照（intent/resolved_task/plan/results/step_statuses/sources/resume_step/final_answer/status） |
| `ConversationSummary` | 会话历史摘要（含 covered_message_count） |
| `RuntimeConfigRecord` | 运行时配置（llm / mcp） |
| `MultiAgentWorkspace` | 会话工作区（root_path + permission） |
| `MultiAgentAttachment` | 会话附件（storage_path/mime_type/file_hash/turn_id） |

### 10.3 事件汇 / 文件作用域 ContextVar

| 名字 | 位置 | 作用 |
|---|---|---|
| `_agent_event_sink` | [events.py](src/agents/multi_agent/events.py) | 当前流要转发到的事件回调；`emit_agent_event` 读取 |
| `_CURRENT_FILE_SCOPE` | [scope.py](src/tools/mcp/scope.py) | 当前执行的 `ExecutionFileScope`；MCP 权限门控读取 |

---

## 11. 关键文件索引

| 文件 | 职责 |
|---|---|
| [src/server/api/multi_agent.py](src/server/api/multi_agent.py) | SSE 路由、会话+工作区校验、断连取消 |
| [src/server/services/multi_agent_service.py](src/server/services/multi_agent_service.py) | 服务包装、文件作用域绑定、多轮上下文、Turn 落库、reconfigure |
| [src/server/services/multi_agent_workspace_service.py](src/server/services/multi_agent_workspace_service.py) | 工作区/附件/执行作用域/资源上下文 |
| [src/tools/mcp/scope.py](src/tools/mcp/scope.py) | `ExecutionFileScope` + 文件权限 ContextVar |
| [src/agents/multi_agent/main_agent.py](src/agents/multi_agent/main_agent.py) | 编排图 + 事件汇绑定 + token 流式 |
| [src/agents/multi_agent/sub_agent.py](src/agents/multi_agent/sub_agent.py) | 子执行器（Plan-and-Solve + 工具 + 事件透传） |
| [src/agents/multi_agent/events.py](src/agents/multi_agent/events.py) | 事件常量 + 事件汇 ContextVar |
| [src/agents/multi_agent/__init__.py](src/agents/multi_agent/__init__.py) | `create_default_registry`（MCP 过滤 + model_kwargs + 出厂 SubAgent） |
| [src/agents/multi_agent/sub_agent_registry.py](src/agents/multi_agent/sub_agent_registry.py) | SubAgent 注册中心（prompt 选择 / 实例化） |
| [src/agents/multi_agent/states.py](src/agents/multi_agent/states.py) | MainAgentState / SubAgentState |
| [src/models/llm.py](src/models/llm.py) | `get_model`（provider/api_key/base_url 运行时注入） |
| [src/server/services/runtime_config_service.py](src/server/services/runtime_config_service.py) | 动态配置中心（LLM + MCP 热更新） |
| [src/server/api/runtime_config.py](src/server/api/runtime_config.py) | `/admin/config` 管理接口 |
| [src/server/services/secret_cipher.py](src/server/services/secret_cipher.py) | 配置密钥加密 |
| [src/tools/mcp/](src/tools/mcp/) | MCP 配置/传输/连接/发现/转换/权限 |
| [src/server/main.py](src/server/main.py) | lifespan 装配与热更新接线 |
| [front/src/views/MultiAgentView.vue](front/src/views/MultiAgentView.vue) | SSE 消费前端 |
| [front/src/views/SettingsView.vue](front/src/views/SettingsView.vue) | 动态配置前端 |
