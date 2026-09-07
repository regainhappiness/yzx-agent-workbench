"""MinerUAgentParser — PDF 解析，通过 MinerU Agent 轻量解析 API (v1)

与 MinerUParser (v4 精准解析) 的对比:
  |                      | v4 精准解析          | v1 Agent 轻量解析 (本类) |
  |----------------------|---------------------|--------------------------|
  | Token                | ✅ 需要              | ❌ 免登录 (IP 限频)       |
  | 文件大小              | ≤200MB              | ≤10MB                    |
  | 页数                  | ≤200 页             | ≤20 页                   |
  | 模型                  | vlm / pipeline 可选 | 固定 pipeline 轻量模型    |
  | 输出                  | zip (Markdown+JSON) | CDN Markdown 链接        |
  | 批量                  | ✅                  | ❌ 单文件                 |

调用流程:
  1. POST /api/v1/agent/parse/file  → 获取 task_id + OSS 上传 URL
  2. PUT  文件到 OSS 上传 URL        → 上传完成后自动解析
  3. 轮询 GET /api/v1/agent/parse/{task_id} → 获取 markdown_url
  4. 下载 markdown → parse_markdown_text() → ParsedDocument

降级策略: API 调用失败时降级到 pypdf。
"""

import os
import time
import logging

import requests

from .base import ParsedDocument
from .markdown_parser import parse_markdown_text
from .mineru_parser import parse_pdf_with_pypdf

logger = logging.getLogger("server.parser.mineru_agent")

# Agent 轻量解析 API 基础地址
AGENT_BASE_URL = "https://mineru.net/api/v1/agent"
# 轮询配置
POLL_TIMEOUT = 300
POLL_INTERVAL = 3
# CDN 下载超时
DOWNLOAD_TIMEOUT = 60

# Agent API 支持的文件类型
AGENT_SUPPORTED_MIMES = [
    "application/pdf",
    "image/png", "image/jpeg", "image/jpg", "image/jp2",
    "image/webp", "image/gif", "image/bmp",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # .pptx
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
]


