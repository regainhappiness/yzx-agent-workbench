"""
===========================================================================
SubAgent — Plan-and-Solve 子执行器（异步）
===========================================================================

基于 LangGraph 的 Plan-and-Solve 智能体:
  1. plan:     分解分配的任务为子步骤
  2. execute:  ReAct 循环执行每个子步骤 (复用 ChatAgent 模式)
  3. evaluate: 自评结果质量
  4. report:   格式化结果返回 MainAgent

Tool 隔离:
  每个 SubAgent 实例创建独立的 ToolRegistry:
    - L1: GENERAL_TOOLS (共享函数引用)
    - L3: 单智能体规划 tools (prompt 函数)
    - L4: 本 subagent 专属 API tools (构造参数注入)
    - MCP: 外部 MCP Server 发现的工具 (async-only，仅异步图可用)

使用:
    sub = SubAgent(name="DataAnalyst", subagent_type="data_analyst",
                   api_tools=[sql_query], mcp_tools=[...])
    await sub.ainitialize()
    result = await sub.arun("查询上月销售总额并按地区分组")
===========================================================================
"""

import asyncio
import sqlite3
import uuid
from pathlib import Path
from typing import AsyncGenerator

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from ..base import BaseAgent
from ...models.llm import get_model, CAN_RUN
from ...tools.registry import ToolRegistry
from ...tools.base import BUILTIN_TOOLS, BUILTIN_TOOLS_META
from ...tools.general import GENERAL_TOOLS
from ...tools.single_agent_planning.task_decomposer import (
    decompose_task, DecompositionOutput,
)
from ...tools.single_agent_planning.self_evaluator import (
    evaluate_result, EvaluationOutput,
)
from ...utils.logger import get_logger
from ...prompt import SUBAGENT_SYSTEM_PROMPT, build_subagent_step_prompt


# ═══════════════════════════════════════════════════════════════════════
# State
# ═══════════════════════════════════════════════════════════════════════

from .states import SubAgentState
from .events import (
    AgentRunCancelled,
    MultiAgentEvent,
    SubAgentExecutionError,
    emit_agent_event,
)


GRAPH_RECURSION_LIMIT = 50


# ═══════════════════════════════════════════════════════════════════════
# SubAgent
# ═══════════════════════════════════════════════════════════════════════

