# 文档上传与解析层实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增文档上传、解析和分块能力 — ObjectStorage 双实现（本地+OSS）、Parser 注册中心（含 MinerU API）、Chunking 策略、后台任务队列、文档 CRUD API。

**Architecture:** 在 `src/server/` 下新增 `storage/`、`parsing/`、`chunking/`、`tasks/`、`documents/` 五个子包。Repository 层新增 Document/Chunk/Task 协议和内存实现。处理管线: 上传→存储→Parser→Chunker→TaskQueue，每个环节通过协议解耦。

**Tech Stack:** pypdf, oss2, python-magic, asyncio

**Spec:** [2026-07-29-document-ingestion-design.md](../specs/2026-07-29-document-ingestion-design.md)

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `requirements.txt` | Modify | Add pypdf, oss2, python-magic |
| `src/server/exceptions.py` | Modify | Add document error codes |
| `src/server/schemas.py` | Modify | Add document Pydantic models |
| `src/server/repositories/base.py` | Modify | Add DocumentRepo/ChunkRepo/TaskRepo protocols + dataclasses |
| `src/server/repositories/memory.py` | Modify | Add InMemoryDocumentRepo/ChunkRepo/TaskRepo |
| `src/server/storage/__init__.py` | Create | Re-exports + create_storage factory |
| `src/server/storage/base.py` | Create | ObjectStorage protocol |
| `src/server/storage/local.py` | Create | LocalStorage |
| `src/server/storage/oss.py` | Create | AliyunOSSStorage |
| `src/server/parsing/__init__.py` | Create | Re-exports |
| `src/server/parsing/base.py` | Create | Parser protocol + ParsedDocument/ParsedPage/ParsedTable |
| `src/server/parsing/registry.py` | Create | ParserRegistry |
| `src/server/parsing/text_parser.py` | Create | TextParser |
| `src/server/parsing/markdown_parser.py` | Create | MarkdownParser |
| `src/server/parsing/mineru_parser.py` | Create | MinerUParser (API) |
| `src/server/parsing/placeholders.py` | Create | 预留 Parser 能力声明 |
| `src/server/chunking/__init__.py` | Create | Re-exports |
| `src/server/chunking/base.py` | Create | ChunkingStrategy protocol + Chunk dataclass |
| `src/server/chunking/registry.py` | Create | ChunkerRegistry |
| `src/server/chunking/paragraph_chunker.py` | Create | ParagraphChunker |
| `src/server/chunking/markdown_chunker.py` | Create | MarkdownChunker |
| `src/server/chunking/pdf_chunker.py` | Create | PDFChunker |
| `src/server/chunking/semantic_chunker.py` | Create | SemanticChunker (skeleton) |
| `src/server/tasks/__init__.py` | Create | Re-exports |
| `src/server/tasks/base.py` | Create | TaskQueue protocol + TaskStatus + TaskInfo |
| `src/server/tasks/in_process.py` | Create | InProcessTaskQueue |
| `src/server/tasks/worker.py` | Create | TaskWorker |
| `src/server/documents/__init__.py` | Create | Re-exports |
| `src/server/documents/errors.py` | Create | Document error codes |
| `src/server/documents/service.py` | Create | DocumentService |
| `src/server/documents/router.py` | Create | API routes |
| `src/server/main.py` | Modify | lifespan: init storage/parser/chunker/taskqueue |
| `src/server/api/__init__.py` | Modify | Register documents router |
| `tests/test_storage.py` | Create | Storage tests |
| `tests/test_parsing.py` | Create | Parser tests |
| `tests/test_chunking.py` | Create | Chunker tests |
| `tests/test_document_api.py` | Create | Document API integration tests |

---

### Task 1: Update dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add new dependencies**

Append to `requirements.txt`:
```
# 文档处理
pypdf>=5.0
python-magic>=0.4

# 阿里云 OSS (可选)
oss2>=2.18
```

---

### Task 2: Storage layer — protocol + LocalStorage + AliyunOSSStorage

**Files:**
- Create: `src/server/storage/__init__.py`
- Create: `src/server/storage/base.py`
- Create: `src/server/storage/local.py`
- Create: `src/server/storage/oss.py`

- [ ] **Step 1: Create protocol**

`src/server/storage/__init__.py`:
```python
"""对象存储 — 协议 + 本地 + OSS"""
from .base import ObjectStorage
from .local import LocalStorage
from .oss import AliyunOSSStorage

def create_storage() -> ObjectStorage:
    import os
    backend = os.getenv("STORAGE_BACKEND", "local")
    if backend == "oss":
        return AliyunOSSStorage(
            endpoint=os.getenv("OSS_ENDPOINT", ""),
            bucket_name=os.getenv("OSS_BUCKET_NAME", ""),
            access_key_id=os.getenv("OSS_ACCESS_KEY_ID", ""),
            access_key_secret=os.getenv("OSS_ACCESS_KEY_SECRET", ""),
        )
    return LocalStorage(
        base_dir=os.getenv("STORAGE_LOCAL_DIR", "./storage/files")
    )

__all__ = ["ObjectStorage", "LocalStorage", "AliyunOSSStorage", "create_storage"]
```

`src/server/storage/base.py`:
```python
"""ObjectStorage 协议定义"""

from typing import Protocol


class ObjectStorage(Protocol):

    async def save(self, content: bytes, extension: str) -> str:
        """保存文件，返回 storage_key"""
        ...

    async def read(self, key: str) -> bytes:
        """读取文件内容"""
        ...

    async def delete(self, key: str) -> None:
        """删除文件 (幂等)"""
        ...

    async def exists(self, key: str) -> bool:
        """检查文件是否存在"""
        ...

    def resolve_path(self, key: str) -> str | None:
        """获取本地文件路径。仅 LocalStorage 返回有效路径，OSS 返回 None"""
        ...
```

- [ ] **Step 2: Implement LocalStorage**

`src/server/storage/local.py`:
```python
"""LocalStorage — 本地文件系统存储"""

import os
import uuid
import aiofiles
import logging

logger = logging.getLogger("server.storage.local")


class LocalStorage:

    def __init__(self, base_dir: str = "./storage/files"):
        self._base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

    def _key_to_path(self, key: str) -> str:
        return os.path.join(self._base_dir, key)

    async def save(self, content: bytes, extension: str) -> str:
        # 三级桶结构: {xx}/{yy}/{uuid}.{ext}
        bucket1 = str(uuid.uuid4())[:2]
        bucket2 = str(uuid.uuid4())[:2]
        file_id = str(uuid.uuid4())
        ext = extension.lstrip(".")
        key = f"{bucket1}/{bucket2}/{file_id}.{ext}"

        full_path = self._key_to_path(key)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        async with aiofiles.open(full_path, "wb") as f:
            await f.write(content)

        logger.debug("文件已保存: key=%s, size=%d", key, len(content))
        return key

    async def read(self, key: str) -> bytes:
        full_path = self._key_to_path(key)
        async with aiofiles.open(full_path, "rb") as f:
            return await f.read()

    async def delete(self, key: str) -> None:
        full_path = self._key_to_path(key)
        try:
            os.remove(full_path)
        except FileNotFoundError:
            pass  # 幂等

    async def exists(self, key: str) -> bool:
        return os.path.exists(self._key_to_path(key))

    def resolve_path(self, key: str) -> str:
        return self._key_to_path(key)
```

