"""分块策略注册中心"""

from .base import ChunkingStrategy
from .paragraph_chunker import ParagraphChunker
from .markdown_chunker import MarkdownChunker
from .pdf_chunker import PDFChunker


class ChunkerRegistry:

    def __init__(self):
        self._defaults: dict[str, ChunkingStrategy] = {
            "text/plain": ParagraphChunker(),
            "text/markdown": MarkdownChunker(),
            "application/pdf": PDFChunker(),
        }
        self._overrides: dict[str, ChunkingStrategy] = {}

    def get(self, mime: str) -> ChunkingStrategy:
        if mime in self._overrides:
            return self._overrides[mime]
        if mime in self._defaults:
            return self._defaults[mime]
        return self._defaults["text/plain"]

    def override(self, mime: str, strategy: ChunkingStrategy) -> None:
        self._overrides[mime] = strategy
