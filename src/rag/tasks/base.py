"""TaskQueue 协议"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


class TaskStatus(str, Enum):
    QUEUED = "queued"
    PARSING = "parsing"
    CHUNKING = "chunking"
    DONE = "done"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass
class TaskInfo:
    task_id: str
    document_id: str
    status: str = TaskStatus.QUEUED.value
    progress: float = 0.0
    error_message: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


class TaskQueue(Protocol):
    async def enqueue(self, document_id: str) -> str: ...
    async def get(self, task_id: str) -> TaskInfo | None: ...
    async def get_many(self, task_ids: list[str]) -> list[TaskInfo]: ...
    async def recover(self) -> int: ...
    async def close(self) -> None: ...
