# FastAPI 层设计规格

> 日期: 2026-07-28 | 状态: 已确认 | 关联: [design.md](../../design.md)

## 1. 目标与范围

在现有 Agent-demo 项目上新增 FastAPI HTTP 服务层，提供认证、会话管理和流式问答能力，为后续企业知识库助手提供 API 入口。

### 首版范围

- FastAPI 应用启动、lifespan、健康检查
- API Key 认证 + user/admin 角色
- 会话管理 (CRUD)
- 同步问答 + SSE 流式问答
- `ChatAgent` 原生异步方法 (`achat` / `achat_stream`)
- 统一错误响应、结构化日志、`request_id` 追踪
- 全部内存存储 (用户/Key/会话元数据 + LangGraph MemorySaver)

### 不在首版范围

- 文档上传/检索/Milvus
- SQLite 持久化
- 公共知识库审批
- MCP 工具
- 限流、Docker Compose

---

## 2. 包结构

```
src/server/              ← 新增独立包，不修改现有 src/ 下的 CLI 代码
├── main.py              # FastAPI 应用创建、lifespan、路由注册
├── api/
│   ├── __init__.py
│   ├── auth.py          # POST /api/v1/api-keys
│   ├── users.py         # POST /api/v1/users, GET /api/v1/me
│   ├── sessions.py      # CRUD /api/v1/sessions
│   └── chat.py          # POST /api/v1/chat, POST /api/v1/chat/stream
├── services/
│   ├── __init__.py
│   ├── auth_service.py
│   ├── session_service.py
│   └── chat_service.py
├── repositories/
│   ├── __init__.py
│   ├── base.py          # 协议 (Protocol/ABC)
│   └── memory.py        # 内存实现
├── middleware/
│   ├── __init__.py
│   ├── auth.py          # API Key 校验
│   ├── logging.py       # request_id + 请求日志
│   └── cors.py          # CORS
├── schemas.py           # Pydantic v2 请求/响应模型
├── exceptions.py        # 统一异常类 + 错误码
└── deps.py              # FastAPI 依赖注入 (get_current_user 等)
```

**修改的文件** (仅限为了添加异步方法):

```
src/agents/chat_agent.py  ← 新增 achat() / achat_stream() 异步方法
```

其他现有文件 (`src/main.py`, `src/models/`, `src/tools/`, `src/config/`, `src/utils/`) 保持不变。

---

## 3. 请求流转

```
HTTP Request
  → Middleware (request_id 注入 → 认证校验 → 拒绝或注入 identity)
    → API Router (Pydantic 参数校验 → 提取 body/query/path params)
      → Service (业务编排 → 调用 Repository / ChatAgent)
        → Repository (内存 CRUD) / ChatAgent (LangGraph ainvoke/astream)
          → Response / SSE Stream
```

**依赖方向**: `api → services → repositories ←→ ChatAgent`  
**规则**: API 路由不直接操作 Repository 或 ChatAgent。

---

## 4. 认证设计

### 4.1 静态 Key 配置

在 `.env` 中配置 (后续替换为数据库):

```bash
ADMIN_API_KEYS=sk-admin-001,sk-admin-002
USER_API_KEYS=sk-user-001,sk-user-002
```

### 4.2 认证中间件

`middleware/auth.py` — 全局中间件，处理 `Authorization: Bearer <key>`:

1. 白名单路径放行: `/health/live`, `/health/ready`, `/docs`, `/openapi.json`
2. 提取 Bearer token，匹配静态 Key 列表
3. 确定 `user_id` (取 key 前 8 位哈希作为标识) 和 `role` (`admin` / `user`)
4. 注入 `request.state.user_id`, `request.state.role`, `request.state.api_key_prefix`
5. 不匹配 → 返回 `401 AUTHENTICATION_REQUIRED`

### 4.3 AuthService

```python
class AuthService:
    def __init__(self, user_repo: UserRepository, api_key_repo: ApiKeyRepository):
        ...

    async def validate(api_key: str) -> Identity | None
    async def create_user(name: str, role: str) -> User
    async def create_api_key(user_id: str) -> ApiKeyResponse   # 返回完整 Key 仅此一次
    async def revoke_api_key(key_prefix: str) -> None
```

