"""
===========================================================================
L3: self_evaluator — 评估结果质量
===========================================================================

SubAgent.evaluate 节点使用。
对自己执行的结果进行自我评估，判断是否需要修正。
===========================================================================
"""

from pydantic import BaseModel, Field
from ...prompt.planning import EVALUATE_PROMPT


# ═══════════════════════════════════════════════════════════════════════
# Prompt 模板
# ═══════════════════════════════════════════════════════════════════════

class EvaluationOutput(BaseModel):
    """自评结果的结构化输出"""
    needs_revision: bool = Field(
        description="是否需要修正",
    )
    completeness: str = Field(
        description="完整性评估: complete / partial / incomplete",
    )
    accuracy: str = Field(
        description="准确性评估: accurate / uncertain / inaccurate",
    )
    feedback: str = Field(
        description="具体的改进建议 (如果 needs_revision=True)",
    )
    ready_for_main_agent: bool = Field(
        description="结果是否可以直接返回给主智能体",
    )


def evaluate_result(
    assigned_task: str,
    plan_summary: str,
    execution_results: str,
) -> str:
    """构建自评 prompt"""
    return EVALUATE_PROMPT.format(
        assigned_task=assigned_task,
        plan_summary=plan_summary,
        execution_results=execution_results,
    )
