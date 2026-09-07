"""Embedding 服务 — 协议 + 百炼实现"""
from .base import EmbeddingService, EmbeddingResult
from .bailian import BailianEmbedding

__all__ = ["EmbeddingService", "EmbeddingResult", "BailianEmbedding"]
