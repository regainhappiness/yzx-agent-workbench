"""CRUD /api/v1/sessions"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends

from ..exceptions import AppError, NotFoundError
from ..schemas import CreateSessionRequest, UpdateSessionRequest, SessionResponse, MessageView
from ..deps import (
    get_identity,
    get_session_service,
    get_chat_service,
    get_multi_agent_service,
)
from ..repositories.base import Identity, Session, SessionMessage
from ..services.session_service import SessionService
from ..services.chat_service import ChatService
from ..services.multi_agent_service import (
    MultiAgentService,
    MultiAgentSessionBusyError,
)

router = APIRouter()


def _session_response(session: Session) -> SessionResponse:
    return SessionResponse(
        session_id=session.session_id,
        session_type=session.session_type,
        title=session.title,
        message_count=session.message_count,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=201,
)
async def create_session(
    body: CreateSessionRequest,
    identity: Identity = Depends(get_identity),
    session_service: SessionService = Depends(get_session_service),
):
    """创建新会话"""
    session = await session_service.create_session(
        user_id=identity.user_id,
        session_type=body.session_type,
        title=body.title,
    )
    return _session_response(session)


@router.get(
    "/sessions",
    response_model=list[SessionResponse],
)
async def list_sessions(
    session_type: Literal["chat", "multi_agent"],
    identity: Identity = Depends(get_identity),
    session_service: SessionService = Depends(get_session_service),
):
    """按智能体类型列出当前用户的会话"""
    sessions = await session_service.list_sessions(
        identity.user_id, session_type,
    )
    return [_session_response(session) for session in sessions]


@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[MessageView],
)
async def get_messages(
    session_id: str,
    identity: Identity = Depends(get_identity),
    session_service: SessionService = Depends(get_session_service),
    chat_service: ChatService = Depends(get_chat_service),
    multi_agent_service: MultiAgentService = Depends(get_multi_agent_service),
):
    """获取会话消息历史"""
    # 验证会话属于当前用户
    session = await session_service.get_session(session_id)
    if session.user_id != identity.user_id:
        raise NotFoundError("会话", session_id)

    if session.session_type == "chat":
        stored_messages = chat_service.get_session_messages(
            identity.user_id, session_id,
        )
    else:
        stored_messages = await multi_agent_service.get_session_messages(
            identity.user_id, session_id,
        )

    messages: list[MessageView] = []
    from langchain_core.messages import HumanMessage, AIMessage
    for msg in stored_messages:
        if isinstance(msg, SessionMessage):
            messages.append(MessageView(
                role=msg.role,
                content=msg.content,
                created_at=msg.created_at,
                message_id=msg.message_id,
                turn_id=msg.turn_id,
                status=msg.status,
                metadata=msg.metadata,
            ))
        elif isinstance(msg, HumanMessage):
            messages.append(MessageView(
                role="user", content=str(msg.content),
                created_at=datetime.utcnow(),
            ))
        elif isinstance(msg, AIMessage):
            messages.append(MessageView(
                role="assistant", content=str(msg.content),
                created_at=datetime.utcnow(),
            ))
    return messages


@router.patch(
    "/sessions/{session_id}",
    response_model=SessionResponse,
)
async def update_session(
    body: UpdateSessionRequest,
    session_id: str,
    identity: Identity = Depends(get_identity),
    session_service: SessionService = Depends(get_session_service),
):
    """重命名会话"""
    session = await session_service.rename_session(
        identity.user_id, session_id, body.title,
    )
    return _session_response(session)


@router.delete(
    "/sessions/{session_id}",
    status_code=204,
)
async def delete_session(
    session_id: str,
    identity: Identity = Depends(get_identity),
    session_service: SessionService = Depends(get_session_service),
    multi_agent_service: MultiAgentService = Depends(get_multi_agent_service),
):
    """删除会话索引，并清理对应 Agent 的持久化状态。"""
    session = await session_service.get_session(session_id)
    if session.user_id != identity.user_id:
        raise NotFoundError("会话", session_id)

    if session.session_type == "multi_agent":
        try:
            await multi_agent_service.delete_session_state(
                identity.user_id, session_id,
            )
        except MultiAgentSessionBusyError as exc:
            raise AppError(
                code="SESSION_BUSY",
                message=str(exc),
                status_code=409,
            ) from exc

    await session_service.delete_session(identity.user_id, session_id)
