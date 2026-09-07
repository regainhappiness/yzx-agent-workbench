"""PDFChunker — 以页为边界，单页大内容按段细分"""

from .base import ChunkingStrategy, Chunk, get_token_encoder
from ..parsing.base import ParsedDocument

MAX_TOKENS = 512


class PDFChunker:

    @property
    def name(self) -> str:
        return "pdf"

    def chunk(self, parsed: ParsedDocument, document_id: str) -> list[Chunk]:
        enc = get_token_encoder()
        chunks = []
        for page in parsed.pages:
            page_tokens = enc.encode(page.text)
            if len(page_tokens) <= MAX_TOKENS:
                chunks.append(Chunk(
                    document_id=document_id, chunk_index=len(chunks),
                    text=page.text, page_start=page.page_number,
                    page_end=page.page_number, sections=page.sections,
                ))
            else:
                paragraphs = [p.strip() for p in page.text.split("\n\n") if p.strip()]
                buffer = ""
                for para in paragraphs:
                    if len(enc.encode(buffer + "\n\n" + para)) <= MAX_TOKENS:
                        buffer = buffer + ("\n\n" if buffer else "") + para
                    else:
                        if buffer:
                            chunks.append(Chunk(
                                document_id=document_id, chunk_index=len(chunks),
                                text=buffer, page_start=page.page_number,
                                page_end=page.page_number, sections=page.sections,
                            ))
                        buffer = para
                if buffer:
                    chunks.append(Chunk(
                        document_id=document_id, chunk_index=len(chunks),
                        text=buffer, page_start=page.page_number,
                        page_end=page.page_number, sections=page.sections,
                    ))
        return chunks