class SubAgent(BaseAgent):
    """Plan-and-Solve 子智能体

    参数:
        name:            Agent 名称 (用于日志)
        subagent_type:   类型标识, 如 "data_analyst"
        description:     能力描述 (LLM 选择依据)
        capabilities:    能力标签列表
        api_tools:       本 subagent 专属的 L4 API tools 列表
        mcp_tools:       外部 MCP 工具列表 (async-only)
        model_kwargs:    传递给 get_model() 的额外参数
        store_type:      存储类型: "memory" | "sqlite"
        sqlite_path:     SQLite 路径 (store_type="sqlite" 时)
    """

    def __init__(
        self,
        name: str = "SubAgent",
        subagent_type: str = "general",
        description: str = "通用子智能体",
        capabilities: list[str] | None = None,
        api_tools: list | None = None,
        api_tools_meta: dict[str, dict] | None = None,
        model_kwargs: dict | None = None,
        store_type: str = "memory",
        sqlite_path: str | None = None,
        mcp_tools: list | None = None,
        mcp_tools_meta: dict[str, dict] | None = None,
        **kwargs,
    ):
        super().__init__(name=name, **kwargs)
        self.subagent_type = subagent_type
        self.description = description
        self.capabilities = capabilities or []
        self._api_tools = api_tools or []
        self._api_tools_meta = api_tools_meta or {}
        self._model_kwargs = model_kwargs or {}
        self._store_type = store_type
        self._sqlite_path = sqlite_path
        self._mcp_tools = mcp_tools or []
        self._mcp_tools_meta = mcp_tools_meta or {}

        # 在 _setup 中设置
        self.tool_registry: ToolRegistry | None = None
        self._graph = None
        self._checkpointer = None
        self._store = None
        self._sqlite_connections: tuple[sqlite3.Connection, ...] = ()
        self._async_connections: tuple = ()
        self._cancellation_events: dict[str, asyncio.Event] = {}

    # ═══ 初始化 ═══

    def _setup(self, **kwargs):
        """初始化 SubAgent 组件 (模型 + 工具注册中心 + 图构建)"""
        logger = get_logger(f"SubAgent.{self.name}")

        # 1. 模型
        self.model = get_model(**self._model_kwargs)
        if self.model is None:
            logger.warning("无可用 LLM — SubAgent 将以降级模式运行")

        # 2. 工具注册中心 (隔离)
        self.tool_registry = ToolRegistry()
        # L1: 通用 tools
        self.tool_registry.register_with_meta(BUILTIN_TOOLS, BUILTIN_TOOLS_META)
        # L4: 本 subagent 专属 API tools
        if self._api_tools:
            if self._api_tools_meta:
                self.tool_registry.register_with_meta(self._api_tools, self._api_tools_meta)
            else:
                self.tool_registry.register_many(self._api_tools, category="backend_api")
        # MCP: 外部工具 (async-only)
        if self._mcp_tools:
            self.tool_registry.register_with_meta(self._mcp_tools, self._mcp_tools_meta)
        logger.info(
            "ToolRegistry: %d tools (L1=%d, L4=%d, MCP=%d)",
            self.tool_registry.tool_count,
            len(GENERAL_TOOLS),
            len(self._api_tools),
            len(self._mcp_tools),
        )

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

        db_path = Path(self._sqlite_path or "./data/subagent.db").expanduser()
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
        """构建 Plan-and-Solve LangGraph 图 (异步节点):
        plan → execute(ReAct) → evaluate → (needs_revision? → plan | → report) → END
        """
        # 绑定 tools 用于 execute 节点的 ReAct 循环
        tools = self.tool_registry.list_all()
        # ── 节点定义 ──

        async def plan_node(state: SubAgentState, config: RunnableConfig) -> dict:
            await self._check_cancelled(config)
            """分解任务为子步骤"""
            prompt = decompose_task(
                assigned_task=state.get("assigned_task", ""),
                subagent_type=self.subagent_type,
                capabilities=", ".join(self.capabilities),
                available_tools=self._format_available_tools(),
                context=state.get("step_results", {}).get("_context", ""),
            )
            messages = [SystemMessage(content=SUBAGENT_SYSTEM_PROMPT.format(
                subagent_type=self.subagent_type,
                description=self.description,
                capabilities=", ".join(self.capabilities),
            )), HumanMessage(content=prompt)]

            structured_model = self.model.with_structured_output(DecompositionOutput)
            response = await structured_model.ainvoke(messages)

            sub_plan = [
                {"step_id": s.step_id, "description": s.description,
                 "tool_hint": self._resolve_tool_hint(s.tool_hint)}
                for s in response.sub_plan
            ]
            available_tool_names = set(self.tool_registry.list_names())
            invalid_hints = [
                str(step["tool_hint"])
                for step in sub_plan
                if step.get("tool_hint")
                and step["tool_hint"] not in available_tool_names
            ]
            if invalid_hints:
                raise SubAgentExecutionError(
                    "子智能体计划引用了不可用工具: "
                    f"{', '.join(invalid_hints)}；"
                    f"当前可用工具: {', '.join(sorted(available_tool_names)) or '无'}",
                    retryable=False,
                )

            self.logger.info("Plan: %d steps — %s", len(sub_plan), response.strategy)
            for index, step in enumerate(sub_plan, 1):
                self.logger.info(
                    "Plan step %d/%d: id=%s tool_hint=%s description=%s",
                    index, len(sub_plan), step["step_id"],
                    step.get("tool_hint") or "none",
                    self._log_preview(step.get("description", ""), 240),
                )
            await emit_agent_event(MultiAgentEvent.SUBAGENT_PLAN, {
                "subagent_type": self.subagent_type,
                "plan": sub_plan,
                "strategy": response.strategy,
            })
            return {
                "sub_plan": sub_plan,
                "plan_raw": response.strategy,
                "current_step_index": 0,
                "react_iteration_count": 0,
                "iteration_count": state.get("iteration_count", 0),
                "messages": [AIMessage(content=f"计划已生成: {response.strategy}")],
            }

        async def agent_node(state: SubAgentState, config: RunnableConfig) -> dict:
            await self._check_cancelled(config)
            """ReAct agent 节点 — 决定调用工具或输出文本"""
            step_idx = state.get("current_step_index", 0)
            sub_plan = state.get("sub_plan", [])
            step_desc = ""
            tool_hint = None
            if 0 <= step_idx < len(sub_plan):
                step_desc = sub_plan[step_idx].get("description", "")
                tool_hint = sub_plan[step_idx].get("tool_hint")

            step_instruction = ""
            # 每个计划步骤只在首次进入 agent 节点时注入一次执行指令。
            # 工具调用后的消息历史已经包含 ToolMessage，不能再次提示模型
            # “请使用工具”，否则模型容易在同一步骤重复调用相同工具。
            if step_desc and state.get("react_iteration_count", 0) == 0:
                step_instruction = build_subagent_step_prompt(
                    step_desc,
                    step_idx + 1,
                    len(sub_plan),
                    tool_hint=tool_hint,
                )
                await emit_agent_event(MultiAgentEvent.SUBAGENT_STEP, {
                    "subagent_type": self.subagent_type,
                    "step_id": str(
                        sub_plan[step_idx].get("step_id", step_idx + 1)
                    ),
                    "description": step_desc,
                    "status": "running",
                    "step_index": step_idx + 1,
                    "total_steps": len(sub_plan),
                })

            messages = list(state.get("messages", []))
            if step_instruction:
                messages.append(HumanMessage(content=step_instruction))

            self.logger.info(
                "Execute step %d/%d: tool_hint=%s description=%s",
                step_idx + 1, len(sub_plan), tool_hint or "none",
                self._log_preview(step_desc, 240),
            )
            # Reasoning/synthesis steps must not be able to invent a fallback
            # tool call. Tool-backed steps are constrained to their plan hint.
            expected_tool = (
                self.tool_registry.get(tool_hint) if tool_hint else None
            )
            execution_model = (
                self.model.bind_tools([expected_tool])
                if expected_tool is not None else self.model
            )
            response = await execution_model.ainvoke(messages)
            await self._check_cancelled(config)
            tool_calls = list(getattr(response, "tool_calls", None) or [])
            if tool_hint and tool_calls:
                matching_calls = [
                    call for call in tool_calls if call.get("name") == tool_hint
                ]
                if not matching_calls:
                    requested = ", ".join(
                        str(call.get("name", "unknown")) for call in tool_calls
                    )
                    raise SubAgentExecutionError(
                        f"步骤 {step_idx + 1} 应调用 {tool_hint}，"
                        f"但模型请求了 {requested}",
                        retryable=True,
                    )
                if len(tool_calls) != 1:
                    self.logger.warning(
                        "Ignoring unexpected tool calls: step=%d expected=%s ignored=%s",
                        step_idx + 1, tool_hint,
                        [
                            call.get("name", "unknown") for call in tool_calls
                            if call is not matching_calls[0]
                        ],
                    )
                    response = response.model_copy(
                        update={"tool_calls": [matching_calls[0]]},
                    )
                    tool_calls = [matching_calls[0]]
            if tool_calls:
                for call in tool_calls:
                    self.logger.info(
                        "Model requested tool: step=%d tool=%s args=%s",
                        step_idx + 1, call.get("name", "unknown"),
                        self._safe_tool_args(call.get("args", {})),
                    )
            else:
                self.logger.info(
                    "Model returned text: step=%d chars=%d preview=%s",
                    step_idx + 1,
                    len(self._message_chunk_text(response.content)),
                    self._log_preview(
                        self._message_chunk_text(response.content), 240,
                    ),
                )
                if tool_hint:
                    raise SubAgentExecutionError(
                        f"步骤 {step_idx + 1} 指定了工具 {tool_hint}，"
                        "但模型没有发起工具调用",
                        retryable=True,
                    )
            return {
                "messages": [response],
                "react_iteration_count": state.get("react_iteration_count", 0) + 1,
            }

        async def tools_node(state: SubAgentState, config: RunnableConfig) -> dict:
            await self._check_cancelled(config)
            """工具执行节点"""
            last_message = state.get("messages", [])[-1]
            tool_calls = list(getattr(last_message, "tool_calls", None) or [])
            self.logger.info(
                "Tool node started: calls=%s",
                [call.get("name", "unknown") for call in tool_calls],
            )
            step_idx = state.get("current_step_index", 0)
            sub_plan = state.get("sub_plan", [])
            step_id = str(
                sub_plan[step_idx].get("step_id", step_idx + 1)
                if 0 <= step_idx < len(sub_plan)
                else step_idx + 1
            )
            for call in tool_calls:
                await emit_agent_event(MultiAgentEvent.TOOL_CALL, {
                    "agent": self.subagent_type,
                    "subagent_type": self.subagent_type,
                    "step_id": step_id,
                    "tool_name": call.get("name", "unknown"),
                    "args": call.get("args", {}),
                })
            try:
                result = await ToolNode(tools).ainvoke(
                    {"messages": state["messages"]}, config=config,
                )
            except AgentRunCancelled:
                raise
            except Exception:
                self.logger.exception(
                    "Tool node raised: calls=%s",
                    [call.get("name", "unknown") for call in tool_calls],
                )
                raise
            await self._check_cancelled(config)
            for message in result.get("messages", []):
                text = self._message_chunk_text(getattr(message, "content", ""))
                tool_name = getattr(message, "name", None) or "unknown"
                self.logger.info(
                    "Tool result: tool=%s status=%s chars=%d preview=%s",
                    tool_name, getattr(message, "status", "success"), len(text),
                    self._log_preview(text, 320),
                )
                await emit_agent_event(MultiAgentEvent.TOOL_RESULT, {
                    "agent": self.subagent_type,
                    "subagent_type": self.subagent_type,
                    "step_id": step_id,
                    "tool_name": tool_name,
                    "result_summary": self._log_preview(text, 400),
                    "success": getattr(message, "status", "success") != "error",
                })
                failure = self._tool_failure(message, text)
                if failure is not None:
                    message_text, retryable = failure
                    self.logger.error(
                        "Tool execution rejected: tool=%s retryable=%s reason=%s",
                        tool_name, retryable, message_text,
                    )
                    raise SubAgentExecutionError(
                        message_text, retryable=retryable,
                    )
            return result

        async def advance_step_node(state: SubAgentState, config: RunnableConfig) -> dict:
            """Persist the current output and move to the next planned step."""
            await self._check_cancelled(config)
            step_idx = state.get("current_step_index", 0)
            sub_plan = state.get("sub_plan", [])
            step_id = str(
                sub_plan[step_idx].get("step_id", step_idx + 1)
                if 0 <= step_idx < len(sub_plan)
                else step_idx + 1
            )
            step_results = dict(state.get("step_results", {}))
            step_results[step_id] = self._latest_execution_result(
                state.get("messages", [])
            )
            description = (
                sub_plan[step_idx].get("description", "")
                if 0 <= step_idx < len(sub_plan) else ""
            )
            await emit_agent_event(MultiAgentEvent.SUBAGENT_STEP, {
                "subagent_type": self.subagent_type,
                "step_id": step_id,
                "description": description,
                "status": "completed",
                "step_index": step_idx + 1,
                "total_steps": len(sub_plan),
            })
            await emit_agent_event(MultiAgentEvent.SUBAGENT_PROGRESS, {
                "subagent_type": self.subagent_type,
                "step_id": step_id,
                "progress": round((step_idx + 1) / max(1, len(sub_plan)) * 100),
            })
            return {
                "step_results": step_results,
                "current_step_index": step_idx + 1,
                "react_iteration_count": 0,
            }

        async def evaluate_node(state: SubAgentState, config: RunnableConfig) -> dict:
            await self._check_cancelled(config)
            """自评结果质量"""
            await emit_agent_event(MultiAgentEvent.SUBAGENT_STEP, {
                "subagent_type": self.subagent_type,
                "description": "正在评估执行结果",
                "status": "evaluating",
            })
            sub_plan = state.get("sub_plan", [])
            step_results = {
                key: value
                for key, value in state.get("step_results", {}).items()
                if not str(key).startswith("_")
            }
            plan_summary = "\n".join(
                f"  {s['step_id']}: {s['description']}" for s in sub_plan
            ) if sub_plan else "（无计划）"

            results_text = "\n".join(
                f"步骤 {k}: {v}" for k, v in step_results.items()
            ) if step_results else "（无结果）"

            prompt = evaluate_result(
                assigned_task=state.get("assigned_task", ""),
                plan_summary=plan_summary,
                execution_results=results_text,
            )
            messages = [HumanMessage(content=prompt)]
            structured_model = self.model.with_structured_output(EvaluationOutput)
            response = await structured_model.ainvoke(messages)

            self.logger.info(
                "Evaluate: needs_revision=%s, completeness=%s, accuracy=%s",
                response.needs_revision,
                response.completeness,
                response.accuracy,
            )
            return {
                "self_evaluation": response.feedback,
                "needs_revision": response.needs_revision,
                "iteration_count": state.get("iteration_count", 0) + 1,
                "messages": [AIMessage(content=f"自评: {response.feedback}")],
            }

        async def report_node(state: SubAgentState, config: RunnableConfig) -> dict:
            await self._check_cancelled(config)
            """格式化最终结果"""
            await emit_agent_event(MultiAgentEvent.SUBAGENT_STEP, {
                "subagent_type": self.subagent_type,
                "description": "正在整理执行结果",
                "status": "reporting",
            })
            step_results = {
                key: value
                for key, value in state.get("step_results", {}).items()
                if not str(key).startswith("_")
            }
            result_parts = []
            for step_id, result in sorted(step_results.items()):
                result_parts.append(f"## 步骤 {step_id}\n{result}")

            final = "\n\n".join(result_parts) if result_parts else "（无结果）"
            self.logger.info("Report: %d steps completed", len(step_results))
            return {
                "final_result": final,
                "messages": [AIMessage(content=f"任务完成。执行了 {len(step_results)} 个步骤。")],
            }

        # ── 路由函数 ──

        def should_continue(state: SubAgentState) -> str:
            """ReAct 循环: 检查是否需要调用工具"""
            messages = state.get("messages", [])
            if not messages:
                return END
            last_msg = messages[-1]
            if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                # 只要存在 tool_calls，就必须先由 ToolNode 为每个
                # tool_call_id 生成对应 ToolMessage，不能直接跳过。
                return "tools"
            return "advance_step"

        def after_advance_step(state: SubAgentState) -> str:
            if state.get("current_step_index", 0) < len(state.get("sub_plan", [])):
                return "agent"
            """计划执行后: 进入评估"""
            return "evaluate"

        def after_evaluate(state: SubAgentState) -> str:
            """评估后: 需要修正则重新规划, 否则提交结果"""
            needs_revision = state.get("needs_revision", False)
            iteration = state.get("iteration_count", 0)
            if needs_revision and iteration < 3:
                self.logger.info("需要修正，重新规划 (迭代 %d)", iteration)
                return "plan"
            return "report"

        # ── 构建图 ──

        workflow = StateGraph(SubAgentState)
        workflow.add_node("plan", plan_node)
        workflow.add_node("agent", agent_node)
        workflow.add_node("tools", tools_node)
        workflow.add_node("advance_step", advance_step_node)
        workflow.add_node("evaluate", evaluate_node)
        workflow.add_node("report", report_node)

        workflow.set_entry_point("plan")

        # plan → agent (开始 ReAct 执行)
        workflow.add_edge("plan", "agent")

        # ReAct 循环
        workflow.add_conditional_edges(
            "agent",
            should_continue,
            {"tools": "tools", "advance_step": "advance_step"},
        )
        # 子计划中的每个步骤都是原子操作。工具执行完成后直接保存工具
        # 结果并推进下一步，避免 tools → agent 循环导致同一步骤重复调用。
        workflow.add_edge("tools", "advance_step")
        workflow.add_conditional_edges(
            "advance_step",
            after_advance_step,
            {"agent": "agent", "evaluate": "evaluate"},
        )

        # 评估 → 修正或提交
        workflow.add_conditional_edges(
            "evaluate",
            after_evaluate,
            {"plan": "plan", "report": "report"},
        )
        workflow.add_edge("report", END)

        self._graph = workflow.compile(
            checkpointer=self._checkpointer,
            store=self._store,
        )
        self.logger.info("Graph compiled: plan → agent→tools?→advance → evaluate → (plan|report)")

    # ═══ 执行 (异步) ═══

    async def arun(
        self,
        assigned_task: str,
        thread_id: str | None = None,
        context: str = "",
        cancellation_event: asyncio.Event | None = None,
    ) -> str:
        """执行分配的任务 (异步)

        返回:
            执行结果文本
        """
        await self.ainitialize()
        tid = thread_id or str(uuid.uuid4())[:12]
        if cancellation_event is not None:
            self._cancellation_events[tid] = cancellation_event
        config = {
            "configurable": {"thread_id": tid},
            "recursion_limit": GRAPH_RECURSION_LIMIT,
        }

        initial_state = {
            "assigned_task": assigned_task,
            "subagent_type": self.subagent_type,
            "step_results": {"_context": context},
            "iteration_count": 0,
            "react_iteration_count": 0,
            "messages": [
                SystemMessage(content=SUBAGENT_SYSTEM_PROMPT.format(
                    subagent_type=self.subagent_type,
                    description=self.description,
                    capabilities=", ".join(self.capabilities),
                )),
                HumanMessage(content=self._assignment_context_message(
                    assigned_task, context,
                )),
            ],
        }

        self.logger.info(
            "Run started: thread_id=%s task=%s context_chars=%d tools=%s",
            tid, self._log_preview(assigned_task, 300), len(context),
            self.tool_registry.list_names() if self.tool_registry else [],
        )
        try:
            result = await self._graph.ainvoke(initial_state, config)
            final_result = result.get("final_result", "")
            self.logger.info(
                "Run completed: thread_id=%s result_chars=%d preview=%s",
                tid, len(final_result), self._log_preview(final_result, 320),
            )
            return final_result
        except AgentRunCancelled:
            self.logger.info("Run cancelled: thread_id=%s", tid)
            raise
        except Exception:
            self.logger.exception("Run failed: thread_id=%s", tid)
            raise
        finally:
            self._cancellation_events.pop(tid, None)

    async def arun_stream(
        self,
        assigned_task: str,
        thread_id: str | None = None,
        context: str = "",
        cancellation_event: asyncio.Event | None = None,
    ) -> AsyncGenerator[dict, None]:
        """执行任务 (异步流式)

        Yields:
            dict: {event, data} SSE 事件
        """
        await self.ainitialize()
        tid = thread_id or str(uuid.uuid4())[:12]
        if cancellation_event is not None:
            self._cancellation_events[tid] = cancellation_event
        config = {
            "configurable": {"thread_id": tid},
            "recursion_limit": GRAPH_RECURSION_LIMIT,
        }

        initial_state = {
            "assigned_task": assigned_task,
            "subagent_type": self.subagent_type,
            "step_results": {"_context": context},
            "iteration_count": 0,
            "react_iteration_count": 0,
            "messages": [
                SystemMessage(content=SUBAGENT_SYSTEM_PROMPT.format(
                    subagent_type=self.subagent_type,
                    description=self.description,
                    capabilities=", ".join(self.capabilities),
                )),
                HumanMessage(content=self._assignment_context_message(
                    assigned_task, context,
                )),
            ],
        }

        final_result = ""
        try:
            async for chunk, metadata in self._graph.astream(
                initial_state, config, stream_mode="messages"
            ):
                node_name = metadata.get("langgraph_node", "")
                if isinstance(chunk, AIMessage) and chunk.content:
                    text = self._message_chunk_text(chunk.content)
                    if text:
                        yield {"event": "token", "data": {"text": text, "agent": self.subagent_type}}

                # 检测节点转换
                if node_name == "plan" and not final_result:
                    yield {
                        "event": "subagent_plan",
                        "data": {"subagent_type": self.subagent_type, "plan": []},
                    }
                elif node_name == "evaluate":
                    yield {
                        "event": "subagent_step",
                        "data": {
                            "subagent_type": self.subagent_type,
                            "status": "evaluating",
                        },
                    }

            # 获取最终状态
            final_state = await self._graph.aget_state(config)
            if final_state and final_state.values:
                final_result = final_state.values.get("final_result", "")

            yield {
                "event": "subagent_done",
                "data": {
                    "subagent_type": self.subagent_type,
                    "result_summary": final_result[:200] if final_result else "",
                    "success": bool(final_result),
                },
            }
        finally:
            if cancellation_event is not None:
                cancellation_event.set()
            self._cancellation_events.pop(tid, None)

    # ═══ 辅助方法 ═══

    def _format_available_tools(self) -> str:
        """格式化可用工具列表 (注入 plan prompt)"""
        if not self.tool_registry:
            return "（无可用工具）"

        tools = self.tool_registry.list_all()
        if not tools:
            return "（无可用工具）"

        lines = []
        for t in tools:
            desc = getattr(t, "description", "") or ""
            # 截断过长的描述
            if len(desc) > 120:
                desc = desc[:120] + "..."
            lines.append(f"  - **{t.name}**: {desc}")
        return "\n".join(lines)

    @staticmethod
    def _assignment_context_message(assigned_task: str, context: str) -> str:
        context_text = context.strip()
        if context_text and context_text in assigned_task:
            context_text = "（资源上下文已包含在上方委托中）"
        return (
            "## 主智能体分配的任务\n"
            f"{assigned_task}\n\n"
            "## 当前执行上下文\n"
            f"{context_text or '（无额外上下文）'}\n\n"
            "执行每个步骤时必须继续使用以上上下文中的真实路径和约束，"
            "不得改用系统剪贴板或猜测文件路径。"
        )

    def _resolve_tool_hint(self, tool_hint: str | None) -> str | None:
        """Resolve an MCP server's short tool name to its registered full name."""
        if not tool_hint or not self.tool_registry:
            return tool_hint
        names = self.tool_registry.list_names()
        if tool_hint in names:
            return tool_hint
        matches = [name for name in names if name.endswith(f"_{tool_hint}")]
        return matches[0] if len(matches) == 1 else tool_hint

    @staticmethod
    def _safe_tool_args(arguments) -> dict:
        if not isinstance(arguments, dict):
            return {"value": f"<{type(arguments).__name__}>"}
        summary = {}
        for key, value in arguments.items():
            if key == "path" or key.endswith("_path"):
                summary[key] = value
            elif value is None or isinstance(value, (bool, int, float)):
                summary[key] = value
            elif isinstance(value, (list, tuple)):
                summary[key] = f"<{type(value).__name__}:{len(value)}>"
            else:
                summary[key] = f"<{type(value).__name__}:{len(str(value))} chars>"
        return summary

    @staticmethod
    def _log_preview(value: str, limit: int) -> str:
        text = " ".join(str(value or "").split())
        return text if len(text) <= limit else f"{text[:limit]}..."

    @staticmethod
    def _tool_failure(message, text: str) -> tuple[str, bool] | None:
        if getattr(message, "status", None) == "error":
            return (text or "工具执行失败", True)
        if text.startswith("[MCP] 权限校验失败:"):
            return (text, False)
        if text.startswith("[MCP] 服务器") and "当前不可用" in text:
            return (text, False)
        if text.startswith("[MCP] 工具调用失败:"):
            return (text, True)
        if text.startswith("[MCP] 工具结果重试已耗尽:"):
            return (text, False)
        if text.startswith("[MCP] 工具调用已由用户中止"):
            return (text, False)
        normalized = text.strip().lower()
        if normalized.startswith("input validation error:"):
            return (text, False)
        if normalized.startswith("错误:") or normalized.startswith("error:"):
            retryable = any(
                marker in normalized
                for marker in ("error code: 429", "timeout", "timed out")
            ) or any(f"error code: {code}" in normalized for code in range(500, 600))
            return (text, retryable)
        return None

    @staticmethod
    def _message_chunk_text(content) -> str:
        """提取 message chunk 的文本内容"""
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

    @staticmethod
    def _latest_execution_result(messages) -> str:
        """Return the latest useful model/tool output for a completed step."""
        for message in reversed(messages):
            content = getattr(message, "content", None)
            if isinstance(message, AIMessage) and not getattr(message, "tool_calls", None):
                text = SubAgent._message_chunk_text(content)
                if text:
                    return text
            if isinstance(message, ToolMessage):
                text = SubAgent._message_chunk_text(content)
                if text:
                    return text
        return "（该步骤未返回可用结果）"

    async def _check_cancelled(self, config: RunnableConfig) -> None:
        thread_id = config.get("configurable", {}).get("thread_id")
        cancellation_event = self._cancellation_events.get(thread_id)
        if cancellation_event is not None and cancellation_event.is_set():
            raise AgentRunCancelled("任务已由用户中止")

    # ═══ 生命周期 ═══

    def close(self):
        """清理资源（同步路径，仅内存场景；SQLite 请用 aclose）。"""
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
        self.logger.info("SubAgent 已关闭")

    async def aclose(self):
        """异步清理资源（关闭 aiosqlite 连接）。"""
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
        self.logger.info("SubAgent 已关闭")
