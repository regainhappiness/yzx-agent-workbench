# 文档上传与解析层设计规格

> 日期: 2026-07-29 | 状态: 已确认 | 关联: [design.md](../../design.md) §5-7, [上一模块](../specs/2026-07-28-fastapi-layer-design.md)

## 1. 目标与范围

在现有 FastAPI 服务层上新增文档上传、解析和分块能力。用户可上传 Markdown、TXT、PDF 文件，系统异步完成解析和分块，为后续 Embedding 与检索准备结构化数据。

### 首版范围

- 文件上传 API（multipart/form-data，最大 20MB）
- ObjectStorage 协议 + LocalStorage + AliyunOSSStorage（配置切换）
- Parser 协议 + ParserRegistry（扩展名优先 + MIME 安全校验）
- TextParser（内置）、MarkdownParser（内置）、MinerUParser（PDF，API 调用方式）
- ChunkingStrategy 协议 + 按格式匹配的分块策略
- InProcessTaskQueue（asyncio.create_task）+ 任务状态查询 API
- Document / Chunk / TaskInfo 内存存储，Repository 协议预留

### 不在首版范围

- OCR 图片识别、Office 文档（仅注册能力声明）
- Milvus向量写入、Embedding 服务、Reranker
- SQLite 持久化（后续统一迁移）
- 公共知识库审批
- 完整语义分块（SemanticChunker 只留骨架）
- 重新索引（reindex 端点预留，不实现）

---

## 2. 处理管线

```
HTTP Upload (multipart/form-data)
  → ObjectStorage.save(content, extension) → storage_key
    → DocumentRepo.create() → document_id
      → TaskQueue.enqueue(document_id) → task_id (立即返回)

[后台异步]
TaskWorker.execute(document_id):
  1. DocumentRepo.get(doc) → Document
  2. 获取文件路径:
     - LocalStorage: resolve_path(storage_key)
     - OSS: 下载到临时文件
  3. ParserRegistry.select(doc.mime, doc.filename) → Parser
  4. Parser.parse(file_path, doc.filename, doc.mime) → ParsedDocument
  5. ChunkerRegistry.get(doc.mime).chunk(parsed_doc) → list[Chunk]
  6. ChunkRepo.batch_save(chunks)
  7. DocumentRepo.update(doc_id, status="indexed", chunk_count=len(chunks))
```

---

## 3. 包结构

```
src/server/storage/
├── __init__.py          # 导出 ObjectStorage, create_storage()
├── base.py              # ObjectStorage 协议
├── local.py             # LocalStorage 实现
└── oss.py               # AliyunOSSStorage 实现

src/server/parsing/
├── __init__.py          # 导出 ParserRegistry, 各 Parser
├── base.py              # Parser 协议 + ParsedDocument/ParsedPage/ParsedTable
├── registry.py          # ParserRegistry
├── text_parser.py       # TextParser
├── markdown_parser.py   # MarkdownParser
├── mineru_parser.py     # MinerUParser (API 调用)
└── placeholders.py      # 预留 Parser 能力声明

src/server/chunking/
├── __init__.py          # 导出 ChunkerRegistry, 各策略
├── base.py              # ChunkingStrategy 协议 + Chunk 数据类
├── registry.py          # ChunkerRegistry + MIME→策略映射
├── paragraph_chunker.py # 按 \n\n 切分
├── markdown_chunker.py  # 按 ## 标题切段
├── pdf_chunker.py       # 按页 + MinerU 段切分
└── semantic_chunker.py  # 语义递归分块 (骨架)

src/server/tasks/
├── __init__.py          # 导出 TaskQueue, InProcessTaskQueue
├── base.py              # TaskQueue 协议 + TaskStatus + TaskInfo
├── in_process.py        # InProcessTaskQueue
└── worker.py            # TaskWorker (编排管线)

src/server/documents/
├── __init__.py          # 导出 router, DocumentService
├── schemas.py           # Pydantic 模型
├── service.py           # DocumentService
├── router.py            # API 路由
└── errors.py            # 文档相关错误码
```

**新增依赖**:
```
pypdf>=5.0          # PDF 元数据提取 (MinerU 不可用时的 fallback)
oss2>=2.18          # 阿里云 OSS SDK
python-magic>=0.4   # MIME 类型检测
```

