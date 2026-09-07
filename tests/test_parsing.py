"""Parser 测试 — 文本/Markdown/MinerU"""

import os
import io
import zipfile
import tempfile
from unittest import mock

import pytest


# ═══════════════════════════════════════════════════════════════
# fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def txt_file():
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8",
    ) as f:
        f.write("第一段内容。\n\n第二段内容。")
    yield f.name
    os.unlink(f.name)


@pytest.fixture
def md_file():
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8",
    ) as f:
        f.write("# 标题\n\n## 子标题\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n正文内容。")
    yield f.name
    os.unlink(f.name)


@pytest.fixture
def pdf_file():
    """创建一个最小的合法 PDF 文件 (PDF 1.4)"""
    # 最小合法 PDF
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
        b"trailer<</Size 4/Root 1 0 R>>\n"
        b"startxref\n206\n%%EOF"
    )
    with tempfile.NamedTemporaryFile(
        mode="wb", suffix=".pdf", delete=False,
    ) as f:
        f.write(pdf_content)
    yield f.name
    os.unlink(f.name)


def _make_mineru_zip(markdown_content: str) -> bytes:
    """构造 MinerU 风格的 zip 包（包含 full.md）"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # MinerU 实际路径格式: {uuid}/full.md
        zf.writestr("a90e6ab6-44f3-4554-b459-b62fe4c6b436/full.md", markdown_content)
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════════
# TextParser
# ═══════════════════════════════════════════════════════════════

def test_text_parser(txt_file):
    from src.rag.parsing import TextParser
    parser = TextParser()
    result = parser.parse(txt_file, "test.txt", "text/plain")
    assert "第一段" in result.text
    assert len(result.pages) == 1


# ═══════════════════════════════════════════════════════════════
# MarkdownParser
# ═══════════════════════════════════════════════════════════════

def test_markdown_parser(md_file):
    from src.rag.parsing import MarkdownParser
    parser = MarkdownParser()
    result = parser.parse(md_file, "test.md", "text/markdown")
    assert "标题" in result.text
    assert len(result.tables) >= 1
    sections = result.pages[0].sections
    assert "标题" in sections


# ═══════════════════════════════════════════════════════════════
# ParserRegistry
# ═══════════════════════════════════════════════════════════════

def test_parser_registry_select_by_extension():
    from src.rag.parsing import ParserRegistry, TextParser
    reg = ParserRegistry()
    reg.register(TextParser(), extensions=[".txt"], mime_types=["text/plain"])
    parser = reg.select("text/plain", "doc.txt")
    assert isinstance(parser, TextParser)


def test_parser_registry_select_by_mime_fallback():
    from src.rag.parsing import ParserRegistry, TextParser
    reg = ParserRegistry()
    reg.register(TextParser(), extensions=[".txt"], mime_types=["text/plain"])
    parser = reg.select("text/plain", "doc.unknown")
    assert isinstance(parser, TextParser)


def test_parser_registry_mime_mismatch():
    from src.rag.parsing import ParserRegistry, TextParser
    from src.server.exceptions import AppError
    reg = ParserRegistry()
    reg.register(TextParser(), extensions=[".txt"], mime_types=["text/plain"])
    with pytest.raises(AppError, match="MIME"):
        reg.select("text/html", "doc.txt")


def test_parser_registry_unsupported():
    from src.rag.parsing import ParserRegistry, TextParser
    from src.server.exceptions import AppError
    reg = ParserRegistry()
    reg.register(TextParser(), extensions=[".txt"], mime_types=["text/plain"])
    with pytest.raises(AppError, match="不支持"):
        reg.select("application/pdf", "doc.pdf")


# ═══════════════════════════════════════════════════════════════
# MinerUParser — API 调用 Mock 测试
# ═══════════════════════════════════════════════════════════════

MINERU_MARKDOWN = """# 第一章 概述

## 1.1 背景介绍

这是一段背景介绍文本，用于测试 MinerU 解析结果的 Markdown 转 ParsedDocument。

