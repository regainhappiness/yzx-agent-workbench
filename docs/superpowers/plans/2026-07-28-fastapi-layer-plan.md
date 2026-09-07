# FastAPI Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add FastAPI HTTP service layer to Agent-demo with API Key auth, session management, sync chat, and SSE streaming — all as an independent `src/server/` package.

**Architecture:** Layered (API → Service → Repository), middleware-based auth, `ChatAgent` extended with native async methods (`achat`/`achat_stream`) using LangGraph's `ainvoke`/`astream`. All storage in-memory for the first version.

**Tech Stack:** FastAPI, Pydantic v2, sse-starlette, LangGraph (existing), pytest + httpx

**Spec:** [2026-07-28-fastapi-layer-design.md](../specs/2026-07-28-fastapi-layer-design.md)

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `requirements.txt` | Modify | Add fastapi, uvicorn, sse-starlette |
| `.env.example` | Modify | Add ADMIN_API_KEYS, USER_API_KEYS |
| `src/agents/chat_agent.py` | Modify | Add `achat()`, `achat_stream()` async methods |
| `src/server/__init__.py` | Create | Package marker |
| `src/server/exceptions.py` | Create | AppError hierarchy + error codes |
| `src/server/schemas.py` | Create | All Pydantic request/response models |
| `src/server/repositories/__init__.py` | Create | Re-exports |
| `src/server/repositories/base.py` | Create | Protocol definitions |
| `src/server/repositories/memory.py` | Create | In-memory implementations |
| `src/server/middleware/__init__.py` | Create | Re-exports |
| `src/server/middleware/logging.py` | Create | request_id + request logging |
| `src/server/middleware/auth.py` | Create | Bearer token validation |
| `src/server/middleware/cors.py` | Create | CORS config factory |
| `src/server/deps.py` | Create | FastAPI dependency injection |
| `src/server/services/__init__.py` | Create | Re-exports |
| `src/server/services/auth_service.py` | Create | Key validation, user/API Key CRUD |
| `src/server/services/session_service.py` | Create | Session metadata CRUD |
| `src/server/services/chat_service.py` | Create | ChatAgent async wrapper |
| `src/server/api/__init__.py` | Create | Router aggregation |
| `src/server/api/auth.py` | Create | POST /api/v1/api-keys |
| `src/server/api/users.py` | Create | POST /api/v1/users, GET /api/v1/me |
| `src/server/api/sessions.py` | Create | CRUD /api/v1/sessions |
| `src/server/api/chat.py` | Create | POST /api/v1/chat, /chat/stream |
| `src/server/main.py` | Create | FastAPI app, lifespan, route mounting |
| `tests/__init__.py` | Create | Package marker |
| `tests/test_server.py` | Create | Full API integration tests |

---

### Task 1: Update dependencies and environment config

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`

- [ ] **Step 1: Add FastAPI dependencies to requirements.txt**

Append to `requirements.txt`:
```
# FastAPI 服务层
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
sse-starlette>=2.0.0

# 测试
pytest>=8.0.0
pytest-asyncio>=0.24.0
httpx>=0.27.0
```

- [ ] **Step 2: Add server config to .env.example**

Append to `.env.example`:
```bash
# ============================================================================
# FastAPI 服务配置
# ============================================================================

# Admin API Keys (逗号分隔, 拥有所有权限)
ADMIN_API_KEYS=sk-admin-001

# User API Keys (逗号分隔, 普通用户权限)
USER_API_KEYS=sk-user-001
```

- [ ] **Step 3: Install dependencies**

Run: `pip install -r requirements.txt`

---

### Task 2: Add async methods to ChatAgent

**Files:**
- Modify: `src/agents/chat_agent.py` (append new methods before `_fallback_response`)

- [ ] **Step 1: Add `achat()` async method**

Insert before the `# ═══ 兜底 ═══` comment block (before `_fallback_response`), add:

```python
    # ══════════════════════════════════════════════════════════════
    # 异步对话 (FastAPI 用)
    # ══════════════════════════════════════════════════════════════
    async def achat(self, user_input: str, thread_id: str = None) -> str:
        """异步对话 — 内部调用 self._graph.ainvoke()

        参数:
            user_input: 用户输入文本
            thread_id:  会话线程 ID

        返回:
            Agent 的文本响应
        """
        if not self._initialized:
            self.initialize()

        tid = thread_id or self._thread_id
        config_for_check = {"configurable": {"thread_id": tid}}
        current_state = self._graph.get_state(config_for_check)

        if current_state and current_state.values:
            messages = [HumanMessage(content=user_input)]
        else:
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=user_input),
            ]
            self.logger.info(f"🆕 新会话 (async): thread_id={tid}")

        config = {
            "configurable": {"thread_id": tid},
            "callbacks": [self._token_counter],
            "recursion_limit": self.max_agent_steps * 2,
        }

        try:
            result = await self._graph.ainvoke({"messages": messages}, config)

            for msg in reversed(result.get("messages", [])):
                if isinstance(msg, AIMessage) and msg.content:
                    return str(msg.content)

            return "抱歉，我没有生成有效的回复。"

        except Exception as e:
            self.logger.error(f"❌ Agent 异步执行错误: {e}")
            return f"抱歉，处理请求时出错: {e}"

    async def achat_stream(self, user_input: str, thread_id: str = None):
        """异步流式对话 — 内部调用 self._graph.astream()

        使用:
            async for chunk in agent.achat_stream("你好"):
                print(chunk, end="", flush=True)

        参数:
            user_input: 用户输入文本
            thread_id:  会话线程 ID
        """
        if not self._initialized:
            self.initialize()

        tid = thread_id or self._thread_id

        config_for_check = {"configurable": {"thread_id": tid}}
        current_state = self._graph.get_state(config_for_check)

        if current_state and current_state.values:
            messages = [HumanMessage(content=user_input)]
        else:
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=user_input),
            ]
            self.logger.info(f"🆕 新会话 (async stream): thread_id={tid}")

        config = {
            "configurable": {"thread_id": tid},
            "callbacks": [self._token_counter],
        }

        try:
            async for event in self._graph.astream(
                {"messages": messages}, config
            ):
                for node_name, node_output in event.items():
                    for msg in node_output.get("messages", []):
                        if isinstance(msg, AIMessage) and msg.content:
                            yield str(msg.content)

        except Exception as e:
            self.logger.error(f"❌ Agent 异步流式错误: {e}")
            yield f"抱歉，处理请求时出错: {e}"
```

