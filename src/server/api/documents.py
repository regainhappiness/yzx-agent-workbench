"""文档管理 API 路由"""

import logging
import mimetypes
from urllib.parse import quote

try:
    import magic
except ImportError:  # python-magic on Windows may be installed without libmagic DLL.
    magic = None
from fastapi import APIRouter, Depends, Request, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse

from ..deps import get_identity
from ..exceptions import AppError
from ..repositories.base import Identity
from ..schemas import (
    DocumentBatchUploadItemResponse,
    DocumentBatchUploadResponse,
    DocumentPageResponse,
    DocumentResponse,
    DocumentUploadResponse,
    TaskResponse,
)
from ...rag.documents.service import DocumentService, MAX_FILE_SIZE
from ...rag.documents.errors import FileTooLargeError, UnsupportedFormatError

logger = logging.getLogger("server.document_api")
router = APIRouter()


def _detect_mime(content: bytes, filename: str) -> str:
    if magic is not None:
        return str(magic.from_buffer(content[:2048], mime=True))
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    guessed = mimetypes.guess_type(filename)[0]
    if guessed in {"text/markdown", "text/x-markdown"}:
        return "text/plain"
    return guessed or "application/octet-stream"


def get_doc_service(request: Request) -> DocumentService:
    service = request.app.state.doc_service
    if service is None:
        logger.error(
            "文档服务不可用: request_id=%s embedding 或 Milvus 未配置",
            getattr(request.state, "request_id", "unknown"),
        )
        raise AppError(
            code="DOCUMENT_SERVICE_UNAVAILABLE",
            message="文档索引服务未启用，请检查 Embedding 和 Milvus 配置",
            status_code=503,
        )
    return service


async def _upload_one(
    file: UploadFile,
    scope: str,
    identity: Identity,
    doc_service: DocumentService,
    request_id: str = "unknown",
) -> DocumentUploadResponse:
    filename = file.filename or "unknown"
    try:
        logger.info(
            "开始处理上传: request_id=%s file=%r declared_type=%s scope=%s user=%s",
            request_id,
            filename,
            file.content_type or "unknown",
            scope,
            identity.user_id,
        )
        if not file.filename:
            raise UnsupportedFormatError(filename, "unknown")

        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise FileTooLargeError(len(content), MAX_FILE_SIZE)

        detected_mime = _detect_mime(content, filename)
        effective_scope = scope
        if effective_scope == "shared" and identity.role != "admin":
            effective_scope = "private"

        result = await doc_service.upload(
            identity=identity,
            filename=file.filename,
            content=content,
            mime_type=detected_mime,
            scope=effective_scope,
        )
        return DocumentUploadResponse(**result)
    except AppError as exc:
        logger.warning(
            "上传被拒绝: request_id=%s file=%r code=%s message=%s",
            request_id,
            filename,
            exc.code,
            exc.message,
        )
        raise
    except Exception:
        logger.exception(
            "上传处理失败: request_id=%s file=%r",
            request_id,
            filename,
        )
        raise
    finally:
        await file.close()


@router.post("/documents", response_model=DocumentUploadResponse, status_code=201)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    scope: str = Form("private"),
    identity: Identity = Depends(get_identity),
    doc_service: DocumentService = Depends(get_doc_service),
):
    """上传文档"""
    return await _upload_one(
        file,
        scope,
        identity,
        doc_service,
        getattr(request.state, "request_id", "unknown"),
    )


@router.post("/documents/batch", response_model=DocumentBatchUploadResponse)
async def upload_documents_batch(
    request: Request,
    files: list[UploadFile] = File(...),
    scope: str = Form("private"),
    identity: Identity = Depends(get_identity),
    doc_service: DocumentService = Depends(get_doc_service),
):
    """批量上传文档，逐文件返回成功或失败结果。"""
    results: list[DocumentBatchUploadItemResponse] = []
    request_id = getattr(request.state, "request_id", "unknown")
    logger.info(
        "开始批量上传: request_id=%s files=%d scope=%s user=%s",
        request_id,
        len(files),
        scope,
        identity.user_id,
    )

    for file in files:
        filename = file.filename or "unknown"
        try:
            document = await _upload_one(
                file, scope, identity, doc_service, request_id,
            )
            results.append(DocumentBatchUploadItemResponse(
                filename=filename,
                success=True,
                document=document,
            ))
        except AppError as exc:
            results.append(DocumentBatchUploadItemResponse(
                filename=filename,
                success=False,
                error_code=exc.code,
                error_message=exc.message,
            ))
        except Exception:
            logger.exception("批量上传文件失败: %s", filename)
            results.append(DocumentBatchUploadItemResponse(
                filename=filename,
                success=False,
                error_code="UPLOAD_FAILED",
                error_message="文件上传失败，请稍后重试",
            ))

    succeeded = sum(item.success for item in results)
    logger.info(
        "批量上传完成: request_id=%s total=%d succeeded=%d failed=%d",
        request_id,
        len(results),
        succeeded,
        len(results) - succeeded,
    )
    return DocumentBatchUploadResponse(
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        results=results,
    )


@router.get("/documents", response_model=DocumentPageResponse)
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=200),
    scope: str | None = Query(None, pattern="^(private|shared)$"),
    status: str | None = Query(None, pattern="^(indexed|processing|failed)$"),
    identity: Identity = Depends(get_identity),
    doc_service: DocumentService = Depends(get_doc_service),
):
    """分页列出当前用户的文档，并支持服务端筛选。"""
    docs, total = await doc_service.list_documents(
        identity.user_id,
        page=page,
        page_size=page_size,
        search=search,
        scope=scope,
        status=status,
    )
    return DocumentPageResponse(
        items=[
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
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


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


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: str,
    request: Request,
    identity: Identity = Depends(get_identity),
    doc_service: DocumentService = Depends(get_doc_service),
):
    """下载原始文件"""
    from ..exceptions import NotFoundError
    doc = await doc_service.get_document(document_id)
    if not doc or doc.user_id != identity.user_id:
        raise NotFoundError("文档", document_id)

    storage = request.app.state.storage
    content = await storage.read(doc.storage_key)

    return StreamingResponse(
        iter([content]),
        media_type=doc.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{quote(doc.filename, safe='')}"
            ),
        },
    )


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    identity: Identity = Depends(get_identity),
    doc_service: DocumentService = Depends(get_doc_service),
):
    """删除文档"""
    await doc_service.delete_document(identity.user_id, document_id)


def _task_response(task) -> TaskResponse:
    return TaskResponse(
        task_id=task.task_id,
        document_id=task.document_id,
        status=task.status,
        progress=task.progress,
        error_message=task.error_message,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.get("/tasks", response_model=list[TaskResponse])
async def get_tasks(
    task_ids: list[str] = Query(...),
    doc_service: DocumentService = Depends(get_doc_service),
):
    """批量查询索引任务进度。"""
    unique_ids = list(dict.fromkeys(task_ids))[:100]
    tasks = await doc_service._task_queue.get_many(unique_ids)
    return [_task_response(task) for task in tasks]


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
    return _task_response(task)
