"""预留 Parser 能力声明 — 不实现，仅供查询"""

from .registry import ParserRegistry


def register_placeholders(registry: ParserRegistry) -> None:
    """注册预留解析能力 (available=False)"""
    placeholders = [
        (["docx"], [".docx"],
         ["application/vnd.openxmlformats-officedocument.wordprocessingml.document"]),
        (["xlsx"], [".xlsx"],
         ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]),
        (["pptx"], [".pptx"],
         ["application/vnd.openxmlformats-officedocument.presentationml.presentation"]),
        (["html", "web"], [".html", ".htm"],
         ["text/html"]),
        (["image", "ocr"], [".png", ".jpg", ".jpeg"],
         ["image/png", "image/jpeg"]),
    ]

    for name, exts, mimes in placeholders:
        registry.register_capability_only(name, exts, mimes)
