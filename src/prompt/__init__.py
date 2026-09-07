"""集中管理 Agent 使用的提示词。"""

from .multi_agent import (
    MAIN_AGENT_SYSTEM_PROMPT,
    SUBAGENT_SYSTEM_PROMPT,
    build_delegation_task_prompt,
    build_direct_response_prompt,
    build_direct_step_prompt,
    build_structured_output_retry_prompt,
    build_subagent_step_prompt,
)
from .general_assistant import (
    GENERAL_ASSISTANT_CAPABILITIES,
    GENERAL_ASSISTANT_DESCRIPTION,
)
from .file_agents import (
    WORKSPACE_FILE_AGENT_CAPABILITIES,
    WORKSPACE_FILE_AGENT_DESCRIPTION,
    VISION_AGENT_CAPABILITIES,
    VISION_AGENT_DESCRIPTION,
)
from .chat import DEFAULT_SYSTEM_PROMPT

__all__ = [
    "MAIN_AGENT_SYSTEM_PROMPT",
    "SUBAGENT_SYSTEM_PROMPT",
    "GENERAL_ASSISTANT_CAPABILITIES",
    "GENERAL_ASSISTANT_DESCRIPTION",
    "WORKSPACE_FILE_AGENT_CAPABILITIES",
    "WORKSPACE_FILE_AGENT_DESCRIPTION",
    "VISION_AGENT_CAPABILITIES",
    "VISION_AGENT_DESCRIPTION",
    "DEFAULT_SYSTEM_PROMPT",
    "build_delegation_task_prompt",
    "build_direct_response_prompt",
    "build_direct_step_prompt",
    "build_structured_output_retry_prompt",
    "build_subagent_step_prompt",
]
