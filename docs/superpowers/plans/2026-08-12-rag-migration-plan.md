# RAG Module Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate knowledge-base modules (chunking, documents, embedding, milvus, parsing, storage, tasks, retrieval) from `src/server/` to `src/rag/`, updating all internal and external imports.

**Architecture:** Pure refactoring — move files and update import paths. No logic changes. `repositories/` stays in server as a shared base layer. `documents/router.py` moves to `server/api/documents.py`. `retrieval_service.py` and `advanced_retrieval.py` move to `rag/retrieval/`.

**Tech Stack:** Python, FastAPI (no new dependencies)

**Spec:** `docs/superpowers/specs/2026-08-12-rag-migration-design.md`

**Key import transform rules:**
- RAG→RAG: `from ..xxx` stays `from ..xxx` (both under `rag/`, relative path unchanged)
- RAG→Server: `from ..repositories` → `from ...server.repositories`; `from ..exceptions` → `from ...server.exceptions`
- Server→RAG: `from .chunking` → `from ..rag.chunking`
- Tests: `from src.server.xxx` → `from src.rag.xxx` (preserving `src.server.repositories` references)

---

### Task 1: Create `src/rag/` directory structure and move files

**Files:**
- Create all directories under `src/rag/`
- Move 7 module directories + create retrieval/

- [ ] **Step 1: Create rag directory structure**

```bash
mkdir -p src/rag/chunking src/rag/documents src/rag/embedding src/rag/milvus \
  src/rag/parsing src/rag/storage src/rag/tasks src/rag/retrieval
```

- [ ] **Step 2: Move chunking, embedding, milvus, parsing, storage, tasks**

```bash
mv src/server/chunking/*.py src/rag/chunking/
mv src/server/embedding/*.py src/rag/embedding/
mv src/server/milvus/*.py src/rag/milvus/
mv src/server/parsing/*.py src/rag/parsing/
mv src/server/storage/*.py src/rag/storage/
mv src/server/tasks/*.py src/rag/tasks/
```

- [ ] **Step 3: Move documents/ files (except router.py)**

```bash
mv src/server/documents/__init__.py src/rag/documents/
mv src/server/documents/errors.py src/rag/documents/
mv src/server/documents/service.py src/rag/documents/
```

- [ ] **Step 4: Move retrieval service files**

```bash
mv src/server/services/retrieval_service.py src/rag/retrieval/
mv src/server/services/advanced_retrieval.py src/rag/retrieval/
```

- [ ] **Step 5: Create rag/__init__.py and rag/retrieval/__init__.py**

Write `src/rag/__init__.py`:
```python
"""RAG 知识库层 — 解析、分块、Embedding、Milvus、存储、任务管线、检索"""
```

Write `src/rag/retrieval/__init__.py`:
```python
"""检索服务 — 基础检索 + 高阶检索 (Query 改写 + 多路 + RRF)"""
from .retrieval_service import RetrievalService
from .advanced_retrieval import AdvancedRetrievalService

__all__ = ["RetrievalService", "AdvancedRetrievalService"]
```

- [ ] **Step 6: Remove empty old directories**

```bash
rmdir src/server/chunking src/server/embedding src/server/milvus \
  src/server/parsing src/server/storage src/server/tasks 2>/dev/null || true
```

- [ ] **Step 7: Commit**

```bash
git add src/rag/
git add src/server/
git rm src/server/chunking/__init__.py src/server/chunking/base.py \
  src/server/chunking/registry.py src/server/chunking/paragraph_chunker.py \
  src/server/chunking/markdown_chunker.py src/server/chunking/pdf_chunker.py \
  src/server/chunking/semantic_chunker.py \
  src/server/embedding/__init__.py src/server/embedding/base.py \
  src/server/embedding/bailian.py \
  src/server/milvus/__init__.py src/server/milvus/client.py \
  src/server/parsing/__init__.py src/server/parsing/base.py \
  src/server/parsing/registry.py src/server/parsing/text_parser.py \
  src/server/parsing/markdown_parser.py src/server/parsing/mineru_parser.py \
  src/server/parsing/mineru_agent_parser.py src/server/parsing/placeholders.py \
  src/server/storage/__init__.py src/server/storage/base.py \
  src/server/storage/local.py src/server/storage/oss.py \
  src/server/tasks/__init__.py src/server/tasks/base.py \
  src/server/tasks/in_process.py src/server/tasks/worker.py \
  src/server/documents/__init__.py src/server/documents/errors.py \
  src/server/documents/service.py \
  src/server/services/retrieval_service.py \
  src/server/services/advanced_retrieval.py
git commit -m "refactor: move RAG modules from src/server/ to src/rag/"
```

---

### Task 2: Fix imports in moved RAG modules (server references)

**Files:**
- Modify: `src/rag/parsing/registry.py:6`
- Modify: `src/rag/tasks/in_process.py:10`
- Modify: `src/rag/tasks/worker.py:9-11`
- Modify: `src/rag/documents/__init__.py:2-5`
- Modify: `src/rag/documents/errors.py:1`
- Modify: `src/rag/documents/service.py:12-18`