- [ ] **Step 2: Run existing tests to verify no regression**

Run: `python src/main.py` and type `/exit` to confirm CLI still works.

---

### Task 3: Create exceptions module

**Files:**
- Create: `src/server/__init__.py`
- Create: `src/server/exceptions.py`

- [ ] **Step 1: Create package init**

`src/server/__init__.py`:
```python
"""FastAPI 服务层 — HTTP API, 认证, 会话管理, 流式问答"""
```

- [ ] **Step 2: Create exceptions with error codes**

`src/server/exceptions.py`:
```python
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
```

---

### Task 4: Create Pydantic schemas

**Files:**
- Create: `src/server/schemas.py`

- [ ] **Step 1: Write all request/response models**

`src/server/schemas.py`:
```python
"""Pydantic v2 请求/响应模型"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
# 身份
# ═══════════════════════════════════════════════════════════════

class CreateUserRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    role: Literal["user", "admin"] = "user"


class CreateApiKeyRequest(BaseModel):
    user_id: str = Field(min_length=1)


class ApiKeyResponse(BaseModel):
    key: str
    prefix: str
    created_at: datetime


class UserResponse(BaseModel):
    user_id: str
    name: str
    role: str
    created_at: datetime


class MeResponse(BaseModel):
    user_id: str
    name: str
    role: str
    api_key_prefix: str


# ═══════════════════════════════════════════════════════════════
# 会话
# ═══════════════════════════════════════════════════════════════

class CreateSessionRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class SessionResponse(BaseModel):
    session_id: str
    title: str | None
    message_count: int
    created_at: datetime
    updated_at: datetime


class MessageView(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


# ═══════════════════════════════════════════════════════════════
# 问答
# ═══════════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None
    knowledge_scope: Literal["private", "shared", "hybrid"] = "hybrid"


class Citation(BaseModel):
    index: int
    document_name: str
    scope: Literal["private", "shared"]
    page: int | None = None
    section: str | None = None
    text_snippet: str


class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    citations: list[Citation] = []
    token_usage: TokenUsage | None = None


# ═══════════════════════════════════════════════════════════════
# 错误
# ═══════════════════════════════════════════════════════════════

class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str
    details: dict[str, Any] = {}


class ErrorResponse(BaseModel):
    error: ErrorDetail
```

---

### Task 5: Create Repository layer

**Files:**
- Create: `src/server/repositories/__init__.py`
- Create: `src/server/repositories/base.py`
- Create: `src/server/repositories/memory.py`

- [ ] **Step 1: Define protocols**

`src/server/repositories/__init__.py`:
```python
"""存储层 — 协议定义 + 内存实现"""
from .base import UserRepository, ApiKeyRepository, SessionRepository
from .memory import InMemoryUserRepo, InMemoryApiKeyRepo, InMemorySessionRepo

__all__ = [
    "UserRepository", "ApiKeyRepository", "SessionRepository",
    "InMemoryUserRepo", "InMemoryApiKeyRepo", "InMemorySessionRepo",
]
```

`src/server/repositories/base.py`:
```python
"""存储层协议定义"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class User:
    user_id: str
    name: str
    role: str
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ApiKey:
    key_hash: str
    prefix: str
    user_id: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    revoked_at: datetime | None = None


@dataclass
class Session:
    session_id: str
    user_id: str
    title: str | None
    message_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Identity:
    user_id: str
    role: str
    api_key_prefix: str


class UserRepository(Protocol):
    async def create(self, name: str, role: str) -> User: ...
    async def get_by_id(self, user_id: str) -> User | None: ...
    async def list_all(self) -> list[User]: ...


class ApiKeyRepository(Protocol):
    async def create(self, user_id: str, key_hash: str, prefix: str) -> ApiKey: ...
    async def validate(self, api_key: str) -> Identity | None: ...
    async def revoke(self, prefix: str) -> None: ...
    async def list_by_user(self, user_id: str) -> list[ApiKey]: ...


class SessionRepository(Protocol):
    async def create(self, user_id: str, title: str | None) -> Session: ...
    async def get(self, session_id: str) -> Session | None: ...
    async def list_by_user(self, user_id: str) -> list[Session]: ...
    async def update(self, session_id: str, **kwargs) -> Session | None: ...
    async def delete(self, session_id: str) -> None: ...
```

