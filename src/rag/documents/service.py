"""文档服务 — 上传、查询、删除"""

import asyncio
import hashlib
import uuid
import logging
from datetime import datetime
from io import BytesIO

from pypdf import PdfReader

from ..milvus import MilvusClient

from ...server.repositories.base import (
    DocumentRepository, ChunkRepository,
    Document, Identity,
)
from ..tasks.base import TaskQueue
from .errors import (
    UnsupportedFormatError, FileTooLargeError,
    MimeMismatchError, DuplicateDocumentError,
    InvalidPdfError, PdfPageLimitError,
)

logger = logging.getLogger("server.document_service")

MAX_FILE_SIZE = 200 * 1024 * 1024  # 200 MB
MAX_PDF_PAGES = 200
MIME_TYPES_BY_EXTENSION = {
    "txt": {"text/plain"},
    "md": {"text/plain", "text/markdown", "text/x-markdown"},
    "pdf": {"application/pdf"},
}
CANONICAL_MIME_BY_EXTENSION = {
    "txt": "text/plain",
    "md": "text/markdown",
    "pdf": "application/pdf",
}
DOCUMENT_STATUSES = {
    "indexed": ["indexed"],
    "processing": ["uploaded", "queued", "parsing", "chunking", "embedding"],
    "failed": ["failed", "cleanup_pending"],
}


class DocumentService:

    def __init__(
        self,
        doc_repo: DocumentRepository,
        chunk_repo: ChunkRepository,
        storage,
        task_queue: TaskQueue,
        milvus_client: MilvusClient  # MilvusClient 
    ):
        self._doc_repo = doc_repo
        self._chunk_repo = chunk_repo
        self._storage = storage
        self._task_queue = task_queue
        self._milvus = milvus_client  

    async def upload(
        self, identity: Identity, filename: str,
        content: bytes, mime_type: str, scope: str = "private",
    ) -> dict:
        # 1. 校验
        if len(content) > MAX_FILE_SIZE:
            raise FileTooLargeError(len(content), MAX_FILE_SIZE)
        mime_type = self._validate_file(filename, content, mime_type)

        # 2. 去重检查
        file_hash = hashlib.sha256(content).hexdigest()
        existing = await self._doc_repo.list_by_user(identity.user_id)
        for doc in existing:
            if (
                doc.status != "failed"
                and doc.file_hash == file_hash
                and doc.scope == scope
            ):
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
        try:
            await self._doc_repo.create(doc)

            # 5. 提交索引任务
            task_id = await self._task_queue.enqueue(doc.document_id)
        except Exception:
            logger.exception(
                "文档上传提交失败，正在回滚: document=%s file=%r user=%s",
                doc.document_id,
                doc.filename,
                identity.user_id,
            )
            # 上传阶段尚未返回客户端，可直接回滚元数据和原始文件。
            try:
                await self._doc_repo.delete(doc.document_id)
            finally:
                await self._storage.delete(storage_key)
            raise

        logger.info(
            "文档上传已受理: document=%s task=%s file=%r size=%d scope=%s user=%s",
            doc.document_id,
            task_id,
            doc.filename,
            doc.file_size,
            doc.scope,
            identity.user_id,
        )

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

    async def list_documents(
        self,
        user_id: str,
        *,
        page: int,
        page_size: int,
        search: str | None = None,
        scope: str | None = None,
        status: str | None = None,
    ) -> tuple[list[Document], int]:
        return await self._doc_repo.list_by_user_paginated(
            user_id,
            offset=(page - 1) * page_size,
            limit=page_size,
            search=search.strip() if search and search.strip() else None,
            scope=scope,
            statuses=DOCUMENT_STATUSES.get(status) if status else None,
        )

    async def delete_document(self, user_id: str, document_id: str):
        doc = await self._doc_repo.get(document_id)
        if not doc:
            return
        if doc.user_id != user_id:
            from ...server.exceptions import NotFoundError
            raise NotFoundError("文档", document_id)

        await self._storage.delete(doc.storage_key)
        await self._chunk_repo.delete_by_document(document_id, user_id)
        # 同步清理 Milvus 向量 — 带 user_id 双重校验
        if self._milvus:
            delete_user_id = user_id if doc.scope == "private" else ""
            await asyncio.to_thread(
                self._milvus.delete_by_document, document_id, delete_user_id,
            )
        await self._doc_repo.delete(document_id)

    def _validate_file(self, filename: str, content: bytes, mime: str) -> str:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        allowed_mimes = MIME_TYPES_BY_EXTENSION.get(ext)
        normalized_mime = mime.partition(";")[0].strip().lower()

        if allowed_mimes is None:
            raise UnsupportedFormatError(filename, normalized_mime or "unknown")
        if normalized_mime not in allowed_mimes:
            raise MimeMismatchError(f".{ext}", mime)

        if ext == "pdf":
            self._validate_pdf(content)

        return CANONICAL_MIME_BY_EXTENSION[ext]

    @staticmethod
    def _validate_pdf(content: bytes) -> None:
        try:
            reader = PdfReader(BytesIO(content), strict=False)
            if reader.is_encrypted and reader.decrypt("") == 0:
                raise InvalidPdfError("PDF 已加密，无法读取页数")
            page_count = len(reader.pages)
        except InvalidPdfError:
            raise
        except Exception as exc:
            raise InvalidPdfError() from exc

        if page_count < 1:
            raise InvalidPdfError("PDF 不包含可读取页面")
        if page_count > MAX_PDF_PAGES:
            raise PdfPageLimitError(page_count, MAX_PDF_PAGES)
