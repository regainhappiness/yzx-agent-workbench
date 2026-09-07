"""解析层 — Parser 协议 + 注册中心 + 实现"""
from .base import Parser, ParsedDocument, ParsedPage, ParsedTable
from .registry import ParserRegistry
from .text_parser import TextParser
from .markdown_parser import (
    MarkdownParser,
    parse_markdown_text,
    extract_sections,
    extract_tables,
)
from .mineru_parser import MinerUParser, parse_pdf_with_pypdf
from .mineru_agent_parser import MinerUAgentParser
from .placeholders import register_placeholders

__all__ = [
    "Parser", "ParsedDocument", "ParsedPage", "ParsedTable",
    "ParserRegistry", "TextParser", "MarkdownParser", "MinerUParser",
    "MinerUAgentParser",
    "parse_markdown_text", "extract_sections", "extract_tables",
    "parse_pdf_with_pypdf",
    "register_placeholders",
]
