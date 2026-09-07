"""
===========================================================================
工具注册中心 — 统一管理所有工具
===========================================================================

功能:
  - 注册/注销工具
  - 按名称、分类、标签查询
  - 列出所有已注册工具
  - 绑定工具到模型 (bind_tools)

使用:
    from tools import ToolRegistry, BUILTIN_TOOLS

    registry = ToolRegistry()
    registry.register_many(BUILTIN_TOOLS)

    # 查询
    tools = registry.list_all()
    utility_tools = registry.get_by_tag("计算")

    # 绑定到模型
    model_with_tools = registry.bind_to_model(model)
===========================================================================
"""
from langchain_core.tools import BaseTool
from langchain_core.language_models import BaseChatModel

from ..utils.logger import get_logger

logger = get_logger(__name__)


class ToolMeta:
    """工具元数据"""
    def __init__(self, name: str, description: str ="", category: str = "general",
                 tags: list[str] = None, version: str = "1.0.0"):
        self.name = name
        self.description = description
        self.category = category
        self.tags = tags or []
        self.version = version


class ToolRegistry:
    """工具注册中心

    管理所有可用工具，支持:
      - 注册/批量注册/注销
      - 按名称、分类、标签查询
      - 绑定工具到 LLM 模型
    """

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}    # name → tool
        self._metadata: dict[str, ToolMeta] = {} # name → metadata

    # ═══ 注册 ═══
    def register(self, tool: BaseTool, category: str = "general",
                 tags: list[str] = None, version: str = "1.0.0"):
        """注册单个工具

        参数:
            tool:     LangChain BaseTool 实例
            category: 工具分类 (utility / search / database / ...)
            tags:     标签列表
            version:  版本号
        """
        self._tools[tool.name] = tool
        self._metadata[tool.name] = ToolMeta(
            name=tool.name,
            description=tool.description,
            category=category,
            tags=tags or [],
            version=version,
        )
        logger.info(f"📦 注册工具: [{category}] {tool.name} v{version}")

    def register_many(self, tools: list[BaseTool], category: str = "general"):
        """批量注册工具 (所有工具归入同一分类)"""
        for tool in tools:
            self.register(tool, category=category)

    def register_with_meta(self, tools: list[BaseTool], metas: dict[str, dict]):
        """批量注册工具并附带元数据

        参数:
            tools: 工具列表
            metas: {tool_name: {category, tags, version}} 元数据字典
        """
        for tool in tools:
            meta = metas.get(tool.name, {})
            self.register(
                tool,
                category=meta.get("category", "general"),
                tags=meta.get("tags", []),
                version=meta.get("version", "1.0.0"),
            )

    # ═══ 注销 ═══
    def unregister(self, name: str):
        """注销工具"""
        self._tools.pop(name, None)
        self._metadata.pop(name, None)
        logger.info(f"🗑️ 注销工具: {name}")

    # ═══ 查询 ═══
    def get(self, name: str) -> BaseTool | None:
        """按名称获取工具"""
        return self._tools.get(name)

    def get_by_tag(self, tag: str) -> list[BaseTool]:
        """按标签筛选工具"""
        return [
            tool for name, tool in self._tools.items()
            if tag in self._metadata.get(name, ToolMeta(name)).tags
        ]

    def get_by_category(self, category: str) -> list[BaseTool]:
        """按分类筛选工具"""
        return [
            tool for name, tool in self._tools.items()
            if self._metadata.get(name, ToolMeta(name)).category == category
        ]

    def list_all(self) -> list[BaseTool]:
        """列出所有已注册工具"""
        return list(self._tools.values())

    def list_names(self) -> list[str]:
        """列出所有工具名称"""
        return list(self._tools.keys())

    # ═══ 模型绑定 ═══
    def bind_to_model(self, model: BaseChatModel,
                      tool_names: list[str] | None = None) -> BaseChatModel:
        """将工具绑定到模型

        参数:
            model:      LangChain ChatModel 实例
            tool_names: 要绑定的工具名称列表 (None=绑定全部)

        返回:
            带有工具绑定能力的模型实例
        """
        if tool_names:
            tools = [self._tools[name] for name in tool_names if name in self._tools]
        else:
            tools = self.list_all()

        logger.info(f"🔗 绑定 {len(tools)} 个工具到模型: {[t.name for t in tools]}")
        return model.bind_tools(tools)

    # ═══ 信息 ═══
    def summary(self) -> str:
        """打印工具注册中心概览"""
        lines = [f"📦 工具注册中心: {len(self._tools)} 个工具"]
        by_category: dict[str, list[str]] = {}
        for name, meta in self._metadata.items():
            by_category.setdefault(meta.category, []).append(name)

        for cat, names in sorted(by_category.items()):
            lines.append(f"  [{cat}] {', '.join(names)}")
        return "\n".join(lines)

    @property
    def tool_count(self) -> int:
        return len(self._tools)
