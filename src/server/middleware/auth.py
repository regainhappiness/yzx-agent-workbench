"""API Key 认证中间件"""

import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger("server.auth")

# 无需认证的路径
PUBLIC_PATHS = {
    "/health/live",
    "/health/ready",
    "/docs",
    "/openapi.json",
    "/redoc",
}


class AuthMiddleware(BaseHTTPMiddleware):
    """从 Authorization: Bearer <key> 头提取身份，注入 request.state

    认证服务通过 request.app.state.auth_service 获取，
    该属性在 lifespan startup 阶段设置，无需构造时注入。
    """

    async def dispatch(self, request: Request, call_next):
        # CORS 预检请求不带 Authorization 头，直接放行
        if request.method == "OPTIONS":
            return await call_next(request)

        # 白名单放行
        if request.url.path in PUBLIC_PATHS or request.url.path.startswith("/docs"):
            return await call_next(request)

        # 提取 Bearer token
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "AUTHENTICATION_REQUIRED",
                        "message": "缺少 API Key (Authorization: Bearer <key>)",
                        "request_id": getattr(request.state, "request_id", "unknown"),
                        "details": {},
                    }
                },
            )

        api_key = auth_header[7:]  # 去掉 "Bearer "
        auth_service = request.app.state.auth_service
        identity = await auth_service.validate_key(api_key)

        if identity is None:
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "AUTHENTICATION_REQUIRED",
                        "message": "无效的 API Key",
                        "request_id": getattr(request.state, "request_id", "unknown"),
                        "details": {},
                    }
                },
            )

        request.state.user_id = identity.user_id
        request.state.role = identity.role
        request.state.api_key_prefix = identity.api_key_prefix

        return await call_next(request)
