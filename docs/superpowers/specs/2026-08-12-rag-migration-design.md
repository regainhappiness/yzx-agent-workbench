# RAG Module Migration Design

**Date:** 2026-08-12
**Status:** Approved

## Goal

Migrate knowledge-base (RAG) related modules from `src/server/` to `src/rag/` to separate concerns between the HTTP/server layer and the RAG/knowledge-base layer.

## Target Structure

### `src/rag/` — Knowledge-base layer (new home)

```
src/rag/
├── __init__.py
├── chunking/          # moved from src/server/chunking/
│   ├── __init__.py
│   ├── base.py
│   ├── registry.py
│   ├── paragraph_chunker.py
│   ├── markdown_chunker.py
│   ├── pdf_chunker.py
│   └── semantic_chunker.py
├── embedding/         # moved from src/server/embedding/
│   ├── __init__.py
│   ├── base.py
│   └── bailian.py
├── milvus/            # moved from src/server/milvus/
│   ├── __init__.py
│   └── client.py
├── parsing/           # moved from src/server/parsing/
│   ├── __init__.py
│   ├── base.py
│   ├── registry.py
│   ├── text_parser.py
│   ├── markdown_parser.py
│   ├── mineru_parser.py
│   ├── mineru_agent_parser.py
│   └── placeholders.py
├── storage/           # moved from src/server/storage/
│   ├── __init__.py
│   ├── base.py
│   ├── local.py
│   └── oss.py
├── tasks/             # moved from src/server/tasks/
│   ├── __init__.py
│   ├── base.py
│   ├── in_process.py
│   └── worker.py
├── documents/         # moved from src/server/documents/ (minus router.py)
│   ├── __init__.py
│   ├── errors.py
│   └── service.py
└── retrieval/         # moved from src/server/services/ (retrieval only)
    ├── __init__.py
    ├── retrieval_service.py
    └── advanced_retrieval.py
```

### `src/server/` — What stays

```
src/server/
├── api/
│   ├── documents.py       # NEW — was documents/router.py
│   ├── auth.py, chat.py, sessions.py, users.py, multi_agent.py (unchanged)
│   └── __init__.py
├── services/              # auth, session, chat, multi_agent (remove retrieval)
│   └── __init__.py
├── repositories/          # FULLY PRESERVED — shared base layer
├── middleware/             # unchanged
├── main.py                # updated imports
├── deps.py, schemas.py, exceptions.py, bootstrap_admin.py  # mostly unchanged
```

## Import Changes

### RAG internal imports (relative within rag):
| Before (in server) | After (in rag) |
|---|---|
| `from ..parsing.base import ParsedDocument` | `from .parsing.base import ParsedDocument` |
| `from ..milvus import MilvusClient` | `from .milvus import MilvusClient` |
| `from .base import Chunk` | `from .base import Chunk` (unchanged, same package) |

### Server → RAG imports:
| Before | After |
|---|---|
| `from .chunking import ...` | `from ..rag.chunking import ...` |
| `from .parsing import ...` | `from ..rag.parsing import ...` |
| `from .embedding import ...` | `from ..rag.embedding import ...` |
| `from .milvus import ...` | `from ..rag.milvus import ...` |
| `from .storage import create_storage` | `from ..rag.storage import create_storage` |
| `from .tasks import ...` | `from ..rag.tasks import ...` |
| `from .documents import DocumentService` | `from ..rag.documents import DocumentService` |
| `from .services.retrieval_service import ...` | `from ..rag.retrieval import ...` |

### RAG → Server reverse dependencies (valid):
- `rag/tasks/worker.py` → `server.repositories.base`
- `rag/documents/service.py` → `server.repositories.base`
- `rag/retrieval/` → `server.repositories.base`
- `rag/documents/errors.py` → `server.exceptions`
- `rag/parsing/registry.py` → `server.exceptions`
- `rag/tasks/in_process.py` → `server.repositories.base`

### documents/router.py → server/api/documents.py:
- Move the file, update imports from `..documents.service` to `..rag.documents`
- Update `api/__init__.py` to import from `.documents` instead of `..documents`

## Steps

1. Create `src/rag/` directory structure
2. Move chunking, embedding, milvus, parsing, storage, tasks directories wholesale
3. Move documents/ (without router.py) to rag
4. Create rag/retrieval/ with retrieval_service.py and advanced_retrieval.py
5. Move documents/router.py → server/api/documents.py
6. Update all `__init__.py` re-exports
7. Update all internal imports within moved modules (sibling references)
8. Update server/main.py imports
9. Update server/api/__init__.py
10. Update server services references
11. Verify the app starts correctly
