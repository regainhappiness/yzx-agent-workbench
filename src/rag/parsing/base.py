"""Parser 协议 + 标准化数据模型"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ParsedTable:
    page_number: int
    caption: str | None = None
    markdown: str = ""


@dataclass
class ParsedPage:
    page_number: int
    text: str = ""
    sections: list[str] = field(default_factory=list)


@dataclass
class ParsedDocument:
    text: str = ""
    pages: list[ParsedPage] = field(default_factory=list)
    tables: list[ParsedTable] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class Parser(Protocol):
    """文档解析器 — 面向文件路径"""

    @property
    def supported_mime_types(self) -> list[str]: ...

    def parse(self, file_path: str, filename: str, mime: str) -> ParsedDocument: ...
