"""存储层协议定义"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol


SessionType = Literal["chat", "multi_agent"]
MessageRole = Literal["user", "assistant"]
MessageStatus = Literal["pending", "complete", "failed", "cancelled"]
TurnStatus = Literal["running", "completed", "failed", "cancelled"]
WorkspacePermission = Literal["read_only", "read_write"]
AttachmentSource = Literal["file_picker", "clipboard"]


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
class Identity:
    user_id: str
    role: str
    api_key_prefix: str


@dataclass
class Session:
    session_id: str
    user_id: str
    session_type: SessionType
    title: str | None
    message_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


class UserRepository(Protocol):
    async def create(self, name: str, role: str) -> User: ...
    async def get_by_id(self, user_id: str) -> User | None: ...
    async def list_all(self) -> list[User]: ...
    async def delete(self, user_id: str) -> None: ...


class ApiKeyRepository(Protocol):
    async def create(self, user_id: str, key_hash: str, prefix: str) -> ApiKey: ...
    async def validate(self, api_key: str) -> Identity | None: ...
    async def revoke(self, prefix: str) -> None: ...
    async def list_by_user(self, user_id: str) -> list[ApiKey]: ...


class SessionRepository(Protocol):
    async def create(
        self, user_id: str, title: str | None, session_type: SessionType,
    ) -> Session: ...
    async def get(self, session_id: str) -> Session | None: ...
    async def list_by_user(
        self, user_id: str, session_type: SessionType,
    ) -> list[Session]: ...
    async def update(self, session_id: str, **kwargs) -> Session | None: ...
    async def delete(self, session_id: str) -> None: ...


# ═══════════════════════════════════════════════════════════════
# 会话消息与 Multi-Agent 轮次
# ═══════════════════════════════════════════════════════════════

@dataclass
class SessionMessage:
    message_id: str
    session_id: str
    turn_id: str
    role: MessageRole
    content: str
    status: MessageStatus = "complete"
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class MultiAgentTurn:
    turn_id: str
    session_id: str
    user_id: str
    status: TurnStatus = "running"
    intent: str = "new_task"
    resolved_task: str = ""
    plan: list[dict] = field(default_factory=list)
    results: dict[str, str] = field(default_factory=dict)
    step_statuses: dict[str, str] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)
    resume_step: int = 0
    final_answer: str = ""
    error_message: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None


@dataclass
class ConversationSummary:
    session_id: str
    summary: str
    covered_message_count: int = 0
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class MultiAgentWorkspace:
    session_id: str
    user_id: str
    root_path: str
    permission: WorkspacePermission = "read_only"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class MultiAgentAttachment:
    attachment_id: str
    session_id: str
    user_id: str
    filename: str
    storage_path: str
    mime_type: str
    file_size: int
    file_hash: str
    source: AttachmentSource = "file_picker"
    turn_id: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)


class SessionMessageRepository(Protocol):
    async def create(self, message: SessionMessage) -> SessionMessage: ...
    async def list_by_session(self, session_id: str) -> list[SessionMessage]: ...
    async def count_by_session(self, session_id: str) -> int: ...
    async def delete_by_session(self, session_id: str) -> None: ...


class MultiAgentTurnRepository(Protocol):
    async def create(self, turn: MultiAgentTurn) -> MultiAgentTurn: ...
    async def get(self, turn_id: str) -> MultiAgentTurn | None: ...
    async def list_by_session(self, session_id: str) -> list[MultiAgentTurn]: ...
    async def update(self, turn_id: str, **kwargs) -> MultiAgentTurn | None: ...
    async def delete_by_session(self, session_id: str) -> None: ...


class ConversationSummaryRepository(Protocol):
    async def get(self, session_id: str) -> ConversationSummary | None: ...
    async def upsert(self, summary: ConversationSummary) -> ConversationSummary: ...
    async def delete(self, session_id: str) -> None: ...


class MultiAgentWorkspaceRepository(Protocol):
    async def get(self, session_id: str) -> MultiAgentWorkspace | None: ...
    async def upsert(self, workspace: MultiAgentWorkspace) -> MultiAgentWorkspace: ...
    async def delete(self, session_id: str) -> None: ...


class MultiAgentAttachmentRepository(Protocol):
    async def create(self, attachment: MultiAgentAttachment) -> MultiAgentAttachment: ...
    async def get(self, attachment_id: str) -> MultiAgentAttachment | None: ...
    async def list_by_session(self, session_id: str) -> list[MultiAgentAttachment]: ...
    async def bind_to_turn(self, attachment_ids: list[str], turn_id: str) -> None: ...
    async def delete(self, attachment_id: str) -> None: ...
    async def delete_by_session(self, session_id: str) -> None: ...


# ═══════════════════════════════════════════════════════════════
# Document
# ═══════════════════════════════════════════════════════════════

@dataclass
class Document:
    document_id: str
    user_id: str
    filename: str
    storage_key: str
    mime_type: str
    file_size: int = 0
    file_hash: str = ""
    scope: str = "private"
    status: str = "uploaded"
    chunk_count: int = 0
    error_message: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


class DocumentRepository(Protocol):
    async def create(self, doc: Document) -> Document: ...
    async def get(self, document_id: str) -> Document | None: ...
    async def get_many(self, document_ids: list[str]) -> list[Document]: ...
    async def list_by_user(self, user_id: str) -> list[Document]: ...
    async def list_by_user_paginated(
        self,
        user_id: str,
        *,
        offset: int,
        limit: int,
        search: str | None = None,
        scope: str | None = None,
        statuses: list[str] | None = None,
    ) -> tuple[list[Document], int]: ...
    async def update(self, document_id: str, **kwargs) -> Document | None: ...
    async def delete(self, document_id: str) -> None: ...


# ═══════════════════════════════════════════════════════════════
# Chunk
# ═══════════════════════════════════════════════════════════════

@dataclass
class ChunkRecord:
    chunk_id: str
    document_id: str
    user_id: str
    chunk_index: int
    chunk_hash: str
    text: str
    page_start: int
    page_end: int
    sections: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


class ChunkRepository(Protocol):
    async def batch_save(self, chunks: list[ChunkRecord]) -> None: ...
    async def get_by_document(self, document_id: str) -> list[ChunkRecord]: ...
    async def delete_by_document(self, document_id: str, user_id: str = "") -> None: ...


# ═══════════════════════════════════════════════════════════════
# Task
# ═══════════════════════════════════════════════════════════════

@dataclass
class TaskRecord:
    task_id: str
    document_id: str
    status: str
    progress: float = 0.0
    error_message: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


class TaskRepository(Protocol):
    async def save(self, task: TaskRecord) -> None: ...
    async def get(self, task_id: str) -> TaskRecord | None: ...
    async def get_many(self, task_ids: list[str]) -> list[TaskRecord]: ...
    async def list_by_document(self, document_id: str) -> list[TaskRecord]: ...
    async def list_incomplete(self) -> list[TaskRecord]: ...


# ═══════════════════════════════════════════════════════════════
# Runtime configuration
# ═══════════════════════════════════════════════════════════════

@dataclass
class RuntimeConfigRecord:
    config_id: str
    category: str
    name: str
    enabled: bool
    payload: str
    revision: int = 1
    status: str = "unconfigured"
    last_error: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


class RuntimeConfigRepository(Protocol):
    async def list_by_category(self, category: str) -> list[RuntimeConfigRecord]: ...
    async def get(self, config_id: str) -> RuntimeConfigRecord | None: ...
    async def upsert(self, record: RuntimeConfigRecord) -> RuntimeConfigRecord: ...
    async def update_status(
        self, config_id: str, status: str, last_error: str | None = None,
    ) -> None: ...
    async def delete(self, config_id: str) -> None: ...
