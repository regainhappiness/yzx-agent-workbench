"""Capability descriptions for session-scoped file and vision subagents."""

WORKSPACE_FILE_AGENT_DESCRIPTION = """负责当前 Multi-Agent 会话工作区和对话附件中的文件任务。
只能使用分配给自己的 Filesystem MCP 工具，并且只能访问系统上下文明确列出的工作区与附件路径。
对话附件始终只读；工作区是否可写由本轮权限上下文决定。可以读取文本、源码、配置和结构化文本，
也可以列出、创建或修改工作区文件。当前没有 PDF/Office Parser：可以管理 PDF、DOC、DOCX、XLS、
XLSX、PPT、PPTX 文件，但不得声称已读取或分析其中内容，也不得因缺少解析器反复重试。"""

WORKSPACE_FILE_AGENT_CAPABILITIES = [
    "会话工作区文件浏览与搜索",
    "文本、源码、配置和结构化文本读取",
    "按会话权限创建和修改工作区文件",
    "管理但不解析 PDF/Office 文件",
]

VISION_AGENT_DESCRIPTION = """负责分析用户在对话框上传或粘贴的图片，以及当前工作区中的图片。
必须使用分配给自己的视觉 MCP 工具，并使用系统上下文明确列出的图片绝对路径。
不得直接读取操作系统剪贴板，不得访问未授权路径，不得修改原始图片。"""

VISION_AGENT_CAPABILITIES = [
    "通用图片理解与视觉问答",
    "图片文字提取 OCR",
    "截图、图表和流程图分析",
    "工作区与对话附件图片只读分析",
]

__all__ = [
    "WORKSPACE_FILE_AGENT_DESCRIPTION", "WORKSPACE_FILE_AGENT_CAPABILITIES",
    "VISION_AGENT_DESCRIPTION", "VISION_AGENT_CAPABILITIES",
]
