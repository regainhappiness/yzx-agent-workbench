"""ParagraphChunker — 按 \n\n 切分，限制 512 token"""

from .base import ChunkingStrategy, Chunk, get_token_encoder
from ..parsing.base import ParsedDocument

MAX_TOKENS = 512


class ParagraphChunker:

    @property
    def name(self) -> str:
        return "paragraph"

    def chunk(self, parsed: ParsedDocument, document_id: str) -> list[Chunk]:
        enc = get_token_encoder()
        paragraphs = [p.strip() for p in parsed.text.split("\n\n") if p.strip()]

        chunks = []
        buffer = ""
        for para in paragraphs:
            combined = buffer + ("\n\n" if buffer else "") + para
            if len(enc.encode(combined)) <= MAX_TOKENS:
                buffer = combined
            else:
                if buffer:
                    chunks.append(self._make_chunk(buffer, document_id, len(chunks), 1, 1))
                if len(enc.encode(para)) > MAX_TOKENS:
                    sub = self._split_long_para(para, enc, document_id, len(chunks), 1, 1)
                    chunks.extend(sub)
                    buffer = ""
                else:
                    buffer = para

        if buffer:
            chunks.append(self._make_chunk(buffer, document_id, len(chunks), 1, 1))

        return chunks

    def _make_chunk(self, text, doc_id, idx, page_start, page_end):
        return Chunk(
            document_id=doc_id, chunk_index=idx,
            text=text, page_start=page_start, page_end=page_end,
        )

    def _split_long_para(self, para, enc, doc_id, start_idx, page_start, page_end):
        sentences = para.replace("。", "。\n").split("\n")
        chunks = []
        buffer = ""
        for s in sentences:
            if len(enc.encode(buffer + s)) <= MAX_TOKENS:
                buffer += s
            else:
                if buffer:
                    chunks.append(self._make_chunk(buffer, doc_id, start_idx + len(chunks), page_start, page_end))
                buffer = s
        if buffer:
            chunks.append(self._make_chunk(buffer, doc_id, start_idx + len(chunks), page_start, page_end))
        return chunks
