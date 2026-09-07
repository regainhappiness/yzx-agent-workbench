"""POST /api/v1/chat, POST /api/v1/chat/stream"""

import json
import logging
from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse
from starlette.background import BackgroundTask

from ..schemas import ChatRequest, ChatResponse
from ..deps import get_identity, get_chat_service, get_session_service
from ..repositories.base import Identity
from ..services.chat_service import ChatService
from ..services.session_service import SessionService

logger = logging.getLogger("server.chat_api")
router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    identity: Identity = Depends(get_identity),
    chat_service: ChatService = Depends(get_chat_service),
    session_service: SessionService = Depends(get_session_service),
):
    """同步问答 — 等待完整回答后返回"""
    # 获取或创建会话
    if body.session_id:
        await session_service.require_session(
            identity.user_id, body.session_id, "chat",
        )
        session_id = body.session_id
    else:
        session = await session_service.create_session(
            identity.user_id, "chat",
        )
        session_id = session.session_id

    # 调用 Agent
    answer = await chat_service.chat(
        user_id=identity.user_id,
        session_id=session_id,
        query=body.query,
        scope=body.knowledge_scope,
    )

    # 更新消息计数
    await session_service.bump_message_count(session_id)

    return ChatResponse(
        answer=answer,
        session_id=session_id,
        citations=[],
        token_usage=None,
    )


@router.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    request: Request,
    identity: Identity = Depends(get_identity),
    chat_service: ChatService = Depends(get_chat_service),
    session_service: SessionService = Depends(get_session_service),
):
    """SSE 流式问答 — 逐 token 输出"""
    # 获取或创建会话
    if body.session_id:
        await session_service.require_session(
            identity.user_id, body.session_id, "chat",
        )
        session_id = body.session_id
    else:
        session = await session_service.create_session(
            identity.user_id, "chat",
        )
        session_id = session.session_id

    async def event_generator():
        # start 事件
        yield {
            "event": "start",
            "data": json.dumps({"session_id": session_id}, ensure_ascii=False),
        }

        try:
            async for chunk in chat_service.chat_stream(
                user_id=identity.user_id,
                session_id=session_id,
                query=body.query,
                scope=body.knowledge_scope,
            ):
                yield {
                    "event": "token",
                    "data": json.dumps({"text": chunk}, ensure_ascii=False),
                }
        except Exception as e:
            logger.error("SSE 流错误: %s", e)
            yield {
                "event": "error",
                "data": json.dumps({
                    "code": "AGENT_ERROR",
                    "message": str(e),
                }, ensure_ascii=False),
            }

        # done 事件
        yield {
            "event": "done",
            "data": json.dumps({"session_id": session_id}, ensure_ascii=False),
        }

    # 后台更新消息计数
    async def after_stream():
        await session_service.bump_message_count(session_id)

    return EventSourceResponse(
        event_generator(),
        background=BackgroundTask(after_stream),
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
