"""BailianEmbedding — 阿里云百炼平台 Embedding API

支持两种调用模式:
  1. OpenAI 兼容: 简单，支持 dimensions，适用于纯文本向量化
  2. DashScope 原生: 全功能，支持 text_type, instruct, 多模态

文本模型:
  - qwen3.7-text-embedding       最新最強, 201语种, batch=20, instruct+稀疏向量
  - text-embedding-v4            推荐主力, 100+语种, batch=10, query/document区分
  - text-embedding-v3/v2/v1      旧版

多模态模型 (DashScope 原生):
  - qwen3-vl-embedding           融合+独立, 图文视频
  - tongyi-embedding-vision-plus   独立向量
  - tongyi-embedding-vision-flash  成本优先

文档: https://help.aliyun.com/zh/model-studio/embedding-rerank-model

配置:
  BAILIAN_API_KEY         — API Key (必填)
  BAILIAN_WORKSPACE_ID    — 业务空间ID (推荐; 不填使用旧版兼容域名)
  BAILIAN_REGION          — cn-beijing | ap-southeast-1 (默认 cn-beijing)
  EMBEDDING_MODEL         — 模型名 (默认 text-embedding-v4)
  EMBEDDING_DIMENSION     — 向量维度 (默认由模型决定)
  EMBEDDING_API_MODE      — openai_compatible | dashscope (默认 openai_compatible)
"""

import os
import asyncio
import logging

import requests

from .base import EmbeddingResult

logger = logging.getLogger("server.embedding.bailian")

# ═══════════════════════════════════════════════════════════════
# 通用常量
# ═══════════════════════════════════════════════════════════════

# 旧版兼容域名 (无需 WorkspaceId)
LEGACY_BASE_URL = "https://dashscope.aliyuncs.com"

# OpenAI 兼容端点模板 (需要 WorkspaceId)
REGION_OPENAI_TEMPLATE = (
    "https://{workspace_id}.{region}.maas.aliyuncs.com/compatible-mode/v1"
)
# DashScope 原生端点模板 (需要 WorkspaceId)
REGION_DASHSCOPE_TEMPLATE = (
    "https://{workspace_id}.{region}.maas.aliyuncs.com/api/v1"
)

DEFAULT_REGION = "cn-beijing"

# ═══════════════════════════════════════════════════════════════
# 模型信息表
# ═══════════════════════════════════════════════════════════════

# (默认维度, 可选维度列表, 批次大小, 单文本最大token)
_MODEL_SPEC = {
    "qwen3.7-text-embedding": {
        "default_dim": 1024,
        "dims": [2560, 2048, 1536, 1024, 768, 512, 256],
        "batch": 20,
        "max_tokens": 128000,
    },
    "text-embedding-v4": {
        "default_dim": 1024,
        "dims": [2048, 1536, 1024, 768, 512, 256, 128, 64],
        "batch": 10,
        "max_tokens": 33000,
    },
    "text-embedding-v3": {
        "default_dim": 1024,
        "dims": [1024, 768, 512, 256, 128, 64],
        "batch": 10,
        "max_tokens": 8192,
    },
    "text-embedding-v2": {
        "default_dim": 1536,
        "dims": [1536],
        "batch": 25,
        "max_tokens": 2048,
    },
    "text-embedding-v1": {
        "default_dim": 1536,
        "dims": [1536],
        "batch": 25,
        "max_tokens": 2048,
    },
}

# 支持 text_type 参数的模型 (DashScope 原生接口)
_TEXT_TYPE_MODELS = {
    "text-embedding-v4", "text-embedding-v3", "qwen3.7-text-embedding",
}

# 支持 instruct 参数的模型 (DashScope 原生接口, 需配合 text_type=query)
_INSTRUCT_MODELS = {"text-embedding-v4", "qwen3.7-text-embedding"}

# 多模态模型 — 需调用独立的多模态 API
_MULTIMODAL_MODELS = {
    "qwen3-vl-embedding",
    "qwen2.5-vl-embedding",
    "tongyi-embedding-vision-plus-2026-03-06",
    "tongyi-embedding-vision-flash-2026-03-06",
    "tongyi-embedding-vision-plus",
    "tongyi-embedding-vision-flash",
    "multimodal-embedding-v1",
}


