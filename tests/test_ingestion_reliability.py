"""文档摄取并发、事务和补偿行为的回归测试。"""

import asyncio
from types import SimpleNamespace

import pytest

from src.server.repositories.base import ChunkRecord, Document, TaskRecord
from src.server.repositories.memory import (
    InMemoryChunkRepo,
    InMemoryDocumentRepo,
    InMemoryTaskRepo,
)
from src.server.repositories.sqlite import (
    SqliteChunkRepo,
    SqliteDb,
    SqliteDocumentRepo,
    SqliteTaskRepo,
)
from src.rag.milvus.client import SearchResult
from src.rag.retrieval import RetrievalService
from src.rag.tasks import InProcessTaskQueue
from src.rag.tasks import TaskWorker


def make_document(document_id: str = "doc-1") -> Document:
    return Document(
        document_id=document_id,
        user_id="user-1",
        filename="notes.txt",
        storage_key="notes.txt",
        mime_type="text/plain",
        file_size=5,
        file_hash="hash",
        status="queued",
    )


@pytest.mark.asyncio
async def test_aiosqlite_handles_concurrent_repository_operations(tmp_path):
    db = SqliteDb(str(tmp_path / "concurrent.db"))
    await db.init_schema()
    repo = SqliteTaskRepo(db)

    tasks = [
        TaskRecord(task_id=f"task-{index}", document_id=f"doc-{index}", status="queued")
        for index in range(32)
    ]
    await asyncio.gather(*(repo.save(task) for task in tasks))
    loaded = await asyncio.gather(*(repo.get(task.task_id) for task in tasks))

    assert {task.task_id for task in loaded if task} == {task.task_id for task in tasks}
    await db.close()


@pytest.mark.asyncio
async def test_sqlite_document_repository_paginates_and_filters(tmp_path):
    db = SqliteDb(str(tmp_path / "document-page.db"))
    await db.init_schema()
    repo = SqliteDocumentRepo(db)

    for index, filename in enumerate(
        ["alpha.txt", "beta.txt", "alpha-guide.txt", "gamma.txt", "alpha-faq.txt"]
    ):
        document = make_document(f"doc-{index}")
        document.filename = filename
        document.file_hash = f"hash-{index}"
        document.status = "indexed" if index % 2 == 0 else "queued"
        await repo.create(document)

    items, total = await repo.list_by_user_paginated(
        "user-1",
        offset=1,
        limit=1,
        search="alpha",
        statuses=["indexed"],
    )

    assert total == 3
    assert len(items) == 1
    assert "alpha" in items[0].filename
    assert items[0].status == "indexed"
    await db.close()


@pytest.mark.asyncio
async def test_sqlite_index_commit_updates_chunks_document_and_task_atomically(tmp_path):
    db = SqliteDb(str(tmp_path / "commit.db"))
    await db.init_schema()
    docs = SqliteDocumentRepo(db)
    chunks = SqliteChunkRepo(db)
    tasks = SqliteTaskRepo(db)
    document = make_document()
    task = TaskRecord(task_id="task-1", document_id=document.document_id, status="queued")
    chunk = ChunkRecord(
        chunk_id="chunk-1",
        document_id=document.document_id,
        user_id=document.user_id,
        chunk_index=0,
        chunk_hash="chunk-hash",
        text="hello",
        page_start=1,
        page_end=1,
    )

    await docs.create(document)
    await tasks.save(task)
    await chunks.commit_index(document.document_id, [chunk], task.task_id)

    saved_doc = await docs.get(document.document_id)
    saved_task = await tasks.get(task.task_id)
    assert saved_doc and saved_doc.status == "indexed" and saved_doc.chunk_count == 1
    assert saved_task and saved_task.status == "done" and saved_task.progress == 1.0
    assert [item.chunk_id for item in await chunks.get_by_document(document.document_id)] == ["chunk-1"]
    await db.close()


