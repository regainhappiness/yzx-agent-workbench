"""
===========================================================================
L2: subagent_matcher — 匹配任务到最佳 subagent
===========================================================================

MainAgent.plan 节点使用。
将分析结果转化为具体的 subagent 选择 + 执行计划。
===========================================================================
"""

from pydantic import BaseModel, Field, field_validator
from ...prompt.planning import MATCH_SUBAGENT_PROMPT


# ═══════════════════════════════════════════════════════════════════════
# Prompt 模板
# ═══════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════
# 结构化输出模型
# ═══════════════════════════════════════════════════════════════════════

class PlanStepOutput(BaseModel):
    """单个计划步骤 (LLM 输出的格式)"""
    step_id: int = Field(description="步骤序号, 从 1 开始")
    description: str = Field(description="该步骤的详细任务描述")
    subagent_type: str | None = Field(
        default=None,
        description="分配给哪个 subagent 类型 (不需要子智能体则留空)",
    )

    @field_validator("subagent_type", mode="before")
    @classmethod
    def normalize_subagent_type(cls, value):
        """将模型返回的空字符串统一视为无需子智能体。"""
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value
    input_summary: str = Field(
        default="",
        description="传递给 subagent 的输入摘要",
    )
    depends_on: list[int] = Field(
        default_factory=list,
        description="依赖的前置步骤 ID 列表",
    )


class SubagentMatchOutput(BaseModel):
    """subagent 匹配 + 计划的完整输出"""
    plan: list[PlanStepOutput] = Field(
        description="执行计划步骤列表",
    )
    overall_strategy: str = Field(
        description="整体执行策略说明 (1-2 句话)",
    )


# ═══════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════

def build_selection_context(subagent_descriptions: list[str]) -> str:
    """构建 subagent 选择上下文 (纯文本列表)"""
    if not subagent_descriptions:
        return "## 可用的子智能体\n（无）"
    return "## 可用的子智能体\n" + "\n".join(subagent_descriptions)


def match_subagents(
    user_task: str,
    task_summary: str,
    subagent_context: str,
) -> str:
    """构建 subagent_matcher 的完整 prompt"""
    return MATCH_SUBAGENT_PROMPT.format(
        subagent_context=subagent_context,
        user_task=user_task,
        task_summary=task_summary,
    )
