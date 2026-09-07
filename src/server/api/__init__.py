"""API 路由层"""
from fastapi import APIRouter

from .auth import router as auth_router
from .users import router as users_router
from .sessions import router as sessions_router
from .chat import router as chat_router
from .multi_agent import router as multi_agent_router
from .multi_agent_resources import router as multi_agent_resources_router
from .documents import router as documents_router
from .runtime_config import router as runtime_config_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router, tags=["认证"])
api_router.include_router(users_router, tags=["用户"])
api_router.include_router(sessions_router, tags=["会话"])
api_router.include_router(chat_router, tags=["问答"])
api_router.include_router(multi_agent_router, tags=["多智能体"])
api_router.include_router(multi_agent_resources_router, tags=["多智能体文件"])
api_router.include_router(documents_router, tags=["文档"])
api_router.include_router(runtime_config_router, tags=["运行时配置"])