- [ ] **Step 3: Implement AliyunOSSStorage**

`src/server/storage/oss.py`:
```python
"""AliyunOSSStorage — 阿里云 OSS 对象存储"""

import os
import uuid
import tempfile
import logging

logger = logging.getLogger("server.storage.oss")


class AliyunOSSStorage:

    def __init__(self, endpoint: str, bucket_name: str,
                 access_key_id: str, access_key_secret: str):
        import oss2
        self._bucket = oss2.Bucket(
            oss2.Auth(access_key_id, access_key_secret),
            endpoint, bucket_name,
        )

    async def save(self, content: bytes, extension: str) -> str:
        bucket1 = str(uuid.uuid4())[:2]
        bucket2 = str(uuid.uuid4())[:2]
        file_id = str(uuid.uuid4())
        ext = extension.lstrip(".")
        key = f"{bucket1}/{bucket2}/{file_id}.{ext}"

        self._bucket.put_object(key, content)
        logger.debug("OSS 文件已保存: key=%s, size=%d", key, len(content))
        return key

    async def read(self, key: str) -> bytes:
        result = self._bucket.get_object(key)
        return result.read()

    async def delete(self, key: str) -> None:
        try:
            self._bucket.delete_object(key)
        except Exception:
            pass

    async def exists(self, key: str) -> bool:
        return self._bucket.object_exists(key)

    def resolve_path(self, key: str) -> str | None:
        return None  # OSS 无本地路径
```

---

### Task 3: Parser layer — protocol + registry + 3 parsers + placeholders

**Files:**
- Create: `src/server/parsing/__init__.py`
- Create: `src/server/parsing/base.py`
- Create: `src/server/parsing/registry.py`
- Create: `src/server/parsing/text_parser.py`
- Create: `src/server/parsing/markdown_parser.py`
- Create: `src/server/parsing/mineru_parser.py`
- Create: `src/server/parsing/placeholders.py`

- [ ] **Step 1: Create parser base types**

`src/server/parsing/__init__.py`:
```python
"""解析层 — Parser 协议 + 注册中心 + 实现"""
from .base import Parser, ParsedDocument, ParsedPage, ParsedTable
from .registry import ParserRegistry
from .text_parser import TextParser
from .markdown_parser import MarkdownParser
from .mineru_parser import MinerUParser
from .placeholders import register_placeholders

__all__ = [
    "Parser", "ParsedDocument", "ParsedPage", "ParsedTable",
    "ParserRegistry", "TextParser", "MarkdownParser", "MinerUParser",
    "register_placeholders",
]
```

`src/server/parsing/base.py`:
```python
"""Parser 协议 + 标准化数据模型"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ParsedTable:
    page_number: int
    caption: str | None = None
    markdown: str = ""  # Markdown 格式的表格内容


@dataclass
class ParsedPage:
    page_number: int          # 从 1 开始
    text: str = ""            # 该页的结构化文本
    sections: list[str] = field(default_factory=list)  # 标题层级如 ["第1章", "1.1 概述"]


@dataclass
class ParsedDocument:
    text: str = ""            # 完整的结构化文本 (Markdown 格式)
    pages: list[ParsedPage] = field(default_factory=list)
    tables: list[ParsedTable] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class Parser(Protocol):
    """文档解析器 — 面向文件路径"""

    @property
    def supported_mime_types(self) -> list[str]: ...

    def parse(self, file_path: str, filename: str, mime: str) -> ParsedDocument: ...
```

- [ ] **Step 2: Create ParserRegistry**

`src/server/parsing/registry.py`:
```python
"""Parser 注册中心 — 扩展名优先 + MIME 回退 + 安全校验"""

import logging

from .base import Parser
from ..exceptions import AppError

logger = logging.getLogger("server.parser_registry")

# 扩展名 → 预期 MIME 白名单 (安全校验用)
EXTENSION_MIME_MAP = {
    ".txt":  {"text/plain"},
    ".md":   {"text/markdown", "text/plain"},
    ".pdf":  {"application/pdf"},
}


class ParserRegistry:

    def __init__(self):
        self._by_extension: dict[str, Parser] = {}
        self._by_mime: dict[str, Parser] = {}
        self._capabilities: list[dict] = []  # 包括预留未实现的

    def register(self, parser, extensions: list[str],
                 mime_types: list[str], available: bool = True) -> None:
        for ext in extensions:
            self._by_extension[ext] = parser
        for mt in mime_types:
            self._by_mime[mt] = parser
        self._capabilities.append({
            "extensions": extensions,
            "mime_types": mime_types,
            "available": available,
        })

    def select(self, mime: str, filename: str) -> Parser:
        # 1. 扩展名优先
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext in self._by_extension:
            if self._validate_mime(mime, ext):
                return self._by_extension[ext]

        # 2. MIME 回退
        if mime in self._by_mime:
            return self._by_mime[mime]

        raise AppError(
            code="UNSUPPORTED_FORMAT",
            message=f"不支持的文件格式: {filename} ({mime})",
            status_code=400,
        )

    def _validate_mime(self, mime: str, ext: str) -> bool:
        allowed = EXTENSION_MIME_MAP.get(ext)
        if allowed is None:
            return True  # 未知扩展名不校验
        if mime not in allowed:
            raise AppError(
                code="MIME_MISMATCH",
                message=f"文件扩展名 {ext} 与 MIME 类型 {mime} 不匹配",
                status_code=400,
            )
        return True

    def list_capabilities(self) -> list[dict]:
        return self._capabilities
```

- [ ] **Step 3: Implement TextParser + MarkdownParser**

`src/server/parsing/text_parser.py`:
```python
"""TextParser — 纯文本解析"""

import logging
from .base import Parser, ParsedDocument, ParsedPage

logger = logging.getLogger("server.parser.text")


class TextParser:

    @property
    def supported_mime_types(self) -> list[str]:
        return ["text/plain"]

    def parse(self, file_path: str, filename: str, mime: str) -> ParsedDocument:
        # 编码检测
        try:
            import chardet
            with open(file_path, "rb") as f:
                raw = f.read()
            encoding = chardet.detect(raw).get("encoding", "utf-8") or "utf-8"
            text = raw.decode(encoding)
        except ImportError:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()

        return ParsedDocument(
            text=text,
            pages=[ParsedPage(page_number=1, text=text)],
            metadata={"encoding": encoding if "encoding" in dir() else "utf-8"},
        )
```