- [ ] **Step 2: Write memory implementations**

`src/server/repositories/memory.py`:
```python
"""内存存储实现"""

import asyncio
import hashlib
import uuid
from datetime import datetime

from .base import User, ApiKey, Session, Identity


class InMemoryUserRepo:
    def __init__(self):
        self._users: dict[str, User] = {}
        self._lock = asyncio.Lock()

    async def create(self, name: str, role: str) -> User:
        async with self._lock:
            user = User(
                user_id=str(uuid.uuid4())[:8],
                name=name,
                role=role,
            )
            self._users[user.user_id] = user
            return user

    async def get_by_id(self, user_id: str) -> User | None:
        return self._users.get(user_id)

    async def list_all(self) -> list[User]:
        return list(self._users.values())


class InMemoryApiKeyRepo:
    def __init__(self):
        self._keys: dict[str, ApiKey] = {}     # prefix → ApiKey
        self._plain_map: dict[str, str] = {}   # plain_key → prefix
        self._lock = asyncio.Lock()

    @staticmethod
    def _hash(key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()

    @staticmethod
    def _prefix(key: str) -> str:
        return key[:11] + "***" + key[-4:]

    async def create(self, user_id: str, key_hash: str, prefix: str) -> ApiKey:
        async with self._lock:
            entry = ApiKey(key_hash=key_hash, prefix=prefix, user_id=user_id)
            self._keys[prefix] = entry
            return entry

    async def register_plain(self, plain_key: str, prefix: str) -> None:
        """注册明文 Key → prefix 映射 (仅用于静态配置)"""
        self._plain_map[plain_key] = prefix

    async def validate(self, api_key: str) -> Identity | None:
        # 1. 通过明文映射 (静态配置的 Key)
        prefix = self._plain_map.get(api_key)
        if prefix and prefix in self._keys:
            entry = self._keys[prefix]
            if entry.revoked_at is None:
                user = entry  # 需要外部注入 user repo 的查询
                return None  # 由 AuthService 处理此逻辑

        # 2. 通过哈希匹配 (动态创建的 Key)
        key_hash = self._hash(api_key)
        for entry in self._keys.values():
            if entry.key_hash == key_hash and entry.revoked_at is None:
                return Identity(
                    user_id=entry.user_id,
                    role="user",
                    api_key_prefix=entry.prefix,
                )
        return None

    async def revoke(self, prefix: str) -> None:
        if entry := self._keys.get(prefix):
            entry.revoked_at = datetime.utcnow()

    async def list_by_user(self, user_id: str) -> list[ApiKey]:
        return [e for e in self._keys.values() if e.user_id == user_id]


class InMemorySessionRepo:
    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._lock = asyncio.Lock()

    async def create(self, user_id: str, title: str | None) -> Session:
        async with self._lock:
            session = Session(
                session_id=str(uuid.uuid4()),
                user_id=user_id,
                title=title,
            )
            self._sessions[session.session_id] = session
            return session

    async def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    async def list_by_user(self, user_id: str) -> list[Session]:
        return [
            s for s in self._sessions.values()
            if s.user_id == user_id
        ]

    async def update(self, session_id: str, **kwargs) -> Session | None:
        if session := self._sessions.get(session_id):
            for k, v in kwargs.items():
                if hasattr(session, k):
                    setattr(session, k, v)
            session.updated_at = datetime.utcnow()
            return session
        return None

    async def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
```

---

### Task 6: Create middleware modules

**Files:**
- Create: `src/server/middleware/__init__.py`
- Create: `src/server/middleware/logging.py`
- Create: `src/server/middleware/auth.py`
- Create: `src/server/middleware/cors.py`

- [ ] **Step 1: Create middleware package init**

`src/server/middleware/__init__.py`:
```python
"""中间件 — 认证, 日志, CORS"""
from .logging import LoggingMiddleware
from .auth import AuthMiddleware
from .cors import setup_cors

__all__ = ["LoggingMiddleware", "AuthMiddleware", "setup_cors"]
```

- [ ] **Step 2: Create logging middleware**

`src/server/middleware/logging.py`:
```python
"""请求日志中间件 — request_id 生成 + 请求追踪"""

import time
import uuid
import logging
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

        start = time.time()
        response: Response = await call_next(request)
        elapsed_ms = (time.time() - start) * 1000

        response.headers["X-Request-ID"] = request_id

        logger.info(
            "%s %s → %s (%.0fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response
```

- [ ] **Step 3: Create auth middleware**

`src/server/middleware/auth.py`:
```python
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
```

- [ ] **Step 4: Create CORS config**

`src/server/middleware/cors.py`:
```python
"""CORS 配置"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def setup_cors(app: FastAPI) -> None:
    """配置开发阶段 CORS (允许所有来源)"""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

---

### Task 7: Create AuthService

**Files:**
- Create: `src/server/services/__init__.py`
- Create: `src/server/services/auth_service.py`

- [ ] **Step 1: Create services init**

`src/server/services/__init__.py`:
```python
"""业务服务层"""
from .auth_service import AuthService
from .session_service import SessionService
from .chat_service import ChatService