- [ ] **Step 1: Fix `rag/parsing/registry.py`**

Replace line 6: `from ..exceptions import AppError` → `from ...server.exceptions import AppError`

- [ ] **Step 2: Fix `rag/tasks/in_process.py`**

Replace line 10: `from ..repositories.base import TaskRepository` → `from ...server.repositories.base import TaskRepository`

- [ ] **Step 3: Fix `rag/tasks/worker.py`**

Replace lines 9-11:
```python
from ..repositories.base import (
    DocumentRepository, ChunkRepository, ChunkRecord,
)
```
→
```python
from ...server.repositories.base import (
    DocumentRepository, ChunkRepository, ChunkRecord,
)
```

- [ ] **Step 4: Fix `rag/documents/__init__.py`**

Remove `from .router import router` and remove `router` from `__all__`. New content:
```python
"""文档管理模块"""
from .service import DocumentService

__all__ = ["DocumentService"]
```

- [ ] **Step 5: Fix `rag/documents/errors.py`**

Replace the import line: `from ..exceptions import AppError` → `from ...server.exceptions import AppError`

- [ ] **Step 6: Fix `rag/documents/service.py`**

Replace lines 14-17:
```python
from ..repositories.base import (
    DocumentRepository, ChunkRepository,
    Document, Identity,
)
```
→
```python
from ...server.repositories.base import (
    DocumentRepository, ChunkRepository,
    Document, Identity,
)
```

- [ ] **Step 7: Commit**

```bash
git add src/rag/
git commit -m "refactor: fix RAG internal imports to reference server.repositories/exceptions"
```

---

### Task 3: Move documents/router.py to server/api/documents.py and fix imports

**Files:**
- Create: `src/server/api/documents.py`
- Modify: `src/server/api/__init__.py:9`

- [ ] **Step 1: Move and fix router file**

Copy `src/server/documents/router.py` → `src/server/api/documents.py` with these import changes:

Lines 21-22, replace:
```python
from .service import DocumentService, MAX_FILE_SIZE
from .errors import FileTooLargeError, UnsupportedFormatError
```
→
```python
from ...rag.documents.service import DocumentService, MAX_FILE_SIZE
from ...rag.documents.errors import FileTooLargeError, UnsupportedFormatError
```

(All other imports — `from ..deps`, `from ..exceptions`, `from ..repositories.base`, `from ..schemas` — stay unchanged as they reference server modules.)

- [ ] **Step 2: Update `server/api/__init__.py`**

Replace line 9: `from ..documents import router as documents_router` → `from .documents import router as documents_router`

- [ ] **Step 3: Commit**

```bash
git add src/server/api/documents.py src/server/api/__init__.py
git commit -m "refactor: move documents router to server/api/documents.py"
```

---

### Task 4: Update `server/main.py` imports

**Files:**
- Modify: `src/server/main.py:30-40`

- [ ] **Step 1: Update main.py imports**

Replace lines 30-40:
```python
from .storage import create_storage
from .parsing import (
    ParserRegistry, TextParser, MarkdownParser, MinerUParser,
    MinerUAgentParser,
    register_placeholders,
)
from .chunking import ChunkerRegistry
from .embedding import BailianEmbedding
from .milvus import MilvusClient
from .tasks import InProcessTaskQueue, TaskWorker
from .documents import DocumentService
```
→
```python
from ..rag.storage import create_storage
from ..rag.parsing import (
    ParserRegistry, TextParser, MarkdownParser, MinerUParser,
    MinerUAgentParser,
    register_placeholders,
)
from ..rag.chunking import ChunkerRegistry
from ..rag.embedding import BailianEmbedding
from ..rag.milvus import MilvusClient
from ..rag.tasks import InProcessTaskQueue, TaskWorker
from ..rag.documents import DocumentService
```

Also update line 155 and 168:
- Line 155: `from .services.retrieval_service import RetrievalService` → `from ..rag.retrieval import RetrievalService`
- Line 168: `from .services.advanced_retrieval import AdvancedRetrievalService` → `from ..rag.retrieval import AdvancedRetrievalService`

- [ ] **Step 2: Commit**

```bash
git add src/server/main.py
git commit -m "refactor: update main.py imports to reference src/rag"
```

---

### Task 5: Update test file imports

**Files:**
- Modify: `tests/conftest.py:25,31,32`
- Modify: `tests/test_chunking.py:3,7,20,34,53,63,71`
- Modify: `tests/test_parsing.py:71,83,97,105,113,114,122,123,153,213,274,289,299,323,324,365,414,464,477,513`
- Modify: `tests/test_storage.py:10`
- Modify: `tests/test_document_api.py:11`
- Modify: `tests/test_ingestion_reliability.py:20-23`

- [ ] **Step 1: Update `tests/conftest.py`**

Replace:
```python
from src.server.documents.service import DocumentService
```
→ `from src.rag.documents import DocumentService`