`src/server/parsing/markdown_parser.py`:
```python
"""MarkdownParser — Markdown 解析，提取标题层级和表格"""

import re
import logging
from .base import Parser, ParsedDocument, ParsedPage, ParsedTable

logger = logging.getLogger("server.parser.markdown")


class MarkdownParser:

    @property
    def supported_mime_types(self) -> list[str]:
        return ["text/markdown"]

    def parse(self, file_path: str, filename: str, mime: str) -> ParsedDocument:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()

        sections = self._extract_sections(text)
        tables = self._extract_tables(text)

        return ParsedDocument(
            text=text,
            pages=[ParsedPage(page_number=1, text=text, sections=sections)],
            tables=tables,
            metadata={"sections_count": len(sections)},
        )

    def _extract_sections(self, text: str) -> list[str]:
        """提取标题层级"""
        sections = []
        for line in text.split("\n"):
            if line.startswith("#"):
                sections.append(line.lstrip("#").strip())
        return sections

    def _extract_tables(self, text: str) -> list[ParsedTable]:
        """提取 Markdown 表格"""
        tables = []
        lines = text.split("\n")
        i = 0
        while i < len(lines):
            if "|" in lines[i] and i + 1 < len(lines) and "---" in lines[i + 1]:
                # 找到表格开始
                table_lines = [lines[i], lines[i + 1]]
                j = i + 2
                while j < len(lines) and "|" in lines[j]:
                    table_lines.append(lines[j])
                    j += 1
                tables.append(ParsedTable(
                    page_number=1,
                    markdown="\n".join(table_lines),
                ))
                i = j
            else:
                i += 1
        return tables
```

- [ ] **Step 4: Implement MinerUParser**

`src/server/parsing/mineru_parser.py`:
```python
"""MinerUParser — PDF 解析，通过 MinerU API 调用"""

import os
import logging
import requests
from .base import Parser, ParsedDocument, ParsedPage, ParsedTable

logger = logging.getLogger("server.parser.mineru")


class MinerUParser:

    def __init__(self, api_url: str = "", api_key: str = ""):
        self._api_url = api_url or os.getenv("MINERU_API_URL", "http://localhost:8080")
        self._api_key = api_key or os.getenv("MINERU_API_KEY", "")

    @property
    def supported_mime_types(self) -> list[str]:
        return ["application/pdf"]

    def parse(self, file_path: str, filename: str, mime: str) -> ParsedDocument:
        try:
            return self._parse_with_mineru(file_path, filename)
        except Exception as e:
            logger.warning("MinerU 解析失败，降级到 pypdf: %s", e)
            return self._parse_with_pypdf(file_path)

    def _parse_with_mineru(self, file_path: str, filename: str) -> ParsedDocument:
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        with open(file_path, "rb") as f:
            resp = requests.post(
                f"{self._api_url}/parse",
                files={"file": (filename, f)},
                headers=headers,
                timeout=300,
            )
        resp.raise_for_status()
        data = resp.json()

        pages = [
            ParsedPage(
                page_number=p.get("page_number", i + 1),
                text=p.get("text", ""),
                sections=p.get("sections", []),
            )
            for i, p in enumerate(data.get("pages", []))
        ]

        tables = [
            ParsedTable(
                page_number=t.get("page_number", 1),
                caption=t.get("caption"),
                markdown=t.get("markdown", ""),
            )
            for t in data.get("tables", [])
        ]

        return ParsedDocument(
            text=data.get("text", ""),
            pages=pages,
            tables=tables,
            metadata={"parser": "mineru", "version": data.get("version", "")},
        )

    def _parse_with_pypdf(self, file_path: str) -> ParsedDocument:
        """降级: 使用 pypdf 做基础文本提取"""
        from pypdf import PdfReader

        reader = PdfReader(file_path)
        pages = []
        full_text = ""

        for i, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            full_text += page_text + "\n\n"
            pages.append(ParsedPage(
                page_number=i + 1,
                text=page_text,
            ))

        return ParsedDocument(
            text=full_text.strip(),
            pages=pages,
            metadata={"parser": "pypdf", "total_pages": len(reader.pages)},
        )
```

- [ ] **Step 5: Create placeholder parsers**

`src/server/parsing/placeholders.py`:
```python
"""预留 Parser 能力声明 — 不实现，仅供查询"""

from .registry import ParserRegistry


def register_placeholders(registry: ParserRegistry) -> None:
    """注册预留解析能力 (available=False)"""
    placeholders = [
        (["docx"], [".docx"],
         ["application/vnd.openxmlformats-officedocument.wordprocessingml.document"]),
        (["xlsx"], [".xlsx"],
         ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]),
        (["pptx"], [".pptx"],
         ["application/vnd.openxmlformats-officedocument.presentationml.presentation"]),
        (["html", "web"], [".html", ".htm"],
         ["text/html"]),
        (["image", "ocr"], [".png", ".jpg", ".jpeg"],
         ["image/png", "image/jpeg"]),
    ]

    for name, exts, mimes in placeholders:
        registry.register_capability_only(name, exts, mimes)
```

Add to `ParserRegistry`:
```python
    def register_capability_only(self, name: str, extensions: list[str],
                                  mime_types: list[str]) -> None:
        """注册能力声明 (无实际 Parser 实现)"""
        self._capabilities.append({
            "name": name,
            "extensions": extensions,
            "mime_types": mime_types,
            "available": False,
        })
```

---

### Task 4: Chunking layer — protocol + registry + 3 strategies + semantic skeleton

**Files:**
- Create: `src/server/chunking/__init__.py`
- Create: `src/server/chunking/base.py`
- Create: `src/server/chunking/registry.py`
- Create: `src/server/chunking/paragraph_chunker.py`
- Create: `src/server/chunking/markdown_chunker.py`
- Create: `src/server/chunking/pdf_chunker.py`
- Create: `src/server/chunking/semantic_chunker.py`

- [ ] **Step 1: Create chunking base types**

`src/server/chunking/__init__.py`:
```python
"""分块层 — 策略协议 + 注册中心 + 实现"""
from .base import ChunkingStrategy, Chunk
from .registry import ChunkerRegistry
from .paragraph_chunker import ParagraphChunker
from .markdown_chunker import MarkdownChunker
from .pdf_chunker import PDFChunker
from .semantic_chunker import SemanticChunker

__all__ = [
    "ChunkingStrategy", "Chunk", "ChunkerRegistry",
    "ParagraphChunker", "MarkdownChunker", "PDFChunker", "SemanticChunker",
]
```

`src/server/chunking/base.py`:
```python
"""分块策略协议 + Chunk 数据模型"""

import uuid
import hashlib
from datetime import datetime
from dataclasses import dataclass, field
from typing import Protocol

from ..parsing.base import ParsedDocument


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
```

- [ ] **Step 2: Create ChunkerRegistry**

