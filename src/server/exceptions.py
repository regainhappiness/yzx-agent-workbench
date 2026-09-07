"""统一异常类 + 错误码定义"""

from typing import Any


class AppError(Exception):
    """应用级异常基类"""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class AuthenticationError(AppError):
    """认证失败 — 401"""

    def __init__(self, message: str = "缺少或无效的 API Key"):
        super().__init__(
            code="AUTHENTICATION_REQUIRED",
            message=message,
            status_code=401,
        )


class AuthorizationError(AppError):
    """权限不足 — 403"""

    def __init__(self, message: str = "权限不足"):
        super().__init__(
            code="UNAUTHORIZED",
            message=message,
            status_code=403,
        )


class NotFoundError(AppError):
    """资源不存在 — 404"""

    def __init__(self, resource: str, identifier: str):
        super().__init__(
            code=f"{resource.upper()}_NOT_FOUND",
            message=f"{resource} 不存在: {identifier}",
            status_code=404,
        )


class ValidationError(AppError):
    """参数校验失败 — 422"""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            status_code=422,
            details=details,
        )


class AgentError(AppError):
    """AI Agent 执行异常 — 502"""

    def __init__(self, message: str = "AI 服务异常"):
        super().__init__(
            code="AGENT_ERROR",
            message=message,
            status_code=502,
        )
