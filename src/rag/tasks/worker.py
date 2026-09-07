"""TaskWorker — 编排完整的 解析→分块→Embedding→Milvus 写入 管线"""

import os
import asyncio
import time
import tempfile
import logging

from ...server.repositories.base import (
    DocumentRepository, ChunkRepository, ChunkRecord,
)

logger = logging.getLogger("server.task_worker")


class TaskWorker:
    """文档索引管线编排器。

    管线步骤:
      1. 获取文件 (OSS → 临时文件, Local → 直接路径)
      2. 解析: Parser.parse() → ParsedDocument
      3. 分块: ChunkingStrategy.chunk() → list[Chunk]
      4. Embedding: EmbeddingService.embed() → 每个 Chunk 追加向量
      5. Milvus: 批量写入向量 Collection
      6. SQLite: 保存 ChunkRecord
      7. 更新文档状态 → "indexed"
    """

    def __init__(
        self,
        doc_repo: DocumentRepository,
        chunk_repo: ChunkRepository,
        storage,
        parser_registry,
        chunker_registry,
        embedding_service,
        milvus_client,
    ):
        self._doc_repo = doc_repo
        self._chunk_repo = chunk_repo
        self._storage = storage
        self._parser_registry = parser_registry
        self._chunker_registry = chunker_registry
        self._embedding = embedding_service
        self._milvus = milvus_client

    async def get_document_status(self, document_id: str) -> str | None:
        doc = await self._doc_repo.get(document_id)
        return doc.status if doc else None

    async def cleanup_failed(self, document_id: str) -> None:
        """重试清理失败任务可能遗留的向量、Chunk 和原始文件。"""
        doc = await self._doc_repo.get(document_id)
        if not doc:
            return
        milvus_user_id = doc.user_id if doc.scope == "private" else ""
        await self._delete_milvus_with_retry(document_id, milvus_user_id)
        await self._chunk_repo.delete_by_document(document_id, doc.user_id)
        await self._storage.delete(doc.storage_key)
        await self._doc_repo.update(document_id, status="failed", chunk_count=0)

    async def execute(self, document_id: str, task_id: str | None = None):
        doc = await self._doc_repo.get(document_id)
        if not doc:
            raise ValueError(f"文档不存在: {document_id}")

        logger.info(
            "文档索引任务开始: document=%s task=%s file=%r",
            document_id,
            task_id or "unknown",
            doc.filename,
        )

        file_path = None
        cleanup_temp = False

        try:
            # ---- 1. 获取文件路径 ----
            file_path = self._storage.resolve_path(doc.storage_key)
            if file_path is None:
                content = await self._storage.read(doc.storage_key)
                ext = doc.filename.rsplit(".", 1)[-1] if "." in doc.filename else ""
                with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as f:
                    f.write(content)
                file_path = f.name
                cleanup_temp = True

            # ---- 2. 解析 ----
            await self._doc_repo.update(document_id, status="parsing")
            parser = self._parser_registry.select(doc.mime_type, doc.filename)
            parsed = await asyncio.to_thread(
                parser.parse, file_path, doc.filename, doc.mime_type,
            )
            logger.info(
                "文档解析完成: document=%s task=%s chars=%d pages=%d",
                document_id,
                task_id or "unknown",
                len(getattr(parsed, "text", "") or ""),
                len(getattr(parsed, "pages", []) or []),
            )

            # ---- 3. 分块 ----
            await self._doc_repo.update(document_id, status="chunking")
            chunker = self._chunker_registry.get(doc.mime_type)
            chunks = await asyncio.to_thread(chunker.chunk, parsed, document_id)
            logger.info(
                "文档分块完成: document=%s task=%s chunks=%d",
                document_id,
                task_id or "unknown",
                len(chunks),
            )

            # ---- 4. Embedding ----
            if chunks:
                await self._doc_repo.update(document_id, status="embedding")
                chunk_texts = [c.text for c in chunks]
                embed_results = await self._embedding.embed(chunk_texts)
                result_indexes = {er.index for er in embed_results}
                if result_indexes != set(range(len(chunks))):
                    raise RuntimeError(
                        f"Embedding 返回不完整: expected={len(chunks)}, "
                        f"actual={len(result_indexes)}"
                    )

                # 将向量附加到 Chunk metadata
                for er in embed_results:
                    chunks[er.index].metadata["embedding"] = er.vector
                    chunks[er.index].metadata["embedding_model"] = self._embedding.model_name

                logger.info(
                    "Embedding 完成: document=%s task=%s vectors=%d",
                    document_id,
                    task_id or "unknown",
                    len(embed_results),
                )
            else:
                logger.warning("文档 %s 未产生任何 Chunk", document_id)

            # ---- 5. Milvus 写入 ----
            milvus_rows = []
            now_ts = int(time.time())
            # 确定 Milvus 分区键: private→实际user, shared→公共分区""
            milvus_user_id = doc.user_id if doc.scope == "private" else ""
            for c in chunks:
                milvus_rows.append({
                    "chunk_id": c.chunk_id,
                    "document_id": c.document_id,
                    "chunk_index": c.chunk_index,
                    "chunk_hash": c.chunk_hash,
                    "scope": doc.scope,
                    "user_id": milvus_user_id,
                    "text": c.text,
                    "source_name": doc.filename,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                    "sections": c.sections,
                    "embedding": c.metadata.get("embedding", []),
                    "created_at": now_ts,
                })

            # 先清理同一文档的旧向量，使崩溃恢复和人工重试保持幂等。
            await asyncio.to_thread(
                self._milvus.delete_by_document, document_id, milvus_user_id,
            )

            # 分批写入 Milvus (每批 100 条)
            BATCH = 100
            for i in range(0, len(milvus_rows), BATCH):
                batch = milvus_rows[i:i + BATCH]
                await asyncio.to_thread(self._milvus.insert, batch)

            logger.info("Milvus 写入完成: %d 条", len(milvus_rows))

            # ---- 6. SQLite 保存 ChunkRecord ----
            records = [
                ChunkRecord(
                    chunk_id=c.chunk_id,
                    document_id=c.document_id,
                    user_id=doc.user_id,  # 记录实际上传者，用于审计
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
            commit_index = getattr(self._chunk_repo, "commit_index", None)
            if callable(commit_index):
                await commit_index(document_id, records, task_id)
            else:
                # 内存/第三方仓储回退；SQLite 实现会走上面的原子事务。
                await self._chunk_repo.delete_by_document(document_id, doc.user_id)
                await self._chunk_repo.batch_save(records)
                await self._doc_repo.update(
                    document_id,
                    status="indexed",
                    chunk_count=len(chunks),
                    error_message=None,
                )
            logger.info("文档索引完成: %s (%d chunks)", document_id, len(chunks))

        except Exception as exc:
            await self._compensate(doc, task_id, str(exc))
            raise
        finally:
            if cleanup_temp and file_path:
                try:
                    os.unlink(file_path)
                except OSError:
                    pass

    async def _compensate(self, doc, task_id: str | None, error_message: str) -> None:
        """撤销索引管线已产生的外部副作用，并留下失败审计记录。"""
        milvus_user_id = doc.user_id if doc.scope == "private" else ""
        cleanup_pending = False
        try:
            await self._delete_milvus_with_retry(
                doc.document_id, milvus_user_id,
            )
        except Exception:
            cleanup_pending = True
            logger.exception("补偿 Milvus 数据失败: document=%s", doc.document_id)

        try:
            await self._storage.delete(doc.storage_key)
        except Exception:
            cleanup_pending = True
            logger.exception("补偿原始文件失败: document=%s", doc.document_id)

        try:
            fail_index = getattr(self._chunk_repo, "fail_index", None)
            if callable(fail_index):
                await fail_index(
                    doc.document_id,
                    task_id,
                    error_message,
                    "cleanup_pending" if cleanup_pending else "failed",
                )
            else:
                await self._chunk_repo.delete_by_document(
                    doc.document_id, doc.user_id,
                )
                await self._doc_repo.update(
                    doc.document_id,
                    status="cleanup_pending" if cleanup_pending else "failed",
                    chunk_count=0,
                    error_message=error_message,
                )
        except Exception:
            logger.exception("补偿 SQLite 数据失败: document=%s", doc.document_id)

    async def _delete_milvus_with_retry(
        self,
        document_id: str,
        user_id: str,
    ) -> None:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                await asyncio.to_thread(
                    self._milvus.delete_by_document, document_id, user_id,
                )
                return
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(0.25 * (2 ** attempt))
        assert last_error is not None
        raise last_error