**修改文件**:
- `src/server/main.py` — lifespan 中初始化 storage + parser registry + chunker registry + task queue
- `src/server/api/__init__.py` — 注册 documents 路由
- `src/server/repositories/` — 新增 DocumentRepo + ChunkRepo + TaskRepo 协议和内存实现
- `src/server/schemas.py` — 新增文档相关 Pydantic 模型
- `src/server/exceptions.py` — 新增文档相关错误码

---

## 4. ObjectStorage

### 4.1 协议

```python
class ObjectStorage(Protocol):
    async def save(self, content: bytes, extension: str) -> str:
        """保存文件，返回 storage_key"""

    async def read(self, key: str) -> bytes:
        """读取文件内容"""

    async def delete(self, key: str) -> None:
        """删除文件 (幂等)"""

    async def exists(self, key: str) -> bool:
        """检查是否存在"""

    def resolve_path(self, key: str) -> str | None:
        """获取本地文件路径. 仅 LocalStorage 支持; OSS 返回 None"""
```

### 4.2 LocalStorage

- 存储目录: `STORAGE_LOCAL_DIR` 环境变量，默认 `./storage/files/`
- storage_key 格式: `{xx}/{yy}/{uuid}.{ext}`，三级桶结构防单目录过大
- `save()`: 写入二进制文件
- `read()`: 直接读取
- `resolve_path()`: 返回文件的绝对路径（供 Parser 使用）

### 4.3 AliyunOSSStorage

- 通过 `oss2` SDK 封装
- 配置环境变量:
  ```
  STORAGE_BACKEND=oss
  OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
  OSS_BUCKET_NAME=my-bucket
  OSS_ACCESS_KEY_ID=xxx
  OSS_ACCESS_KEY_SECRET=xxx
  ```
- `save()`: `bucket.put_object(key, content)`
- `read()`: `bucket.get_object(key).read()`
- `resolve_path()`: 返回 None — 调用方需先 `read()` 到临时文件
- 连接失败抛出 `STORAGE_UNAVAILABLE` 错误

### 4.4 工厂函数

```python
def create_storage() -> ObjectStorage:
    backend = os.getenv("STORAGE_BACKEND", "local")
    if backend == "oss":
        return AliyunOSSStorage(...)
    return LocalStorage(base_dir=os.getenv("STORAGE_LOCAL_DIR", "./storage/files"))
```

---

## 5. Parser 层

### 5.1 数据模型

```python
@dataclass
class ParsedTable:
    page_number: int
    caption: str | None
    markdown: str            # Markdown 格式表格

@dataclass
class ParsedPage:
    page_number: int         # 从 1 开始
    text: str                # 该页结构化文本
    sections: list[str]      # 标题层级

@dataclass
class ParsedDocument:
    text: str               # 完整结构化文本 (Markdown 格式)
    pages: list[ParsedPage]
    tables: list[ParsedTable]
    metadata: dict           # 格式特定元数据
```

### 5.2 Parser 协议

```python
class Parser(Protocol):
    @property
    def supported_mime_types(self) -> list[str]: ...

    def parse(self, file_path: str, filename: str, mime: str) -> ParsedDocument:
        """面向文件路径解析，直接读取本地文件"""
```

### 5.3 ParserRegistry

```python
class ParserRegistry:
    def register(self, parser: Parser, extensions: list[str], mime_types: list[str]) -> None: ...

    def select(self, mime: str, filename: str) -> Parser:
        """扩展名优先 → MIME 回退 → 抛 UNSUPPORTED_FORMAT"""

    def validate_mime(self, mime: str, filename: str) -> bool:
        """安全检查: 扩展名预期 MIME vs 实际 MIME 是否一致"""

    def list_capabilities(self) -> list[dict]:
        """列出所有已注册的解析能力（含预留的不可用能力）"""
```

选择逻辑：`ext` = `filename.split('.')[-1]` → 查扩展名映射 → 如有且 MIME 通过安全校验 → 返回。否则 → MIME 映射 → 返回。否则 → 抛异常。

### 5.4 首版 Parser 实现

| Parser | MIME | 实现方式 |
|--------|------|----------|
| `TextParser` | `text/plain` | 编码检测 (chardet) + 解码，文本直接输出，单页 |
| `MarkdownParser` | `text/markdown` | 解码 + 提取 `#` 标题层级 + 提取表格 |
| `MinerUParser` | `application/pdf` | 调用 MinerU API 服务，返回结构化 Markdown + 表格 + 阅读顺序 |