`src/server/chunking/registry.py`:
```python
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
        # fallback: paragraph chunker for any unknown text type
        return self._defaults["text/plain"]

    def override(self, mime: str, strategy: ChunkingStrategy) -> None:
        self._overrides[mime] = strategy
```

- [ ] **Step 3: Implement chunking strategies**

`src/server/chunking/paragraph_chunker.py`:
```python
"""ParagraphChunker — 按 \n\n 切分，限制 512 token"""

import tiktoken
from .base import ChunkingStrategy, Chunk
from ..parsing.base import ParsedDocument

MAX_TOKENS = 512
MIN_TOKENS = 128


class ParagraphChunker:

    @property
    def name(self) -> str:
        return "paragraph"

    def chunk(self, parsed: ParsedDocument, document_id: str) -> list[Chunk]:
        enc = tiktoken.get_encoding("cl100k_base")
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
                # 如果单段超过 MAX_TOKENS，按句号再分
                if len(enc.encode(para)) > MAX_TOKENS:
                    sub_chunks = self._split_long_para(para, enc, document_id, len(chunks), 1, 1)
                    chunks.extend(sub_chunks)
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
```

`src/server/chunking/markdown_chunker.py`:
```python
"""MarkdownChunker — 按 ## 标题切节，同级下按段落细分"""

import re
import tiktoken
from .base import ChunkingStrategy, Chunk
from ..parsing.base import ParsedDocument

MAX_TOKENS = 512


class MarkdownChunker:

    @property
    def name(self) -> str:
        return "markdown"

    def chunk(self, parsed: ParsedDocument, document_id: str) -> list[Chunk]:
        enc = tiktoken.get_encoding("cl100k_base")
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
                # 按段落再细分
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
```

`src/server/chunking/pdf_chunker.py`:
```python
"""PDFChunker — 以页为边界，单页大内容按段细分"""

import tiktoken
from .base import ChunkingStrategy, Chunk
from ..parsing.base import ParsedDocument

MAX_TOKENS = 512


class PDFChunker:

    @property
    def name(self) -> str:
        return "pdf"

    def chunk(self, parsed: ParsedDocument, document_id: str) -> list[Chunk]:
        enc = tiktoken.get_encoding("cl100k_base")
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
                # 按段落切分页面
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
```

`src/server/chunking/semantic_chunker.py`:
```python
"""SemanticChunker — 语义递归分块 (骨架，后续完善)"""

from .base import ChunkingStrategy, Chunk
from ..parsing.base import ParsedDocument


class SemanticChunker:

    @property
    def name(self) -> str:
        return "semantic"

    def chunk(self, parsed: ParsedDocument, document_id: str) -> list[Chunk]:
        raise NotImplementedError("SemanticChunker: 语义递归分块功能尚未实现")
```

---

### Task 5: Repository extensions — Document, Chunk, Task

**Files:**
- Modify: `src/server/repositories/base.py`
- Modify: `src/server/repositories/memory.py`
- Modify: `src/server/repositories/__init__.py`

- [ ] **Step 1: Add protocols and dataclasses to base.py**

Append to `src/server/repositories/base.py`:
```python
# ── Document ──

@dataclass
class Document:
    document_id: str
    user_id: str
    filename: str
    storage_key: str
    mime_type: str
    file_size: int = 0
    file_hash: str = ""
    scope: str = "private"
    status: str = "uploaded"
    chunk_count: int = 0
    error_message: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


class DocumentRepository(Protocol):
    async def create(self, doc: Document) -> Document: ...
    async def get(self, document_id: str) -> Document | None: ...
    async def list_by_user(self, user_id: str) -> list[Document]: ...
    async def update(self, document_id: str, **kwargs) -> Document | None: ...
    async def delete(self, document_id: str) -> None: ...


# ── Chunk ──

@dataclass
class ChunkRecord:
    chunk_id: str
    document_id: str
    chunk_index: int
    chunk_hash: str
    text: str
    page_start: int
    page_end: int
    sections: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


class ChunkRepository(Protocol):
    async def batch_save(self, chunks: list[ChunkRecord]) -> None: ...
    async def get_by_document(self, document_id: str) -> list[ChunkRecord]: ...
    async def delete_by_document(self, document_id: str) -> None: ...


# ── Task ──

@dataclass
class TaskRecord:
    task_id: str
    document_id: str
    status: str  # queued / parsing / chunking / done / failed
    progress: float = 0.0
    error_message: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


class TaskRepository(Protocol):
    async def save(self, task: TaskRecord) -> None: ...
    async def get(self, task_id: str) -> TaskRecord | None: ...
    async def list_by_document(self, document_id: str) -> list[TaskRecord]: ...
```

- [ ] **Step 2: Add memory implementations**

Append to `src/server/repositories/memory.py`:
```python
# ── Document ──

class InMemoryDocumentRepo:
    def __init__(self):
        self._docs: dict[str, Document] = {}
        self._lock = asyncio.Lock()

    async def create(self, doc: Document) -> Document:
        async with self._lock:
            self._docs[doc.document_id] = doc
            return doc

    async def get(self, document_id: str) -> Document | None:
        return self._docs.get(document_id)

    async def list_by_user(self, user_id: str) -> list[Document]:
        return [d for d in self._docs.values() if d.user_id == user_id]

    async def update(self, document_id: str, **kwargs) -> Document | None:
        if doc := self._docs.get(document_id):
            for k, v in kwargs.items():
                if hasattr(doc, k):
                    setattr(doc, k, v)
            doc.updated_at = datetime.utcnow()
            return doc
        return None

    async def delete(self, document_id: str) -> None:
        self._docs.pop(document_id, None)


# ── Chunk ──

class InMemoryChunkRepo:
    def __init__(self):
        self._chunks: dict[str, list[ChunkRecord]] = {}
        self._lock = asyncio.Lock()

    async def batch_save(self, chunks: list[ChunkRecord]) -> None:
        async with self._lock:
            for c in chunks:
                self._chunks.setdefault(c.document_id, []).append(c)

    async def get_by_document(self, document_id: str) -> list[ChunkRecord]:
        return self._chunks.get(document_id, [])

    async def delete_by_document(self, document_id: str) -> None:
        self._chunks.pop(document_id, None)


# ── Task ──

class InMemoryTaskRepo:
    def __init__(self):
        self._tasks: dict[str, TaskRecord] = {}
        self._lock = asyncio.Lock()

    async def save(self, task: TaskRecord) -> None:
        async with self._lock:
            self._tasks[task.task_id] = task

    async def get(self, task_id: str) -> TaskRecord | None:
        return self._tasks.get(task_id)

    async def list_by_document(self, document_id: str) -> list[TaskRecord]:
        return [t for t in self._tasks.values() if t.document_id == document_id]
```

- [ ] **Step 3: Update repositories __init__.py**