`ApiKeyResponse` 返回 `{ key: "sk-xxx", prefix: "sk-xxx", created_at: "..." }`，Key 只在创建时返回完整值。

### 4.4 依赖注入

```python
# deps.py
async def get_current_user(request: Request) -> Identity:
    """从 request.state 提取身份，路由层用 Depends(get_current_user) 获取"""

async def require_admin(identity: Identity = Depends(get_current_user)) -> Identity:
    """要求 admin 角色，否则抛 403"""
```

---

## 5. ChatAgent 异步化

### 5.1 修改点

在 `src/agents/chat_agent.py` 中新增两个方法，**不修改任何现有同步方法**:

```python
class ChatAgent(BaseAgent):

    # ═══ 新增: 异步对话 ═══
    async def achat(
        self, user_input: str, thread_id: str = None
    ) -> str:
        """异步对话 — 内部调用 self._graph.ainvoke()"""
        if not self._initialized:
            self.initialize()

        tid = thread_id or self._thread_id
        config_for_check = {"configurable": {"thread_id": tid}}
        current_state = self._graph.get_state(config_for_check)

        if current_state and current_state.values:
            messages = [HumanMessage(content=user_input)]
        else:
            messages = [SystemMessage(content=self.system_prompt),
                        HumanMessage(content=user_input)]

        config = {
            "configurable": {"thread_id": tid},
            "callbacks": [self._token_counter],
            "recursion_limit": self.max_agent_steps * 2,
        }

        result = await self._graph.ainvoke({"messages": messages}, config)

        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage) and msg.content:
                return str(msg.content)
        return "抱歉，我没有生成有效的回复。"

    # ═══ 新增: 异步流式 ═══
    async def achat_stream(
        self, user_input: str, thread_id: str = None
    ) -> AsyncGenerator[str, None]:
        """异步流式 — 内部调用 self._graph.astream()"""
        if not self._initialized:
            self.initialize()

        tid = thread_id or self._thread_id
        ...  # 同 achat 的消息准备逻辑

        config = {"configurable": {"thread_id": tid},
                  "callbacks": [self._token_counter]}

        async for event in self._graph.astream({"messages": messages}, config):
            for node_name, node_output in event.items():
                for msg in node_output.get("messages", []):
                    if isinstance(msg, AIMessage) and msg.content:
                        yield str(msg.content)
```

### 5.2 ChatService

ChatService 封装 ChatAgent 实例管理和 thread_id 构造:

```python
class ChatService:
    def __init__(self):
        self._agents: dict[str, ChatAgent] = {}

    # --- thread_id 构造 (user_id + session_id 共同组成) ---
    @staticmethod
    def _make_tid(user_id: str, session_id: str) -> str:
        return f"{user_id}:{session_id}"

    # --- 实例管理 ---
    def _get_or_create_agent(self, user_id: str) -> ChatAgent:
        if user_id not in self._agents:
            self._agents[user_id] = ChatAgent(stream=True)
            self._agents[user_id].initialize()
        return self._agents[user_id]

    # --- 同步问答 ---
    async def chat(
        self, user_id: str, session_id: str, query: str, scope: str
    ) -> ChatResult:
        agent = self._get_or_create_agent(user_id)
        tid = self._make_tid(user_id, session_id)
        answer = await agent.achat(query, thread_id=tid)
        return ChatResult(answer=answer, session_id=session_id, citations=[], token_usage=None)

    # --- SSE 流式 ---
    async def chat_stream(
        self, user_id: str, session_id: str, query: str, scope: str
    ) -> AsyncGenerator[str, None]:
        agent = self._get_or_create_agent(user_id)
        tid = self._make_tid(user_id, session_id)
        async for chunk in agent.achat_stream(query, thread_id=tid):
            yield chunk
```

**设计理由**: `thread_id = f"{user_id}:{session_id}"` 使会话隔离在 LangGraph Checkpointer 层直接生效，即使应用层逻辑出错也不会串数据。

---

## 6. API 端点

全部使用 `/api/v1` 前缀。

### 6.1 身份管理

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| `POST` | `/api/v1/users` | admin | 创建用户 |
| `POST` | `/api/v1/api-keys` | admin | 为用户生成 API Key |
| `GET` | `/api/v1/me` | any | 当前用户身份信息 |

