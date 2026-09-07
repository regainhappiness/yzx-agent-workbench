"""
===========================================================================
L2: delegation_builder — 构建委托指令
===========================================================================

MainAgent.execute 节点的 dispatch_to_subagent 使用。
将计划步骤 + 前置结果转化为 SubAgent 可理解的委托请求。
===========================================================================
"""

from pydantic import BaseModel, Field
from ...prompt.planning import DELEGATION_PROMPT


# ═══════════════════════════════════════════════════════════════════════
# Prompt 模板
# ═══════════════════════════════════════════════════════════════════════

class DelegationOutput(BaseModel):
    """委托指令的结构化输出"""
    task: str = Field(description="分配给 subagent 的完整任务描述")
    context: str = Field(description="来自前置步骤的上下文/数据")
    expected_output: str = Field(description="期望的输出格式说明")


def build_delegation(
    step_id: int,
    description: str,
    subagent_type: str,
    context: str = "",
    user_task: str = "",
) -> str:
    """构建委托指令 prompt"""
    return DELEGATION_PROMPT.format(
        step_id=step_id,
        description=description,
        subagent_type=subagent_type,
        context=context or "（无前置步骤）",
        user_task=user_task,
    )
