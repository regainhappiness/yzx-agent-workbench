"""请求日志中间件 — request_id 生成 + 请求追踪"""

import logging
import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("server.access")


def generate_request_id() -> str:
    """生成短 request_id (uuid4 前 8 位)"""
    return str(uuid.uuid4())[:8]


class LoggingMiddleware(BaseHTTPMiddleware):
    """为每个请求注入 request_id 并记录访问日志"""

    async def dispatch(self, request: Request, call_next):
        request_id = generate_request_id()
        request.state.request_id = request_id

        start = time.perf_counter()
        start_level = (
            logging.INFO
            if request.method not in {"GET", "HEAD", "OPTIONS"}
            else logging.DEBUG
        )
        logger.log(
            start_level,
            "请求开始: request_id=%s %s %s content_length=%s",
            request_id,
            request.method,
            request.url.path,
            request.headers.get("content-length", "unknown"),
        )
        try:
            response: Response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "请求异常: request_id=%s %s %s → 500 (%.0fms)",
                request_id,
                request.method,
                request.url.path,
                elapsed_ms,
            )
            raise

        elapsed_ms = (time.perf_counter() - start) * 1000

        response.headers["X-Request-ID"] = request_id

        logger.info(
            "请求完成: request_id=%s %s %s → %s (%.0fms)",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response