Update `src/server/repositories/__init__.py`:
```python
"""存储层 — 协议定义 + 内存实现"""
from .base import (
    UserRepository, ApiKeyRepository, SessionRepository,
    DocumentRepository, ChunkRepository, TaskRepository,
    User, ApiKey, Session, Identity,
    Document, ChunkRecord, TaskRecord,
)
from .memory import (
    InMemoryUserRepo, InMemoryApiKeyRepo, InMemorySessionRepo,
    InMemoryDocumentRepo, InMemoryChunkRepo, InMemoryTaskRepo,
)

__all__ = [
    "UserRepository", "ApiKeyRepository", "SessionRepository",
    "DocumentRepository", "ChunkRepository", "TaskRepository",
    "User", "ApiKey", "Session", "Identity",
    "Document", "ChunkRecord", "TaskRecord",
    "InMemoryUserRepo", "InMemoryApiKeyRepo", "InMemorySessionRepo",
    "InMemoryDocumentRepo", "InMemoryChunkRepo", "InMemoryTaskRepo",
]
```

---

### Task 6: TaskQueue layer — protocol + in-process + worker

**Files:**
- Create: `src/server/tasks/__init__.py`
- Create: `src/server/tasks/base.py`
- Create: `src/server/tasks/in_process.py`
- Create: `src/server/tasks/worker.py`

- [ ] **Step 1: Create task protocol**

`src/server/tasks/__init__.py`:
```python
"""任务队列 — 协议 + 进程内实现"""
from .base import TaskQueue, TaskStatus, TaskInfo
from .in_process import InProcessTaskQueue
from .worker import TaskWorker

__all__ = ["TaskQueue", "TaskStatus", "TaskInfo", "InProcessTaskQueue", "TaskWorker"]
```

`src/server/tasks/base.py`:
```python
"""TaskQueue 协议"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


class TaskStatus(str, Enum):
    QUEUED = "queued"
    PARSING = "parsing"
    CHUNKING = "chunking"
    DONE = "done"
    FAILED = "failed"


@dataclass
class TaskInfo:
    task_id: str
    document_id: str
    status: str = TaskStatus.QUEUED.value
    progress: float = 0.0
    error_message: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


class TaskQueue(Protocol):
    async def enqueue(self, document_id: str) -> str: ...
    async def get(self, task_id: str) -> TaskInfo | None: ...
```

- [ ] **Step 2: Implement InProcessTaskQueue**

`src/server/tasks/in_process.py`:
```python
"""InProcessTaskQueue — asyncio.create_task 实现"""

import asyncio
import uuid
import logging
from datetime import datetime

from .base import TaskStatus, TaskInfo
from .worker import TaskWorker
from ..repositories.base import TaskRepository

logger = logging.getLogger("server.task_queue")


class InProcessTaskQueue:

    def __init__(self, worker: TaskWorker, task_repo: TaskRepository):
        self._worker = worker
        self._repo = task_repo

    async def enqueue(self, document_id: str) -> str:
        task_id = str(uuid.uuid4())[:8]
        task = TaskInfo(task_id=task_id, document_id=document_id)
        await self._repo.save(task)
        asyncio.create_task(self._run(task))
        return task_id

    async def get(self, task_id: str) -> TaskInfo | None:
        return await self._repo.get(task_id)

    async def _run(self, task: TaskInfo):
        try:
            await self._worker.execute(task.document_id)
            task.status = TaskStatus.DONE.value
            task.progress = 1.0
        except Exception as e:
            logger.error("任务失败: task=%s, error=%s", task.task_id, e)
            task.status = TaskStatus.FAILED.value
            task.error_message = str(e)
        finally:
            task.updated_at = datetime.utcnow()
            await self._repo.save(task)
```

- [ ] **Step 3: Implement TaskWorker**

`src/server/tasks/worker.py`:
```python
"""TaskWorker — 编排完整的解析→分块管线"""

import os
import tempfile
import logging

from ..repositories.base import (
    DocumentRepository, ChunkRepository, ChunkRecord,
)

logger = logging.getLogger("server.task_worker")


class TaskWorker:

    def __init__(
        self,
        doc_repo: DocumentRepository,
        chunk_repo: ChunkRepository,
        storage,
        parser_registry,
        chunker_registry,
    ):
        self._doc_repo = doc_repo
        self._chunk_repo = chunk_repo
        self._storage = storage
        self._parser_registry = parser_registry
        self._chunker_registry = chunker_registry

    async def execute(self, document_id: str):
        doc = await self._doc_repo.get(document_id)
        if not doc:
            raise ValueError(f"文档不存在: {document_id}")

        # 1. 获取文件路径
        file_path = self._storage.resolve_path(doc.storage_key)
        cleanup_temp = False
        if file_path is None:
            content = await self._storage.read(doc.storage_key)
            ext = doc.filename.rsplit(".", 1)[-1] if "." in doc.filename else ""
            with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as f:
                f.write(content)
            file_path = f.name
            cleanup_temp = True

        try:
            # 2. 解析
            await self._doc_repo.update(document_id, status="parsing")
            parser = self._parser_registry.select(doc.mime_type, doc.filename)
            parsed = parser.parse(file_path, doc.filename, doc.mime_type)

            # 3. 分块
            await self._doc_repo.update(document_id, status="chunking")
            chunker = self._chunker_registry.get(doc.mime_type)
            chunks = chunker.chunk(parsed, document_id)

            # 4. 保存 Chunks (转为 ChunkRecord)
            records = [
                ChunkRecord(
                    chunk_id=c.chunk_id,
                    document_id=c.document_id,
                    chunk_index=c.chunk_index,
                    chunk_hash=c.chunk_hash,
                    text=c.text,
                    page_start=c.page_start,
                    page_end=c.page_end,
                    sections=c.sections,
                    metadata=c.metadata,
                )
                for c in chunks
            ]
            await self._chunk_repo.batch_save(records)

            # 5. 更新文档
            await self._doc_repo.update(
                document_id, status="indexed", chunk_count=len(chunks),
            )
        finally:
            if cleanup_temp:
                try:
                    os.unlink(file_path)
                except OSError:
                    pass
```

---

### Task 7: Document schemas + error codes

**Files:**
- Modify: `src/server/exceptions.py` (minimal — mostly using existing AppError with new codes)
- Create: `src/server/documents/__init__.py`
- Create: `src/server/documents/errors.py`

- [ ] **Step 1: Create document errors**

`src/server/documents/__init__.py`:
```python
"""文档管理模块"""
from .router import router
from .service import DocumentService

__all__ = ["router", "DocumentService"]
```

