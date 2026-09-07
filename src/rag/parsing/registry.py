"""Parser 注册中心 — 扩展名优先 + MIME 回退 + 安全校验"""

import logging

from .base import Parser
from ...server.exceptions import AppError

logger = logging.getLogger("server.parser_registry")

EXTENSION_MIME_MAP = {
    ".txt":  {"text/plain"},
    ".md":   {"text/markdown", "text/plain"},
    ".pdf":  {"application/pdf"},
}


class ParserRegistry:

    def __init__(self):
        self._by_extension: dict[str, Parser] = {}
        self._by_mime: dict[str, Parser] = {}
        self._capabilities: list[dict] = []

    def register(self, parser: Parser, extensions: list[str],
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

    def register_capability_only(self, name: str, extensions: list[str],
                                  mime_types: list[str]) -> None:
        """注册能力声明 (无实际 Parser 实现)"""
        self._capabilities.append({
            "name": name,
            "extensions": extensions,
            "mime_types": mime_types,
            "available": False,
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
            return True
        if mime not in allowed:
            raise AppError(
                code="MIME_MISMATCH",
                message=f"文件扩展名 {ext} 与 MIME 类型 {mime} 不匹配",
                status_code=400,
            )
        return True

    def list_capabilities(self) -> list[dict]:
        return self._capabilities