__all__ = ["AuthService", "SessionService", "ChatService"]
```

- [ ] **Step 2: Write AuthService**

`src/server/services/auth_service.py`:
```python
"""认证服务 — Key 校验, 用户/API Key 管理"""

import hashlib
import secrets
import uuid
import logging
from datetime import datetime

from ..repositories.base import (
    UserRepository, ApiKeyRepository, Identity,
)
from ..exceptions import AuthenticationError, AuthorizationError, NotFoundError

logger = logging.getLogger("server.auth_service")

STATIC_KEY_PREFIX = "sk-static"


class AuthService:
    """认证服务

    支持两种 Key 来源:
    1. 静态配置 (ADMIN_API_KEYS / USER_API_KEYS 环境变量)
    2. 动态创建 (POST /api/v1/api-keys)
    """

    def __init__(
        self,
        user_repo: UserRepository,
        api_key_repo: ApiKeyRepository,
        admin_keys: list[str] | None = None,
        user_keys: list[str] | None = None,
    ):
        self._user_repo = user_repo
        self._api_key_repo = api_key_repo
        self._admin_keys = set(admin_keys or [])
        self._user_keys = set(user_keys or [])
        # 静态 Key → Identity 的内存映射
        self._static_identities: dict[str, Identity] = {}

    async def initialize(self) -> None:
        """注册静态配置的 Key (启动时调用)"""
        for key in self._admin_keys:
            await self._register_static_key(key, "admin")
        for key in self._user_keys:
            await self._register_static_key(key, "user")
        count = len(self._admin_keys) + len(self._user_keys)
        if count > 0:
            logger.info("已加载 %d 个静态 API Key", count)

    async def _register_static_key(self, plain_key: str, role: str) -> None:
        """注册一个静态 Key"""
        user_id = f"{STATIC_KEY_PREFIX}-{role}-{hashlib.md5(plain_key.encode()).hexdigest()[:6]}"
        prefix = self._key_prefix(plain_key)
        key_hash = self._hash_key(plain_key)

        # 确保用户存在
        existing = await self._user_repo.get_by_id(user_id)
        if not existing:
            await self._user_repo.create(
                name=f"Static {role} ({prefix})",
                role=role,
            )

        # 注册 Key
        await self._api_key_repo.create(user_id, key_hash, prefix)
        # 同时注册明文映射 (用于 validate_key)
        if hasattr(self._api_key_repo, 'register_plain'):
            await self._api_key_repo.register_plain(plain_key, prefix)

        self._static_identities[plain_key] = Identity(
            user_id=user_id,
            role=role,
            api_key_prefix=prefix,
        )

    @staticmethod
    def _hash_key(key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()

    @staticmethod
    def _key_prefix(key: str) -> str:
        return key[:11] + "***" + key[-4:]

    async def validate_key(self, api_key: str) -> Identity | None:
        """校验 API Key，返回 Identity 或 None"""
        # 1. 先查静态映射
        if identity := self._static_identities.get(api_key):
            return identity

        # 2. 查动态创建的 Key
        return await self._api_key_repo.validate(api_key)

    async def create_user(self, name: str, role: str) -> dict:
        """创建用户"""
        user = await self._user_repo.create(name=name, role=role)
        return {
            "user_id": user.user_id,
            "name": user.name,
            "role": user.role,
            "created_at": user.created_at,
        }

    async def create_api_key(self, user_id: str) -> dict:
        """为用户生成 API Key (返回完整 Key 仅此一次)"""
        user = await self._user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("用户", user_id)

        plain_key = f"sk-{secrets.token_hex(16)}"
        key_hash = self._hash_key(plain_key)
        prefix = self._key_prefix(plain_key)

        await self._api_key_repo.create(user_id, key_hash, prefix)
        if hasattr(self._api_key_repo, 'register_plain'):
            await self._api_key_repo.register_plain(plain_key, prefix)

        return {
            "key": plain_key,
            "prefix": prefix,
            "created_at": datetime.utcnow(),
        }

    async def revoke_key(self, prefix: str) -> None:
        """撤销 API Key"""
        await self._api_key_repo.revoke(prefix)

    async def require_admin(self, user_id: str) -> None:
        """确保用户是 admin，否则抛出 AuthorizationError"""
        user = await self._user_repo.get_by_id(user_id)
        if not user or user.role != "admin":
            raise AuthorizationError("需要管理员权限")
```

---

### Task 8: Create SessionService

**Files:**
- Create: `src/server/services/session_service.py`

- [ ] **Step 1: Write SessionService**

`src/server/services/session_service.py`:
```python
"""会话服务 — 会话元数据管理"""

import logging
from ..repositories.base import SessionRepository, Session
from ..exceptions import NotFoundError

logger = logging.getLogger("server.session_service")


class SessionService:
    """会话管理

    会话元数据 (所有权, 标题, 统计) 由 Repository 管理.
    消息正文由 LangGraph Checkpointer (MemorySaver) 以
    thread_id = "{user_id}:{session_id}" 管理.
    """

    def __init__(self, session_repo: SessionRepository):
        self._repo = session_repo

    async def create_session(
        self, user_id: str, title: str | None = None
    ) -> Session:
        session = await self._repo.create(user_id=user_id, title=title)
        logger.info("会话创建: %s (user=%s)", session.session_id, user_id)
        return session

    async def get_session(self, session_id: str) -> Session:
        session = await self._repo.get(session_id)
        if not session:
            raise NotFoundError("会话", session_id)
        return session

    async def list_sessions(self, user_id: str) -> list[Session]:
        return await self._repo.list_by_user(user_id)

    async def delete_session(self, user_id: str, session_id: str) -> None:
        session = await self.get_session(session_id)
        if session.user_id != user_id:
            raise NotFoundError("会话", session_id)
        await self._repo.delete(session_id)
        logger.info("会话已删除: %s", session_id)

    async def bump_message_count(self, session_id: str) -> None:
        """问答后更新消息计数和时间戳"""
        session = await self._repo.get(session_id)
        if session:
            await self._repo.update(
                session_id,
                message_count=session.message_count + 2,  # user + assistant
            )
```

---

### Task 9: Create ChatService

**Files:**
- Create: `src/server/services/chat_service.py`

- [ ] **Step 1: Write ChatService**

`src/server/services/chat_service.py`:
```python
"""问答服务 — ChatAgent 异步包装 + 多用户管理"""

import logging
from agents import ChatAgent

logger = logging.getLogger("server.chat_service")


class ChatService:
    """ChatAgent 的异步包装

    - 按 user_id 缓存 ChatAgent 实例
    - thread_id = "{user_id}:{session_id}" 实现 Checkpointer 层会话隔离
    """

    def __init__(self):
        self._agents: dict[str, ChatAgent] = {}

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
            )
            agent.initialize()
            self._agents[user_id] = agent
            logger.info("新 Agent 实例: user=%s", user_id[:8])
        return self._agents[user_id]

    async def chat(
        self, user_id: str, session_id: str, query: str, scope: str = "hybrid"
    ) -> str:
        """同步问答 — 调用 ChatAgent.achat()"""
        agent = self._get_or_create_agent(user_id)
        tid = self._make_tid(user_id, session_id)
        return await agent.achat(query, thread_id=tid)

    async def chat_stream(
        self, user_id: str, session_id: str, query: str, scope: str = "hybrid"
    ):
        """SSE 流式问答 — 调用 ChatAgent.achat_stream()"""
        agent = self._get_or_create_agent(user_id)
        tid = self._make_tid(user_id, session_id)
        async for chunk in agent.achat_stream(query, thread_id=tid):
            yield chunk
