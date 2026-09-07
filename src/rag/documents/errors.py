"""文档相关错误码 — 复用 AppError"""

from ...server.exceptions import AppError


class UnsupportedFormatError(AppError):
    def __init__(self, filename: str, mime: str):
        super().__init__(
            code="UNSUPPORTED_FORMAT",
            message=f"不支持的文件格式: {filename} ({mime})",
            status_code=400,
        )


class FileTooLargeError(AppError):
    def __init__(self, size: int, max_size: int):
        size_mb = size / 1024 / 1024
        max_size_mb = max_size // 1024 // 1024
        super().__init__(
            code="FILE_TOO_LARGE",
            message=f"文件大小 {size_mb:.1f} MB 超过限制 {max_size_mb} MB",
            status_code=413,
            details={"size": size, "max_size": max_size},
        )


class MimeMismatchError(AppError):
    def __init__(self, ext: str, mime: str):
        super().__init__(
            code="MIME_MISMATCH",
            message=f"文件扩展名 {ext} 与 MIME 类型 {mime} 不一致",
            status_code=400,
        )


class InvalidPdfError(AppError):
    def __init__(self, message: str = "PDF 文件损坏、已加密或无法读取"):
        super().__init__(
            code="INVALID_PDF",
            message=message,
            status_code=400,
        )


class PdfPageLimitError(AppError):
    def __init__(self, page_count: int, max_pages: int):
        super().__init__(
            code="PDF_PAGE_LIMIT_EXCEEDED",
            message=f"PDF 共 {page_count} 页，超过 {max_pages} 页限制",
            status_code=422,
            details={"page_count": page_count, "max_pages": max_pages},
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
