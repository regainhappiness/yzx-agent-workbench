"""MinerUParser — PDF 解析，通过 MinerU API 调用

MinerU API 是异步的，调用流程:
  1. POST /api/v4/file-urls/batch  → 获取 batch_id + 文件上传 URL
  2. PUT  文件到返回的预签名 URL      → 上传完成后 MinerU 自动提交解析
  3. 轮询 GET /api/v4/extract-results/batch/{batch_id} → 获取解析结果
  4. 下载 full_zip_url 对应的 zip 包 → 解压提取 full.md
  5. Markdown → ParsedDocument     → 结构化为内部数据模型

降级策略: MinerU 调用失败时，自动降级到 pypdf 做基础文本提取。
"""

import os
import io
import time
import zipfile
import logging

import requests

from .base import ParsedDocument, ParsedPage
from .markdown_parser import parse_markdown_text

logger = logging.getLogger("server.parser.mineru")

# MinerU 官方 API 地址
MINERU_BASE_URL = "https://mineru.net/api/v4"
# 轮询配置
POLL_TIMEOUT = 300        # 最长等待 5 分钟
POLL_INTERVAL = 3         # 每 3 秒轮询一次
# 下载超时
DOWNLOAD_TIMEOUT = 120    # zip 下载超时 2 分钟