class MinerUAgentParser:
    """MinerU v1 Agent 轻量解析器 — 免 Token，适合 AI Agent 工作流。

    优势:
      - 无需注册/Token，开箱即用
      - 接口简单，快速集成

    限制:
      - 文件 ≤10MB, ≤20页
      - 仅输出 Markdown
      - IP 限频 (每分钟请求数有限制)
      - 固定 pipeline 轻量模型

    适用场景:
      - 快速原型验证
      - 小文件/短文档解析
      - 无 MinerU 账号时的降级方案
    """

    def __init__(
        self,
        api_url: str = "",
        language: str = "ch",
        enable_table: bool = True,
        enable_formula: bool = True,
        is_ocr: bool = False,
    ):
        """
        Args:
            api_url: Agent API 地址，默认官方地址
            language: 文档语言，默认 ch（中英文）
            enable_table: 是否开启表格识别，默认 True (仅 PDF)
            enable_formula: 是否开启公式识别，默认 True (仅 PDF)
            is_ocr: 是否开启 OCR，默认 False (仅 PDF)
        """
        self._base_url = (api_url or AGENT_BASE_URL).rstrip("/")
        self._language = language
        self._enable_table = enable_table
        self._enable_formula = enable_formula
        self._is_ocr = is_ocr

    # ------------------------------------------------------------------
    # Parser 协议
    # ------------------------------------------------------------------

    @property
    def supported_mime_types(self) -> list[str]:
        """Agent API 支持的文件类型比 v4 少（不含 .doc/.ppt/.xls 旧格式）"""
        return AGENT_SUPPORTED_MIMES

    def parse(self, file_path: str, filename: str, mime: str) -> ParsedDocument:
        """解析文件，返回 ParsedDocument。
        优先使用 MinerU Agent API，失败时降级到 pypdf。
        """
        try:
            return self._parse_with_agent_api(file_path, filename)
        except Exception as e:
            logger.warning("Agent API 解析失败，降级到 pypdf: %s", e)
            return parse_pdf_with_pypdf(file_path)

    # ------------------------------------------------------------------
    # Agent API 调用
    # ------------------------------------------------------------------

    def _parse_with_agent_api(
        self, file_path: str, filename: str
    ) -> ParsedDocument:
        """完整的 Agent API 调用流程:
        Step 1: 获取签名上传 URL
        Step 2: PUT 文件到 MinerU OSS
        Step 3: 轮询获取解析结果
        Step 4: 下载 Markdown → 结构化
        """
        logger.info("开始 Agent 轻量解析: file=%s", filename)

        # Step 1: 申请上传 URL
        task_id, file_url = self._request_upload(filename)
        logger.debug("Agent 任务已创建: task_id=%s", task_id)

        # Step 2: PUT 上传文件
        self._upload_file(file_url, file_path, filename)
        logger.debug("文件已上传到 Agent OSS: %s", filename)

        # Step 3: 轮询结果
        markdown_url = self._poll_result(task_id)
        logger.debug("Agent 解析完成: markdown_url=%s", markdown_url)

        # Step 4: 下载 Markdown → 结构化
        markdown_text = self._download_markdown(markdown_url)
        return self._markdown_to_parsed_document(markdown_text, filename)

    def _request_upload(self, filename: str) -> tuple[str, str]:
        """Step 1: 调用 Agent API 获取签名上传 URL。

        POST /api/v1/agent/parse/file

        注意: 无需 Authorization 请求头。
        """
        payload: dict = {
            "file_name": filename,
            "language": self._language,
            "enable_table": self._enable_table,
            "is_ocr": self._is_ocr,
            "enable_formula": self._enable_formula,
        }

        url = f"{self._base_url}/parse/file"
        resp = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(
                f"Agent API 获取上传 URL 失败: code={data.get('code')}, "
                f"msg={data.get('msg')}"
            )

        task_id = data["data"]["task_id"]
        file_url = data["data"]["file_url"]
        return task_id, file_url

    def _upload_file(self, upload_url: str, file_path: str, filename: str):
        """Step 2: PUT 文件到 MinerU 返回的 OSS 签名 URL。

        PUT 方法，Body 为文件二进制数据。
        """
        with open(file_path, "rb") as f:
            resp = requests.put(upload_url, data=f, timeout=300)

        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"Agent 文件上传失败: HTTP {resp.status_code}, file={filename}"
            )

    def _poll_result(self, task_id: str) -> str:
        """Step 3: 轮询解析结果，直到完成或超时。

        GET /api/v1/agent/parse/{task_id}

        Returns:
            解析完成的 markdown_url (CDN 链接)
        """
        url = f"{self._base_url}/parse/{task_id}"

        start_time = time.time()
        state_labels = {
            "waiting-file": "等待文件上传",
            "uploading": "文件下载中",
            "pending": "排队中",
            "running": "解析中",
        }

        while time.time() - start_time < POLL_TIMEOUT:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 0:
                raise RuntimeError(
                    f"Agent API 查询结果失败: code={data.get('code')}, "
                    f"msg={data.get('msg')}"
                )

            task_data = data.get("data", {})
            state = task_data.get("state", "unknown")
            elapsed = int(time.time() - start_time)

            if state == "done":
                markdown_url = task_data.get("markdown_url", "")
                if not markdown_url:
                    raise RuntimeError("Agent API 返回 done 但没有 markdown_url")
                logger.info("[%ds] Agent 解析完成", elapsed)
                return markdown_url

            if state == "failed":
                err_msg = task_data.get("err_msg", "未知错误")
                err_code = task_data.get("err_code", "")
                raise RuntimeError(
                    f"Agent API 解析失败: err_code={err_code}, err_msg={err_msg}"
                )

            label = state_labels.get(state, state)
            logger.info("[%ds] Agent 状态: %s", elapsed, label)
            time.sleep(POLL_INTERVAL)

        raise TimeoutError(
            f"Agent API 解析超时 ({POLL_TIMEOUT}s): task_id={task_id}"
        )

    def _download_markdown(self, markdown_url: str) -> str:
        """Step 4: 从 CDN 下载 Markdown 结果文本。"""
        logger.debug("下载 Agent Markdown 结果: %s", markdown_url)
        resp = requests.get(markdown_url, timeout=DOWNLOAD_TIMEOUT)
        resp.raise_for_status()
        return resp.text

    # ------------------------------------------------------------------
    # Markdown → ParsedDocument (复用 markdown_parser)
    # ------------------------------------------------------------------

    def _markdown_to_parsed_document(
        self, markdown_text: str, filename: str
    ) -> ParsedDocument:
        """将 MinerU Agent 输出的 Markdown 转为 ParsedDocument。

        委托给 markdown_parser.parse_markdown_text()。
        """
        return parse_markdown_text(
            markdown_text,
            parser="mineru-agent",
            language=self._language,
            filename=filename,
        )