```

---

### Task 10: Create FastAPI dependencies (deps.py)

**Files:**
- Create: `src/server/deps.py`

- [ ] **Step 1: Write dependency injection helpers**

`src/server/deps.py`:
```python
"""FastAPI 依赖注入"""

from fastapi import Request, Depends

from .repositories.base import Identity
from .exceptions import AuthenticationError, AuthorizationError


async def get_identity(request: Request) -> Identity:
    """从 request.state 提取当前用户身份"""
    user_id = getattr(request.state, "user_id", None)
    role = getattr(request.state, "role", None)
    prefix = getattr(request.state, "api_key_prefix", None)

    if not user_id:
        raise AuthenticationError()

    return Identity(
        user_id=user_id,
        role=role or "user",
        api_key_prefix=prefix or "unknown",
    )


async def require_admin(identity: Identity = Depends(get_identity)) -> Identity:
    """要求 admin 角色"""
    if identity.role != "admin":
        raise AuthorizationError("需要管理员权限")
    return identity


def get_auth_service(request: Request):
    """获取 AuthService (从 app.state 注入)"""
    return request.app.state.auth_service


def get_session_service(request: Request):
    """获取 SessionService"""
    return request.app.state.session_service


def get_chat_service(request: Request):
    """获取 ChatService"""
    return request.app.state.chat_service
```

---

### Task 11: Create API routes

**Files:**
- Create: `src/server/api/__init__.py`
- Create: `src/server/api/auth.py`
- Create: `src/server/api/users.py`
- Create: `src/server/api/sessions.py`
- Create: `src/server/api/chat.py`

- [ ] **Step 1: Create API package init with router**

`src/server/api/__init__.py`:
```python
"""API 路由层"""
from fastapi import APIRouter

from .auth import router as auth_router
from .users import router as users_router
from .sessions import router as sessions_router
from .chat import router as chat_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router, tags=["认证"])
api_router.include_router(users_router, tags=["用户"])
api_router.include_router(sessions_router, tags=["会话"])
api_router.include_router(chat_router, tags=["问答"])
```

- [ ] **Step 2: Create auth routes**

`src/server/api/auth.py`:
```python
"""POST /api/v1/api-keys"""

from fastapi import APIRouter, Depends

from ..schemas import CreateApiKeyRequest, ApiKeyResponse
from ..deps import require_admin, get_auth_service
from ..services.auth_service import AuthService

router = APIRouter()


@router.post(
    "/api-keys",
    response_model=ApiKeyResponse,
    status_code=201,
)
async def create_api_key(
    body: CreateApiKeyRequest,
    auth_service: AuthService = Depends(get_auth_service),
    _admin=Depends(require_admin),
):
    """为指定用户生成 API Key (仅 admin)"""
    result = await auth_service.create_api_key(body.user_id)
    return ApiKeyResponse(**result)
