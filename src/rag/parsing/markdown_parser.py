"""MarkdownParser — Markdown 解析，提取标题层级和表格。

同时提供模块级函数 parse_markdown_text() 供 MinerUParser 等复用:
  输入 Markdown 文本字符串 → 输出 ParsedDocument
"""

import re
import logging
from .base import ParsedDocument, ParsedPage, ParsedTable

logger = logging.getLogger("server.parser.markdown")


# ═══════════════════════════════════════════════════════════════
# 模块级工具函数 — 可被 MinerUParser 等复用
# ═══════════════════════════════════════════════════════════════

def extract_sections(text: str) -> list[str]:
    """从 Markdown 文本中提取标题层级列表。

    识别 # / ## / ### 等 ATX 标题，保留完整标题文本（含编号）。

    >>> extract_sections("# 第一章\\n\\n## 1.1 概述")
    ['第一章', '1.1 概述']
    """
    sections: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#"):
            # 去掉 # 前缀，保留编号和正文
            title = stripped.lstrip("#").strip()
            if title:
                sections.append(title)
    return sections


def extract_tables(text: str) -> list[ParsedTable]:
    """从 Markdown 文本中提取表格。

    识别标准 Markdown 表格格式:
      | Header1 | Header2 |
      |---------|---------|
      | Cell1   | Cell2   |
    """
    tables: list[ParsedTable] = []
    lines = text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        # 检测表头行: 以 | 开头且以 | 结尾
        if (line.startswith("|") and line.endswith("|")
                and not re.match(r'^\|[\s\-:|]+\|$', line)):
            # 下一行必须是分隔行
            if i + 1 < len(lines) and re.match(
                r'^\|[\s\-:|]+\|$', lines[i + 1].strip()
            ):
                table_lines = [lines[i].rstrip(), lines[i + 1].rstrip()]

                # 尝试提取 caption (表格前的非空行)
                caption = None
                if i > 0:
                    prev = lines[i - 1].strip()
                    if prev and not prev.startswith("#"):
                        caption = prev[:200]

                # 收集数据行
                j = i + 2
                while j < len(lines):
                    row = lines[j].strip()
                    if row.startswith("|") and row.endswith("|"):
                        table_lines.append(lines[j].rstrip())
                        j += 1
                    else:
                        break

                tables.append(ParsedTable(
                    page_number=1,
                    caption=caption,
                    markdown="\n".join(table_lines),
                ))
                i = j
                continue
        i += 1

    return tables


def parse_markdown_text(text: str, **metadata) -> ParsedDocument:
    """纯文本 → ParsedDocument。

    MinerU 等外部解析器输出 Markdown 后，调用此函数完成结构化。

    Args:
        text: Markdown 文本
        **metadata: 附加元数据 (如 parser="mineru", model_version="vlm" 等)

    Returns:
        ParsedDocument (单 page, 含 sections 和 tables)
    """
    sections = extract_sections(text)
    tables = extract_tables(text)

    return ParsedDocument(
        text=text,
        pages=[ParsedPage(page_number=1, text=text, sections=sections)],
        tables=tables,
        metadata={
            "sections_count": len(sections),
            "tables_count": len(tables),
            **metadata,
        },
    )


# ═══════════════════════════════════════════════════════════════
# MarkdownParser — 文件 → ParsedDocument
# ═══════════════════════════════════════════════════════════════

class MarkdownParser:
    """Markdown 文件解析器。
    从磁盘读取 .md 文件，委托给 parse_markdown_text() 做结构化。
    """

    @property
    def supported_mime_types(self) -> list[str]:
        return ["text/markdown"]

    def parse(self, file_path: str, filename: str, mime: str) -> ParsedDocument:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()

        return parse_markdown_text(
            text,
            parser="markdown",
            filename=filename,
        )