### 6.2 会话管理

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| `POST` | `/api/v1/sessions` | any | 创建新会话 |
| `GET` | `/api/v1/sessions` | any | 列出当前用户的所有会话 |
| `GET` | `/api/v1/sessions/{session_id}/messages` | owner | 获取会话消息历史 |
| `DELETE` | `/api/v1/sessions/{session_id}` | owner | 删除会话 |

### 6.3 问答

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| `POST` | `/api/v1/chat` | any | 同步问答 |
| `POST` | `/api/v1/chat/stream` | any | SSE 流式问答 |

### 6.4 健康检查

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| `GET` | `/health/live` | none | 应用进程存活 |
| `GET` | `/health/ready` | none | 检查 ChatAgent 可用性 |

---

## 7. Pydantic Schemas

```python
# ── 身份 ──
class CreateUserRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    role: Literal["user", "admin"] = "user"

class CreateApiKeyRequest(BaseModel):
    user_id: str

class ApiKeyResponse(BaseModel):
    key: str           # 完整 Key，仅创建时返回
    prefix: str        # Key 前缀 (sk-xxx...)
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

# ── 会话 ──
class CreateSessionRequest(BaseModel):
    title: str | None = None

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

# ── 问答 ──
class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None     # None → 自动创建新会话
    knowledge_scope: Literal["private", "shared", "hybrid"] = "hybrid"

class Citation(BaseModel):
    index: int
    document_name: str
    scope: Literal["private", "shared"]
    page: int | None
    section: str | None
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

# ── 错误 ──
class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str
    details: dict[str, Any] = {}

class ErrorResponse(BaseModel):
    error: ErrorDetail
```

---

## 8. SSE 流式协议

端点: `POST /api/v1/chat/stream`  
请求体: `ChatRequest` (JSON)  
响应: `text/event-stream`

### 事件类型

| 事件 | 数据 | 触发时机 |
|------|------|----------|
| `start` | `{"session_id": "xxx"}` | 流开始 |
| `status` | `{"stage": "retrieving" \| "thinking" \| "generating"}` | 阶段性状态变更 |
| `token` | `{"text": "回答片段"}` | 逐 token 输出 |
| `citation` | `{"index": 1, "doc_name": "...", "page": 3, "text": "..."}` | 引用锚点 |
| `tool_call` | `{"tool_name": "search", "args": {...}}` | 工具调用开始 |
| `tool_result` | `{"tool_name": "search", "result": "..."}` | 工具调用结束 |
| `error` | `{"code": "AGENT_ERROR", "message": "..."}` | 非致命错误 |
| `done` | `{"session_id": "xxx", "token_usage": {...}}` | 流结束 |

首版实现 `start`, `token`, `error`, `done`，其余事件预留在 `ChatService` 返回结构中。

---

## 9. Session 管理

`SessionService` 管理会话元数据:

```python
class SessionService:
    # 会话 CRUD
    async def create_session(user_id: str, title: str | None = None) -> Session
    async def list_sessions(user_id: str) -> list[Session]
    async def get_session(session_id: str) -> Session | None
    async def delete_session(user_id: str, session_id: str) -> None

    # 消息历史 (从 ChatAgent Checkpointer 读取)
    async def get_messages(user_id: str, session_id: str) -> list[MessageView]
```

**数据模型**:

```python
@dataclass
class Session:
    session_id: str       # UUID
    user_id: str
    title: str | None
    message_count: int    # 从 ChatAgent 获取
    created_at: datetime
    updated_at: datetime
```

消息正文由 LangGraph Checkpointer (MemorySaver) 以 `thread_id = "{user_id}:{session_id}"` 管理，SessionService 不存储消息副本。

---

## 10. Repository 层

### 协议定义

```python
# repositories/base.py

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
    async def delete(self, session_id: str) -> None: ...
```

### 首版实现

`repositories/memory.py` — 所有数据存在 `dict`，通过 `asyncio.Lock` 保护并发写。API Key 存储 SHA-256 哈希，前缀用于匹配和展示。

---

## 11. 中间件

