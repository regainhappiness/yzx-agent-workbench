"""AdvancedRetrievalService — 带 Query 改写 + 多路检索 + RRF 合并的高阶检索

与 RetrievalService 的关系:
  RetrievalService        — 基础检索: embed → search → dedupe
  AdvancedRetrievalService — 包装 RetrievalService, 增加:
    1. Query 改写   (基于会话上下文 + LLM 生成多条改写查询)
    2. 多路检索     (每条改写查询分别搜索)
    3. RRF 合并     (Reciprocal Rank Fusion 融合排序)

组合优于继承: AdvancedRetrievalService 持有 RetrievalService 实例,
不改动现有基础检索逻辑。
"""

import logging
import math
from langchain_core.messages import BaseMessage

from .retrieval_service import RetrievalService
from ..milvus.client import SearchResult

logger = logging.getLogger("server.advanced_retrieval")

# 查询改写 Prompt 模板
QUERY_REWRITE_PROMPT = """你是一个搜索查询优化专家。根据对话上下文和用户当前问题，生成 1~3 个优化后的搜索查询词。

规则:
1. 如果用户问题本身就是精准的检索查询，直接返回原问题，不要改写。
2. 如果问题模糊或依赖上下文（如 "那个呢"、"继续说"），结合历史补全为完整的检索查询。
3. 如果问题涉及多个方面，生成 2~3 条从不同角度检索的查询词。
4. 每条查询词应简洁、关键词化，适合向量检索。
5. 输出每条查询词占一行，不要编号，不要额外解释。

{context}

用户问题: {query}

优化查询词:

"""

# RRF 参数
RRF_K = 60  # RRF 平滑常数