class MinerUParser:
    """MinerU 文档解析器 — 通过 MinerU v4 精准解析 API。

    使用批量文件上传模式:
      - 先在 MinerU 申请上传链接
      - PUT 文件到 MinerU OSS
      - MinerU 自动解析
      - 轮询获取结果

    文件限制:
      - 大小 ≤ 200 MB
      - 页数 ≤ 200 页
      - 支持 PDF / 图片 / Doc / Docx / Ppt / PPTx / Xls / Xlsx
    """

    def __init__(
        self,
        api_url: str = "",
        api_key: str = "",
        model_version: str = "vlm",
        language: str = "ch",
    ):
        """
        Args:
            api_url: MinerU API 地址，默认官方地址
            api_key: MinerU API Token（API 管理页面创建）
            model_version: 模型版本 — pipeline / vlm (推荐) / MinerU-HTML
            language: 文档语言，默认 ch（中英文）
        """
        self._base_url = (api_url or MINERU_BASE_URL).rstrip("/")
        self._api_key = api_key or os.getenv("MINERU_API_KEY", "")
        self._model_version = model_version
        self._language = language

    # ------------------------------------------------------------------
    # Parser 协议
    # ------------------------------------------------------------------

    @property
    def supported_mime_types(self) -> list[str]:
        return ["application/pdf"]

    def parse(self, file_path: str, filename: str, mime: str) -> ParsedDocument:
        """解析 PDF 文件，返回 ParsedDocument。
        优先使用 MinerU，失败时降级到 pypdf。
        """
        if not self._api_key:
            logger.warning("未配置 MINERU_API_KEY，直接使用 pypdf 降级")
            return self._parse_with_pypdf(file_path)

        try:
            return self._parse_with_mineru(file_path, filename)
        except Exception as e:
            logger.warning("MinerU 解析失败，降级到 pypdf: %s", e)
            return self._parse_with_pypdf(file_path)

    # ------------------------------------------------------------------
    # MinerU 异步 API 调用
    # ------------------------------------------------------------------

    def _parse_with_mineru(self, file_path: str, filename: str) -> ParsedDocument:
        """完整的 MinerU 调用流程:
        Step 1: 申请批量上传 URL
        Step 2: PUT 文件到 MinerU OSS
        Step 3: 轮询获取解析结果
        Step 4: 下载 zip + 解压 markdown
        Step 5: 结构化 → ParsedDocument
        """
        logger.info("开始 MinerU 解析: file=%s, model=%s", filename, self._model_version)

        # Step 1: 申请上传 URL
        batch_id, file_url = self._request_upload_url(filename)
        logger.debug("获取上传 URL: batch_id=%s", batch_id)

        # Step 2: PUT 上传文件
        self._upload_file(file_url, file_path, filename)
        logger.debug("文件已上传到 MinerU: %s", filename)

        # Step 3: 轮询结果
        full_zip_url = self._poll_batch_result(batch_id, filename)
        logger.debug("MinerU 解析完成: zip_url=%s", full_zip_url)

        # Step 4: 下载并解压
        markdown_text = self._download_and_extract_md(full_zip_url)

        # Step 5: 结构化
        return self._markdown_to_parsed_document(markdown_text, filename)

    def _request_upload_url(self, filename: str) -> tuple[str, str]:
        """Step 1: 调用 MinerU 批量上传接口，获取 batch_id 和文件上传 URL。

        POST /api/v4/file-urls/batch

        Returns:
            (batch_id, file_url)
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        payload = {
            "files": [
                {"name": filename}
            ],
            "model_version": self._model_version,
            "language": self._language,
        }

        url = f"{self._base_url}/file-urls/batch"
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(
                f"MinerU 申请上传 URL 失败: code={data.get('code')}, "
                f"msg={data.get('msg')}"
            )

        batch_id = data["data"]["batch_id"]
        file_url = data["data"]["file_urls"][0]
        return batch_id, file_url

    def _upload_file(self, upload_url: str, file_path: str, filename: str):
        """Step 2: PUT 文件到 MinerU 返回的预签名 OSS URL。

        PUT 方法，Body 为文件二进制数据，无需设置 Content-Type。
        """
        with open(file_path, "rb") as f:
            resp = requests.put(upload_url, data=f, timeout=300)

        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"文件上传到 MinerU 失败: HTTP {resp.status_code}, "
                f"file={filename}"
            )

    def _poll_batch_result(self, batch_id: str, filename: str) -> str:
        """Step 3: 轮询批量解析结果，直到全部完成或超时。

        GET /api/v4/extract-results/batch/{batch_id}

        Returns:
            解析完成的 full_zip_url
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        url = f"{self._base_url}/extract-results/batch/{batch_id}"

        start_time = time.time()
        state_labels = {
            "waiting-file": "等待文件上传",
            "pending": "排队中",
            "running": "解析中",
            "converting": "格式转换中",
        }

        while time.time() - start_time < POLL_TIMEOUT:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 0:
                raise RuntimeError(
                    f"MinerU 查询结果失败: code={data.get('code')}, "
                    f"msg={data.get('msg')}"
                )

            results = data.get("data", {}).get("extract_result", [])
            if not results:
                elapsed = int(time.time() - start_time)
                logger.debug("[%ds] 结果尚未就绪，继续等待...", elapsed)
                time.sleep(POLL_INTERVAL)
                continue

            # 找到当前文件的结果
            for r in results:
                if r.get("file_name") == filename:
                    state = r.get("state", "unknown")
                    elapsed = int(time.time() - start_time)

                    if state == "done":
                        full_zip_url = r.get("full_zip_url", "")
                        if not full_zip_url:
                            raise RuntimeError("MinerU 返回 done 但没有 full_zip_url")
                        logger.info("[%ds] MinerU 解析完成: %s", elapsed, filename)
                        return full_zip_url

                    if state == "failed":
                        err_msg = r.get("err_msg", "未知错误")
                        raise RuntimeError(
                            f"MinerU 解析失败: file={filename}, err={err_msg}"
                        )

                    label = state_labels.get(state, state)
                    logger.info("[%ds] MinerU 状态: %s", elapsed, label)

            time.sleep(POLL_INTERVAL)

        raise TimeoutError(
            f"MinerU 解析超时 ({POLL_TIMEOUT}s): batch_id={batch_id}, "
            f"file={filename}"
        )

    # ------------------------------------------------------------------
    # Zip 下载 & Markdown 提取
    # ------------------------------------------------------------------

    def _download_and_extract_md(self, full_zip_url: str) -> str:
        """Step 4: 下载 MinerU 结果 zip，解压提取 full.md。

        MinerU zip 包内容 (非 HTML 文件):
          - full.md          — 完整 Markdown 解析结果 ← 我们需要的
          - layout.json      — 中间处理结果 (middle.json)
          - *_model.json     — 模型推理结果 (model.json)
          - *_content_list.json — 内容列表 (content_list.json)

        Returns:
            full.md 的文本内容
        """
        logger.debug("下载 MinerU 结果 zip: %s", full_zip_url)

        resp = requests.get(full_zip_url, timeout=DOWNLOAD_TIMEOUT)
        resp.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            # 查找 full.md
            for name in zf.namelist():
                if name.endswith("full.md") or name == "full.md":
                    content = zf.read(name).decode("utf-8")
                    logger.debug("提取 full.md: %s (%d chars)", name, len(content))
                    return content

            # 没找到 full.md，列出所有文件方便调试
            available = zf.namelist()
            raise RuntimeError(
                f"MinerU zip 中未找到 full.md，可用文件: {available}"
            )

    # ------------------------------------------------------------------
    # Markdown → ParsedDocument 结构化 (复用 MarkdownParser 的解析逻辑)
    # ------------------------------------------------------------------

    def _markdown_to_parsed_document(
        self, markdown_text: str, filename: str
    ) -> ParsedDocument:
        """Step 5: 将 MinerU 输出的 Markdown 转为 ParsedDocument。

        直接委托给 markdown_parser.parse_markdown_text()，
        避免重复的标题/表格提取逻辑。

        MinerU 输出的 Markdown 是连续文本（不含页码信息），
        因此 ParsedDocument 只有一个 ParsedPage。
        如需精确页码信息，可后续解析 zip 中的 content_list.json。
        """
        return parse_markdown_text(
            markdown_text,
            parser="mineru",
            model_version=self._model_version,
            language=self._language,
            filename=filename,
        )

    # ------------------------------------------------------------------
    # pypdf 降级 (委托给共享模块函数)
    # ------------------------------------------------------------------

    def _parse_with_pypdf(self, file_path: str) -> ParsedDocument:
        return parse_pdf_with_pypdf(file_path)


# ═══════════════════════════════════════════════════════════════
# 共享工具函数 — MinerUParser / MinerUAgentParser 均可使用
# ═══════════════════════════════════════════════════════════════

def parse_pdf_with_pypdf(file_path: str) -> ParsedDocument:
    """pypdf 降级方案: 按页提取纯文本。

    MinerU 不可用时（网络故障/未配置/API 报错）的兜底方案。
    无法获取结构化标题和表格，但保留页码信息。

    MinerUParser 和 MinerUAgentParser 共享此函数。
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError(
            "MinerU 不可用且 pypdf 未安装，无法解析 PDF。"
            "请安装: pip install pypdf"
        )

    reader = PdfReader(file_path)
    pages = []
    full_text_parts = []

    for i, page in enumerate(reader.pages):
        page_text = page.extract_text() or ""
        full_text_parts.append(page_text)
        pages.append(ParsedPage(
            page_number=i + 1,
            text=page_text,
        ))

    return ParsedDocument(
        text="\n\n".join(full_text_parts),
        pages=pages,
        metadata={
            "parser": "pypdf",
            "total_pages": len(reader.pages),
        },
    )