`src/server/documents/errors.py`:
```python
"""文档相关错误码 — 复用 AppError"""

from ..exceptions import AppError, NotFoundError


class UnsupportedFormatError(AppError):
    def __init__(self, filename: str, mime: str):
        super().__init__(
            code="UNSUPPORTED_FORMAT",
            message=f"不支持的文件格式: {filename} ({mime})",
            status_code=400,
        )


class FileTooLargeError(AppError):
    def __init__(self, size: int, max_size: int):
        super().__init__(
            code="FILE_TOO_LARGE",
            message=f"文件大小 {size} 超过限制 {max_size}",
            status_code=413,
        )


class MimeMismatchError(AppError):
    def __init__(self, ext: str, mime: str):
        super().__init__(
            code="MIME_MISMATCH",
            message=f"文件扩展名 {ext} 与 MIME 类型 {mime} 不一致",
            status_code=400,
        )


class DuplicateDocumentError(AppError):
    def __init__(self, filename: str):
        super().__init__(
            code="DUPLICATE_DOCUMENT",
            message=f"相同文件已存在: {filename}",
            status_code=409,
        )


class DocumentNotReadyError(AppError):
    def __init__(self, document_id: str, status: str):
        super().__init__(
            code="DOCUMENT_NOT_READY",
            message=f"文档仍在处理中: {status}",
            status_code=409,
        )
```

- [ ] **Step 2: Add document schemas to main schemas.py**

Append to `src/server/schemas.py`:
```python
# ═══════════════════════════════════════════════════════════════
# 文档
# ═══════════════════════════════════════════════════════════════

class DocumentResponse(BaseModel):
    document_id: str
    filename: str
    mime_type: str
    file_size: int
    scope: str
    status: str
    chunk_count: int = 0
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    mime_type: str
    file_size: int
    scope: str
    status: str
    task_id: str
    created_at: datetime


class TaskResponse(BaseModel):
    task_id: str
    document_id: str
    status: str
    progress: float
    error_message: str | None
    created_at: datetime
    updated_at: datetime
```

---

### Task 8: DocumentService

**Files:**
- Create: `src/server/documents/service.py`

- [ ] **Step 1: Write DocumentService**

`src/server/documents/service.py`:
```python
"""文档服务 — 上传、查询、删除"""

import hashlib
import uuid
import logging
from datetime import datetime

from ..repositories.base import (
    DocumentRepository, ChunkRepository,
    Document, Identity,
)
from ..tasks.base import TaskQueue
from .errors import (
    UnsupportedFormatError, FileTooLargeError,
    MimeMismatchError, DuplicateDocumentError,
)

logger = logging.getLogger("server.document_service")

ALLOWED_MIMES = {"text/plain", "text/markdown", "application/pdf"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


class DocumentService:

    def __init__(
        self,
        doc_repo: DocumentRepository,
        chunk_repo: ChunkRepository,
        storage,
        task_queue: TaskQueue,
    ):
        self._doc_repo = doc_repo
        self._chunk_repo = chunk_repo
        self._storage = storage
        self._task_queue = task_queue

    async def upload(
        self, identity: Identity, filename: str,
        content: bytes, mime_type: str, scope: str = "private",
    ) -> dict:
        # 1. 校验
        if mime_type not in ALLOWED_MIMES:
            raise UnsupportedFormatError(filename, mime_type)
        if len(content) > MAX_FILE_SIZE:
            raise FileTooLargeError(len(content), MAX_FILE_SIZE)
        self._validate_extension(filename, mime_type)

        # 2. 去重检查
        file_hash = hashlib.sha256(content).hexdigest()
        existing = await self._doc_repo.list_by_user(identity.user_id)
        for doc in existing:
            if doc.file_hash == file_hash and doc.scope == scope:
                raise DuplicateDocumentError(filename)

        # 3. 存储文件
        ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
        storage_key = await self._storage.save(content, ext)

        # 4. 创建文档记录
        doc = Document(
            document_id=str(uuid.uuid4()),
            user_id=identity.user_id,
            filename=filename,
            storage_key=storage_key,
            mime_type=mime_type,
            file_size=len(content),
            file_hash=file_hash,
            scope=scope,
            status="queued",
        )
        await self._doc_repo.create(doc)

        # 5. 提交索引任务
        task_id = await self._task_queue.enqueue(doc.document_id)

        return {
            "document_id": doc.document_id,
            "filename": doc.filename,
            "mime_type": doc.mime_type,
            "file_size": doc.file_size,
            "scope": doc.scope,
            "status": doc.status,
            "task_id": task_id,
            "created_at": doc.created_at,
        }

    async def get_document(self, document_id: str) -> Document | None:
        return await self._doc_repo.get(document_id)

    async def list_documents(self, user_id: str) -> list[Document]:
        return await self._doc_repo.list_by_user(user_id)

    async def delete_document(self, user_id: str, document_id: str):
        doc = await self._doc_repo.get(document_id)
        if not doc:
            return
        if doc.user_id != user_id:
            from ..exceptions import NotFoundError
            raise NotFoundError("文档", document_id)

        await self._storage.delete(doc.storage_key)
        await self._chunk_repo.delete_by_document(document_id)
        await self._doc_repo.delete(document_id)

    def _validate_extension(self, filename: str, mime: str):
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        ext_mime_map = {
            "txt": "text/plain",
            "md": "text/markdown",
            "pdf": "application/pdf",
        }
        expected = ext_mime_map.get(ext)
        if expected and expected != mime:
            raise MimeMismatchError(f".{ext}", mime)
```

---

### Task 9: Document API router

**Files:**
- Create: `src/server/documents/router.py`

- [ ] **Step 1: Write API routes**

