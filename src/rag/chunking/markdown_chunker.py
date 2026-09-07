"""MarkdownChunker — 按 ## 标题切节，同级下按段落细分"""

from .base import ChunkingStrategy, Chunk, get_token_encoder
from ..parsing.base import ParsedDocument

MAX_TOKENS = 512


class MarkdownChunker:

    @property
    def name(self) -> str:
        return "markdown"

    def chunk(self, parsed: ParsedDocument, document_id: str) -> list[Chunk]:
        enc = get_token_encoder()
        sections_text = parsed.text.split("\n## ")

        chunks = []
        for sec in sections_text:
            if not sec.strip():
                continue
            tokens = enc.encode(sec)
            if len(tokens) <= MAX_TOKENS:
                chunks.append(Chunk(
                    document_id=document_id, chunk_index=len(chunks),
                    text=sec, page_start=1, page_end=1,
                    sections=self._find_sections(sec),
                ))
            else:
                paragraphs = [p.strip() for p in sec.split("\n\n") if p.strip()]
                buffer = ""
                for para in paragraphs:
                    if len(enc.encode(buffer + "\n\n" + para)) <= MAX_TOKENS:
                        buffer = buffer + ("\n\n" if buffer else "") + para
                    else:
                        if buffer:
                            chunks.append(Chunk(
                                document_id=document_id, chunk_index=len(chunks),
                                text=buffer, page_start=1, page_end=1,
                                sections=self._find_sections(sec),
                            ))
                        buffer = para
                if buffer:
                    chunks.append(Chunk(
                        document_id=document_id, chunk_index=len(chunks),
                        text=buffer, page_start=1, page_end=1,
                        sections=self._find_sections(sec),
                    ))
        return chunks

    def _find_sections(self, text: str) -> list[str]:
        return [line.lstrip("#").strip()
                for line in text.split("\n") if line.startswith("#")]
