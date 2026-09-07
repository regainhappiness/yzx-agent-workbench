"""存储层 — 协议定义 + 内存实现 + SQLite 持久化"""
from .base import (
    UserRepository, ApiKeyRepository, SessionRepository,
    DocumentRepository, ChunkRepository, TaskRepository,
    RuntimeConfigRepository,
    SessionMessageRepository, MultiAgentTurnRepository,
    ConversationSummaryRepository,
    MultiAgentWorkspaceRepository, MultiAgentAttachmentRepository,
    User, ApiKey, Session, SessionType, Identity,
    Document, ChunkRecord, TaskRecord, RuntimeConfigRecord,
    SessionMessage, MultiAgentTurn, ConversationSummary,
    MultiAgentWorkspace, MultiAgentAttachment,
)
from .memory import (
    InMemoryUserRepo, InMemoryApiKeyRepo, InMemorySessionRepo,
    InMemoryDocumentRepo, InMemoryChunkRepo, InMemoryTaskRepo,
    InMemoryRuntimeConfigRepo,
    InMemorySessionMessageRepo, InMemoryMultiAgentTurnRepo,
    InMemoryConversationSummaryRepo,
    InMemoryMultiAgentWorkspaceRepo, InMemoryMultiAgentAttachmentRepo,
)
from .sqlite import (
    SqliteDb,
    SqliteUserRepo, SqliteApiKeyRepo, SqliteSessionRepo,
    SqliteDocumentRepo, SqliteChunkRepo, SqliteTaskRepo,
    SqliteRuntimeConfigRepo,
    SqliteSessionMessageRepo, SqliteMultiAgentTurnRepo,
    SqliteConversationSummaryRepo,
    SqliteMultiAgentWorkspaceRepo, SqliteMultiAgentAttachmentRepo,
    DEFAULT_DB_PATH,
)

__all__ = [
    "UserRepository", "ApiKeyRepository", "SessionRepository",
    "DocumentRepository", "ChunkRepository", "TaskRepository",
    "RuntimeConfigRepository",
    "SessionMessageRepository", "MultiAgentTurnRepository",
    "ConversationSummaryRepository",
    "MultiAgentWorkspaceRepository", "MultiAgentAttachmentRepository",
    "User", "ApiKey", "Session", "SessionType", "Identity",
    "Document", "ChunkRecord", "TaskRecord", "RuntimeConfigRecord",
    "SessionMessage", "MultiAgentTurn", "ConversationSummary",
    "MultiAgentWorkspace", "MultiAgentAttachment",
    # 内存实现
    "InMemoryUserRepo", "InMemoryApiKeyRepo", "InMemorySessionRepo",
    "InMemoryDocumentRepo", "InMemoryChunkRepo", "InMemoryTaskRepo",
    "InMemoryRuntimeConfigRepo",
    "InMemorySessionMessageRepo", "InMemoryMultiAgentTurnRepo",
    "InMemoryConversationSummaryRepo",
    "InMemoryMultiAgentWorkspaceRepo", "InMemoryMultiAgentAttachmentRepo",
    # SQLite 持久化
    "SqliteDb",
    "SqliteUserRepo", "SqliteApiKeyRepo", "SqliteSessionRepo",
    "SqliteDocumentRepo", "SqliteChunkRepo", "SqliteTaskRepo",
    "SqliteRuntimeConfigRepo",
    "SqliteSessionMessageRepo", "SqliteMultiAgentTurnRepo",
    "SqliteConversationSummaryRepo",
    "SqliteMultiAgentWorkspaceRepo", "SqliteMultiAgentAttachmentRepo",
    "DEFAULT_DB_PATH",
]