`src/server/documents/router.py`:
```python
"""文档管理 API 路由"""

import logging
from fastapi import APIRouter, Depends, Request, UploadFile, File, Form

from ..deps import get_identity, get_auth_service
from ..repositories.base import Identity
from ..schemas import DocumentResponse, DocumentUploadResponse, TaskResponse
from .service import DocumentService
from .errors import FileTooLargeError

logger = logging.getLogger("server.document_api")
router = APIRouter()

MAX_UPLOAD_SIZE = 20 * 1024 * 1024


def get_doc_service(request: Request) -> DocumentService:
    return request.app.state.doc_service


@router.post("/documents", response_model=DocumentUploadResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    scope: str = Form("private"),
    identity: Identity = Depends(get_identity),
    doc_service: DocumentService = Depends(get_doc_service),
):
    """上传文档"""
    if not file.filename:
        from .errors import UnsupportedFormatError
        raise UnsupportedFormatError("unknown", "unknown")

    # 校验扩展名
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ("txt", "md", "pdf"):
        from .errors import UnsupportedFormatError
        raise UnsupportedFormatError(file.filename, f".{ext}")

    # 读取内容 (限制 20MB + 1KB buffer)
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise FileTooLargeError(len(content), MAX_UPLOAD_SIZE)

    # MIME 检测 (python-magic)
    import magic
    detected_mime = magic.from_buffer(content[:2048], mime=True)

    # admin 才能上传 shared
    if scope == "shared" and identity.role != "admin":
        scope = "private"

    result = await doc_service.upload(
        identity=identity,
        filename=file.filename,
        content=content,
        mime_type=detected_mime,
        scope=scope,
    )
    return DocumentUploadResponse(**result)


@router.get("/documents", response_model=list[DocumentResponse])
async def list_documents(
    identity: Identity = Depends(get_identity),
    doc_service: DocumentService = Depends(get_doc_service),
):
    """列出当前用户的文档"""
    docs = await doc_service.list_documents(identity.user_id)
    return [
        DocumentResponse(
            document_id=d.document_id,
            filename=d.filename,
            mime_type=d.mime_type,
            file_size=d.file_size,
            scope=d.scope,
            status=d.status,
            chunk_count=d.chunk_count,
            error_message=d.error_message,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d in docs
    ]


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    identity: Identity = Depends(get_identity),
    doc_service: DocumentService = Depends(get_doc_service),
):
    """获取文档详情"""
    from ..exceptions import NotFoundError
    doc = await doc_service.get_document(document_id)
    if not doc or doc.user_id != identity.user_id:
        raise NotFoundError("文档", document_id)
    return DocumentResponse(
        document_id=doc.document_id,
        filename=doc.filename,
        mime_type=doc.mime_type,
        file_size=doc.file_size,
        scope=doc.scope,
        status=doc.status,
        chunk_count=doc.chunk_count,
        error_message=doc.error_message,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    identity: Identity = Depends(get_identity),
    doc_service: DocumentService = Depends(get_doc_service),
):
    """删除文档"""
    await doc_service.delete_document(identity.user_id, document_id)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    doc_service: DocumentService = Depends(get_doc_service),
):
    """查询索引任务进度"""
    task = await doc_service._task_queue.get(task_id)
    if not task:
        from ..exceptions import NotFoundError
        raise NotFoundError("任务", task_id)
    return TaskResponse(
        task_id=task.task_id,
        document_id=task.document_id,
        status=task.status,
        progress=task.progress,
        error_message=task.error_message,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )
```

---

### Task 10: Integration — main.py + api/__init__.py

**Files:**
- Modify: `src/server/main.py`
- Modify: `src/server/api/__init__.py`

- [ ] **Step 1: Update main.py lifespan**

Edit `src/server/main.py`. Add imports:
```python
from .storage import create_storage
from .parsing import ParserRegistry, TextParser, MarkdownParser, MinerUParser, register_placeholders
from .chunking import ChunkerRegistry
from .tasks import InProcessTaskQueue, TaskWorker
from .repositories import (
    InMemoryDocumentRepo, InMemoryChunkRepo, InMemoryTaskRepo,
)
from .documents import DocumentService
```

In lifespan startup, after `chat_service = ChatService()`, add:
```python
    # 文档管理
    doc_repo = InMemoryDocumentRepo()
    chunk_repo = InMemoryChunkRepo()
    task_repo = InMemoryTaskRepo()

    storage = create_storage()

    parser_registry = ParserRegistry()
    parser_registry.register(TextParser(), extensions=[".txt"], mime_types=["text/plain"])
    parser_registry.register(MarkdownParser(), extensions=[".md"], mime_types=["text/markdown"])
    parser_registry.register(
        MinerUParser(
            api_url=os.getenv("MINERU_API_URL", "http://localhost:8080"),
            api_key=os.getenv("MINERU_API_KEY", ""),
        ),
        extensions=[".pdf"], mime_types=["application/pdf"],
    )
    register_placeholders(parser_registry)

    chunker_registry = ChunkerRegistry()

    task_worker = TaskWorker(
        doc_repo=doc_repo, chunk_repo=chunk_repo,
        storage=storage, parser_registry=parser_registry,
        chunker_registry=chunker_registry,
    )
    task_queue = InProcessTaskQueue(worker=task_worker, task_repo=task_repo)

    doc_service = DocumentService(
        doc_repo=doc_repo, chunk_repo=chunk_repo,
        storage=storage, task_queue=task_queue,
    )

    app.state.storage = storage
    app.state.parser_registry = parser_registry
    app.state.chunker_registry = chunker_registry
    app.state.task_queue = task_queue
    app.state.doc_service = doc_service
```

- [ ] **Step 2: Register documents router**

Edit `src/server/api/__init__.py`. Add:
```python
from ..documents import router as documents_router
api_router.include_router(documents_router, tags=["文档"])
```

Also add `from .chat import router as chat_router` after sessions import if not already there.

---

### Task 11: Tests

**Files:**
- Create: `tests/test_storage.py`
- Create: `tests/test_parsing.py`
- Create: `tests/test_chunking.py`
- Create: `tests/test_document_api.py`

- [ ] **Step 1: Storage tests**

`tests/test_storage.py`:
```python
"""ObjectStorage 测试"""

import os
import tempfile
import pytest


@pytest.fixture
def local_storage():
    from src.server.storage import LocalStorage
    with tempfile.TemporaryDirectory() as tmp:
        storage = LocalStorage(base_dir=tmp)
        yield storage


@pytest.mark.asyncio
async def test_save_and_read(local_storage):
    key = await local_storage.save(b"hello world", "txt")
    assert key.endswith(".txt")
    data = await local_storage.read(key)
    assert data == b"hello world"


@pytest.mark.asyncio
async def test_exists(local_storage):
    key = await local_storage.save(b"test", "md")
    assert await local_storage.exists(key) is True
    assert await local_storage.exists("nonexistent") is False


@pytest.mark.asyncio
async def test_delete_idempotent(local_storage):
    key = await local_storage.save(b"test", "txt")
    await local_storage.delete(key)
    assert await local_storage.exists(key) is False
    await local_storage.delete(key)  # 不抛异常


@pytest.mark.asyncio
async def test_resolve_path(local_storage):
    key = await local_storage.save(b"test", "txt")
    path = local_storage.resolve_path(key)
    assert os.path.exists(path)
    with open(path, "rb") as f:
        assert f.read() == b"test"


@pytest.mark.asyncio
async def test_unique_keys(local_storage):
    key1 = await local_storage.save(b"a", "txt")
    key2 = await local_storage.save(b"b", "txt")
    assert key1 != key2
```

- [ ] **Step 2: Parser tests**

