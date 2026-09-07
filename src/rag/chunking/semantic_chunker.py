"""SemanticChunker — 语义递归分块 (骨架，后续完善)"""

from .base import ChunkingStrategy, Chunk
from ..parsing.base import ParsedDocument


class SemanticChunker:

    @property
    def name(self) -> str:
        return "semantic"

    def chunk(self, parsed: ParsedDocument, document_id: str) -> list[Chunk]:
        raise NotImplementedError("SemanticChunker: 语义递归分块功能尚未实现")
