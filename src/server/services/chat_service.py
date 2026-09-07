"""问答服务 — ChatAgent 异步包装 + 知识库检索 + Query 改写 + 多用户管理"""

import logging
import re
from langchain_core.messages import AIMessage, HumanMessage

from ...agents import ChatAgent

logger = logging.getLogger("server.chat_service")

_KNOWLEDGE_INSTRUCTION = (
    "请根据以下知识库内容回答用户问题。如果知识库内容不足以回答，请如实说明。"
)
_KNOWLEDGE_HEADER = "--- 知识库检索结果 ---"
_LEGACY_QUERY_MARKER = re.compile(r"\r?\n---\r?\n用户问题:\s*")


class ChatService:
    """ChatAgent 的异步包装。

    - 按 user_id 缓存 ChatAgent 实例
    - thread_id = "{user_id}:{session_id}" 实现 Checkpointer 层会话隔离
    - 注入知识库检索结果到上下文 (如果配置了 retrieval)
    - 传递会话历史到检索服务 (用于 context-aware query 改写)
    """

    def __init__(
        self,
        retrieval_service=None,
        model_kwargs: dict | None = None,
        *,
        store_type: str = "sqlite",
        sqlite_path: str | None = None,
    ):
        self._agents: dict[str, ChatAgent] = {}
        self._retired_agents: list[ChatAgent] = []
        self._retrieval = retrieval_service  # RetrievalService | AdvancedRetrievalService | None
        self._model_kwargs = dict(model_kwargs or {})
        self._store_type = store_type
        self._sqlite_path = sqlite_path

    @staticmethod
    def _make_tid(user_id: str, session_id: str) -> str:
        """构造 LangGraph thread_id: user_id + session_id 共同索引"""
        return f"{user_id}:{session_id}"

    def _get_or_create_agent(self, user_id: str) -> ChatAgent:
        """获取或创建用户的 ChatAgent 实例"""
        if user_id not in self._agents:
            agent = ChatAgent(
                name=f"api-{user_id[:8]}",
                stream=True,
                store_type=self._store_type,
                **(
                    {"sqlite_path": self._sqlite_path}
                    if self._store_type == "sqlite" and self._sqlite_path
                    else {}
                ),
                **self._model_kwargs,
            )
            agent.initialize()
            self._agents[user_id] = agent
            logger.info("新 Agent 实例: user=%s", user_id[:8])
        return self._agents[user_id]

    async def reconfigure_model(self, model_kwargs: dict) -> None:
        """让后续请求使用新模型，已有请求继续持有原 Agent。"""
        self._model_kwargs = dict(model_kwargs)
        self._retired_agents.extend(self._agents.values())
        self._agents = {}
        logger.info("ChatAgent 模型配置已刷新")

    async def close_all(self) -> None:
        """关闭当前及已经退役的 Agent。"""
        agents = [*self._agents.values(), *self._retired_agents]
        self._agents = {}
        self._retired_agents = []
        for agent in agents:
            try:
                await agent.aclose()
            except Exception as exc:
                logger.warning("关闭 ChatAgent 失败: %s", exc)

    @staticmethod
    def _legacy_user_content(content: object) -> str:
        """从旧版检索增强消息中还原用户的原始问题。"""
        if not isinstance(content, str):
            return str(content)

        normalized = content.lstrip()
        query_markers = list(_LEGACY_QUERY_MARKER.finditer(normalized))
        is_legacy_enhanced_query = (
            normalized.startswith(_KNOWLEDGE_INSTRUCTION)
            and _KNOWLEDGE_HEADER in normalized
            and query_markers
        )
        if not is_legacy_enhanced_query:
            return content

        return normalized[query_markers[-1].end():].strip()

    @classmethod
    def visible_messages(cls, messages: list) -> list:
        """过滤系统/工具消息，并兼容清理旧版污染的用户消息。"""
        visible = []
        for message in messages:
            if isinstance(message, HumanMessage):
                content = cls._legacy_user_content(message.content)
                if content == message.content:
                    visible.append(message)
                else:
                    visible.append(HumanMessage(content=content))
            elif isinstance(message, AIMessage):
                visible.append(message)
        return visible

    def _get_session_messages(
        self, user_id: str, session_id: str, max_rounds: int = 6,
    ) -> list:
        """从 LangGraph Checkpointer 读取最近 N 轮会话消息。

        只取最近 max_rounds 轮，避免上下文过长导致:
          - Query 改写 prompt 膨胀
          - Token 浪费

        Args:
            user_id: 用户 ID
            session_id: 会话 ID
            max_rounds: 最大轮数 (每轮=user+assistant, 默认 6 轮 = 12 条)

        Returns:
            最近的 LangChain message 对象列表
        """
        try:
            agent = self._get_or_create_agent(user_id)
            tid = self._make_tid(user_id, session_id)
            info = agent.get_session_info(tid)

            if not info.get("has_state"):
                return []

            config = {"configurable": {"thread_id": tid}}
            state = agent._graph.get_state(config)
            stored_messages = (
                state.values.get("messages", []) if state.values else []
            )
            messages = self.visible_messages(stored_messages)

            # 只取最近 max_rounds * 2 条 (user + assistant 各算一条)
            max_messages = max_rounds * 2
            if len(messages) > max_messages:
                return messages[-max_messages:]
            return messages
        except Exception as e:
            logger.debug("读取会话消息失败 (新会话?): %s", e)
            return []

    def get_session_messages(self, user_id: str, session_id: str) -> list:
        """Return all user-visible messages for the session history API."""
        return self._get_session_messages(
            user_id=user_id,
            session_id=session_id,
            max_rounds=1_000_000,
        )

    async def chat(
        self, user_id: str, session_id: str, query: str, scope: str = "hybrid"
    ) -> str:
        """同步问答 — 先检索知识库，再调用 ChatAgent"""
        context = await self._get_knowledge_context(
            query, scope, user_id, session_id,
        )
        agent = self._get_or_create_agent(user_id)
        tid = self._make_tid(user_id, session_id)
        return await agent.achat(
            query, thread_id=tid, extra_system_content=context,
        )

    async def chat_stream(
        self, user_id: str, session_id: str, query: str, scope: str = "hybrid"
    ):
        """SSE 流式问答 — 先检索知识库，再流式输出"""
        context = await self._get_knowledge_context(
            query, scope, user_id, session_id,
        )
        agent = self._get_or_create_agent(user_id)
        tid = self._make_tid(user_id, session_id)
        logger.info(
            "chat_stream: query=%r context_injected=%s",
            query[:80], "yes" if context else "no",
        )
        async for chunk in agent.achat_stream(
            query, thread_id=tid, extra_system_content=context,
        ):
            yield chunk

    async def _get_knowledge_context(
        self, query: str, scope: str, user_id: str, session_id: str = "",
    ) -> str | None:
        """获取知识库检索上下文，用于注入 SystemMessage。

        与 _build_query 不同，这里只返回检索到的知识内容 +
        指令提示词，不包含用户原始问题。返回 None 表示无需注入。

        检索结果注入为 SystemMessage 而非 HumanMessage，确保
        会话历史中只展示用户原始问题。
        """
        if not self._retrieval:
            return None

        try:
            # 提取会话消息 (用于上下文改写)
            messages = []
            if session_id:
                messages = self._get_session_messages(user_id, session_id)

            # 调用检索
            from .advanced_retrieval import AdvancedRetrievalService

            if isinstance(self._retrieval, AdvancedRetrievalService):
                hits = await self._retrieval.search(
                    query=query,
                    scope=scope,
                    user_id=user_id,
                    messages=messages,
                )
            else:
                hits = await self._retrieval.search(
                    query=query,
                    scope=scope,
                    user_id=user_id,
                )

            if not hits:
                logger.debug("检索无结果: scope=%s", scope)
                return None

            from .retrieval_service import RetrievalService
            context = RetrievalService.format_context(hits)
            # 只返回检索上下文 + 指令，不包含用户原始问题。
            # 用户原始问题通过 HumanMessage 独立存储，确保聊天历史
            # 中不会出现提示词。
            system_context = f"{_KNOWLEDGE_INSTRUCTION}\n\n{context}"
            logger.debug("检索增强: hits=%d, chars=%d", len(hits), len(system_context))
            return system_context

        except Exception as e:
            logger.warning("检索失败，降级为普通对话: %s", e)
            return None