```

- [ ] **Step 3: Create user routes**

`src/server/api/users.py`:
```python
"""POST /api/v1/users, GET /api/v1/me"""

from fastapi import APIRouter, Depends

from ..schemas import (
    CreateUserRequest, UserResponse, MeResponse,
)
from ..deps import require_admin, get_identity, get_auth_service
from ..repositories.base import Identity
from ..services.auth_service import AuthService

router = APIRouter()


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=201,
)
async def create_user(
    body: CreateUserRequest,
    auth_service: AuthService = Depends(get_auth_service),
    _admin=Depends(require_admin),
):
    """创建用户 (仅 admin)"""
    result = await auth_service.create_user(
        name=body.name, role=body.role,
    )
    return UserResponse(**result)


@router.get(
    "/me",
    response_model=MeResponse,
)
async def get_me(
    identity: Identity = Depends(get_identity),
    auth_service: AuthService = Depends(get_auth_service),
):
    """获取当前用户身份"""
    # 从 AuthService 获取用户名称
    user = await auth_service._user_repo.get_by_id(identity.user_id)
    name = user.name if user else identity.user_id
    return MeResponse(
        user_id=identity.user_id,
        name=name,
        role=identity.role,
        api_key_prefix=identity.api_key_prefix,
    )
```

- [ ] **Step 4: Create session routes**

`src/server/api/sessions.py`:
```python
"""CRUD /api/v1/sessions"""

from fastapi import APIRouter, Depends

from ..schemas import CreateSessionRequest, SessionResponse, MessageView
from ..deps import get_identity, get_session_service, get_chat_service
from ..repositories.base import Identity
from ..services.session_service import SessionService
from ..services.chat_service import ChatService

router = APIRouter()


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
        title=body.title,
    )
    return SessionResponse(
        session_id=session.session_id,
        title=session.title,
        message_count=session.message_count,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.get(
    "/sessions",
    response_model=list[SessionResponse],
)
async def list_sessions(
    identity: Identity = Depends(get_identity),
    session_service: SessionService = Depends(get_session_service),
):
    """列出当前用户的所有会话"""
    sessions = await session_service.list_sessions(identity.user_id)
    return [
        SessionResponse(
            session_id=s.session_id,
            title=s.title,
            message_count=s.message_count,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in sessions
    ]


@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[MessageView],
)
async def get_messages(
    session_id: str,
    identity: Identity = Depends(get_identity),
    session_service: SessionService = Depends(get_session_service),
    chat_service: ChatService = Depends(get_chat_service),
):
    """获取会话消息历史"""
    # 验证会话属于当前用户
    session = await session_service.get_session(session_id)
    if session.user_id != identity.user_id:
        from ..exceptions import NotFoundError
        raise NotFoundError("会话", session_id)

    # 从 ChatAgent Checkpointer 读取消息
    agent = chat_service._get_or_create_agent(identity.user_id)
    tid = chat_service._make_tid(identity.user_id, session_id)
    info = agent.get_session_info(tid)

    messages: list[MessageView] = []
    if info["has_state"]:
        config = {"configurable": {"thread_id": tid}}
        state = agent._graph.get_state(config)
        from langchain_core.messages import HumanMessage, AIMessage
        from datetime import datetime

        for msg in state.values.get("messages", []):
            if isinstance(msg, HumanMessage):
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


@router.delete(
    "/sessions/{session_id}",
    status_code=204,
)
async def delete_session(
    session_id: str,
    identity: Identity = Depends(get_identity),
    session_service: SessionService = Depends(get_session_service),
):
    """删除会话"""
    await session_service.delete_session(identity.user_id, session_id)
```

- [ ] **Step 5: Create chat routes**

`src/server/api/chat.py`:
```python
"""POST /api/v1/chat, POST /api/v1/chat/stream"""

import json
import logging
from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

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
        session = await session_service.get_session(body.session_id)
        if session.user_id != identity.user_id:
            from ..exceptions import NotFoundError
            raise NotFoundError("会话", body.session_id)
        session_id = body.session_id
    else:
        session = await session_service.create_session(identity.user_id)
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
        session = await session_service.get_session(body.session_id)
        if session.user_id != identity.user_id:
            from ..exceptions import NotFoundError
            raise NotFoundError("会话", body.session_id)
        session_id = body.session_id
    else:
        session = await session_service.create_session(identity.user_id)
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
            request_id = getattr(request.state, "request_id", "unknown")
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
        background=after_stream(),
    )
```

---

### Task 12: Create main FastAPI application

**Files:**
- Create: `src/server/main.py`

- [ ] **Step 1: Write main.py with lifespan and error handlers**

`src/server/main.py`:
```python
"""
===========================================================================
FastAPI 服务入口 — Agent-demo HTTP API
===========================================================================

启动:
    uvicorn src.server.main:app --reload --port 8000
===========================================================================
"""

import os
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .api import api_router
from .middleware import LoggingMiddleware, AuthMiddleware, setup_cors
from .services import AuthService, SessionService, ChatService
from .repositories import (
    InMemoryUserRepo, InMemoryApiKeyRepo, InMemorySessionRepo,
)
from .exceptions import AppError
from .schemas import ErrorResponse, ErrorDetail