### 5.5 MinerUParser

```python
class MinerUParser:
    def __init__(self, api_url: str, api_key: str | None = None):
        self._api_url = api_url
        self._api_key = api_key

    def parse(self, file_path: str, filename: str, mime: str) -> ParsedDocument:
        # 1. 读取文件为 bytes
        # 2. POST {api_url}/parse, body=multipart(file)
        # 3. 等待返回 (MinerU 是同步处理，大文件可能较慢)
        # 4. 解析 MinerU 返回的结构化 Markdown → ParsedDocument
```

配置:
```bash
MINERU_API_URL=http://localhost:8080
MINERU_API_KEY=  # 可选
```

MinerU 不可用时回退到 `pypdf` 做基础文本提取（降级不阻断流程）。

### 5.6 预留解析能力

注册但不实现，查询时返回 `PARSER_NOT_AVAILABLE`:

- `DocxParser` (`.docx`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`)
- `SpreadsheetParser` (`.xlsx`)
- `PresentationParser` (`.pptx`)
- `HtmlParser` (`.html`, `text/html`)
- `OcrImageParser` (`.png`, `.jpg` — OCR 图片)

---

## 6. Chunking 层

### 6.1 Chunk 数据模型

```python
@dataclass
class Chunk:
    chunk_id: str             # UUID
    document_id: str
    chunk_index: int          # 序号 (0-based)
    chunk_hash: str           # SHA-256(text) — 幂等去重
    text: str
    page_start: int
    page_end: int
    sections: list[str]       # 标题层级
    metadata: dict            # 策略特定字段
    created_at: datetime
```

### 6.2 ChunkingStrategy 协议

```python
class ChunkingStrategy(Protocol):
    @property
    def name(self) -> str: ...

    def chunk(self, parsed: ParsedDocument) -> list[Chunk]: ...
```

### 6.3 策略实现

| 策略 | 默认 MIME | 分块逻辑 |
|------|-----------|----------|
| `ParagraphChunker` | `text/plain` | 按 `\n\n` 切分。单段 > 512 token 则按句号再分；< 128 token 合并到下一段 |
| `MarkdownChunker` | `text/markdown` | 先按 `##` 标题切节，同级标题下按段落细分 |
| `PDFChunker` | `application/pdf` | 以页为边界。单页 ≤512 token → 整页一个 chunk；否则按 MinerU 输出的段落切分 |
| `SemanticChunker` | — | 基于 token 窗口 + 相似度递归分块。首版只留类和接口定义，`chunk()` 返回 `NotImplementedError` |

### 6.4 ChunkerRegistry

```python
class ChunkerRegistry:
    def __init__(self):
        self._defaults: dict[str, ChunkingStrategy] = {
            "text/plain": ParagraphChunker(),
            "text/markdown": MarkdownChunker(),
            "application/pdf": PDFChunker(),
        }
        self._overrides: dict[str, ChunkingStrategy] = {}

    def get(self, mime: str) -> ChunkingStrategy:
        return self._overrides.get(mime) or self._defaults[mime]

    def override(self, mime: str, strategy: ChunkingStrategy) -> None:
        """允许用户自定义某 MIME 类型的策略"""

    def register(self, mime: str, strategy: ChunkingStrategy) -> None:
        """注册新策略 (后续可选)"""
```

---

## 7. TaskQueue

### 7.1 协议

```python
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
    status: TaskStatus
    progress: float          # 0.0 ~ 1.0
    error_message: str | None
    created_at: datetime
    updated_at: datetime

class TaskQueue(Protocol):
    async def enqueue(self, document_id: str) -> str:       # → task_id
    async def get(self, task_id: str) -> TaskInfo | None:
    async def list_by_document(self, document_id: str) -> list[TaskInfo]:
```

### 7.2 InProcessTaskQueue

```python
class InProcessTaskQueue:
    def __init__(self, worker: TaskWorker, task_repo: TaskRepository):
        self._worker = worker
        self._repo = task_repo

    async def enqueue(self, document_id: str) -> str:
        task_id = str(uuid.uuid4())[:8]
        task = TaskInfo(task_id=task_id, document_id=document_id, status=TaskStatus.QUEUED, ...)
        await self._repo.save(task)
        asyncio.create_task(self._run(task))
        return task_id

    async def _run(self, task: TaskInfo):
        try:
            await self._worker.execute(task.document_id)
            task.status = TaskStatus.DONE
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
        finally:
            task.updated_at = datetime.utcnow()
            await self._repo.save(task)
```

### 7.3 TaskWorker

```python
class TaskWorker:
    def __init__(self, doc_repo, storage, parser_registry, chunker_registry, chunk_repo):
        ...

    async def execute(self, document_id: str):
        doc = await self._doc_repo.get(document_id)

        # 1. 获取文件路径
        file_path = self._storage.resolve_path(doc.storage_key)
        cleanup_temp = False
        if file_path is None:
            # OSS: 下载到临时文件
            content = await self._storage.read(doc.storage_key)
            ext = doc.filename.rsplit(".", 1)[-1] if "." in doc.filename else ""
            with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as f:
                f.write(content)
            file_path = f.name
            cleanup_temp = True

        try:
            # 2. Parser
            await self._doc_repo.update(doc.document_id, status="parsing")
            parser = self._parser_registry.select(doc.mime_type, doc.filename)
            parsed = parser.parse(file_path, doc.filename, doc.mime_type)

            # 3. Chunker
            await self._doc_repo.update(doc.document_id, status="chunking")
            chunker = self._chunker_registry.get(doc.mime_type)
            chunks = chunker.chunk(parsed)

            # 4. 保存 Chunks
            await self._chunk_repo.batch_save(chunks)

            # 5. 更新文档状态
            await self._doc_repo.update(doc.document_id, status="indexed", chunk_count=len(chunks))
        finally:
            if cleanup_temp:
                os.unlink(file_path)
```

---

## 8. Document 数据模型

```python
@dataclass
class Document:
    document_id: str          # UUID, API 对外标识
    user_id: str              # 上传者
    filename: str             # 原始文件名 (展示用)
    storage_key: str          # ObjectStorage 内部键 (不暴露给 API)
    mime_type: str            # 检测到的 MIME
    file_size: int            # 字节数
    file_hash: str            # SHA-256 (去重)
    scope: Literal["private", "shared"]
    status: str               # uploaded → queued → parsing → chunking → indexed / failed
    chunk_count: int          # 分块数量
    error_message: str | None
    created_at: datetime
    updated_at: datetime
```

`DocumentRepository` 协议：
```python
class DocumentRepository(Protocol):
    async def create(self, doc: Document) -> Document: ...
    async def get(self, document_id: str) -> Document | None: ...
    async def list_by_user(self, user_id: str) -> list[Document]: ...
    async def update(self, document_id: str, **kwargs) -> Document | None: ...
    async def delete(self, document_id: str) -> None: ...
```

---

## 9. API 端点

全部使用 `/api/v1` 前缀，需要认证。

### 9.1 文档管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/documents` | 上传文档 (multipart/form-data, ≤20MB) |
| `GET` | `/api/v1/documents` | 列出当前用户的文档 |
| `GET` | `/api/v1/documents/{document_id}` | 获取文档详情 |
| `DELETE` | `/api/v1/documents/{document_id}` | 删除文档 + chunks |

### 9.2 任务查询

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/tasks/{task_id}` | 查询索引任务进度 |

### 9.3 预留（不实现）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/documents/{document_id}/reindex` | 重新索引 |
| `GET` | `/api/v1/documents/{document_id}/chunks` | 获取文档的所有 Chunk |

### 9.4 请求/响应模型

上传请求:
```
POST /api/v1/documents
Content-Type: multipart/form-data
  file: <binary>
  scope: "private" | "shared"  (默认 private, shared 仅 admin 可设置)
```

上传响应:
```json
{
  "document_id": "abc123",
  "filename": "月度报告.pdf",
  "mime_type": "application/pdf",
  "file_size": 1048576,
  "scope": "private",
  "status": "queued",
  "task_id": "a1b2c3d4",
  "created_at": "2026-07-29T10:30:00Z"
}
```

任务查询响应:
```json
{
  "task_id": "a1b2c3d4",
  "document_id": "abc123",
  "status": "parsing",
  "progress": 0.5,
  "error_message": null,
  "created_at": "2026-07-29T10:30:00Z",
  "updated_at": "2026-07-29T10:30:05Z"
}
```

---

## 10. 安全约束

- 文件大小上限: 20MB
- MIME 白名单: `text/plain`, `text/markdown`, `application/pdf`
- storage_key 不通过 API 暴露
- 普通用户只能上传 `private` 文档；admin 可上传 `shared`
- 用户只能查看/删除自己的文档（admin 除外）
- `file_hash` (SHA-256) 用于去重: 同用户同 scope 同 hash → 拒绝重复上传
- 上传的文件扩展名须与 MIME 一致，不一致则拒绝 (解析层安全校验)
- OSS 模式下临时文件处理完立即删除

---

## 11. 错误码

| 错误码 | HTTP | 说明 |
|--------|------|------|
| `UNSUPPORTED_FORMAT` | 400 | 文件格式不支持 |
| `FILE_TOO_LARGE` | 413 | 超过 20MB 限制 |
| `MIME_MISMATCH` | 400 | 扩展名与 MIME 不一致 |
| `DUPLICATE_DOCUMENT` | 409 | 相同文件已存在 |
| `DOCUMENT_NOT_FOUND` | 404 | 文档不存在 |
| `DOCUMENT_NOT_READY` | 409 | 文档仍在处理中 |
| `TASK_NOT_FOUND` | 404 | 任务不存在 |
| `STORAGE_UNAVAILABLE` | 502 | 存储服务不可用 |
| `PARSER_NOT_AVAILABLE` | 501 | 解析能力未实现 |
| `PARSER_ERROR` | 502 | 解析过程异常 |

---

## 12. 生命周期集成

在 `main.py` 的 lifespan startup 中新增:

```python
# Storage
app.state.storage = create_storage()

# Parsers
parser_registry = ParserRegistry()
parser_registry.register(TextParser(), ext=[".txt"], mime=["text/plain"])
parser_registry.register(MarkdownParser(), ext=[".md"], mime=["text/markdown"])
parser_registry.register(MinerUParser(api_url=...), ext=[".pdf"], mime=["application/pdf"])
# 注册预留能力...
app.state.parser_registry = parser_registry

# Chunkers
app.state.chunker_registry = ChunkerRegistry()

# TaskQueue
task_repo = InMemoryTaskRepo()
task_worker = TaskWorker(...)
app.state.task_queue = InProcessTaskQueue(worker=task_worker, task_repo=task_repo)
```

---

## 13. 测试策略

### 单元测试
- `LocalStorage`: save/read/delete/exists/resolve_path
- `ParserRegistry`: 扩展名匹配、MIME 回退、安全校验拒绝
- `TextParser`/`MarkdownParser`: 输入预期输出
- `ParagraphChunker`/`MarkdownChunker`: 分块数量和边界验证
- `DocumentService`: 创建/查询/删除 + 所有权校验

### 集成测试
- `MinerUParser` 的集成测试使用 mock API 服务器
- TaskQueue + TaskWorker 端到端: 上传 TXT 文件 → 查询任务 → 验证 chunks 生成
- 去重: 上传相同文件两次 → 第二次返回 409
- MIME 安全校验: `.txt` 文件带 `text/html` MIME → 拒绝

### API 测试
- 上传 + 查询 + 删除 完整流程
- 任务查询状态变化
- 用户隔离: user A 看不到 user B 的文档
- 文件大小和格式限制验证

---

## 14. 完成标准

- [ ] `POST /api/v1/documents` 可上传 TXT/MD/PDF 文件
- [ ] 上传后立即返回 document_id + task_id
- [ ] `GET /api/v1/tasks/{id}` 可查询任务进度
- [ ] 后台异步完成解析 → 分块，文档状态变为 `indexed`
- [ ] `GET /api/v1/documents` 列出当前用户的文档
- [ ] `DELETE /api/v1/documents/{id}` 删除文档 + chunks
- [ ] 用户隔离有效（不能访问他人文档）
- [ ] LocalStorage 和 OSS Storage 可通过配置切换
- [ ] MinerU 不可用时 PDF 降级到 pypdf 不阻断流程
- [ ] 重复文件上传返回 409
- [ ] MIME 不一致返回 400
- [ ] 所有单元和 API 测试通过（不依赖外部服务）
