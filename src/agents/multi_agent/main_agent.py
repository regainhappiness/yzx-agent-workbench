"""
===========================================================================
MainAgent — 层级多智能体编排器（异步）
===========================================================================

基于 LangGraph 的编排器, 负责:
  1. analyze:   分析用户任务, 判断是否需要 subagent
  2. plan:      生成执行计划 (选择 subagent + 步骤排序)
  3. execute:   逐步骤调度 subagent, 收集结果
  4. synthesize: 综合 subagent 结果 → 最终回答
  5. retry:     步骤失败时回到当前执行步骤重试

与 SubAgent 的关系:
  MainAgent 通过 SubAgentRegistry 发现可用 subagent,
  按需实例化, 通过 await subagent.arun() 委托任务。

流式输出:
  每个节点过渡时 yield SSE event, 支持分级展示进度。

使用:
    registry = SubAgentRegistry()
    main = MainAgent(sub_agent_registry=registry)
    await main.ainitialize()
    answer = await main.arun("帮我分析销售数据并生成报告")
===========================================================================
"""

import asyncio
import sqlite3
import uuid
from contextlib import suppress
from pathlib import Path
from typing import AsyncGenerator

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
)
from langchain_core.runnables import RunnableConfig

from ..base import BaseAgent
from ...models.llm import get_model, CAN_RUN
from ...tools.registry import ToolRegistry
from ...tools.base import BUILTIN_TOOLS, BUILTIN_TOOLS_META
from ...tools.general import GENERAL_TOOLS
from ...tools.multi_agent_planning.task_analyzer import (
    analyze_user_task, TaskAnalysisOutput,
)
from ...tools.multi_agent_planning.subagent_matcher import (
    match_subagents, build_selection_context, SubagentMatchOutput,
)
from ...tools.multi_agent_planning.result_aggregator import (
    aggregate_results, AggregationOutput,
)
from .sub_agent_registry import SubAgentRegistry
from .sub_agent import SubAgent
from .states import MainAgentState
from .events import (
    AgentRunCancelled,
    MultiAgentEvent,
    SubAgentExecutionError,
    emit_agent_event,
    reset_agent_event_sink,
    set_agent_event_sink,
)
from ...utils.logger import get_logger
from ...prompt import (
    MAIN_AGENT_SYSTEM_PROMPT,
    build_delegation_task_prompt,
    build_direct_response_prompt,
    build_direct_step_prompt,
    build_structured_output_retry_prompt,
)


GRAPH_RECURSION_LIMIT = 50


# ═══════════════════════════════════════════════════════════════════════
# MainAgent
# ═══════════════════════════════════════════════════════════════════════

