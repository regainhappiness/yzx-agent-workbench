"""Embedding 服务协议定义"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class EmbeddingResult:
    """单条 Embedding 结果"""
    index: int          # 输入文本在批次中的序号
    text: str           # 原始文本 (用于校验)
    vector: list[float] # Embedding 向量
    tokens: int = 0     # Token 消耗


class EmbeddingService(Protocol):
    """文本向量化服务协议。

    实现方:
      - BailianEmbedding:  阿里云百炼平台 API
      - OpenAIEmbedding:   OpenAI 兼容 API (预留)
      - LocalEmbedding:    本地 BGE 模型 (预留)
    """

    @property
    def model_name(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    async def embed(self, texts: list[str]) -> list[EmbeddingResult]:
        """批量文本向量化。每批最多 25 条（百炼限制）。"""
        ...

    async def embed_single(self, text: str) -> EmbeddingResult:
        """单条文本向量化"""
        ...
