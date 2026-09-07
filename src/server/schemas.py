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


class ApiKeyInfo(BaseModel):
    """API Key 信息 (不含原始 Key — 仅展示用)"""
    prefix: str
    user_id: str
    created_at: datetime
    revoked_at: datetime | None = None


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
# 运行时配置
# ═══════════════════════════════════════════════════════════════

class LlmConfigRequest(BaseModel):
    provider: Literal["openai", "deepseek", "anthropic"]
    model_name: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(default=None, max_length=10000)
    base_url: str | None = Field(default=None, max_length=1000)
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=1_000_000)


class LlmConfigResponse(BaseModel):
    configured: bool
    provider: str
    model_name: str
    base_url: str | None = None
    temperature: float
    max_tokens: int | None = None
    api_key_configured: bool
    api_key_hint: str | None = None
    source: str
    revision: int
    status: str
    last_error: str | None = None


class ConfigTestResponse(BaseModel):
    success: bool
    message: str
    tool_count: int | None = None


class McpServerConfigRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    transport: Literal["stdio", "streamable-http"]
    enabled: bool = True
    command: str | None = Field(default=None, max_length=1000)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = Field(default=None, max_length=2000)
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    allowed_tools: list[str] = Field(default_factory=lambda: ["*"])
    subagents: list[str] = Field(default_factory=lambda: ["*"])


class McpServerConfigResponse(McpServerConfigRequest):
    config_id: str
    revision: int
    status: str
    last_error: str | None = None
    tool_count: int = 0
    created_at: datetime
    updated_at: datetime


class McpEnabledRequest(BaseModel):
    enabled: bool


# ═══════════════════════════════════════════════════════════════
# 会话
# ═══════════════════════════════════════════════════════════════

class CreateSessionRequest(BaseModel):
    session_type: Literal["chat", "multi_agent"]
    title: str | None = Field(default=None, max_length=200)


class UpdateSessionRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class SessionResponse(BaseModel):
    session_id: str
    session_type: Literal["chat", "multi_agent"]
    title: str | None
    message_count: int
    created_at: datetime
    updated_at: datetime


class MessageView(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    message_id: str | None = None
    turn_id: str | None = None
    status: str = "complete"
    metadata: dict[str, Any] = Field(default_factory=dict)


class MultiAgentWorkspaceRequest(BaseModel):
    root_path: str = Field(min_length=1, max_length=4096)
    permission: Literal["read_only", "read_write"] = "read_only"


class MultiAgentWorkspaceResponse(BaseModel):
    session_id: str
    root_path: str
    permission: Literal["read_only", "read_write"]
    created_at: datetime
    updated_at: datetime


class MultiAgentWorkspaceRootsResponse(BaseModel):
    roots: list[str]


class MultiAgentAttachmentResponse(BaseModel):
    attachment_id: str
    session_id: str
    turn_id: str | None = None
    filename: str
    mime_type: str
    file_size: int
    source: Literal["file_picker", "clipboard"]
    kind: Literal["text", "image", "pdf_office_unparsed", "binary"]
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
# 文档
# ═══════════════════════════════════════════════════════════════

class DocumentResponse(BaseModel):
    document_id: str
    filename: str
    mime_type: str
    file_size: int
    scope: str
    status: str
    chunk_count: int = 0
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentPageResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    mime_type: str
    file_size: int
    scope: str
    status: str
    task_id: str
    created_at: datetime


class DocumentBatchUploadItemResponse(BaseModel):
    filename: str
    success: bool
    document: DocumentUploadResponse | None = None
    error_code: str | None = None
    error_message: str | None = None


class DocumentBatchUploadResponse(BaseModel):
    total: int
    succeeded: int
    failed: int
    results: list[DocumentBatchUploadItemResponse]


class TaskResponse(BaseModel):
    task_id: str
    document_id: str
    status: str
    progress: float
    error_message: str | None
    created_at: datetime
    updated_at: datetime


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