load_dotenv()

logger = logging.getLogger("server")


# ═══════════════════════════════════════════════════════════════
# Lifespan
# ═══════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期 — 初始化/清理服务"""
    # Startup
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 仓库
    user_repo = InMemoryUserRepo()
    api_key_repo = InMemoryApiKeyRepo()
    session_repo = InMemorySessionRepo()

    # 静态 Key 配置
    admin_keys = [
        k.strip() for k in
        os.getenv("ADMIN_API_KEYS", "").split(",") if k.strip()
    ]
    user_keys = [
        k.strip() for k in
        os.getenv("USER_API_KEYS", "").split(",") if k.strip()
    ]

    # 服务
    auth_service = AuthService(
        user_repo=user_repo,
        api_key_repo=api_key_repo,
        admin_keys=admin_keys,
        user_keys=user_keys,
    )
    await auth_service.initialize()

    session_service = SessionService(session_repo=session_repo)
    chat_service = ChatService()

    # 挂载到 app.state
    app.state.auth_service = auth_service
    app.state.session_service = session_service
    app.state.chat_service = chat_service

    logger.info("🚀 FastAPI 服务已启动 (admin_keys=%d, user_keys=%d)",
                len(admin_keys), len(user_keys))

    yield

    # Shutdown
    logger.info("🛑 FastAPI 服务已关闭")


# ═══════════════════════════════════════════════════════════════
# Application
# ═══════════════════════════════════════════════════════════════

app = FastAPI(
    title="Agent-demo API",
    description="AI Agent 问答服务 — 认证, 会话管理, 流式问答",
    version="0.1.0",
    lifespan=lifespan,
)

# ── 中间件 (顺序: 日志 → CORS → 认证) ──
setup_cors(app)
app.add_middleware(LoggingMiddleware)
app.add_middleware(AuthMiddleware)


# ── 异常处理 ──

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    request_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=ErrorDetail(
                code=exc.code,
                message=exc.message,
                request_id=request_id,
                details=exc.details,
            )
        ).model_dump(),
    )


# ── 路由 ──

app.include_router(api_router)


# ── 健康检查 ──

@app.get("/health/live")
async def health_live():
    """存活检查 — 应用进程是否运行"""
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready(request: Request):
    """就绪检查 — 依赖是否可用"""
    chat_service = request.app.state.chat_service
    return {
        "status": "ok" if chat_service else "degraded",
        "checks": {
            "chat_agent": "ok" if chat_service else "unavailable",
        },
    }
```

---

### Task 13: Write integration tests

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_server.py`

- [ ] **Step 1: Create tests init**

`tests/__init__.py`:
```python
"""Agent-demo 测试套件"""
```

- [ ] **Step 2: Write API integration tests**

