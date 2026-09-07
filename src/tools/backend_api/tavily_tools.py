"""
===========================================================================
Tavily 网络搜索工具集（基于 tavily-python SDK）
===========================================================================

封装 Tavily 的 Search / Extract / Map / Crawl / Research / GetResearch
六个 API 端点，暴露为 LangChain tool，供 SubAgent 注入使用。

使用:
    from tools.backend_api.tavily_tools import TAVILY_TOOLS, TAVILY_TOOLS_META

    registry.register(SubAgentMeta(
        ...,
        api_tools=TAVILY_TOOLS,
        api_tools_meta=TAVILY_TOOLS_META,
    ))

需要环境变量:
    TAVILY_API_KEY   # 在 https://app.tavily.com 获取
===========================================================================
"""

import json
import os
from typing import Literal

from langchain_core.tools import tool
from tavily import TavilyClient

_client_instance: TavilyClient | None = None


def _client() -> TavilyClient:
    """懒加载 TavilyClient（从 TAVILY_API_KEY 环境变量读取）。"""
    global _client_instance
    if _client_instance is None:
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            raise RuntimeError("缺少 TAVILY_API_KEY 环境变量，无法使用 Tavily 工具")
        _client_instance = TavilyClient(api_key=api_key)
    return _client_instance


@tool
def tavily_search(
    query: str,
    search_depth: Literal["basic", "advanced"] = "basic",
    topic: Literal["general", "news", "finance"] = "general",
    max_results: int = 5,
    time_range: Literal["day", "week", "month", "year"] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    include_answer: bool = False,
    include_images: bool = False,
) -> str:
    """使用 Tavily 搜索引擎执行网络搜索。

    Args:
        query: 自然语言搜索查询。
        search_depth: 搜索深度，"basic"（快）或 "advanced"（更全面）。
        topic: 搜索类别，"general"、"news" 或 "finance"。
        max_results: 最大返回结果数，默认 5。
        time_range: 按发布时间回溯过滤，"day"、"week"、"month" 或 "year"。
        start_date: 起始日期（YYYY-MM-DD），只返回该日期之后的结果。
        end_date: 结束日期（YYYY-MM-DD），只返回该日期之前的结果。
        include_domains: 只包含这些域名（最多 300 个）。
        exclude_domains: 排除这些域名（最多 150 个）。
        include_answer: 是否在结果中包含对查询的答案摘要。
        include_images: 是否包含相关图片。

    Returns:
        搜索结果 JSON 字符串。
    """
    result = _client().search(
        query=query,
        search_depth=search_depth,
        topic=topic,
        max_results=max_results,
        time_range=time_range,
        start_date=start_date,
        end_date=end_date,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        include_answer=include_answer,
        include_images=include_images,
    )
    return json.dumps(result, ensure_ascii=False, default=str)


@tool
def tavily_extract(
    urls: list[str],
    extract_depth: Literal["basic", "advanced"] = "basic",
    include_images: bool = False,
) -> str:
    """从指定 URL 提取网页正文内容。

    Args:
        urls: 要提取内容的 URL 列表。
        extract_depth: 提取深度，"basic" 或 "advanced"。
        include_images: 是否包含图片。

    Returns:
        提取结果 JSON 字符串。
    """
    result = _client().extract(
        urls=urls,
        extract_depth=extract_depth,
        include_images=include_images,
    )
    return json.dumps(result, ensure_ascii=False, default=str)


@tool
def tavily_map(
    url: str,
    instructions: str | None = None,
) -> str:
    """发现并列出某个网站的内部链接，获得站点结构概览。

    Args:
        url: 要映射的根 URL。
        instructions: 指导映射过程的自然语言指令（可选）。

    Returns:
        站点链接列表 JSON 字符串。
    """
    result = _client().map(url=url, instructions=instructions)
    return json.dumps(result, ensure_ascii=False, default=str)


@tool
def tavily_crawl(
    url: str,
    instructions: str | None = None,
    max_depth: int | None = None,
) -> str:
    """从某个 URL 出发爬取并提取完整网页内容。

    Args:
        url: 开始爬取的根 URL。
        instructions: 指导内容提取的自然语言指令（可选）。
        max_depth: 最大爬取深度（可选）。

    Returns:
        爬取结果 JSON 字符串。
    """
    result = _client().crawl(
        url=url,
        instructions=instructions,
        max_depth=max_depth,
    )
    return json.dumps(result, ensure_ascii=False, default=str)


@tool
def tavily_research(
    input: str,
    model: Literal["mini", "pro", "auto"] = "auto",
    citation_format: Literal["numbered", "mla", "apa", "chicago"] = "numbered",
) -> str:
    """创建深度研究任务，生成结构化研究报告。

    Args:
        input: 要研究的任务或问题。
        model: 研究模型，"mini"（快）、"pro"（深）或 "auto"。
        citation_format: 引用格式，"numbered"、"mla"、"apa" 或 "chicago"。

    Returns:
        研究任务信息 JSON 字符串（含 request_id，可用 tavily_get_research 查询结果）。
    """
    result = _client().research(
        input=input,
        model=model,
        citation_format=citation_format,
    )
    return json.dumps(result, ensure_ascii=False, default=str)


@tool
def tavily_get_research(request_id: str) -> str:
    """根据 request_id 查询某个研究任务的最终结果。

    Args:
        request_id: 研究任务的唯一标识（由 tavily_research 返回）。

    Returns:
        研究报告 JSON 字符串。
    """
    result = _client().get_research(request_id)
    return json.dumps(result, ensure_ascii=False, default=str)


TAVILY_TOOLS = [
    tavily_search,
    tavily_extract,
    tavily_map,
    tavily_crawl,
    tavily_research,
    tavily_get_research,
]

TAVILY_TOOLS_META = {
    "tavily_search": {"category": "tavily", "tags": ["搜索", "网络"], "version": "0.1.0"},
    "tavily_extract": {"category": "tavily", "tags": ["提取", "网页内容"], "version": "0.1.0"},
    "tavily_map": {"category": "tavily", "tags": ["站点地图", "发现链接"], "version": "0.1.0"},
    "tavily_crawl": {"category": "tavily", "tags": ["爬取", "内容提取"], "version": "0.1.0"},
    "tavily_research": {"category": "tavily", "tags": ["深度研究", "报告"], "version": "0.1.0"},
    "tavily_get_research": {"category": "tavily", "tags": ["研究结果", "查询"], "version": "0.1.0"},
}

__all__ = [
    "tavily_search",
    "tavily_extract",
    "tavily_map",
    "tavily_crawl",
    "tavily_research",
    "tavily_get_research",
    "TAVILY_TOOLS",
    "TAVILY_TOOLS_META",
]
