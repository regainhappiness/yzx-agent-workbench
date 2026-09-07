"""
===========================================================================
L2: task_analyzer — 分析用户任务
===========================================================================

MainAgent.analyze_task 节点使用。
将用户自然语言任务转化为结构化分析结果。
===========================================================================
"""
from typing import Literal

from pydantic import BaseModel, Field
from ...prompt.planning import ANALYZE_TASK_PROMPT


# ═══════════════════════════════════════════════════════════════════════
# Prompt 模板
# ═══════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════
# 结构化输出模型
# ═══════════════════════════════════════════════════════════════════════

class TaskAnalysisOutput(BaseModel):
    """任务分析的结构化输出"""
    intent: Literal[
        "chat", "new_task", "follow_up", "revise_task", "continue_task",
    ] = Field(description="当前输入相对会话历史的意图类型")
    resolved_task: str = Field(
        description="结合上下文消解指代后的完整、可独立执行任务",
    )
    referenced_turn_ids: list[str] = Field(
        description="当前任务明确引用的历史 turn_id；没有则为空数组",
    )
    reuse_previous_artifacts: bool = Field(
        description="是否需要复用历史计划、执行结果或中止进度",
    )
    needs_subagents: bool = Field(
        description="是否需要子智能体协作",
    )
    task_summary: str = Field(
        description="对用户任务的结构化摘要 (1-3 句话)",
    )
    complexity: Literal["simple", "medium", "complex"] = Field(
        description="任务复杂度: simple / medium / complex",
    )
    suggested_subagents: list[str] = Field(
        description="建议调用的 subagent 类型列表 (从可用列表中选取)",
    )
    reason: str = Field(
        description="简要说明为什么选择 (或不需要) 子智能体",
    )


# ═══════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════

def analyze_user_task(
    user_task: str,
    subagent_list: str = "（无可用子智能体）",
    conversation_context: str = "（无历史对话）",
    conversation_summary: str = "（无历史摘要）",
    previous_artifacts: str = "（无历史任务成果）",
) -> str:
    """构建 task_analyzer 的完整 prompt"""
    return ANALYZE_TASK_PROMPT.format(
        subagent_list=subagent_list,
        user_task=user_task,
        conversation_context=conversation_context,
        conversation_summary=conversation_summary,
        previous_artifacts=previous_artifacts,
    )
