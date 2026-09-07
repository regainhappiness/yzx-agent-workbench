"""
===========================================================================
Level 2 — 多智能体规划 tools
===========================================================================

MainAgent 在 graph node 内部使用这些工具函数进行规划。
不作为 LLM tool (不通过 bind_tools 暴露), 而是 graph node 内部调用
model.with_structured_output(PydanticModel) 获取结构化输出。

每个模块提供:
  - PROMPT_TEMPLATE: 提示词模板
  - OutputModel: Pydantic 输出模型 (用于 with_structured_output)
===========================================================================
"""

from .task_analyzer import (
    ANALYZE_TASK_PROMPT, TaskAnalysisOutput,
    analyze_user_task,
)
from .subagent_matcher import (
    MATCH_SUBAGENT_PROMPT, SubagentMatchOutput,
    match_subagents,
    build_selection_context,
)
from .delegation_builder import (
    DELEGATION_PROMPT,
    build_delegation,
)
from .result_aggregator import (
    AGGREGATE_PROMPT, AggregationOutput,
    aggregate_results,
)
from .plan_adjuster import (
    ADJUST_PLAN_PROMPT, AdjustedPlanOutput,
    adjust_plan,
)

__all__ = [
    # task_analyzer
    "ANALYZE_TASK_PROMPT", "TaskAnalysisOutput", "analyze_user_task",
    # subagent_matcher
    "MATCH_SUBAGENT_PROMPT", "SubagentMatchOutput",
    "match_subagents", "build_selection_context",
    # delegation_builder
    "DELEGATION_PROMPT", "build_delegation",
    # result_aggregator
    "AGGREGATE_PROMPT", "AggregationOutput", "aggregate_results",
    # plan_adjuster
    "ADJUST_PLAN_PROMPT", "AdjustedPlanOutput", "adjust_plan",
]
