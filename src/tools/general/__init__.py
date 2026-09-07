"""
===========================================================================
Level 1 — 通用 tools
===========================================================================

所有 Agent (main_agent + subagent) 共享的基础工具。
从现有 tools/base.py 导入内置工具，保持向后兼容。

使用:
    from tools.general import GENERAL_TOOLS

    # 每个 agent 创建自己的 ToolRegistry 时注册:
    registry.register_many(GENERAL_TOOLS, category="general")
===========================================================================
"""

from ..base import get_current_time

# 所有 Agent 可用的通用工具集
GENERAL_TOOLS = [get_current_time]

__all__ = ["GENERAL_TOOLS", "get_current_time"]
