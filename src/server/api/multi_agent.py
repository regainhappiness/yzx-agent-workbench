"""
===========================================================================
多智能体 API 路由
===========================================================================

POST /api/v1/multi-agent/chat/stream  — SSE 流式多智能体问答

事件类型 (分级展示):
  start, analyzing, analysis_done, plan_created,
  dispatching, subagent_start, subagent_plan, subagent_step,
  subagent_progress, subagent_done,
  synthesizing, synthesis_done,
  tool_call, token, error, done
===========================================================================
"""

import json
import logging
import asyncio

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ..deps import (
    get_identity, get_multi_agent_workspace_service, get_session_service,
)
from ..exceptions import AppError, NotFoundError
from ..repositories.base import Identity
from ..services.multi_agent_service import MultiAgentService
from ..services.session_service import SessionService
from ..services.multi_agent_workspace_service import MultiAgentWorkspaceService

logger = logging.getLogger("server.api.multi_agent")

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════
# 请求模型
# ═══════════════════════════════════════════════════════════════════════

class MultiAgentRequest(BaseModel):
    """多智能体问答请求"""
    query: str = Field(
        min_length=1, max_length=4000,
        description="用户任务描述",
    )
    session_id: str | None = Field(
        default=None,
        description="已选择工作区的 Multi-Agent 会话 ID",
    )
    attachment_ids: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="本轮消息引用的会话附件 ID",
    )


# ═══════════════════════════════════════════════════════════════════════
# 依赖注入 helper
# ═══════════════════════════════════════════════════════════════════════

async def get_multi_agent_service(request: Request) -> MultiAgentService:
    """从 app.state 获取 MultiAgentService"""
    return request.app.state.multi_agent_service


# ═══════════════════════════════════════════════════════════════════════
# 路由
# ═══════════════════════════════════════════════════════════════════════

@router.post("/multi-agent/chat/stream")
async def multi_agent_chat_stream(
    body: MultiAgentRequest,
    request: Request,
    identity: Identity = Depends(get_identity),
    multi_agent_service: MultiAgentService = Depends(get_multi_agent_service),
    session_service: SessionService = Depends(get_session_service),
    workspace_service: MultiAgentWorkspaceService = Depends(
        get_multi_agent_workspace_service,
    ),
):
    """多智能体 SSE 流式问答

    与 /chat/stream 相同的 SSE 模式, 但事件类型更丰富:
      - plan_created:  编排计划已生成
      - dispatching:   正在调度 subagent
      - subagent_*:    subagent 内部事件 (分级展示)
      - synthesizing:  正在综合结果
      - token:         LLM 文本增量
    """
    # 创建或验证会话
    session_id = body.session_id
    if not session_id:
        raise AppError(
            code="WORKSPACE_REQUIRED",
            message="请先创建 Multi-Agent 会话并选择工作区",
            status_code=409,
        )
    await session_service.require_session(
        identity.user_id, session_id, "multi_agent",
    )
    await workspace_service.require_workspace(identity.user_id, session_id)

    async def event_generator():
        # 开始事件
        yield {
            "event": "start",
            "data": json.dumps({"session_id": session_id}, ensure_ascii=False),
        }

        terminal_sent = False
        try:
            async for event in multi_agent_service.chat_stream(
                user_id=identity.user_id,
                session_id=session_id,
                query=body.query,
                attachment_ids=body.attachment_ids,
            ):
                if await request.is_disconnected():
                    multi_agent_service.cancel_run(
                        multi_agent_service._make_tid(identity.user_id, session_id)
                    )
                    return
                event_type = event.get("event", "message")
                if event_type == "done":
                    terminal_sent = True
                data = event.get("data", {})
                yield {
                    "event": event_type,
                    "data": json.dumps(data, ensure_ascii=False, default=str),
                }
        except (GeneratorExit, asyncio.CancelledError):
            multi_agent_service.cancel_run(
                multi_agent_service._make_tid(identity.user_id, session_id)
            )
            raise
        except Exception as e:
            logger.exception("Multi-agent stream error")
            yield {
                "event": "error",
                "data": json.dumps({
                    "code": "AGENT_ERROR",
                    "message": str(e),
                    "agent": "main",
                }, ensure_ascii=False),
            }

        # 结束事件
        if await request.is_disconnected():
            multi_agent_service.cancel_run(
                multi_agent_service._make_tid(identity.user_id, session_id)
            )
            return
        if not terminal_sent:
            yield {
                "event": "done",
                "data": json.dumps({"session_id": session_id}, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())


@router.post("/multi-agent/chat/{session_id}/cancel")
async def cancel_multi_agent_run(
    session_id: str,
    identity: Identity = Depends(get_identity),
    multi_agent_service: MultiAgentService = Depends(get_multi_agent_service),
    session_service: SessionService = Depends(get_session_service),
):
    """Cooperatively cancel the active run owned by the current user."""
    try:
        await session_service.require_session(
            identity.user_id, session_id, "multi_agent",
        )
    except NotFoundError:
        return {"cancelled": False}
    cancelled = multi_agent_service.cancel_run(
        multi_agent_service._make_tid(identity.user_id, session_id)
    )
    return {"cancelled": cancelled}


async def _error_stream(code: str, message: str):
    """生成错误事件流"""
    yield {
        "event": "error",
        "data": json.dumps({"code": code, "message": message}, ensure_ascii=False),
    }
    yield {
        "event": "done",
        "data": json.dumps({"session_id": None}, ensure_ascii=False),
    }
