"""Chunker 测试"""

from src.rag.parsing.base import ParsedDocument, ParsedPage


def test_paragraph_chunker():
    from src.rag.chunking import ParagraphChunker
    parsed = ParsedDocument(
        text="段落一。\n\n段落二。\n\n段落三。",
        pages=[ParsedPage(page_number=1, text="段落一。\n\n段落二。\n\n段落三。")],
    )
    chunker = ParagraphChunker()
    chunks = chunker.chunk(parsed, "doc-001")
    assert len(chunks) >= 1
    assert all(c.document_id == "doc-001" for c in chunks)
    assert all(c.chunk_hash for c in chunks)


def test_markdown_chunker():
    from src.rag.chunking import MarkdownChunker
    parsed = ParsedDocument(
        text="## 第一节\n\n内容A。\n\n## 第二节\n\n内容B。",
        pages=[ParsedPage(page_number=1, text="## 第一节\n\n内容A。\n\n## 第二节\n\n内容B。")],
    )
    chunker = MarkdownChunker()
    chunks = chunker.chunk(parsed, "doc-002")
    assert len(chunks) >= 1
    all_text = " ".join(c.text for c in chunks)
    assert "内容A" in all_text
    assert "内容B" in all_text


def test_pdf_chunker():
    from src.rag.chunking import PDFChunker
    parsed = ParsedDocument(
        pages=[
            ParsedPage(page_number=1, text="第1页内容A。\n\n第1页内容B。"),
            ParsedPage(page_number=2, text="第2页内容C。"),
        ],
    )
    chunker = PDFChunker()
    chunks = chunker.chunk(parsed, "doc-003")
    assert len(chunks) >= 2
    pages_covered = set()
    for c in chunks:
        pages_covered.add(c.page_start)
        pages_covered.add(c.page_end)
    assert 1 in pages_covered
    assert 2 in pages_covered


def test_chunker_registry_defaults():
    from src.rag.chunking import (
        ChunkerRegistry, ParagraphChunker, MarkdownChunker, PDFChunker,
    )
    reg = ChunkerRegistry()
    assert isinstance(reg.get("text/plain"), ParagraphChunker)
    assert isinstance(reg.get("text/markdown"), MarkdownChunker)
    assert isinstance(reg.get("application/pdf"), PDFChunker)


def test_chunker_registry_override():
    from src.rag.chunking import ChunkerRegistry, ParagraphChunker
    reg = ChunkerRegistry()
    custom = ParagraphChunker()
    reg.override("text/plain", custom)
    assert reg.get("text/plain") is custom


def test_semantic_chunker_not_implemented():
    from src.rag.chunking import SemanticChunker
    parsed = ParsedDocument(text="test")
    chunker = SemanticChunker()
    try:
        chunker.chunk(parsed, "doc-004")
        assert False, "should raise NotImplementedError"
    except NotImplementedError:
        pass
