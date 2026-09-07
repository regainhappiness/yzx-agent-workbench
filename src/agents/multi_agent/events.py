"""
===========================================================================
多智能体系统 — SSE 事件类型常量
===========================================================================

定义多智能体流式输出中的所有事件类型。
前端按事件类型分级展示: 主规划 → subagent进度 → 子结果 → 最终答案。
===========================================================================
"""

from contextvars import ContextVar, Token
from enum import StrEnum
from typing import Awaitable, Callable


class AgentRunCancelled(Exception):
    """Raised inside graph nodes when the client cancels a run."""


class SubAgentExecutionError(RuntimeError):
    """A tool-backed SubAgent step failed before it produced usable output."""

    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class MultiAgentEvent(StrEnum):
    """多智能体 SSE 事件类型"""

    # ── 生命周期 ──
    START = "start"                     # 流开始, data={session_id}
    TURN_STARTED = "turn_started"       # 对话轮次开始, data={session_id, turn_id}
    DONE = "done"                       # 流结束, data={session_id}

    # ── MainAgent 状态 ──
    STATUS = "status"                   # 通用状态更新, data={agent, node, message}

    # ── MainAgent 规划阶段 ──
    ANALYZING = "analyzing"             # 正在分析任务
    ANALYSIS_DONE = "analysis_done"     # 任务分析完成, data={task_summary, complexity}

    PLAN_CREATED = "plan_created"       # 计划已生成, data={plan: [PlanStep...]}

    # ── MainAgent 执行阶段 ──
    DISPATCHING = "dispatching"         # 正在调度 subagent, data={step_id, subagent_type}

    # ── SubAgent 内部事件 ──
    SUBAGENT_START = "subagent_start"           # subagent 开始, data={subagent_type, step_id}
    SUBAGENT_PLAN = "subagent_plan"             # subagent 计划, data={subagent_type, plan: [...]}
    SUBAGENT_STEP = "subagent_step"             # subagent 执行步骤, data={step_id, description, status}
    SUBAGENT_PROGRESS = "subagent_progress"     # subagent 进度, data={subagent_type, progress}
    SUBAGENT_DONE = "subagent_done"             # subagent 完成, data={subagent_type, result_summary}

    # ── MainAgent 综合阶段 ──
    SYNTHESIZING = "synthesizing"       # 正在综合结果
    SYNTHESIS_DONE = "synthesis_done"   # 综合完成, data={answer, sources, confidence}

    # ── ReAct 工具调用 (转发自 subagent) ──
    TOOL_CALL = "tool_call"             # 工具调用, data={agent, tool_name, args}
    TOOL_RESULT = "tool_result"         # 工具结果, data={agent, tool_name, result_summary}

    # ── LLM token (来自任意 agent) ──
    TOKEN = "token"                     # 文本增量, data={text, agent}

    # ── 错误 ──
    ERROR = "error"                     # 错误, data={code, message, agent}
    CANCELLED = "cancelled"             # 当前轮次已中止


AgentEventSink = Callable[[dict], Awaitable[None]]
_agent_event_sink: ContextVar[AgentEventSink | None] = ContextVar(
    "multi_agent_event_sink", default=None,
)


def set_agent_event_sink(sink: AgentEventSink) -> Token:
    """Bind an event sink to the current async run and its child tasks."""
    return _agent_event_sink.set(sink)


def reset_agent_event_sink(token: Token) -> None:
    """Restore the event sink that was active before the current run."""
    _agent_event_sink.reset(token)


async def emit_agent_event(
    event: MultiAgentEvent | str,
    data: dict | None = None,
) -> None:
    """Forward an execution event when the caller is inside a streamed run.

    A ContextVar keeps concurrent sessions isolated while allowing nested
    SubAgent graphs and tool nodes to publish into the MainAgent stream.
    Non-streaming ``arun`` calls intentionally ignore these notifications.
    """
    sink = _agent_event_sink.get()
    if sink is None:
        return
    await sink({"event": str(event), "data": data or {}})


# ── 事件元数据 (API 文档用) ──
EVENT_SCHEMAS: dict[str, str] = {
    MultiAgentEvent.START:              "{session_id}",
    MultiAgentEvent.TURN_STARTED:       "{session_id, turn_id}",
    MultiAgentEvent.DONE:               "{session_id}",
    MultiAgentEvent.STATUS:             "{agent, node, message}",
    MultiAgentEvent.ANALYZING:          "{}",
    MultiAgentEvent.ANALYSIS_DONE:      "{task_summary, complexity, needs_subagents}",
    MultiAgentEvent.PLAN_CREATED:       "{plan: [{step_id, description, subagent_type}]}",
    MultiAgentEvent.DISPATCHING:        "{step_id, subagent_type}",
    MultiAgentEvent.SUBAGENT_START:     "{subagent_type, step_id}",
    MultiAgentEvent.SUBAGENT_PLAN:      "{subagent_type, plan: [{step_id, description}]}",
    MultiAgentEvent.SUBAGENT_STEP:      "{subagent_type, step_id, description, status}",
    MultiAgentEvent.SUBAGENT_PROGRESS:  "{subagent_type, progress}",
    MultiAgentEvent.SUBAGENT_DONE:      "{subagent_type, result_summary, success}",
    MultiAgentEvent.SYNTHESIZING:       "{}",
    MultiAgentEvent.SYNTHESIS_DONE:     "{answer, sources, confidence}",
    MultiAgentEvent.TOOL_CALL:          "{agent, tool_name, args}",
    MultiAgentEvent.TOOL_RESULT:        "{agent, tool_name, result_summary}",
    MultiAgentEvent.TOKEN:              "{text, agent}",
    MultiAgentEvent.ERROR:              "{code, message, agent}",
    MultiAgentEvent.CANCELLED:          "{turn_id, message}",
}