## 1.2 数据结构

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| name | string | 名称 |

正文内容继续。
"""


def test_mineru_parser_full_flow(pdf_file):
    """模拟完整的 MinerU 批量上传→轮询→下载→解析流程"""
    from src.rag.parsing.mineru_parser import MinerUParser

    zip_bytes = _make_mineru_zip(MINERU_MARKDOWN)

    with mock.patch("requests.post") as mock_post, \
         mock.patch("requests.put") as mock_put, \
         mock.patch("requests.get") as mock_get:

        # Step 1: 申请上传 URL
        mock_post.return_value.json.return_value = {
            "code": 0,
            "msg": "ok",
            "data": {
                "batch_id": "batch-001",
                "file_urls": ["https://oss-mineru.example.com/upload/abc"],
            },
        }
        mock_post.return_value.status_code = 200

        # Step 2: PUT 上传 (无返回值需要)
        mock_put.return_value.status_code = 200

        # Step 3 + 4: 轮询返回 done + 下载 zip (GET 被两次调用)
        mock_get.return_value.json.return_value = {
            "code": 0,
            "msg": "ok",
            "data": {
                "batch_id": "batch-001",
                "extract_result": [{
                    "file_name": "test.pdf",
                    "state": "done",
                    "full_zip_url": "https://cdn-mineru.example.com/result.zip",
                }],
            },
        }
        mock_get.return_value.status_code = 200
        mock_get.return_value.content = zip_bytes

        parser = MinerUParser(api_key="sk-test-token", model_version="vlm")
        result = parser.parse(pdf_file, "test.pdf", "application/pdf")

    # 验证结果
    assert result.metadata["parser"] == "mineru"
    assert result.metadata["model_version"] == "vlm"
    assert "第一章 概述" in result.text
    assert "背景介绍" in result.text
    # sections 从标题提取 (保留完整标题含编号)
    sections = result.pages[0].sections
    assert any("概述" in s for s in sections)
    assert any("背景介绍" in s for s in sections)
    assert any("数据结构" in s for s in sections)
    # 表格提取
    assert len(result.tables) >= 1
    table_md = result.tables[0].markdown
    assert "字段" in table_md
    assert "类型" in table_md


def test_mineru_parser_polling_retry(pdf_file):
    """测试轮询重试: 前两次 running，第三次 done"""
    from src.rag.parsing.mineru_parser import MinerUParser

    zip_bytes = _make_mineru_zip("# Test Doc\n\nContent.")

    call_count = [0]

    def mock_get_response(url, **kwargs):
        call_count[0] += 1
        resp = mock.MagicMock()
        resp.status_code = 200
        if "/extract-results/batch/" in url:
            if call_count[0] <= 2:
                resp.json.return_value = {
                    "code": 0,
                    "data": {
                        "batch_id": "batch-002",
                        "extract_result": [{
                            "file_name": "test.pdf",
                            "state": "running",
                        }],
                    },
                }
            else:
                resp.json.return_value = {
                    "code": 0,
                    "data": {
                        "batch_id": "batch-002",
                        "extract_result": [{
                            "file_name": "test.pdf",
                            "state": "done",
                            "full_zip_url": "https://cdn-mineru.example.com/result.zip",
                        }],
                    },
                }
        else:
            resp.content = zip_bytes
        return resp

    with mock.patch("requests.post") as mock_post, \
         mock.patch("requests.put") as mock_put, \
         mock.patch("requests.get", side_effect=mock_get_response):

        mock_post.return_value.json.return_value = {
            "code": 0,
            "data": {
                "batch_id": "batch-002",
                "file_urls": ["https://oss-mineru.example.com/upload/def"],
            },
        }
        mock_post.return_value.status_code = 200
        mock_put.return_value.status_code = 200

        parser = MinerUParser(api_key="sk-test-token", model_version="pipeline")
        result = parser.parse(pdf_file, "test.pdf", "application/pdf")

    assert "Test Doc" in result.text
    assert result.metadata["model_version"] == "pipeline"


def test_mineru_parser_failure_fallback_to_pypdf(pdf_file):
    """MinerU 失败时应降级到 pypdf"""
    from src.rag.parsing.mineru_parser import MinerUParser

    with mock.patch("requests.post") as mock_post:
        mock_post.side_effect = Exception("MinerU API 不可用")

        parser = MinerUParser(api_key="sk-test-token", model_version="vlm")
        result = parser.parse(pdf_file, "test.pdf", "application/pdf")

    # 应降级到 pypdf
    assert result.metadata["parser"] == "pypdf"
    assert result.metadata["total_pages"] >= 1


def test_mineru_no_api_key_fallback_to_pypdf(pdf_file):
    """未配置 API Key 时直接使用 pypdf"""
    from src.rag.parsing.mineru_parser import MinerUParser

    parser = MinerUParser(api_key="")  # 无 API Key
    result = parser.parse(pdf_file, "test.pdf", "application/pdf")

    assert result.metadata["parser"] == "pypdf"


def test_mineru_zip_extraction():
    """测试从 MinerU zip 包中提取 full.md"""
    from src.rag.parsing.mineru_parser import MinerUParser

    parser = MinerUParser(api_key="dummy")
    zip_bytes = _make_mineru_zip("# Extracted Content\n\nBody text.")

    result = parser._download_and_extract_md.__wrapped__(
        parser, "https://fake-cdn.example.com/result.zip"
    ) if hasattr(parser._download_and_extract_md, "__wrapped__") else None

    # 直接测试 — 使用 mock 模拟 HTTP GET
    with mock.patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.content = zip_bytes

        md_text = parser._download_and_extract_md(
            "https://fake-cdn.example.com/result.zip"
        )

    assert "# Extracted Content" in md_text
    assert "Body text." in md_text


def test_mineru_markdown_to_parsed_document():
    """测试 Markdown → ParsedDocument 转换"""
    from src.rag.parsing.mineru_parser import MinerUParser
    from src.rag.parsing.base import ParsedDocument

    parser = MinerUParser(api_key="dummy")
    result = parser._markdown_to_parsed_document(
        MINERU_MARKDOWN, "test.pdf",
    )

    assert isinstance(result, ParsedDocument)
    assert result.metadata["parser"] == "mineru"
    assert result.metadata["filename"] == "test.pdf"
    # 标题层级 (保留完整标题含编号)
    sections = result.pages[0].sections
    assert any("概述" in s for s in sections)
    assert any("背景介绍" in s for s in sections)
    assert any("数据结构" in s for s in sections)
    # 表格
    assert len(result.tables) >= 1
    assert "字段" in result.tables[0].markdown


# ═══════════════════════════════════════════════════════════════
# MinerUAgentParser — v1 Agent 轻量解析 Mock 测试
# ═══════════════════════════════════════════════════════════════

AGENT_MARKDOWN = """# 快速解析测试