`tests/test_server.py`:
```python
"""FastAPI 集成测试 — 使用 TestClient + 静态 Key"""

import os
import pytest
from httpx import ASGITransport, AsyncClient


# 设置测试环境 (在任何导入之前)
os.environ.setdefault("ADMIN_API_KEYS", "sk-test-admin")
os.environ.setdefault("USER_API_KEYS", "sk-test-user")


@pytest.fixture
async def client():
    """创建异步测试客户端"""
    from src.server.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def admin_headers():
    return {"Authorization": "Bearer sk-test-admin"}


@pytest.fixture
def user_headers():
    return {"Authorization": "Bearer sk-test-user"}


# ═══════════════════════════════════════════════════════════════
# 健康检查 (无认证)
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_health_live(client: AsyncClient):
    resp = await client.get("/health/live")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_health_ready(client: AsyncClient):
    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ═══════════════════════════════════════════════════════════════
# 认证
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_no_auth_returns_401(client: AsyncClient):
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 401
    data = resp.json()
    assert data["error"]["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.asyncio
async def test_invalid_key_returns_401(client: AsyncClient):
    resp = await client.get(
        "/api/v1/me",
        headers={"Authorization": "Bearer sk-invalid"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_valid_admin_key_works(client: AsyncClient, admin_headers):
    resp = await client.get("/api/v1/me", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "admin"


@pytest.mark.asyncio
async def test_valid_user_key_works(client: AsyncClient, user_headers):
    resp = await client.get("/api/v1/me", headers=user_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "user"


# ═══════════════════════════════════════════════════════════════
# 会话
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_session(client: AsyncClient, user_headers):
    resp = await client.post(
        "/api/v1/sessions",
        json={"title": "测试会话"},
        headers=user_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "session_id" in data
    assert data["title"] == "测试会话"
    assert data["message_count"] == 0


@pytest.mark.asyncio
async def test_list_sessions(client: AsyncClient, user_headers):
    # 先创建一个
    await client.post("/api/v1/sessions", json={}, headers=user_headers)
    resp = await client.get("/api/v1/sessions", headers=user_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_delete_session(client: AsyncClient, user_headers):
    resp = await client.post("/api/v1/sessions", json={}, headers=user_headers)
    session_id = resp.json()["session_id"]

    resp = await client.delete(
        f"/api/v1/sessions/{session_id}",
        headers=user_headers,
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_cannot_access_other_user_session(
    client: AsyncClient, user_headers,
):
    """验证用户隔离: user1 创建会话, user2 用 admin key 不能访问"""
    # user 创建会话
    resp = await client.post(
        "/api/v1/sessions", json={}, headers=user_headers,
    )
    session_id = resp.json()["session_id"]

    # 另一个用户 (admin) 尝试访问 → 应返回 404 (不暴露存在性)
    admin_headers = {"Authorization": "Bearer sk-test-admin"}
    resp = await client.get(
        f"/api/v1/sessions/{session_id}/messages",
        headers=admin_headers,
    )
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════
# 问答 (fallback 模式 — 无外部 LLM)
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_chat_sync(client: AsyncClient, user_headers):
    """同步问答 — 在无 API Key 时使用 fallback 模式"""
    resp = await client.post(
        "/api/v1/chat",
        json={"query": "你好"},
        headers=user_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "session_id" in data


@pytest.mark.asyncio
async def test_chat_with_existing_session(
    client: AsyncClient, user_headers,
):
    """在已有会话中问答"""
    # 创建会话
    resp = await client.post(
        "/api/v1/sessions", json={"title": "Chat"},
        headers=user_headers,
    )
    session_id = resp.json()["session_id"]

    # 在该会话中问答
    resp = await client.post(
        "/api/v1/chat",
        json={"query": "你好", "session_id": session_id},
        headers=user_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session_id


@pytest.mark.asyncio
async def test_chat_stream(client: AsyncClient, user_headers):
    """SSE 流式问答 — 验证事件类型"""
    resp = await client.post(
        "/api/v1/chat/stream",
        json={"query": "你好"},
        headers=user_headers,
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")

    # 解析 SSE 事件
    events = []
    current_event = None
    for line in resp.text.split("\n"):
        line = line.strip()
        if line.startswith("event: "):
            current_event = line[7:]
        elif line.startswith("data: ") and current_event:
            import json
            data = json.loads(line[6:])
            events.append((current_event, data))
            current_event = None

    # 验证事件顺序: start → token* → done
    assert len(events) >= 2
    assert events[0][0] == "start"
    assert events[-1][0] == "done"


@pytest.mark.asyncio
async def test_chat_query_too_long(client: AsyncClient, user_headers):
    """验证 query 长度限制"""
    resp = await client.post(
        "/api/v1/chat",
        json={"query": "x" * 5000},
        headers=user_headers,
    )
    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════
# 用户管理 (admin only)
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_admin_can_create_user(client: AsyncClient):
    admin_headers = {"Authorization": "Bearer sk-test-admin"}
    resp = await client.post(
        "/api/v1/users",
        json={"name": "Test User", "role": "user"},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test User"
    assert data["role"] == "user"


@pytest.mark.asyncio
async def test_user_cannot_create_user(client: AsyncClient, user_headers):
    """普通用户不能创建用户"""
    resp = await client.post(
        "/api/v1/users",
        json={"name": "Hacker", "role": "admin"},
        headers=user_headers,
    )
    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/test_server.py -v`

Expected: Tests pass (fallback mode for chat tests since no external LLM key configured in CI).

---

### Task 14: Verification

**Files:** None (manual verification)

- [ ] **Step 1: Start the server**

Run: `uvicorn src.server.main:app --reload --port 8000`

- [ ] **Step 2: Verify health checks**

```bash
curl http://localhost:8000/health/live
# → {"status":"ok"}

curl http://localhost:8000/health/ready
# → {"status":"ok","checks":{"chat_agent":"ok"}}
```

- [ ] **Step 3: Verify auth flow**

```bash
# 无 Key → 401
curl http://localhost:8000/api/v1/me
# → {"error":{"code":"AUTHENTICATION_REQUIRED",...}}

# Admin Key → 200
curl -H "Authorization: Bearer sk-admin-001" http://localhost:8000/api/v1/me
# → {"user_id":"...","name":"Static admin (...)","role":"admin",...}
```

- [ ] **Step 4: Verify chat (fallback mode)**

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer sk-user-001" \
  -H "Content-Type: application/json" \
  -d '{"query":"你好"}'
# → {"answer":"你好！我收到了你的消息...","session_id":"...","citations":[],"token_usage":null}
```

- [ ] **Step 5: Verify SSE stream**

```bash
curl -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Authorization: Bearer sk-user-001" \
  -H "Content-Type: application/json" \
  -d '{"query":"你好"}'
# → event: start ... event: token ... event: done
```

- [ ] **Step 6: Verify CLI still works**

Run: `python src/main.py` and type `/exit` to confirm CLI is unaffected.

---

## Completion Criteria

- [ ] All 13 API tests pass (`pytest tests/test_server.py -v`)
- [ ] `uvicorn src.server.main:app` starts without errors
- [ ] `GET /health/live` → 200
- [ ] `GET /health/ready` → 200
- [ ] No auth → 401
- [ ] Admin can create users and API keys
- [ ] `GET /me` returns correct identity
- [ ] Session CRUD works with user isolation
- [ ] `POST /api/v1/chat` returns answer
- [ ] `POST /api/v1/chat/stream` outputs `start → token* → done`
- [ ] `python src/main.py` CLI still works
- [ ] Existing `ChatAgent.chat()` and `.chat_stream()` unchanged