| 中间件 | 职责 |
|--------|------|
| `LoggingMiddleware` | 生成 UUID7 `request_id`、记录请求方法/路径/状态码/耗时、注入日志上下文 |
| `AuthMiddleware` | 解析 `Authorization` 头、匹配 Key、注入 `request.state` |
| `CORSMiddleware` | 允许所有来源 (开发阶段)，`allow_methods=["*"]`, `allow_headers=["*"]` |

注册顺序: `Logging → CORS → Auth`

---

## 12. 错误处理

### 异常类

```python
class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 500, details: dict = None): ...

class AuthenticationError(AppError): ...   # 401
class AuthorizationError(AppError): ...    # 403
class NotFoundError(AppError): ...         # 404
class ValidationError(AppError): ...       # 422
class AgentError(AppError): ...            # 502
```

### 错误码

| 错误码 | HTTP 状态 | 说明 |
|--------|-----------|------|
| `AUTHENTICATION_REQUIRED` | 401 | 缺少或无效 API Key |
| `UNAUTHORIZED` | 403 | 权限不足 |
| `USER_NOT_FOUND` | 404 | 用户不存在 |
| `SESSION_NOT_FOUND` | 404 | 会话不存在 |
| `VALIDATION_ERROR` | 422 | 请求参数校验失败 |
| `AGENT_ERROR` | 502 | AI Agent 执行异常 |
| `INTERNAL_ERROR` | 500 | 未预期的内部错误 |

### 全局异常处理器

```python
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=ErrorDetail(code=exc.code, message=exc.message,
                              request_id=request.state.request_id, details=exc.details or {})
        ).model_dump()
    )
```

---

## 13. Lifespan

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    init_logging()
    app.state.auth_service = AuthService(..., static_keys=load_keys_from_env())
    app.state.session_service = SessionService(...)
    app.state.chat_service = ChatService()
    logger.info("🚀 FastAPI 服务已启动")

    yield

    # shutdown
    logger.info("🛑 FastAPI 服务已关闭")
```

---

## 14. 安全约束

- API Key 仅在创建时返回完整值一次，后续只展示前缀
- 内存中存储 Key 的 SHA-256 哈希，不存明文
- 所有资源访问检查所有权 (`user_id` 匹配)
- 普通用户只能管理自己的会话
- 日志不记录 API Key 完整值（脱敏为 `sk-xxx***yyy`）
- `request_id` 贯穿中间件、服务和错误响应

---

## 15. 同步 CLI 兼容

- `src/main.py` CLI 入口完全不变
- `src/agents/chat_agent.py` 仅新增方法，`chat()` / `chat_stream()` 签名和行为不变
- `src/server/` 是独立包，CLI 不依赖 FastAPI 依赖
- `requirements.txt` 新增 `fastapi`, `uvicorn`, `sse-starlette`

---

## 16. 启动方式

```bash
# CLI 模式 (不变)
python src/main.py

# FastAPI 模式 (新增)
uvicorn src.server.main:app --reload --port 8000
```

---

## 17. 测试策略

### API 测试

- 使用 `httpx.AsyncClient` + `pytest-asyncio` 进行异步 API 测试
- 测试覆盖: 未认证请求返回 401、admin 创建用户、普通用户被拒、创建/列出/删除会话、同步问答、SSE 流式事件顺序
- ChatAgent 的 `achat()` 和 `achat_stream()` 使用 mock LLM 或 fallback 模式测试

### 单元测试

- `AuthService` 的 Key 校验、哈希、角色映射
- `SessionService` 所有权隔离验证
- `ChatService` 的 `_make_tid` 组合 Key 验证

---

## 18. 完成标准

- [ ] `uvicorn src.server.main:app` 可启动
- [ ] `/health/live` 和 `/health/ready` 返回 200
- [ ] 无 API Key 请求返回 401
- [ ] admin 可创建用户和 API Key
- [ ] 用户可查看自己的身份 (`GET /me`)
- [ ] 会话 CRUD 完整可用，用户隔离有效
- [ ] 同步问答 `POST /api/v1/chat` 返回完整回答
- [ ] SSE 流式 `POST /api/v1/chat/stream` 输出 `start → token* → done`
- [ ] `ChatAgent.chat()` 和 `.chat_stream()` 同步方法行为不变
- [ ] `python src/main.py` CLI 模式仍可运行
- [ ] 所有 API 测试通过 (无需外部 API Key)
