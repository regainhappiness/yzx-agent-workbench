"""
===========================================================================
多智能体系统 — LangGraph 状态定义
===========================================================================

MainAgentState:  主编排器的图状态
SubAgentState:   子执行器的图状态 (Plan-and-Solve)
===========================================================================
"""

import operator
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage


# ═══════════════════════════════════════════════════════════════════════
# MainAgent — 编排器状态
# ═══════════════════════════════════════════════════════════════════════

class MainAgentState(TypedDict, total=False):
    """MainAgent LangGraph 状态

    对话消息由服务层的 SessionMessageRepository 持久化。这里仅保存当前轮
    的上下文快照和编排状态，避免把分析、计划、工具状态混入用户对话。

    当前运行周期字段:
      - user_task: 原始用户任务
      - needs_subagents: 是否需要多智能体协作
      - plan: 生成的执行计划 (PlanStep 列表)
      - current_step_index: 当前执行到的步骤索引
      - subagent_results: {step_id: result_text}
      - synthesized_answer: 综合后的最终回答
      - iteration_count: 安全计数器
    """

    # ── 当前对话轮次 ──
    turn_id: str
    current_input: str
    conversation_context: list[dict]
    conversation_summary: str
    resource_context: str
    previous_artifacts: list[dict]
    resumed_from_turn_id: str

    # ── 任务分析 ──
    user_task: str
    resolved_task: str
    intent: str
    referenced_turn_ids: list[str]
    reuse_previous_artifacts: bool
    needs_subagents: bool
    task_summary: str

    # ── 计划 ──
    plan: list[dict]          # [{step_id, description, subagent_type, input}]
    plan_raw: str             # LLM 原始输出 (调试用)

    # ── 执行 ──
    current_step_index: int
    subagent_results: dict[str, str]    # {step_id → result_text}
    subagent_statuses: dict[str, str]   # {step_id → pending|running|success|failed}

    step_retry_counts: dict[str, int]   # {step_id → failed attempt count}

    # ── 综合 ──
    synthesized_answer: str
    synthesis_sources: list[str]
    synthesis_confidence: str

    # ── 安全 ──
    iteration_count: int


# ═══════════════════════════════════════════════════════════════════════
# SubAgent — Plan-and-Solve 执行器状态
# ═══════════════════════════════════════════════════════════════════════

class SubAgentState(TypedDict, total=False):
    """SubAgent LangGraph 状态

    通过 checkpointer 持久化的字段:
      - messages: 对话历史 (ReAct 循环中累积)

    临时字段:
      - assigned_task: MainAgent 分配的任务描述
      - sub_plan: 自己生成的子步骤列表
      - current_step_index: 当前执行步骤
      - step_results: {step_id → output}
      - final_result: 返回给 MainAgent 的结果
      - self_evaluation: 自我评估结果
      - needs_revision: 是否需要修正计划
      - iteration_count: 安全计数器
    """

    # ── 对话历史 (checkpointer 管理) ──
    messages: Annotated[list[BaseMessage], operator.add]

    # ── 任务 ──
    assigned_task: str
    subagent_type: str

    # ── 计划 ──
    sub_plan: list[dict]      # [{step_id, description, tool_hint}]
    plan_raw: str

    # ── 执行 ──
    current_step_index: int
    step_results: dict[str, str]   # {step_id → output_text}

    # ── 评估与输出 ──
    final_result: str
    self_evaluation: str
    needs_revision: bool

    # ── 安全 ──
    iteration_count: int
    react_iteration_count: int