class MainAgent(BaseAgent):
    """层级多智能体编排器

    参数:
        name:                   Agent 名称
        sub_agent_registry:     SubAgent 注册中心
        model_kwargs:           传递给 get_model() 的参数
        store_type:             存储类型: "memory" | "sqlite"
        sqlite_path:            SQLite 路径
        max_step_retries:       单个执行步骤的最大重试次数 (默认 2)
        max_replans:            max_step_retries 的兼容别名
        max_structured_retries: 结构化输出解析失败后的额外重试次数 (默认 1)
        mcp_tools:              外部 MCP 工具列表 (透传给 SubAgent)
    """

    def __init__(
        self,
        name: str = "MainAgent",
        sub_agent_registry: SubAgentRegistry | None = None,
        model_kwargs: dict | None = None,
        store_type: str = "memory",
        sqlite_path: str | None = None,
        max_step_retries: int = 2,
        max_replans: int | None = None,
        max_structured_retries: int = 1,
        mcp_tools: list | None = None,
        mcp_tools_meta: dict[str, dict] | None = None,
        **kwargs,
    ):
        super().__init__(name=name, **kwargs)
        self.sub_agent_registry = sub_agent_registry or SubAgentRegistry()
        self._model_kwargs = model_kwargs or {}
        self._store_type = store_type
        self._sqlite_path = sqlite_path
        self._mcp_tools = mcp_tools or []
        self._mcp_tools_meta = mcp_tools_meta or {}
        # Backwards-compatible alias: failures now retry the same execute step.
        self._max_step_retries = (
            max_replans if max_replans is not None else max_step_retries
        )
        self._max_structured_retries = max(0, max_structured_retries)

        # 在 _setup 中设置
        self.tool_registry: ToolRegistry | None = None
        self._graph = None
        self._checkpointer = None
        self._store = None
        self._sqlite_connections: tuple[sqlite3.Connection, ...] = ()
        self._async_connections: tuple = ()
        self._sub_agents_cache: dict[str, SubAgent] = {}
        self._cancellation_events: dict[str, asyncio.Event] = {}

    # ═══ 初始化 ═══

    def _setup(self, **kwargs):
        """初始化 MainAgent 组件 (模型 + 工具注册中心 + 图构建)"""
        logger = get_logger(f"MainAgent.{self.name}")

        # 1. 模型
        self.model = get_model(**self._model_kwargs)
        if self.model is None:
            logger.warning("无可用 LLM — MainAgent 将以降级模式运行")

        # 2. 工具注册中心 (仅 L1 通用 tools)
        self.tool_registry = ToolRegistry()
        self.tool_registry.register_with_meta(BUILTIN_TOOLS, BUILTIN_TOOLS_META)

        # 3. 构建图
        if self.model is not None:
            self._build_graph()
        else:
            logger.warning("跳过图构建 (无可用模型)")

    async def ainitialize(self):
        """异步初始化：SQLite 走异步 store，memory 走同步 MemorySaver。"""
        if self._initialized:
            return
        if self._store_type == "sqlite":
            await self._setup_async_store()
        else:
            self._checkpointer = MemorySaver()
            self._store = InMemoryStore()
        self._setup()
        self._initialized = True

    async def _setup_async_store(self):
        """SQLite 异步 checkpointer/store（aiosqlite + AsyncSqliteSaver/Store）。"""
        try:
            import aiosqlite
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
            from langgraph.store.sqlite.aio import AsyncSqliteStore
        except ImportError:
            self._checkpointer = MemorySaver()
            self._store = InMemoryStore()
            return

        db_path = Path(self._sqlite_path or "./data/main_agent.db").expanduser()
        db_path.parent.mkdir(parents=True, exist_ok=True)

        checkpointer_conn = await aiosqlite.connect(str(db_path))
        # AsyncSqliteStore.setup() 会执行迁移写入；Store 连接必须开启
        # autocommit，否则最后一条写事务会一直占用数据库写锁。
        store_conn = await aiosqlite.connect(
            str(db_path),
            isolation_level=None,
        )
        try:
            self._checkpointer = AsyncSqliteSaver(checkpointer_conn)
            await self._checkpointer.setup()
            self._store = AsyncSqliteStore(store_conn)
            await self._store.setup()
        except Exception:
            await checkpointer_conn.close()
            await store_conn.close()
            raise

        self._async_connections = (checkpointer_conn, store_conn)
        self._sqlite_path = str(db_path)

    def _build_graph(self):
        """构建编排器 LangGraph 图 (异步节点):
        analyze → (simple? → respond) → plan → execute → synthesize → END
                  execute 内部: dispatch → (fail? → retry execute)
        """

        # ── 节点定义 ──

        async def analyze_node(state: MainAgentState, config: RunnableConfig) -> dict:
            await self._check_cancelled(config)
            """分析用户任务"""
            await emit_agent_event(MultiAgentEvent.ANALYZING, {
                "agent": "main",
                "node": "analyze",
                "message": "正在分析任务...",
            })
            user_task = state.get("current_input", state.get("user_task", ""))
            subagent_list = self.sub_agent_registry.build_selection_prompt()

            prompt = analyze_user_task(
                user_task,
                subagent_list,
                conversation_context=self._format_conversation_context(
                    state.get("conversation_context", [])
                ),
                conversation_summary=state.get("conversation_summary", "")
                or "（无历史摘要）",
                previous_artifacts=self._format_previous_artifacts(
                    state.get("previous_artifacts", [])
                ),
            )
            messages = [
                SystemMessage(content=MAIN_AGENT_SYSTEM_PROMPT),
            ]
            resource_context = state.get("resource_context", "").strip()
            if resource_context:
                messages.append(SystemMessage(content=resource_context))
            messages.append(HumanMessage(content=prompt))
            response = await self._ainvoke_structured(
                TaskAnalysisOutput,
                messages,
                run_config=config,
                strict=True,
            )

            self.logger.info(
                "Analyze: needs_subagents=%s, complexity=%s, suggested=%s",
                response.needs_subagents, response.complexity,
                response.suggested_subagents,
            )
            await emit_agent_event(MultiAgentEvent.ANALYSIS_DONE, {
                "agent": "main",
                "node": "analyze",
                "task_summary": response.task_summary,
                "complexity": response.complexity,
                "needs_subagents": response.needs_subagents,
                "suggested_subagents": response.suggested_subagents,
            })
            return {
                "intent": response.intent,
                "resolved_task": response.resolved_task,
                "user_task": response.resolved_task,
                "referenced_turn_ids": response.referenced_turn_ids,
                "reuse_previous_artifacts": response.reuse_previous_artifacts,
                "needs_subagents": response.needs_subagents,
                "task_summary": response.task_summary,
                "iteration_count": 0,
            }

        async def respond_node(state: MainAgentState, config: RunnableConfig) -> dict:
            await self._check_cancelled(config)
            """简单任务直接回答"""
            await emit_agent_event(MultiAgentEvent.STATUS, {
                "agent": "main",
                "node": "respond",
                "message": "正在生成回答...",
            })
            user_task = state.get("resolved_task") or state.get("user_task", "")
            messages = self._build_context_messages(
                state, build_direct_response_prompt(user_task),
            )
            response = await self.model.ainvoke(messages)
            await self._check_cancelled(config)
            return {
                "synthesized_answer": response.content if response.content else "",
                "synthesis_sources": [],
                "synthesis_confidence": "high",
            }

        async def plan_node(state: MainAgentState, config: RunnableConfig) -> dict:
            await self._check_cancelled(config)
            """生成执行计划"""
            await emit_agent_event(MultiAgentEvent.STATUS, {
                "agent": "main",
                "node": "plan",
                "message": "正在生成执行计划...",
            })
            user_task = state.get("resolved_task") or state.get("user_task", "")
            task_summary = state.get("task_summary", "")

            resumed = self._resume_previous_plan(state)
            if resumed is not None:
                self.logger.info(
                    "Resume: turn=%s step=%d/%d",
                    resumed.get("resumed_from_turn_id"),
                    resumed["current_step_index"] + 1,
                    len(resumed["plan"]),
                )
                await emit_agent_event(MultiAgentEvent.PLAN_CREATED, {
                    "agent": "main",
                    "node": "plan",
                    "plan": resumed["plan"],
                    "strategy": resumed["plan_raw"],
                    "resumed_from_turn_id": resumed.get(
                        "resumed_from_turn_id", "",
                    ),
                })
                return resumed

            # 构建 subagent 选择上下文
            entries = self.sub_agent_registry.list_all()
            context_lines = []
            for i, meta in enumerate(entries, 1):
                context_lines.append(meta.to_prompt_line(i))
            subagent_context = build_selection_context(context_lines)

            prompt = match_subagents(user_task, task_summary, subagent_context)
            messages = self._build_context_messages(state, prompt)
            response = await self._ainvoke_structured(
                SubagentMatchOutput,
                messages,
                run_config=config,
            )

            available_types = set(self.sub_agent_registry.list_types())
            plan = []
            for step_output in response.plan:
                subagent_type = self._normalize_subagent_type(
                    step_output.subagent_type
                )
                if (
                    subagent_type is not None
                    and subagent_type not in available_types
                ):
                    raise ValueError(
                        "执行计划包含未注册的 SubAgent 类型: "
                        f"{subagent_type}"
                    )
                plan.append({
                    "step_id": step_output.step_id,
                    "description": step_output.description,
                    "subagent_type": subagent_type,
                    "input_summary": step_output.input_summary,
                    "depends_on": step_output.depends_on,
                })

            self.logger.info("Plan: %d steps — %s", len(plan), response.overall_strategy)
            await emit_agent_event(MultiAgentEvent.PLAN_CREATED, {
                "agent": "main",
                "node": "plan",
                "plan": plan,
                "strategy": response.overall_strategy,
            })
            return {
                "plan": plan,
                "plan_raw": response.overall_strategy,
                "current_step_index": 0,
                "subagent_results": {},
                "subagent_statuses": {},
                "step_retry_counts": {},
            }

        async def execute_node(state: MainAgentState, config: RunnableConfig) -> dict:
            await self._check_cancelled(config)
            """执行当前步骤 — 调度 subagent"""
            plan = state.get("plan", [])
            step_idx = state.get("current_step_index", 0)
            results = dict(state.get("subagent_results", {}))
            statuses = dict(state.get("subagent_statuses", {}))
            retry_counts = dict(state.get("step_retry_counts", {}))
            failure_retryable = True

            if step_idx >= len(plan):
                return {"subagent_results": results, "subagent_statuses": statuses}

            step = plan[step_idx]
            step_id = str(step["step_id"])
            subagent_type = self._normalize_subagent_type(
                step.get("subagent_type")
            )
            effective_agent = subagent_type or "main"
            attempt = retry_counts.get(step_id, 0) + 1

            self.logger.info("Execute step %d/%d: %s → %s",
                             step_idx + 1, len(plan), step_id, subagent_type or "direct")
            event_data = {
                "agent": "main",
                "node": "execute",
                "step_id": step_id,
                "description": step.get("description", ""),
                "subagent_type": effective_agent,
                "attempt": attempt,
                "total_steps": len(plan),
            }
            await emit_agent_event(MultiAgentEvent.DISPATCHING, event_data)
            await emit_agent_event(MultiAgentEvent.SUBAGENT_START, event_data)
            await emit_agent_event(MultiAgentEvent.SUBAGENT_STEP, {
                **event_data,
                "status": "running",
            })

            if subagent_type is None:
                # 无需 subagent — main_agent 直接处理
                task_desc = step["description"]
                prompt = build_direct_step_prompt(
                    task_desc,
                    state.get("resolved_task") or state.get("user_task", ""),
                )
                messages = self._build_context_messages(state, prompt)
                try:
                    response = await self.model.ainvoke(messages)
                    await self._check_cancelled(config)
                    results[step_id] = response.content if response else ""
                    statuses[step_id] = "success"
                except AgentRunCancelled:
                    raise
                except Exception as e:
                    self.logger.exception("MainAgent direct step %s failed", step_id)
                    results[step_id] = f"[失败] {e}"
                    statuses[step_id] = "failed"
            else:
                # 调度 subagent
                if self.sub_agent_registry.get(subagent_type) is None:
                    raise ValueError(
                        "执行计划包含未注册的 SubAgent 类型: "
                        f"{subagent_type}"
                    )
                try:
                    sub = await self._get_or_create_subagent(subagent_type)
                    context = self._build_context_for_step(step, results)
                    resource_context = state.get("resource_context", "").strip()
                    if resource_context:
                        context = "\n\n".join(
                            part for part in (resource_context, context) if part
                        )
                    if state.get("reuse_previous_artifacts"):
                        previous_context = self._format_previous_artifacts(
                            state.get("previous_artifacts", [])
                        )
                        context = "\n\n".join(
                            part for part in (previous_context, context)
                            if part and not part.startswith("（无历史")
                        )
                    delegation_task = build_delegation_task_prompt(
                        step["description"],
                        context,
                        state.get("resolved_task") or state.get("user_task", ""),
                    )
                    result = await sub.arun(
                        delegation_task,
                        context=context,
                        cancellation_event=self._cancellation_events.get(
                            config.get("configurable", {}).get("thread_id")
                        ),
                    )
                    await self._check_cancelled(config)
                    if not str(result or "").strip():
                        raise SubAgentExecutionError(
                            f"SubAgent {subagent_type} 返回了空结果",
                            retryable=True,
                        )
                    results[step_id] = result
                    statuses[step_id] = "success"
                except AgentRunCancelled:
                    raise
                except SubAgentExecutionError as e:
                    failure_retryable = e.retryable
                    self.logger.error(
                        "SubAgent execution failed: type=%s step=%s retryable=%s error=%s",
                        subagent_type, step_id, e.retryable, e,
                    )
                    results[step_id] = f"[失败] {e}"
                    statuses[step_id] = "failed"
                except Exception as e:
                    self.logger.exception(
                        "SubAgent raised unexpectedly: type=%s step=%s",
                        subagent_type, step_id,
                    )
                    results[step_id] = f"[失败] {e}"
                    statuses[step_id] = "failed"

            await emit_agent_event(MultiAgentEvent.SUBAGENT_DONE, {
                **event_data,
                "success": statuses[step_id] == "success",
                "status": statuses[step_id],
                "result_summary": str(results.get(step_id, ""))[:400],
            })

            if statuses[step_id] == "failed":
                failed_attempts = retry_counts.get(step_id, 0) + 1
                retry_counts[step_id] = failed_attempts
                if not failure_retryable:
                    next_step_idx = step_idx + 1
                    self.logger.error(
                        "Step %s has a non-retryable failure; skipping retries",
                        step_id,
                    )
                elif failed_attempts <= self._max_step_retries:
                    next_step_idx = step_idx
                    self.logger.warning(
                        "Retrying failed step %s (%d/%d)",
                        step_id,
                        failed_attempts,
                        self._max_step_retries,
                    )
                else:
                    next_step_idx = step_idx + 1
                    self.logger.error(
                        "Step %s exhausted %d retries; continuing with failure",
                        step_id,
                        self._max_step_retries,
                    )
            else:
                retry_counts.pop(step_id, None)
                next_step_idx = step_idx + 1

            return {
                "subagent_results": results,
                "subagent_statuses": statuses,
                "step_retry_counts": retry_counts,
                "current_step_index": next_step_idx,
            }

        async def synthesize_node(state: MainAgentState, config: RunnableConfig) -> dict:
            await self._check_cancelled(config)
            """综合所有 subagent 结果"""
            await emit_agent_event(MultiAgentEvent.SYNTHESIZING, {
                "agent": "main",
                "node": "synthesize",
                "message": "正在综合结果...",
            })
            user_task = state.get("resolved_task") or state.get("user_task", "")
            results = state.get("subagent_results", {})
            plan = state.get("plan", [])

            # 格式化步骤结果
            result_lines = []
            for step in plan:
                sid = str(step["step_id"])
                status = state.get("subagent_statuses", {}).get(sid, "pending")
                result_text = results.get(sid, "（无结果）")
                result_lines.append(
                    f"### 步骤 {sid}: {step['description']} "
                    f"[subagent: {step.get('subagent_type', 'direct')}] "
                    f"[状态: {status}]\n{result_text}"
                )

            prompt = aggregate_results(user_task, "\n\n".join(result_lines))
            messages = self._build_context_messages(state, prompt)
            response = await self._ainvoke_structured(
                AggregationOutput,
                messages,
                run_config=config,
            )

            self.logger.info("Synthesize: confidence=%s, sources=%s",
                             response.confidence, response.sources)
            await emit_agent_event(MultiAgentEvent.SYNTHESIS_DONE, {
                "agent": "main",
                "node": "synthesize",
                "answer": response.answer,
                "sources": response.sources,
                "confidence": response.confidence,
                "turn_id": state.get("turn_id", ""),
            })
            return {
                "synthesized_answer": response.answer,
                "synthesis_sources": response.sources,
                "synthesis_confidence": response.confidence,
            }

        # ── 路由函数 ──

        def after_analyze(state: MainAgentState) -> str:
            """分析后: 简单任务直接回答, 复杂任务进入规划"""
            if self._resume_previous_plan(state) is not None:
                return "plan"
            if state.get("needs_subagents", False):
                return "plan"
            return "respond"

        def after_plan(state: MainAgentState) -> str:
            """规划后: 开始执行"""
            return "execute"

        def after_execute(state: MainAgentState) -> str:
            """Retry or continue using the index selected by execute_node."""
            plan = state.get("plan", [])
            step_idx = state.get("current_step_index", 0)
            return "execute" if step_idx < len(plan) else "synthesize"

        # ── 构建图 ──

        workflow = StateGraph(MainAgentState)
        workflow.add_node("analyze", analyze_node)
        workflow.add_node("respond", respond_node)
        workflow.add_node("plan", plan_node)
        workflow.add_node("execute", execute_node)
        workflow.add_node("synthesize", synthesize_node)

        workflow.set_entry_point("analyze")

        workflow.add_conditional_edges(
            "analyze",
            after_analyze,
            {"respond": "respond", "plan": "plan"},
        )
        workflow.add_edge("plan", "execute")
        workflow.add_conditional_edges(
            "execute",
            after_execute,
            {
                "execute": "execute",
                "synthesize": "synthesize",
            },
        )
        workflow.add_edge("respond", END)
        workflow.add_edge("synthesize", END)

        self._graph = workflow.compile(
            checkpointer=self._checkpointer,
            store=self._store,
        )
        self.logger.info(
            "Graph compiled: analyze→(respond|plan→execute(retry)→synthesize)"
        )

    # ═══ 执行 (异步) ═══

    async def arun(
        self,
        user_task: str,
        thread_id: str | None = None,
        cancellation_event: asyncio.Event | None = None,
        *,
        turn_id: str = "",
        conversation_context: list[dict] | None = None,
        conversation_summary: str = "",
        previous_artifacts: list[dict] | None = None,
        resource_context: str = "",
    ) -> str:
        """执行用户任务 (异步)

        返回: 最终回答文本
        """
        await self.ainitialize()
        tid = thread_id or str(uuid.uuid4())[:12]
        if cancellation_event is not None:
            self._cancellation_events[tid] = cancellation_event
        config = {
            "configurable": {"thread_id": tid},
            "recursion_limit": GRAPH_RECURSION_LIMIT,
        }

        initial_state = self._new_turn_state(
            user_task=user_task,
            turn_id=turn_id,
            conversation_context=conversation_context,
            conversation_summary=conversation_summary,
            previous_artifacts=previous_artifacts,
            resource_context=resource_context,
        )

        try:
            result = await self._graph.ainvoke(initial_state, config)
            return result.get("synthesized_answer", "无法完成任务")
        finally:
            self._cancellation_events.pop(tid, None)

    async def arun_stream(
        self,
        user_task: str,
        thread_id: str | None = None,
        cancellation_event: asyncio.Event | None = None,
        *,
        turn_id: str = "",
        conversation_context: list[dict] | None = None,
        conversation_summary: str = "",
        previous_artifacts: list[dict] | None = None,
        resource_context: str = "",
    ) -> AsyncGenerator[dict, None]:
        """执行任务 (异步流式)

        Yields:
            dict: {event, data} SSE event
        """
        await self.ainitialize()
        tid = thread_id or str(uuid.uuid4())[:12]
        if cancellation_event is not None:
            self._cancellation_events[tid] = cancellation_event
        config = {
            "configurable": {"thread_id": tid},
            "recursion_limit": GRAPH_RECURSION_LIMIT,
        }

        initial_state = self._new_turn_state(
            user_task=user_task,
            turn_id=turn_id,
            conversation_context=conversation_context,
            conversation_summary=conversation_summary,
            previous_artifacts=previous_artifacts,
            resource_context=resource_context,
        )

        event_queue: asyncio.Queue[dict | object] = asyncio.Queue()
        stream_closed = object()
        synthesis_emitted = False

        async def enqueue_event(event: dict) -> None:
            nonlocal synthesis_emitted
            event = {
                "event": str(event.get("event", "message")),
                "data": event.get("data", {}),
            }
            if event["event"] == MultiAgentEvent.SYNTHESIS_DONE:
                synthesis_emitted = True
            await event_queue.put(event)

        async def produce_events() -> None:
            sink_token = set_agent_event_sink(enqueue_event)
            try:
                async for chunk, metadata in self._graph.astream(
                    initial_state, config, stream_mode="messages"
                ):
                    node_name = metadata.get("langgraph_node", "")
                    if (
                        node_name == "respond"
                        and isinstance(chunk, (AIMessage, AIMessageChunk))
                        and chunk.content
                    ):
                        text = self._message_chunk_text(chunk.content)
                        if text:
                            await enqueue_event({
                                "event": MultiAgentEvent.TOKEN,
                                "data": {"text": text, "agent": "main"},
                            })

                final_state = await self._graph.aget_state(config)
                final_values = final_state.values if final_state else {}
                answer = final_values.get("synthesized_answer", "")
                if answer and not synthesis_emitted:
                    await enqueue_event({
                        "event": MultiAgentEvent.SYNTHESIS_DONE,
                        "data": {
                            "answer": answer,
                            "sources": final_values.get(
                                "synthesis_sources", [],
                            ),
                            "confidence": final_values.get(
                                "synthesis_confidence", "medium",
                            ),
                            "turn_id": turn_id,
                        },
                    })
                await enqueue_event({
                    "event": MultiAgentEvent.DONE,
                    "data": {"session_id": tid, "turn_id": turn_id},
                })
            finally:
                reset_agent_event_sink(sink_token)
                await event_queue.put(stream_closed)

        producer_task = asyncio.create_task(produce_events())
        try:
            while True:
                event = await event_queue.get()
                if event is stream_closed:
                    break
                yield event
            await producer_task
        finally:
            if not producer_task.done():
                producer_task.cancel()
                with suppress(asyncio.CancelledError):
                    await producer_task
            if cancellation_event is not None:
                cancellation_event.set()
            self._cancellation_events.pop(tid, None)

    # ═══ 结构化输出 ═══

    async def _ainvoke_structured(
        self,
        schema,
        messages: list,
        run_config: RunnableConfig | None = None,
        **structured_kwargs,
    ):
        """Invoke a structured model and retry parsing failures only.

        ``include_raw=True`` returns parsing and Pydantic validation failures in
        ``parsing_error``. Request errors raised by ``ainvoke`` (authentication,
        rate limiting, server errors, network failures, and timeouts) are not
        caught here and therefore are never mistaken for format failures.
        """
        structured_model = self.model.with_structured_output(
            schema,
            include_raw=True,
            **structured_kwargs,
        )
        retry_messages = list(messages)
        total_attempts = self._max_structured_retries + 1

        for attempt in range(1, total_attempts + 1):
            if run_config is not None:
                await self._check_cancelled(run_config)
            result = await structured_model.ainvoke(retry_messages)
            if run_config is not None:
                await self._check_cancelled(run_config)
            if isinstance(result, dict):
                raw = result.get("raw")
                parsed = result.get("parsed")
                parsing_error = result.get("parsing_error")
            else:
                raw = result
                parsed = None
                parsing_error = None

            parsed_is_empty = parsed is None or (
                isinstance(parsed, dict) and not parsed
            )
            if not parsed_is_empty and parsing_error is None:
                return parsed

            error = parsing_error or ValueError(
                f"{schema.__name__} 返回了空的结构化结果"
            )
            self.logger.warning(
                "Structured output failed: schema=%s attempt=%d/%d raw=%r error=%r",
                schema.__name__,
                attempt,
                total_attempts,
                raw,
                error,
            )

            if attempt >= total_attempts:
                raise error

            retry_messages = [
                *messages,
                HumanMessage(content=build_structured_output_retry_prompt(
                    schema.__name__,
                    str(error)[:1500],
                )),
            ]

        raise RuntimeError(f"{schema.__name__} 结构化输出重试状态异常")

    # ═══ SubAgent 管理 ═══

    @staticmethod
    def _new_turn_state(
        *,
        user_task: str,
        turn_id: str,
        conversation_context: list[dict] | None,
        conversation_summary: str,
        previous_artifacts: list[dict] | None,
        resource_context: str,
    ) -> MainAgentState:
        """构造完整的新轮次状态，显式覆盖同一 checkpoint 的旧编排字段。"""
        return {
            "turn_id": turn_id,
            "current_input": user_task,
            "conversation_context": list(conversation_context or []),
            "conversation_summary": conversation_summary,
            "resource_context": resource_context,
            "previous_artifacts": list(previous_artifacts or []),
            "resumed_from_turn_id": "",
            "user_task": user_task,
            "resolved_task": user_task,
            "intent": "new_task",
            "referenced_turn_ids": [],
            "reuse_previous_artifacts": False,
            "needs_subagents": False,
            "task_summary": "",
            "plan": [],
            "plan_raw": "",
            "current_step_index": 0,
            "subagent_results": {},
            "subagent_statuses": {},
            "step_retry_counts": {},
            "synthesized_answer": "",
            "synthesis_sources": [],
            "synthesis_confidence": "medium",
            "iteration_count": 0,
        }

    def _build_context_messages(
        self, state: MainAgentState, instruction: str,
    ) -> list:
        """只注入用户可见对话和摘要，不注入编排内部消息。"""
        messages = [SystemMessage(content=MAIN_AGENT_SYSTEM_PROMPT)]
        resource_context = state.get("resource_context", "").strip()
        if resource_context:
            messages.append(SystemMessage(content=resource_context))
        summary = state.get("conversation_summary", "").strip()
        if summary:
            messages.append(SystemMessage(content=f"较早对话摘要：\n{summary}"))
        for item in state.get("conversation_context", []):
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            if item.get("role") == "assistant":
                messages.append(AIMessage(content=content))
            else:
                messages.append(HumanMessage(content=content))
        if state.get("reuse_previous_artifacts"):
            artifacts = self._format_previous_artifacts(
                state.get("previous_artifacts", [])
            )
            if artifacts and not artifacts.startswith("（无历史"):
                messages.append(SystemMessage(content=f"相关历史任务成果：\n{artifacts}"))
        messages.append(HumanMessage(content=instruction))
        return messages

    @staticmethod
    def _format_conversation_context(context: list[dict]) -> str:
        if not context:
            return "（无历史对话）"
        lines = []
        for item in context:
            role = "用户" if item.get("role") == "user" else "助手"
            turn_id = item.get("turn_id", "")
            turn_label = f" [{turn_id}]" if turn_id else ""
            lines.append(f"{role}{turn_label}: {item.get('content', '')}")
        return "\n".join(lines)

    @staticmethod
    def _format_previous_artifacts(artifacts: list[dict]) -> str:
        if not artifacts:
            return "（无历史任务成果）"
        sections = []
        for artifact in artifacts[-3:]:
            results = artifact.get("results", {})
            result_text = "\n".join(
                f"- 步骤 {step_id}: {str(value)[:3000]}"
                for step_id, value in results.items()
            ) or "（无步骤结果）"
            sections.append(
                f"轮次 {artifact.get('turn_id', '')} "
                f"[状态: {artifact.get('status', '')}]\n"
                f"任务: {artifact.get('resolved_task', '')}\n"
                f"最终回答: {str(artifact.get('final_answer', ''))[:4000]}\n"
                f"执行结果:\n{result_text}"
            )
        return "\n\n".join(sections)[-12000:]

    @staticmethod
    def _resume_previous_plan(state: MainAgentState) -> dict | None:
        if (
            state.get("intent") != "continue_task"
            or not state.get("reuse_previous_artifacts")
        ):
            return None
        for artifact in reversed(state.get("previous_artifacts", [])):
            plan = list(artifact.get("plan") or [])
            if artifact.get("status") not in {"cancelled", "failed"} or not plan:
                continue
            statuses = dict(artifact.get("step_statuses") or {})
            next_index = next(
                (
                    index for index, step in enumerate(plan)
                    if statuses.get(str(step.get("step_id"))) != "success"
                ),
                len(plan),
            )
            if next_index >= len(plan):
                continue
            return {
                "plan": plan,
                "plan_raw": f"继续轮次 {artifact.get('turn_id', '')} 的未完成步骤",
                "current_step_index": next_index,
                "subagent_results": dict(artifact.get("results") or {}),
                "subagent_statuses": statuses,
                "step_retry_counts": {},
                "resumed_from_turn_id": str(artifact.get("turn_id", "")),
            }
        return None

    async def get_run_snapshot(self, thread_id: str) -> dict:
        if self._graph is None:
            return {}
        state = await self._graph.aget_state({"configurable": {"thread_id": thread_id}})
        return dict(state.values) if state and state.values else {}

    async def summarize_conversation(
        self,
        existing_summary: str,
        messages: list[dict],
    ) -> str:
        """将较早的用户可见对话压缩为可继续使用的事实摘要。"""
        if not messages:
            return existing_summary
        transcript = self._format_conversation_context(messages)[-24000:]
        prompt = (
            "请更新多轮会话摘要。保留用户目标、约束、已经确认的事实、"
            "关键结论、未完成事项和可复用任务结果；不要保留寒暄和编排过程。\n\n"
            f"已有摘要：\n{existing_summary[-8000:] if existing_summary else '（无）'}\n\n"
            f"新增历史消息：\n{transcript}\n\n"
            "请只返回更新后的摘要正文。"
        )
        response = await self.model.ainvoke([
            SystemMessage(content=MAIN_AGENT_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])
        content = self._message_chunk_text(getattr(response, "content", "")).strip()
        return content[:12000] or existing_summary

    async def _get_or_create_subagent(self, subagent_type: str) -> SubAgent:
        """按需获取或创建 SubAgent 实例 (异步初始化)"""
        if subagent_type not in self._sub_agents_cache:
            meta = self.sub_agent_registry.get(subagent_type)
            if meta is None:
                raise ValueError(f"未知的 SubAgent 类型: {subagent_type}")

            sub = None
            if meta.factory is not None:
                sub = meta.factory()

            if sub is None:
                sub = SubAgent(
                    name=meta.display_name,
                    subagent_type=meta.subagent_type,
                    description=meta.description,
                    capabilities=meta.capabilities,
                    store_type=self._store_type,
                    sqlite_path=self._subagent_sqlite_path(meta.subagent_type),
                )

            # MCP 工具由 create_default_registry 的 factory 注入（方案2），
            # 这里不再用 MainAgent 的 _mcp_tools 覆盖，否则会清空 factory 注入的工具。
            # sub._mcp_tools = self._mcp_tools
            # sub._mcp_tools_meta = self._mcp_tools_meta
            await sub.ainitialize()
            self._sub_agents_cache[subagent_type] = sub
            self.logger.info("创建 SubAgent: %s", subagent_type)

        return self._sub_agents_cache[subagent_type]

    def _subagent_sqlite_path(self, subagent_type: str) -> str | None:
        """为默认 SubAgent 派生独立数据库，避免与 MainAgent 争用同一文件。"""
        if self._store_type != "sqlite":
            return None
        if self._sqlite_path == ":memory:":
            return ":memory:"

        main_path = Path(self._sqlite_path or "./data/main_agent.db")
        suffix = main_path.suffix or ".db"
        safe_type = "".join(
            char if char.isalnum() or char in {"-", "_"} else "-"
            for char in subagent_type
        ).strip("-") or "general"
        return str(main_path.with_name(f"{main_path.stem}-{safe_type}{suffix}"))

    def _build_context_for_step(
        self,
        step: dict,
        all_results: dict[str, str],
    ) -> str:
        """为步骤构建上下文 (前置步骤的结果)"""
        depends_on = step.get("depends_on", [])
        if not depends_on:
            return ""

        context_parts = []
        for dep_id in depends_on:
            dep_result = all_results.get(str(dep_id), "")
            if dep_result:
                context_parts.append(f"[前置步骤 {dep_id} 的结果]\n{dep_result}")

        return "\n\n".join(context_parts)

    # ═══ 辅助方法 ═══

    @staticmethod
    def _normalize_subagent_type(value) -> str | None:
        """将空白的 subagent 类型统一转换为 direct 步骤标记。"""
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @staticmethod
    def _node_to_event(node_name: str) -> dict | None:
        """将 LangGraph 节点名转为 SSE event"""
        mapping = {
            "analyze": MultiAgentEvent.ANALYZING,
            "plan": MultiAgentEvent.STATUS,
            "execute": MultiAgentEvent.DISPATCHING,
            "synthesize": MultiAgentEvent.SYNTHESIZING,
            "respond": MultiAgentEvent.STATUS,
        }
        event_type = mapping.get(node_name)
        if event_type is None:
            return None

        messages = {
            "analyze": "正在分析任务...",
            "plan": "正在生成执行计划...",
            "execute": "正在执行计划步骤...",
            "synthesize": "正在综合结果...",
            "respond": "正在生成回答...",
        }
        return {
            "event": event_type,
            "data": {
                "agent": "main",
                "node": node_name,
                "message": messages.get(node_name, ""),
            },
        }

    @staticmethod
    def _message_chunk_text(content) -> str:
        """提取 message chunk 的文本"""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    parts.append(item["text"])
                elif isinstance(item, str):
                    parts.append(item)
            return "".join(parts)
        return str(content) if content else ""

    async def _check_cancelled(self, config: RunnableConfig) -> None:
        thread_id = config.get("configurable", {}).get("thread_id")
        cancellation_event = self._cancellation_events.get(thread_id)
        if cancellation_event is not None and cancellation_event.is_set():
            raise AgentRunCancelled("任务已由用户中止")

    # ═══ 生命周期 ═══

    def close(self):
        """清理所有 subagent 和资源"""
        for sub in self._sub_agents_cache.values():
            try:
                sub.close()
            except Exception:
                pass
        self._sub_agents_cache.clear()

        # Graph 持有 checkpointer/store 引用，先释放 graph 再关闭底层连接。
        self._graph = None
        for cancellation_event in self._cancellation_events.values():
            cancellation_event.set()
        self._cancellation_events.clear()
        connections = self._sqlite_connections
        self._sqlite_connections = ()
        for connection in reversed(connections):
            try:
                if connection.in_transaction:
                    connection.rollback()
                connection.close()
            except sqlite3.Error as exc:
                self.logger.warning("关闭 SQLite 连接失败: %s", exc)
        self._checkpointer = None
        self._store = None
        self.logger.info("MainAgent 已关闭")

    async def aclose(self):
        """异步清理所有 subagent 和资源（关闭 aiosqlite 连接）。"""
        for sub in self._sub_agents_cache.values():
            try:
                await sub.aclose()
            except Exception:
                pass
        self._sub_agents_cache.clear()

        self._graph = None
        for cancellation_event in self._cancellation_events.values():
            cancellation_event.set()
        self._cancellation_events.clear()
        connections = self._async_connections
        self._async_connections = ()
        for connection in reversed(connections):
            try:
                await connection.close()
            except Exception as exc:
                self.logger.warning("关闭异步 SQLite 连接失败: %s", exc)
        self._checkpointer = None
        self._store = None
        self.logger.info("MainAgent 已关闭")