@pytest.mark.asyncio
async def test_task_queue_enforces_concurrency_limit_and_waits_on_close():
    class CountingWorker:
        def __init__(self):
            self.active = 0
            self.maximum = 0

        async def execute(self, document_id: str, task_id: str | None = None) -> None:
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            await asyncio.sleep(0.02)
            self.active -= 1

        async def get_document_status(self, document_id: str) -> str | None:
            return "queued"

    worker = CountingWorker()
    repo = InMemoryTaskRepo()
    queue = InProcessTaskQueue(worker, repo, max_concurrency=2)
    task_ids = [await queue.enqueue(f"doc-{index}") for index in range(8)]

    await queue.close()

    saved_tasks = await asyncio.gather(*(repo.get(task_id) for task_id in task_ids))
    assert worker.maximum == 2
    assert all(task and task.status == "done" for task in saved_tasks)


@pytest.mark.asyncio
async def test_worker_compensates_all_persistent_outputs_when_commit_fails(tmp_path):
    class FailingChunkRepo(InMemoryChunkRepo):
        async def batch_save(self, chunks: list[ChunkRecord]) -> None:
            await super().batch_save(chunks)
            raise RuntimeError("sqlite commit failed")

    class Storage:
        deleted = False

        def resolve_path(self, key: str) -> str:
            return str(tmp_path / key)

        async def delete(self, key: str) -> None:
            self.deleted = True

    class ParserRegistry:
        def select(self, mime_type: str, filename: str):
            return SimpleNamespace(parse=lambda *args: SimpleNamespace())

    class ChunkerRegistry:
        def get(self, mime_type: str):
            chunk = SimpleNamespace(
                chunk_id="chunk-1",
                document_id="doc-1",
                chunk_index=0,
                chunk_hash="hash-1",
                text="hello",
                page_start=1,
                page_end=1,
                sections=[],
                metadata={},
            )
            return SimpleNamespace(chunk=lambda *args: [chunk])

    class Embedding:
        model_name = "test"

        async def embed(self, texts: list[str]):
            return [SimpleNamespace(index=0, vector=[0.1, 0.2])]

    class Milvus:
        def __init__(self):
            self.rows: list[dict] = []
            self.delete_calls = 0

        def insert(self, rows: list[dict]) -> int:
            self.rows.extend(rows)
            return len(rows)

        def delete_by_document(self, document_id: str, user_id: str = "") -> int:
            self.delete_calls += 1
            deleted = len(self.rows)
            self.rows.clear()
            return deleted

    docs = InMemoryDocumentRepo()
    chunk_repo = FailingChunkRepo()
    storage = Storage()
    milvus = Milvus()
    document = make_document()
    await docs.create(document)
    worker = TaskWorker(
        doc_repo=docs,
        chunk_repo=chunk_repo,
        storage=storage,
        parser_registry=ParserRegistry(),
        chunker_registry=ChunkerRegistry(),
        embedding_service=Embedding(),
        milvus_client=milvus,
    )

    with pytest.raises(RuntimeError, match="sqlite commit failed"):
        await worker.execute(document.document_id, "task-1")

    failed_doc = await docs.get(document.document_id)
    assert failed_doc and failed_doc.status == "failed" and failed_doc.chunk_count == 0
    assert await chunk_repo.get_by_document(document.document_id) == []
    assert milvus.rows == [] and milvus.delete_calls == 2
    assert storage.deleted is True


@pytest.mark.asyncio
async def test_retrieval_hides_vectors_until_document_commit():
    class Embedding:
        async def embed_single(self, query: str):
            return SimpleNamespace(vector=[0.1, 0.2], tokens=2)

    class Milvus:
        def search(self, *args):
            return [
                SearchResult("chunk-ready", "doc-ready", 0, "ready", "ready.txt", "private"),
                SearchResult("chunk-failed", "doc-failed", 0, "failed", "failed.txt", "private"),
                SearchResult("chunk-other", "doc-other", 0, "other", "other.txt", "private"),
            ]

    docs = InMemoryDocumentRepo()
    ready = make_document("doc-ready")
    ready.status = "indexed"
    failed = make_document("doc-failed")
    failed.status = "failed"
    other = make_document("doc-other")
    other.user_id = "user-2"
    other.status = "indexed"
    for document in (ready, failed, other):
        await docs.create(document)

    retrieval = RetrievalService(Embedding(), Milvus(), docs)
    hits = await retrieval.search("hello", scope="private", user_id="user-1")

    assert [hit.chunk_id for hit in hits] == ["chunk-ready"]
