"""
===========================================================================
L2: result_aggregator — 合并 subagent 结果
===========================================================================

MainAgent.synthesize 节点使用。
收集所有 subagent 返回的结果，综合为最终回答。
===========================================================================
"""

from pydantic import BaseModel, Field
from ...prompt.planning import AGGREGATE_PROMPT


# ═══════════════════════════════════════════════════════════════════════
# Prompt 模板
# ═══════════════════════════════════════════════════════════════════════

class AggregationOutput(BaseModel):
    """综合结果的结构化输出"""
    answer: str = Field(description="综合后的最终回答")
    sources: list[str] = Field(
        default_factory=list,
        description="引用的来源 (subagent_type:step_id 列表)",
    )
    confidence: str = Field(
        default="medium",
        description="综合结果的置信度: low / medium / high",
    )
    missing_info: str = Field(
        default="",
        description="未能覆盖的信息或建议的补充步骤",
    )


def aggregate_results(
    user_task: str,
    step_results: str,
) -> str:
    """构建结果聚合 prompt"""
    return AGGREGATE_PROMPT.format(
        user_task=user_task,
        step_results=step_results,
    )