## 简介

Agent 轻量解析 API 输出纯 Markdown，无 zip 包装。

## 数据

| 项 | 值 |
|----|-----|
| A | 100 |
| B | 200 |
"""


def test_agent_parser_full_flow(pdf_file):
    """模拟 Agent API: 申请上传→PUT 文件→轮询→下载 markdown"""
    from src.rag.parsing.mineru_agent_parser import MinerUAgentParser

    with mock.patch("requests.post") as mock_post, \
         mock.patch("requests.put") as mock_put, \
         mock.patch("requests.get") as mock_get:

        # Step 1: POST /parse/file → task_id + file_url
        mock_post.return_value.json.return_value = {
            "code": 0,
            "msg": "ok",
            "data": {
                "task_id": "task-agent-001",
                "file_url": "https://oss-mineru.example.com/agent/upload",
            },
        }
        mock_post.return_value.status_code = 200

        # Step 2: PUT file
        mock_put.return_value.status_code = 200

        # Step 3 + 4: poll → done + download markdown
        mock_get.return_value.json.return_value = {
            "code": 0,
            "data": {
                "task_id": "task-agent-001",
                "state": "done",
                "markdown_url": "https://cdn-mineru.example.com/full.md",
            },
        }
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = AGENT_MARKDOWN

        parser = MinerUAgentParser(language="ch")
        result = parser.parse(pdf_file, "test.pdf", "application/pdf")

    assert result.metadata["parser"] == "mineru-agent"
    assert "快速解析测试" in result.text
    assert "Agent 轻量解析" in result.text
    # sections
    sections = result.pages[0].sections
    assert any("简介" in s for s in sections)
    assert any("数据" in s for s in sections)
    # tables
    assert len(result.tables) == 1
    assert "项" in result.tables[0].markdown


def test_agent_parser_polling_retry(pdf_file):
    """Agent 轮询: 前两次 running，第三次 done"""
    from src.rag.parsing.mineru_agent_parser import MinerUAgentParser

    call_count = [0]

    def mock_get_response(url, **kwargs):
        call_count[0] += 1
        resp = mock.MagicMock()
        resp.status_code = 200
        if "/parse/" in url and call_count[0] <= 2:
            resp.json.return_value = {
                "code": 0,
                "data": {
                    "task_id": "task-002",
                    "state": "running",
                },
            }
        else:
            resp.json.return_value = {
                "code": 0,
                "data": {
                    "task_id": "task-002",
                    "state": "done",
                    "markdown_url": "https://cdn.example.com/md",
                },
            }
            resp.text = "# Done\n\nContent."
        return resp

    with mock.patch("requests.post") as mock_post, \
         mock.patch("requests.put") as mock_put, \
         mock.patch("requests.get", side_effect=mock_get_response):

        mock_post.return_value.json.return_value = {
            "code": 0,
            "data": {
                "task_id": "task-002",
                "file_url": "https://oss.example.com/upload",
            },
        }
        mock_post.return_value.status_code = 200
        mock_put.return_value.status_code = 200

        parser = MinerUAgentParser()
        result = parser.parse(pdf_file, "test.pdf", "application/pdf")

    assert "Done" in result.text


def test_agent_parser_failure_fallback_to_pypdf(pdf_file):
    """Agent API 失败时应降级到 pypdf"""
    from src.rag.parsing.mineru_agent_parser import MinerUAgentParser

    with mock.patch("requests.post") as mock_post:
        mock_post.side_effect = Exception("Agent API 不可用")

        parser = MinerUAgentParser()
        result = parser.parse(pdf_file, "test.pdf", "application/pdf")

    assert result.metadata["parser"] == "pypdf"


def test_agent_parser_failed_state(pdf_file):
    """Agent API 返回 state=failed 时应抛出并降级到 pypdf"""
    from src.rag.parsing.mineru_agent_parser import MinerUAgentParser

    with mock.patch("requests.post") as mock_post, \
         mock.patch("requests.put") as mock_put, \
         mock.patch("requests.get") as mock_get:

        mock_post.return_value.json.return_value = {
            "code": 0,
            "data": {
                "task_id": "task-fail",
                "file_url": "https://oss.example.com/upload",
            },
        }
        mock_post.return_value.status_code = 200
        mock_put.return_value.status_code = 200

        mock_get.return_value.json.return_value = {
            "code": 0,
            "data": {
                "task_id": "task-fail",
                "state": "failed",
                "err_code": -30003,
                "err_msg": "文件页数超出轻量接口限制",
            },
        }
        mock_get.return_value.status_code = 200

        parser = MinerUAgentParser()
        result = parser.parse(pdf_file, "test.pdf", "application/pdf")

    # 应降级
    assert result.metadata["parser"] == "pypdf"


def test_agent_parser_supported_mimes():
    """Agent Parser 支持的文件类型"""
    from src.rag.parsing.mineru_agent_parser import MinerUAgentParser
    parser = MinerUAgentParser()
    mimes = parser.supported_mime_types
    assert "application/pdf" in mimes
    assert "image/png" in mimes
    assert "image/jpeg" in mimes
