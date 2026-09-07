"""
===========================================================================
多智能体系统 — Pydantic 数据模型
===========================================================================

用于 LLM 结构化输出 (with_structured_output) 和 API 请求/响应序列化。
===========================================================================
"""

from typing import Literal

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════
# 计划步骤
# ═══════════════════════════════════════════════════════════════════════

class PlanStep(BaseModel):
    """MainAgent 计划中的一个步骤"""
    step_id: int = Field(description="步骤序号 (从1开始)")
    description: str = Field(description="该步骤的任务描述")
    subagent_type: str | None = Field(
        default=None,
        description="分配给哪个 subagent (None = main_agent 直接处理)",
    )
    input_summary: str = Field(
        default="",
        description="传递给 subagent 的任务输入摘要",
    )
    depends_on: list[int] = Field(
        default_factory=list,
        description="依赖的前置步骤 ID 列表",
    )


class SubStep(BaseModel):
    """SubAgent 自己计划中的一个子步骤"""
    step_id: int = Field(description="子步骤序号 (从1开始)")
    description: str = Field(description="该子步骤的描述")
    tool_hint: str | None = Field(
        default=None,
        description="预期使用的工具名称提示 (可选)",
    )


# ═══════════════════════════════════════════════════════════════════════
# 任务分析
# ═══════════════════════════════════════════════════════════════════════

class TaskAnalysis(BaseModel):
    """MainAgent.analyze_task 的结构化输出"""
    intent: Literal[
        "chat", "new_task", "follow_up", "revise_task", "continue_task",
    ] = Field(description="当前输入相对会话历史的意图类型")
    resolved_task: str = Field(description="结合上下文消解后的完整可执行任务")
    referenced_turn_ids: list[str] = Field(
        description="当前任务明确引用的历史轮次 ID",
    )
    reuse_previous_artifacts: bool = Field(
        description="是否复用历史计划、执行结果或中止进度",
    )
    needs_subagents: bool = Field(
        description="是否需要多智能体协作",
    )
    task_summary: str = Field(
        description="对用户任务的结构化摘要",
    )
    complexity: str = Field(
        description="任务复杂度: simple / medium / complex",
    )
    suggested_approach: str = Field(
        description="建议的处理方式描述",
    )


# ═══════════════════════════════════════════════════════════════════════
# 委托与结果
# ═══════════════════════════════════════════════════════════════════════

class DelegationRequest(BaseModel):
    """MainAgent 向 SubAgent 发出的委托请求"""
    task: str = Field(description="分配给 subagent 的具体任务描述")
    context: str = Field(default="", description="来自前置步骤的上下文/结果")
    subagent_type: str = Field(description="目标 subagent 类型")


class SubAgentResult(BaseModel):
    """SubAgent 返回给 MainAgent 的结果"""
    subagent_type: str = Field(description="subagent 类型标识")
    success: bool = Field(description="是否成功完成任务")
    result: str = Field(description="任务执行结果文本")
    steps_completed: int = Field(default=0, description="完成的子步骤数")
    evaluation: str = Field(default="", description="自我评估结果")


# ═══════════════════════════════════════════════════════════════════════
# 综合结果
# ═══════════════════════════════════════════════════════════════════════

class SynthesisResult(BaseModel):
    """MainAgent.synthesize 的结构化输出"""
    answer: str = Field(description="综合后的最终回答")
    sources: list[str] = Field(
        default_factory=list,
        description="引用的 subagent 结果来源 (step_id 列表)",
    )
    confidence: str = Field(
        default="medium",
        description="综合结果的置信度: low / medium / high",
    )