Replace:
```python
from src.server.storage.local import LocalStorage
```
→ `from src.rag.storage import LocalStorage`

Replace:
```python
from src.server.tasks.in_process import InProcessTaskQueue
```
→ `from src.rag.tasks import InProcessTaskQueue`

- [ ] **Step 2: Update `tests/test_chunking.py`**

Replace all occurrences:
- `from src.server.parsing.base import ParsedDocument, ParsedPage` → `from src.rag.parsing.base import ParsedDocument, ParsedPage`
- `from src.server.chunking import ...` → `from src.rag.chunking import ...`

- [ ] **Step 3: Update `tests/test_parsing.py`**

Replace all occurrences:
- `from src.server.parsing import ...` → `from src.rag.parsing import ...`
- `from src.server.parsing.mineru_parser import ...` → `from src.rag.parsing.mineru_parser import ...`
- `from src.server.parsing.mineru_agent_parser import ...` → `from src.rag.parsing.mineru_agent_parser import ...`
- `from src.server.parsing.base import ParsedDocument` → `from src.rag.parsing.base import ParsedDocument`
- `from src.server.exceptions import AppError` → KEEP AS IS (stays in server)

- [ ] **Step 4: Update `tests/test_storage.py`**

Replace: `from src.server.storage import LocalStorage` → `from src.rag.storage import LocalStorage`

- [ ] **Step 5: Update `tests/test_document_api.py`**

Replace line 11: `from src.server.documents.service import MAX_FILE_SIZE, MAX_PDF_PAGES` → `from src.rag.documents.service import MAX_FILE_SIZE, MAX_PDF_PAGES`

- [ ] **Step 6: Update `tests/test_ingestion_reliability.py`**

Replace:
```python
from src.server.milvus.client import SearchResult
from src.server.services.retrieval_service import RetrievalService
from src.server.tasks.in_process import InProcessTaskQueue
from src.server.tasks.worker import TaskWorker
```
→
```python
from src.rag.milvus.client import SearchResult
from src.rag.retrieval import RetrievalService
from src.rag.tasks import InProcessTaskQueue
from src.rag.tasks import TaskWorker
```
(Keep `from src.server.repositories.base import ...`, `from src.server.repositories.memory import ...`, `from src.server.repositories.sqlite import ...` unchanged.)

- [ ] **Step 7: Commit**

```bash
git add tests/
git commit -m "refactor: update test imports to reference src/rag"
```

---

### Task 6: Remove old router.py and clean up

**Files:**
- Delete: `src/server/documents/router.py`

- [ ] **Step 1: Remove leftover router.py from old documents directory**

```bash
rm src/server/documents/router.py
# If documents/ is now empty, remove it too
rmdir src/server/documents 2>/dev/null || true
```

- [ ] **Step 2: Commit**

```bash
git rm src/server/documents/router.py
git commit -m "chore: remove old documents/router.py (moved to api/documents.py)"
```

---

### Task 7: Verify — sanity check imports

- [ ] **Step 1: Check for any stale import references**

```bash
cd d:/Project/m-knowledge-assistant
grep -rn "from \.chunking" src/server/ --include="*.py" || echo "OK: no stale chunking refs in server"
grep -rn "from \.parsing" src/server/ --include="*.py" || echo "OK: no stale parsing refs in server"
grep -rn "from \.embedding" src/server/ --include="*.py" || echo "OK: no stale embedding refs in server"
grep -rn "from \.milvus" src/server/ --include="*.py" || echo "OK: no stale milvus refs in server"
grep -rn "from \.storage" src/server/ --include="*.py" || echo "OK: no stale storage refs in server"
grep -rn "from \.tasks" src/server/ --include="*.py" || echo "OK: no stale tasks refs in server"
grep -rn "from \.documents" src/server/ --include="*.py" | grep -v "api/__init__" || echo "OK: no stale documents refs in server"
grep -rn "from \.services.retrieval" src/server/ --include="*.py" || echo "OK: no stale retrieval refs in server"
grep -rn "from \.services.advanced_retrieval" src/server/ --include="*.py" || echo "OK: no stale advanced_retrieval refs in server"
```

- [ ] **Step 2: Verify Python can import all moved modules**

```bash
cd d:/Project/m-knowledge-assistant
python -c "
from src.rag.chunking import ChunkerRegistry, ParagraphChunker, MarkdownChunker, PDFChunker
from src.rag.parsing import ParserRegistry, TextParser, MarkdownParser
from src.rag.embedding import EmbeddingService, EmbeddingResult
from src.rag.milvus import MilvusClient
from src.rag.storage import ObjectStorage, LocalStorage, create_storage
from src.rag.tasks import TaskQueue, TaskStatus, InProcessTaskQueue, TaskWorker
from src.rag.documents import DocumentService
from src.rag.retrieval import RetrievalService, AdvancedRetrievalService
print('All imports OK')
"
```

- [ ] **Step 3: Commit if any fixes were needed**

```bash
git add -A && git diff --cached --quiet || git commit -m "chore: fix any remaining import references"
```