`tests/test_parsing.py`:
```python
"""Parser 测试"""

import os
import tempfile
import pytest


@pytest.fixture
def txt_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("第一段内容。\n\n第二段内容。")
    yield f.name
    os.unlink(f.name)


@pytest.fixture
def md_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write("# 标题\n\n## 子标题\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n正文内容。")
    yield f.name
    os.unlink(f.name)


def test_text_parser(txt_file):
    from src.server.parsing import TextParser
    parser = TextParser()
    result = parser.parse(txt_file, "test.txt", "text/plain")
    assert "第一段" in result.text
    assert len(result.pages) == 1


def test_markdown_parser(md_file):
    from src.server.parsing import MarkdownParser
    parser = MarkdownParser()
    result = parser.parse(md_file, "test.md", "text/markdown")
    assert "标题" in result.text
    assert len(result.tables) >= 1
    sections = result.pages[0].sections
    assert "标题" in sections


def test_parser_registry_select_by_extension():
    from src.server.parsing import ParserRegistry, TextParser
    reg = ParserRegistry()
    reg.register(TextParser(), extensions=[".txt"], mime_types=["text/plain"])
    parser = reg.select("text/plain", "doc.txt")
    assert isinstance(parser, TextParser)


def test_parser_registry_select_by_mime_fallback():
    from src.server.parsing import ParserRegistry, TextParser
    reg = ParserRegistry()
    reg.register(TextParser(), extensions=[".txt"], mime_types=["text/plain"])
    parser = reg.select("text/plain", "doc.unknown")
    assert isinstance(parser, TextParser)


def test_parser_registry_mime_mismatch():
    from src.server.parsing import ParserRegistry, TextParser
    from src.server.exceptions import AppError
    reg = ParserRegistry()
    reg.register(TextParser(), extensions=[".txt"], mime_types=["text/plain"])
    with pytest.raises(AppError, match="MIME"):
        reg.select("text/html", "doc.txt")


def test_parser_registry_unsupported():
    from src.server.parsing import ParserRegistry, TextParser
    from src.server.exceptions import AppError
    reg = ParserRegistry()
    reg.register(TextParser(), extensions=[".txt"], mime_types=["text/plain"])
    with pytest.raises(AppError, match="不支持"):
        reg.select("application/pdf", "doc.pdf")
```

- [ ] **Step 3: Chunker tests**

`tests/test_chunking.py`:
```python
"""Chunker 测试"""

from src.server.parsing.base import ParsedDocument, ParsedPage


def test_paragraph_chunker():
    from src.server.chunking import ParagraphChunker
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
    from src.server.chunking import MarkdownChunker
    parsed = ParsedDocument(
        text="## 第一节\n\n内容A。\n\n## 第二节\n\n内容B。",
        pages=[ParsedPage(page_number=1, text="## 第一节\n\n内容A。\n\n## 第二节\n\n内容B。")],
    )
    chunker = MarkdownChunker()
    chunks = chunker.chunk(parsed, "doc-002")
    assert len(chunks) >= 1
    # 应该包含 "第一节" 或 "第二节"
    all_text = " ".join(c.text for c in chunks)
    assert "内容A" in all_text
    assert "内容B" in all_text


def test_pdf_chunker():
    from src.server.chunking import PDFChunker
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
    from src.server.chunking import ChunkerRegistry, ParagraphChunker, MarkdownChunker, PDFChunker
    reg = ChunkerRegistry()
    assert isinstance(reg.get("text/plain"), ParagraphChunker)
    assert isinstance(reg.get("text/markdown"), MarkdownChunker)
    assert isinstance(reg.get("application/pdf"), PDFChunker)


def test_chunker_registry_override():
    from src.server.chunking import ChunkerRegistry, ParagraphChunker
    reg = ChunkerRegistry()
    custom = ParagraphChunker()
    reg.override("text/plain", custom)
    assert reg.get("text/plain") is custom


def test_semantic_chunker_not_implemented():
    from src.server.chunking import SemanticChunker
    parsed = ParsedDocument(text="test")
    chunker = SemanticChunker()
    try:
        chunker.chunk(parsed, "doc-004")
        assert False, "should raise NotImplementedError"
    except NotImplementedError:
        pass
```

- [ ] **Step 4: Document API integration tests**

`tests/test_document_api.py`:
```python
"""文档 API 集成测试"""

import os
import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ADMIN_API_KEYS", "sk-test-admin")
os.environ.setdefault("USER_API_KEYS", "sk-test-user")


@pytest.fixture
async def client():
    from src.server.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def user_headers():
    return {"Authorization": "Bearer sk-test-user"}


@pytest.fixture
def admin_headers():
    return {"Authorization": "Bearer sk-test-admin"}


@pytest.mark.asyncio
async def test_upload_txt(client: AsyncClient, user_headers):
    resp = await client.post(
        "/api/v1/documents",
        files={"file": ("test.txt", b"Hello World\n\nTest content.", "text/plain")},
        data={"scope": "private"},
        headers=user_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "queued"
    assert "task_id" in data
    assert "document_id" in data


@pytest.mark.asyncio
async def test_upload_invalid_extension(client: AsyncClient, user_headers):
    resp = await client.post(
        "/api/v1/documents",
        files={"file": ("test.exe", b"malware", "application/octet-stream")},
        headers=user_headers,
    )
    assert resp.status_code in (400, 422)


@pytest.mark.asyncio
async def test_list_documents(client: AsyncClient, user_headers):
    # 先上传
    await client.post(
        "/api/v1/documents",
        files={"file": ("doc.txt", b"content", "text/plain")},
        headers=user_headers,
    )
    resp = await client.get("/api/v1/documents", headers=user_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_document(client: AsyncClient, user_headers):
    resp = await client.post(
        "/api/v1/documents",
        files={"file": ("doc.txt", b"content", "text/plain")},
        headers=user_headers,
    )
    doc_id = resp.json()["document_id"]
    resp = await client.get(f"/api/v1/documents/{doc_id}", headers=user_headers)
    assert resp.status_code == 200
    assert resp.json()["document_id"] == doc_id


@pytest.mark.asyncio
async def test_delete_document(client: AsyncClient, user_headers):
    resp = await client.post(
        "/api/v1/documents",
        files={"file": ("doc.txt", b"content", "text/plain")},
        headers=user_headers,
    )
    doc_id = resp.json()["document_id"]
    resp = await client.delete(f"/api/v1/documents/{doc_id}", headers=user_headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_user_isolation(client: AsyncClient, user_headers):
    """user A 的文档 user B 看不到"""
    resp = await client.post(
        "/api/v1/documents",
        files={"file": ("secret.txt", b"secret", "text/plain")},
        headers=user_headers,
    )
    doc_id = resp.json()["document_id"]

    # admin 看不到 user 的私人文档
    admin_hdrs = {"Authorization": "Bearer sk-test-admin"}
    resp = await client.get(f"/api/v1/documents/{doc_id}", headers=admin_hdrs)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_task_query(client: AsyncClient, user_headers):
    resp = await client.post(
        "/api/v1/documents",
        files={"file": ("doc.txt", b"content", "text/plain")},
        headers=user_headers,
    )
    task_id = resp.json()["task_id"]

    import asyncio
    await asyncio.sleep(0.5)  # 等待后台任务处理

    resp = await client.get(f"/api/v1/tasks/{task_id}", headers=user_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("queued", "parsing", "chunking", "done", "failed")


@pytest.mark.asyncio
async def test_task_not_found(client: AsyncClient, user_headers):
    resp = await client.get("/api/v1/tasks/nonexistent", headers=user_headers)
    assert resp.status_code == 404