class AdvancedRetrievalService:
    """高阶检索服务 — Query 改写 + 多路检索 + RRF 重排。

    使用方式:
      svc = AdvancedRetrievalService(base_retrieval, rewrite_llm)
      results = await svc.search(query, scope="hybrid", user_id="...",
                                  messages=[...])
    """

    def __init__(
        self,
        base_retrieval: RetrievalService,
        rewrite_llm=None,
    ):
        """
        Args:
            base_retrieval: 基础 RetrievalService 实例
            rewrite_llm: 用于 query 改写的 LLM (langchain BaseChatModel 兼容)
                         为 None 时跳过改写，退化为单路检索
        """
        self._retrieval = base_retrieval
        self._rewrite_llm = rewrite_llm

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        scope: str = "hybrid",
        user_id: str = "",
        top_k: int = 8,
        messages: list | None = None,
        enable_rewrite: bool = True,
    ) -> list[SearchResult]:
        """高阶检索入口。

        Args:
            query: 用户原始问题
            scope: 检索范围
            user_id: 用户 ID
            top_k: 每种范围最终返回数量
            messages: 会话消息列表 (用于上下文改写)
            enable_rewrite: 是否启用 query 改写 (默认 True)

        Returns:
            合并重排后的 SearchResult 列表
        """
        if not enable_rewrite or not self._rewrite_llm:
            return await self._retrieval.search(query, scope, user_id, top_k)

        # 1. Query 改写
        rewritten_queries = await self._rewrite_query(
            query, messages=messages,
        )

        if not rewritten_queries:
            return []

        logger.info(
            "Query 改写: '%s' → %d 条 (%s)",
            query[:60], len(rewritten_queries),
            [q[:40] for q in rewritten_queries],
        )

        # 如果只有一条且和原问题相同，直接走单路检索
        if len(rewritten_queries) == 1 and rewritten_queries[0] == query:
            return await self._retrieval.search(query, scope, user_id, top_k)

        # 2. 多路检索
        all_hits: list[tuple[int, SearchResult]] = []  # (query_idx, hit)
        for idx, rq in enumerate(rewritten_queries):
            hits = await self._retrieval.search(rq, scope, user_id, top_k)
            for hit in hits:
                all_hits.append((idx, hit))

        # 3. RRF 合并
        results = self._rrf_merge(all_hits, top_k)
        logger.info("多路检索完成: queries=%d, total_hits=%d, merged=%d",
                      len(rewritten_queries), len(all_hits), len(results))
        return results

    # ------------------------------------------------------------------
    # Query 改写
    # ------------------------------------------------------------------

    async def _rewrite_query(
        self,
        query: str,
        messages: list | None = None,
    ) -> list[str]:
        """使用 LLM 生成改写后的查询词列表。

        Args:
            query: 用户原始问题
            messages: 会话历史消息

        Returns:
            改写查询列表 (1~3 条)，失败时返回 [原 query]
        """
        # 构建上下文文本
        context = self._build_context(messages)

        prompt = QUERY_REWRITE_PROMPT.format(
            context=context,
            query=query,
        )

        try:
            import asyncio
            response = await asyncio.to_thread(
                self._rewrite_llm.invoke, prompt,
            )
            content = response.content if hasattr(response, "content") else str(response)

            # 解析: 每行一条查询词，过滤空行
            lines = [
                line.strip() for line in content.strip().split("\n")
                if line.strip()
            ]

            # 限制最多 3 条
            queries = lines[:3]
            if not queries:
                return [query]

            # 确保原问题在列表中 (至少有一条接近原始意图)
            if query not in queries:
                queries.insert(0, query)

            # 去重 (保持顺序)
            seen = set()
            unique = []
            for q in queries:
                if q not in seen:
                    seen.add(q)
                    unique.append(q)

            return unique

        except Exception as e:
            logger.warning("Query 改写失败，使用原始查询: %s", e)
            return [query]

    # ------------------------------------------------------------------
    # RRF 合并
    # ------------------------------------------------------------------

    def _rrf_merge(
        self,
        all_hits: list[tuple[int, SearchResult]],
        top_k: int = 8,
    ) -> list[SearchResult]:
        """Reciprocal Rank Fusion — 多路检索结果融合排序。

        公式: RRF_score(d) = Σ 1 / (k + rank_i(d))
        其中 k=60, rank_i(d) 是文档 d 在第 i 路检索中的排名。

        chunk_id 相同的结果视为同一文档，取最高 RRF 分。
        """
        rrf_scores: dict[str, float] = {}
        best_hit: dict[str, SearchResult] = {}

        # 按查询分组，组内按 score 降序排名
        by_query: dict[int, list[SearchResult]] = {}
        for q_idx, hit in all_hits:
            by_query.setdefault(q_idx, []).append(hit)

        for q_idx, hits in by_query.items():
            # 组内按 score 降序排
            hits.sort(key=lambda h: h.score, reverse=True)
            for rank, hit in enumerate(hits, start=1):
                rrf = 1.0 / (RRF_K + rank)
                cid = hit.chunk_id
                rrf_scores[cid] = rrf_scores.get(cid, 0.0) + rrf
                # 保留最高分的 hit 作为代表
                if cid not in best_hit or hit.score > best_hit[cid].score:
                    best_hit[cid] = hit

        # 按 RRF 分数降序排列
        sorted_ids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)

        results: list[SearchResult] = []
        for cid in sorted_ids[:top_k]:
            hit = best_hit[cid]
            hit.score = rrf_scores[cid]  # 用 RRF 分数替换原始分数
            results.append(hit)

        return results

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _build_context(messages: list | None) -> str:
        """从消息列表构建对话上下文 (最近 6 轮)"""
        if not messages:
            return ""

        # 取最近 6 轮 (12 条消息)
        recent = messages[-12:] if len(messages) > 12 else messages
        lines = ["对话历史:"]
        for msg in recent:
            role = msg.role if hasattr(msg, "role") else (
                "用户" if getattr(msg, "type", "") == "human" else "助手"
            )
            content = msg.content if hasattr(msg, "content") else str(msg)
            if isinstance(content, str) and len(content) > 120:
                content = content[:120] + "..."
            lines.append(f"[{role}] {content}")

        return "\n".join(lines) + "\n"

    @staticmethod
    def format_context(hits: list[SearchResult]) -> str:
        """委托给 RetrievalService 的格式化方法"""
        return RetrievalService.format_context(hits)

    @property
    def is_rewrite_enabled(self) -> bool:
        return self._rewrite_llm is not None
