"""
===========================================================================
SubAgentRegistry — subagent 注册中心
===========================================================================

MainAgent 通过注册中心发现可用的 subagent 类型。

新增 subagent 只需:
  1. 定义它的 L4 API tools 列表
  2. 调用 registry.register(SubAgentMeta(...))

模式: 与 ToolRegistry 一致 — 基于 dict 的内存注册表。
===========================================================================
"""

from dataclasses import dataclass, field
from typing import Callable


# ═══════════════════════════════════════════════════════════════════════
# SubAgentMeta — subagent 类型描述
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class SubAgentMeta:
    """subagent 类型元数据

    注册后, MainAgent 通过 build_selection_prompt() 将元数据注入 Planner prompt,
    LLM 根据 description + capabilities 选择合适的 subagent。
    """

    subagent_type: str            # 唯一标识, 如 "data_analyst"
    display_name: str             # 人类可读名称, 如 "数据分析助手"
    description: str              # LLM 选择依据 — 描述该 subagent 擅长什么
    capabilities: list[str] = field(default_factory=list)  # 能力标签
    factory: Callable | None = None   # 懒加载工厂函数 → SubAgent 实例

    def __post_init__(self):
        if self.factory is None:
            # 默认工厂 — 子类或注册时覆盖
            self.factory = lambda: None

    def to_prompt_line(self, index: int = 1) -> str:
        """格式化为一行 Prompt 描述 (注入 MainAgent plan 的 system prompt)"""
        caps = ", ".join(self.capabilities) if self.capabilities else "通用"
        return (
            f"  {index}. **{self.subagent_type}** ({self.display_name}): "
            f"{self.description} [能力: {caps}]"
        )


# ═══════════════════════════════════════════════════════════════════════
# SubAgentRegistry
# ═══════════════════════════════════════════════════════════════════════

class SubAgentRegistry:
    """subagent 类型注册中心

    使用:
        registry = SubAgentRegistry()
        registry.register(SubAgentMeta(
            subagent_type="data_analyst",
            display_name="数据分析助手",
            description="擅长数据库查询、统计分析",
            capabilities=["data_query", "statistics"],
            factory=lambda: DataAnalystSubAgent(...),
        ))

        # 列出所有
        for meta in registry.list_all():
            print(meta.display_name)

        # 注入 Prompt
        prompt_context = registry.build_selection_prompt()
    """

    def __init__(self):
        self._entries: dict[str, SubAgentMeta] = {}

    # ── 注册 / 注销 ──

    def register(self, meta: SubAgentMeta) -> None:
        """注册一个 subagent 类型"""
        if meta.subagent_type in self._entries:
            import logging
            logging.getLogger(__name__).warning(
                "subagent '%s' 已存在，将被覆盖", meta.subagent_type
            )
        self._entries[meta.subagent_type] = meta

    def unregister(self, subagent_type: str) -> None:
        """注销一个 subagent 类型"""
        self._entries.pop(subagent_type, None)

    # ── 查询 ──

    def get(self, subagent_type: str) -> SubAgentMeta | None:
        """按类型名查找"""
        return self._entries.get(subagent_type)

    def list_all(self) -> list[SubAgentMeta]:
        """列出所有已注册的 subagent 类型"""
        return list(self._entries.values())

    def list_types(self) -> list[str]:
        """列出所有已注册的 subagent 类型名"""
        return list(self._entries.keys())

    def find_by_capability(self, capability: str) -> list[SubAgentMeta]:
        """按能力标签查找匹配的 subagent"""
        return [
            meta for meta in self._entries.values()
            if capability in meta.capabilities
        ]

    # ── Prompt 注入 ──

    def build_selection_prompt(self) -> str:
        """构建 subagent 选择 Prompt 片段

        将此输出注入 MainAgent.plan 节点的 system prompt,
        LLM 据此决定调用哪些 subagent。
        """
        entries = self.list_all()
        if not entries:
            return "（当前没有可用的子智能体）"

        lines = ["## 可用的子智能体\n"]
        for i, meta in enumerate(entries, 1):
            lines.append(meta.to_prompt_line(i))
        lines.append("")
        lines.append(
            "在生成计划时，请为每个步骤指定合适的 subagent_type（使用上面的标识符）。"
            "如果某步骤不需要子智能体（如直接回复用户），subagent_type 留空。"
        )
        return "\n".join(lines)

    # ── 信息 ──

    @property
    def count(self) -> int:
        return len(self._entries)

    def summary(self) -> str:
        """打印注册中心概览"""
        lines = [f"📦 SubAgentRegistry: {self.count} 个类型"]
        for meta in self._entries.values():
            caps = ", ".join(meta.capabilities) if meta.capabilities else "-"
            lines.append(f"  [{meta.subagent_type}] {meta.display_name} — {caps}")
        return "\n".join(lines)
