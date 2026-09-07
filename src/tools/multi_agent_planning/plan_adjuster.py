"""
===========================================================================
L2: plan_adjuster — 失败时重新规划
===========================================================================

MainAgent.replan 节点使用。
当某个 subagent 执行失败时，调整后续计划。
===========================================================================
"""

from pydantic import BaseModel, Field
from ...prompt.planning import ADJUST_PLAN_PROMPT


# ═══════════════════════════════════════════════════════════════════════
# Prompt 模板
# ═══════════════════════════════════════════════════════════════════════

class AdjustedPlanStep(BaseModel):
    """调整后的计划步骤"""
    step_id: int = Field(description="步骤序号 (延续原始编号)")
    description: str = Field(description="调整后的任务描述")
    subagent_type: str | None = Field(default=None)
    input_summary: str = Field(default="")
    depends_on: list[int] = Field(default_factory=list)
    action: str = Field(description="retry / replace / skip / degrade")


class AdjustedPlanOutput(BaseModel):
    """调整后计划的结构化输出"""
    adjusted_plan: list[AdjustedPlanStep] = Field(description="调整后的剩余步骤")
    strategy: str = Field(description="调整策略说明")


def adjust_plan(
    user_task: str,
    original_plan: str,
    completed_steps: str,
    failed_step: str,
    error_info: str = "",
) -> str:
    """构建计划调整 prompt"""
    return ADJUST_PLAN_PROMPT.format(
        user_task=user_task,
        original_plan=original_plan,
        completed_steps=completed_steps,
        failed_step=failed_step,
        error_info=error_info or "未知错误",
    )