class BailianEmbedding:
    """阿里云百炼 Embedding 服务。

    支持文本向量化 + 多模态向量化。
    默认使用 OpenAI 兼容接口；配置高级参数 (text_type, instruct) 时
    自动切换到 DashScope 原生接口以获得最佳效果。

    使用方式:
        # 最简单
        emb = BailianEmbedding(api_key="sk-xxx")
        results = await emb.embed(["文本1", "文本2"])

        # 查询侧优化 (提升 RAG 召回)
        results = await emb.embed_query(["用户问题"])

        # 指定维度 + 文档类型
        emb = BailianEmbedding(
            api_key="sk-xxx",
            model="text-embedding-v4",
            dimension=1024,
            text_type="document",       # 文档=被匹配侧
        )
    """

    def __init__(
        self,
        api_key: str = "",
        model: str = "",
        dimension: int | None = None,
        text_type: str = "",
        instruct: str = "",
        workspace_id: str = "",
        region: str = "",
        api_mode: str = "",
        base_url: str = "",
    ):
        # ── 认证 ──
        self._api_key = api_key or os.getenv("BAILIAN_API_KEY", "")
        if not self._api_key:
            logger.warning("BAILIAN_API_KEY 未配置，调用 embed() 将抛异常")

        # ── 模型 ──
        self._model = model or os.getenv("EMBEDDING_MODEL", "text-embedding-v4")
        self._is_multimodal = self._model in _MULTIMODAL_MODELS

        # ── 模型规格 ──
        spec = _MODEL_SPEC.get(self._model, _MODEL_SPEC["text-embedding-v4"])
        self._default_dim = spec["default_dim"]
        self._allowed_dims = spec["dims"]
        self._batch_size = spec["batch"]

        # ── 向量维度 ──
        if dimension is not None:
            self._dimension = dimension
        elif os.getenv("EMBEDDING_DIMENSION"):
            self._dimension = int(os.getenv("EMBEDDING_DIMENSION"))
        else:
            self._dimension: int | None = None  # 使用模型默认

        # 验证维度
        if self._dimension is not None and self._dimension not in self._allowed_dims:
            logger.warning(
                "维度 %d 不在模型 %s 的可选范围 %s 中，API 可能拒绝",
                self._dimension, self._model, self._allowed_dims,
            )

        # ── 高级参数 (仅 DashScope 原生模式) ──
        self._text_type = text_type or os.getenv("EMBEDDING_TEXT_TYPE", "")
        self._instruct = instruct or os.getenv("EMBEDDING_INSTRUCT", "")

        # ── 地域/端点 ──
        self._workspace_id = workspace_id or os.getenv("BAILIAN_WORKSPACE_ID", "")
        self._region = region or os.getenv("BAILIAN_REGION", DEFAULT_REGION)
        self._api_mode = api_mode or os.getenv("EMBEDDING_API_MODE", "openai_compatible")
        self._base_url = base_url  # 最高优先级

        # 构建实际端点 URL
        self._openai_url = self._build_openai_url()
        self._dashscope_url = self._build_dashscope_url()

        # ── 运行时缓存 ──
        self._detected_dimension: int | None = None  # 首次 API 调用后回填

    # ------------------------------------------------------------------
    # URL 构建
    # ------------------------------------------------------------------

    def _build_openai_url(self) -> str:
        """构建 OpenAI 兼容端点。"""
        if self._base_url:
            return self._base_url.rstrip("/")
        if self._workspace_id:
            return REGION_OPENAI_TEMPLATE.format(
                workspace_id=self._workspace_id, region=self._region,
            )
        return f"{LEGACY_BASE_URL}/compatible-mode/v1"

    def _build_dashscope_url(self) -> str:
        """构建 DashScope 原生端点。"""
        if self._workspace_id:
            return REGION_DASHSCOPE_TEMPLATE.format(
                workspace_id=self._workspace_id, region=self._region,
            )
        return f"{LEGACY_BASE_URL}/api/v1"

    # ------------------------------------------------------------------
    # EmbeddingService 协议属性
    # ------------------------------------------------------------------

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        """实际向量维度。

        优先级: 用户指定 > API 检测值 > 模型默认值
        首次调用 embed() 前返回的是预期值；调用后返回 API 实际值。
        """
        if self._detected_dimension is not None:
            return self._detected_dimension
        if self._dimension is not None:
            return self._dimension
        return self._default_dim

    # ------------------------------------------------------------------
    # 公开接口: 文档向量化 (text_type=document)
    # ------------------------------------------------------------------

    async def embed(self, texts: list[str]) -> list[EmbeddingResult]:
        """批量文本向量化 — 文档侧 (text_type=document)。

        用于知识库文档入库。超过模型批次限制自动分批。

        Raises:
            RuntimeError: 未配置 API Key
        """
        if not texts:
            return []
        if not self._api_key:
            raise RuntimeError("未配置 BAILIAN_API_KEY")

        all_results: list[EmbeddingResult] = []

        for batch_start in range(0, len(texts), self._batch_size):
            batch = texts[batch_start:batch_start + self._batch_size]
            batch_results = await asyncio.to_thread(self._call_api, batch)
            # 调整 index 对应原始列表位置
            for r in batch_results:
                r.index += batch_start
            all_results.extend(batch_results)

        return all_results

    async def embed_single(self, text: str) -> EmbeddingResult:
        """单条文本向量化"""
        results = await self.embed([text])
        return results[0]

    # ------------------------------------------------------------------
    # 公开接口: 查询向量化 (text_type=query)
    # ------------------------------------------------------------------

    async def embed_query(
        self,
        texts: list[str],
        instruct: str = "",
    ) -> list[EmbeddingResult]:
        """查询文本向量化 — 自动设置 text_type=query 以获得最佳检索效果。

        与 embed() 的区别:
          - embed():  text_type=document → 向量偏向"被匹配"语义
          - embed_query(): text_type=query → 向量偏向"提问/查找"语义

        使用场景:
          RAG 检索中，用户 query 应使用本方法以提升召回质量。
          文档入库仍使用 embed()。

        Args:
            texts: 查询文本列表
            instruct: 任务指令 (如 "Given a query, retrieve relevant documents")
                      仅 text-embedding-v4 / qwen3.7-text-embedding 支持
        """
        if not texts:
            return []
        if not self._api_key:
            raise RuntimeError("未配置 BAILIAN_API_KEY")

        # 切换为查询模式
        old_text_type = self._text_type
        old_instruct = self._instruct
        self._text_type = "query"
        if instruct:
            self._instruct = instruct
        try:
            return await self.embed(texts)
        finally:
            self._text_type = old_text_type
            self._instruct = old_instruct

    # ------------------------------------------------------------------
    # 核心: API 调用 (模式自适应)
    # ------------------------------------------------------------------

    def _call_api(self, batch: list[str]) -> list[EmbeddingResult]:
        """根据配置选择 OpenAI 兼容接口或 DashScope 原生接口。

        选择策略:
          - 配置了 text_type / instruct → DashScope 原生 (OpenAI 兼容不支持)
          - 其他情况 → OpenAI 兼容 (更简洁, 兼容性更好)
        """
        use_dashscope = (
            self._api_mode == "dashscope"
            or bool(self._text_type)
            or bool(self._instruct)
        )
        if use_dashscope:
            return self._call_dashscope_text(batch)
        return self._call_openai(batch)

    # ------------------------------------------------------------------
    # OpenAI 兼容模式
    # ------------------------------------------------------------------

    def _call_openai(self, texts: list[str]) -> list[EmbeddingResult]:
        """OpenAI 兼容接口。

        POST /compatible-mode/v1/embeddings
        {
          "model": "text-embedding-v4",
          "input": ["text1", "text2", ...],
          "dimensions": 1024          // 可选
        }

        响应:
        {
          "object": "list",
          "data": [
            {"object": "embedding", "index": 0, "embedding": [0.1, 0.2, ...]},
            ...
          ],
          "model": "text-embedding-v4",
          "usage": {"total_tokens": 42}
        }
        """
        url = f"{self._openai_url}/embeddings"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

        payload: dict = {
            "model": self._model,
            "input": texts,
        }
        if self._dimension is not None:
            payload["dimensions"] = self._dimension

        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        # 错误检测
        if "error" in data:
            err = data["error"]
            raise RuntimeError(
                f"百炼 OpenAI 兼容 API 错误: "
                f"code={err.get('code')}, message={err.get('message', err)}"
            )

        embeddings = data.get("data", [])

        # 首次调用后缓存实际维度
        self._detect_and_log(embeddings, "openai")

        tokens = data.get("usage", {}).get("total_tokens", 0)
        per_token = tokens // len(embeddings) if embeddings else 0

        return [
            EmbeddingResult(
                index=item["index"],
                text=texts[item["index"]] if item["index"] < len(texts) else "",
                vector=item["embedding"],
                tokens=per_token,
            )
            for item in embeddings
        ]

    # ------------------------------------------------------------------
    # DashScope 原生模式 — 文本
    # ------------------------------------------------------------------

    def _call_dashscope_text(self, texts: list[str]) -> list[EmbeddingResult]:
        """DashScope 原生文本 Embedding 接口。

        POST /api/v1/services/embeddings/text-embedding/text-embedding
        {
          "model": "text-embedding-v4",
          "input": {
            "texts": ["text1", "text2", ...]
          },
          "parameters": {
            "dimension": 1024,
            "text_type": "query",         // 可选: query | document
            "instruct": "...",            // 可选: 任务指令
            "output_type": "dense"        // 可选: dense | sparse | dense&sparse
          }
        }

        响应:
        {
          "output": {
            "embeddings": [
              {"text_index": 0, "embedding": [0.1, 0.2, ...]},
              ...
            ]
          },
          "usage": {"total_tokens": 42},
          "request_id": "..."
        }
        """
        url = (
            f"{self._dashscope_url}"
            f"/services/embeddings/text-embedding/text-embedding"
        )
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

        # 构建 parameters
        parameters: dict = {}
        if self._dimension is not None:
            parameters["dimension"] = self._dimension
        if self._text_type and self._model in _TEXT_TYPE_MODELS:
            parameters["text_type"] = self._text_type
        if self._instruct and self._model in _INSTRUCT_MODELS:
            parameters["instruct"] = self._instruct
            # instruct 要求 text_type 必须为 query
            if parameters.get("text_type") != "query":
                parameters["text_type"] = "query"

        payload: dict = {
            "model": self._model,
            "input": {"texts": texts},
        }
        if parameters:
            payload["parameters"] = parameters

        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        # DashScope 错误格式: {"code": "...", "message": "..."}
        if data.get("code"):
            raise RuntimeError(
                f"百炼 DashScope API 错误: "
                f"code={data.get('code')}, message={data.get('message', 'unknown')}"
            )

        output = data.get("output", {})
        embeddings = output.get("embeddings", [])

        # 缓存实际维度
        self._detect_and_log(embeddings, "dashscope")

        tokens = data.get("usage", {}).get("total_tokens", 0)
        per_token = tokens // len(embeddings) if embeddings else 0

        results: list[EmbeddingResult] = []
        for item in embeddings:
            # DashScope 用 text_index 标识输入位置
            idx = item.get("text_index", item.get("index", 0))
            results.append(EmbeddingResult(
                index=idx,
                text=texts[idx] if idx < len(texts) else "",
                vector=item.get("embedding", []),
                tokens=per_token,
            ))
        return results

    # ------------------------------------------------------------------
    # 多模态 (可选功能)
    # ------------------------------------------------------------------

    async def embed_multimodal(
        self,
        contents: list[dict],
        model: str = "",
        enable_fusion: bool = False,
    ) -> list[EmbeddingResult]:
        """多模态向量化 — 文本/图片/视频混合。

        POST /api/v1/services/embeddings/multimodal-embedding/multimodal-embedding

        Args:
            contents: 内容列表，每项为 {"text": "..."} / {"image": "url"} / {"video": "url"}
            model: 多模态模型 (默认 qwen3-vl-embedding)
            enable_fusion: True=融合为一个向量, False=每项独立向量

        Returns:
            EmbeddingResult 列表
        """
        if not self._api_key:
            raise RuntimeError("未配置 BAILIAN_API_KEY")
        if not contents:
            return []

        mm_model = model or "qwen3-vl-embedding"

        results = await asyncio.to_thread(
            self._call_multimodal, contents, mm_model, enable_fusion,
        )
        return results

    def _call_multimodal(
        self,
        contents: list[dict],
        model: str,
        enable_fusion: bool,
    ) -> list[EmbeddingResult]:
        """多模态底层调用。"""
        url = (
            f"{self._dashscope_url}"
            f"/services/embeddings/multimodal-embedding/multimodal-embedding"
        )
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

        parameters: dict = {}
        if enable_fusion:
            parameters["enable_fusion"] = True
        if self._dimension is not None:
            parameters["dimension"] = self._dimension

        payload: dict = {
            "model": model,
            "input": {"contents": contents},
        }
        if parameters:
            payload["parameters"] = parameters

        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code"):
            raise RuntimeError(
                f"百炼多模态 API 错误: "
                f"code={data.get('code')}, message={data.get('message', 'unknown')}"
            )

        output = data.get("output", {})
        embeddings = output.get("embeddings", [])
        tokens = data.get("usage", {}).get("total_tokens", 0)
        per_token = tokens // len(embeddings) if embeddings else 0

        return [
            EmbeddingResult(
                index=item.get("index", i),
                text=str(item.get("type", "multimodal")),
                vector=item.get("embedding", []),
                tokens=per_token,
            )
            for i, item in enumerate(embeddings)
        ]

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _detect_and_log(self, embeddings: list[dict], mode: str) -> None:
        """首次调用时从响应中检测并缓存实际向量维度。"""
        if self._detected_dimension is not None:
            return
        if not embeddings:
            return
        first_vec = embeddings[0].get("embedding", [])
        if first_vec:
            self._detected_dimension = len(first_vec)
            logger.info(
                "百炼 Embedding 就绪: model=%s, dim=%s, mode=%s, endpoint=%s",
                self._model,
                self._detected_dimension,
                mode,
                self._openai_url if mode == "openai" else self._dashscope_url,
            )
