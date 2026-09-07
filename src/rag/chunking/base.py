"""分块策略协议 + Chunk 数据模型"""

import uuid
import hashlib
import math
from functools import lru_cache
from datetime import datetime
from dataclasses import dataclass, field
from typing import Protocol

from ..parsing.base import ParsedDocument


class _ApproximateEncoder:
    """Offline fallback used when tiktoken's encoding asset is not cached."""

    @staticmethod
    def encode(text: str) -> list[int]:
        cjk = sum(1 for char in text if "\u3400" <= char <= "\u9fff")
        other = max(0, len(text) - cjk)
        return [0] * max(1, cjk + math.ceil(other / 4)) if text else []


@lru_cache(maxsize=1)
def get_token_encoder():
    try:
        import tiktoken
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return _ApproximateEncoder()


@dataclass
class Chunk:
    chunk_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    document_id: str = ""
    chunk_index: int = 0
    chunk_hash: str = ""
    text: str = ""
    page_start: int = 1
    page_end: int = 1
    sections: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        if not self.chunk_hash and self.text:
            self.chunk_hash = hashlib.sha256(self.text.encode()).hexdigest()


class ChunkingStrategy(Protocol):

    @property
    def name(self) -> str: ...

    def chunk(self, parsed: ParsedDocument, document_id: str) -> list[Chunk]: ...
