"""会话服务 — 会话元数据管理"""

import logging
from ..repositories.base import SessionRepository, Session, SessionType
from ..exceptions import NotFoundError

logger = logging.getLogger("server.session_service")


class SessionService:
    """会话管理

    会话元数据 (所有权, 标题, 统计) 由 Repository 管理.
    Chat 消息仍由对应 Agent 的 Checkpointer 管理；Multi-Agent 的用户可见消息、
    任务轮次和摘要由独立仓储管理，Checkpointer 只保存编排内部状态。
    """

    def __init__(self, session_repo: SessionRepository):
        self._repo = session_repo

    async def create_session(
        self, user_id: str, session_type: SessionType, title: str | None = None,
    ) -> Session:
        session = await self._repo.create(
            user_id=user_id, title=title, session_type=session_type,
        )
        logger.info(
            "会话创建: %s (user=%s, type=%s)",
            session.session_id, user_id, session_type,
        )
        return session

    async def get_session(self, session_id: str) -> Session:
        session = await self._repo.get(session_id)
        if not session:
            raise NotFoundError("会话", session_id)
        return session

    async def list_sessions(
        self, user_id: str, session_type: SessionType,
    ) -> list[Session]:
        return await self._repo.list_by_user(user_id, session_type)

    async def require_session(
        self, user_id: str, session_id: str, session_type: SessionType,
    ) -> Session:
        """Return an owned session only when it belongs to the requested agent."""
        session = await self.get_session(session_id)
        if session.user_id != user_id or session.session_type != session_type:
            raise NotFoundError("会话", session_id)
        return session

    async def delete_session(self, user_id: str, session_id: str) -> None:
        session = await self.get_session(session_id)
        if session.user_id != user_id:
            raise NotFoundError("会话", session_id)
        await self._repo.delete(session_id)
        logger.info("会话已删除: %s", session_id)

    async def rename_session(
        self, user_id: str, session_id: str, title: str | None,
    ) -> Session:
        """重命名会话 — 验证所有权后更新标题"""
        session = await self.get_session(session_id)
        if session.user_id != user_id:
            raise NotFoundError("会话", session_id)
        updated = await self._repo.update(session_id, title=title)
        if not updated:
            raise NotFoundError("会话", session_id)
        logger.info("会话已重命名: %s → %r", session_id, title)
        return updated

    async def bump_message_count(self, session_id: str) -> None:
        """问答后更新消息计数和时间戳"""
        session = await self._repo.get(session_id)
        if session:
            await self._repo.update(
                session_id,
                message_count=session.message_count + 2,  # user + assistant
            )

    async def set_message_count(self, session_id: str, message_count: int) -> None:
        """以消息仓储的实际数量同步统计，避免失败或中止轮次重复累加。"""
        if await self._repo.get(session_id):
            await self._repo.update(
                session_id,
                message_count=max(0, int(message_count)),
            )
