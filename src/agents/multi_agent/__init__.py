"""多智能体系统 — 公开导出

快速开始:
    from agents.multi_agent import (
        MainAgent, SubAgent, SubAgentRegistry, SubAgentMeta,
        create_default_registry,
    )

    registry = create_default_registry()
    main = MainAgent(sub_agent_registry=registry)
    main.initialize()
    answer = main.run("帮我分析数据并生成报告")
"""

from .states import MainAgentState, SubAgentState
from .schemas import (
    PlanStep, SubStep, TaskAnalysis,
    DelegationRequest, SubAgentResult, SynthesisResult,
)
from .events import MultiAgentEvent, EVENT_SCHEMAS
from .sub_agent_registry import SubAgentRegistry, SubAgentMeta
from .sub_agent import SubAgent
from .main_agent import MainAgent
from ...prompt import (
    GENERAL_ASSISTANT_CAPABILITIES,
    GENERAL_ASSISTANT_DESCRIPTION,
    WORKSPACE_FILE_AGENT_CAPABILITIES,
    WORKSPACE_FILE_AGENT_DESCRIPTION,
    VISION_AGENT_CAPABILITIES,
    VISION_AGENT_DESCRIPTION,
)
from ...tools.backend_api.tavily_tools import TAVILY_TOOLS, TAVILY_TOOLS_META

def _filter_mcp(
    tools: list | None,
    metas: dict[str, dict] | None,
    subagent_type: str,
    *,
    include_wildcard: bool = True,
) -> tuple[list, dict[str, dict]]:
    """按 subagents 字段过滤 MCP 工具，只保留属于该 subagent 类型的。"""
    tools = tools or []
    metas = metas or {}
    out_tools: list = []
    out_metas: dict[str, dict] = {}
    for t in tools:
        allowed = metas.get(t.name, {}).get("subagents", ["*"])
        if subagent_type in allowed or (include_wildcard and "*" in allowed):
            out_tools.append(t)
            out_metas[t.name] = metas[t.name]
    return out_tools, out_metas


def create_default_registry(
    mcp_tools: list | None = None,
    mcp_tools_meta: dict[str, dict] | None = None,
    model_kwargs: dict | None = None,
) -> SubAgentRegistry:
    """创建预置了通用 subagent 类型的注册中心

    用户可以调用 registry.register() 添加更多 subagent 类型。
    mcp_tools/mcp_tools_meta 按 server 的 subagents 字段分配到各预置 SubAgent。
    model_kwargs 用于让所有预置 SubAgent 使用同一份运行时模型配置。
    """
    registry = SubAgentRegistry()

    ga_tools, ga_metas = _filter_mcp(mcp_tools, mcp_tools_meta, "general_assistant")
    file_tools, file_metas = _filter_mcp(
        mcp_tools, mcp_tools_meta, "workspace_file_agent", include_wildcard=False,
    )
    vision_tools, vision_metas = _filter_mcp(
        mcp_tools, mcp_tools_meta, "vision_agent", include_wildcard=False,
    )

    # 注册一个通用子智能体 (示例)
    registry.register(SubAgentMeta(
        subagent_type="general_assistant",
        display_name="通用子智能体",
        description=GENERAL_ASSISTANT_DESCRIPTION,
        capabilities=GENERAL_ASSISTANT_CAPABILITIES,
        factory=lambda: SubAgent(
            name="GeneralAssistant",
            subagent_type="general_assistant",
            description=GENERAL_ASSISTANT_DESCRIPTION,
            capabilities=GENERAL_ASSISTANT_CAPABILITIES,
            api_tools=TAVILY_TOOLS,
            api_tools_meta=TAVILY_TOOLS_META,
            mcp_tools=ga_tools,
            mcp_tools_meta=ga_metas,
            model_kwargs=model_kwargs,
        ),
    ))

    registry.register(SubAgentMeta(
        subagent_type="workspace_file_agent",
        display_name="工作区文件助手",
        description=WORKSPACE_FILE_AGENT_DESCRIPTION,
        capabilities=WORKSPACE_FILE_AGENT_CAPABILITIES,
        factory=lambda: SubAgent(
            name="WorkspaceFileAgent",
            subagent_type="workspace_file_agent",
            description=WORKSPACE_FILE_AGENT_DESCRIPTION,
            capabilities=WORKSPACE_FILE_AGENT_CAPABILITIES,
            mcp_tools=file_tools,
            mcp_tools_meta=file_metas,
            model_kwargs=model_kwargs,
        ),
    ))

    registry.register(SubAgentMeta(
        subagent_type="vision_agent",
        display_name="视觉助手",
        description=VISION_AGENT_DESCRIPTION,
        capabilities=VISION_AGENT_CAPABILITIES,
        factory=lambda: SubAgent(
            name="VisionAgent",
            subagent_type="vision_agent",
            description=VISION_AGENT_DESCRIPTION,
            capabilities=VISION_AGENT_CAPABILITIES,
            mcp_tools=vision_tools,
            mcp_tools_meta=vision_metas,
            model_kwargs=model_kwargs,
        ),
    ))

    return registry


__all__ = [
    # Agents
    "MainAgent", "SubAgent",
    # States
    "MainAgentState", "SubAgentState",
    # Schemas
    "PlanStep", "SubStep", "TaskAnalysis",
    "DelegationRequest", "SubAgentResult", "SynthesisResult",
    # Events
    "MultiAgentEvent", "EVENT_SCHEMAS",
    # Registry
    "SubAgentRegistry", "SubAgentMeta",
    "create_default_registry",
]
