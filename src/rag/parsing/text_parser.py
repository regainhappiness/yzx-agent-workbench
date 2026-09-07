"""TextParser — 纯文本解析"""

import logging
from .base import Parser, ParsedDocument, ParsedPage

logger = logging.getLogger("server.parser.text")


class TextParser:

    @property
    def supported_mime_types(self) -> list[str]:
        return ["text/plain"]

    def parse(self, file_path: str, filename: str, mime: str) -> ParsedDocument:
        try:
            import chardet
            with open(file_path, "rb") as f:
                raw = f.read()
            detected = chardet.detect(raw)
            encoding = (detected.get("encoding") if detected else None) or "utf-8"
            text = raw.decode(encoding)
        except ImportError:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            encoding = "utf-8"

        return ParsedDocument(
            text=text,
            pages=[ParsedPage(page_number=1, text=text)],
            metadata={"encoding": encoding},
        )
