"""
===========================================================================
Token 计数回调 — 统计 LLM 调用的 Token 消耗
===========================================================================

基于 LangChain BaseCallbackHandler，在每次 LLM 调用结束后自动统计:
  - 输入 token 数
  - 输出 token 数
  - 总 token 数
  - 调用次数
  - 每次调用的明细

支持多种 token 信息格式:
  - llm_output.token_usage (OpenAI / DeepSeek)
  - usage_metadata (LangChain 新版 API)
  - response_metadata.token_usage (备用)

使用:
    from callbacks import TokenCounterCallback

    counter = TokenCounterCallback()

    # 方式1: 传给模型
    model = ChatOpenAI(callbacks=[counter])

    # 方式2: 传给 LangGraph invoke/config
    graph.invoke({"messages": [...]}, {"callbacks": [counter]})

    # 查询统计
    print(counter.summary())        # 📊 Token 统计: ...
    print(counter.input_tokens)     # 输入 token 总数
    print(counter.total_tokens)     # 总 token 数
===========================================================================
"""
from typing import Any
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

from ..utils.logger import get_logger

logger = get_logger(__name__)


class TokenCounterCallback(BaseCallbackHandler):
    """LLM Token 消耗计数器

    自动识别多种 token 信息格式:
      - llm_output["token_usage"] → OpenAI-style API (DeepSeek 兼容)
      - usage_metadata                        → LangChain 新版标准
      - response_metadata["token_usage"]      → 备用路径

    特性:
      - 累加所有 LLM 调用的 token
      - 记录每次调用明细
      - 支持 reset() 重置
      - 线程安全 (使用简单累加，无锁)
    """

    def __init__(self, verbose: bool = False):
        """
        参数:
            verbose: 是否在每次 LLM 调用后打印 token 消耗
        """
        super().__init__()
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.total_tokens: int = 0
        self.call_count: int = 0
        self.verbose = verbose

        # 每次调用的明细
        self._call_details: list[dict] = []

    # ═══ 核心回调 ═══
    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """LLM 调用完成后自动触发，提取 token 使用信息"""
        inp, out, total = self._extract_tokens(response)

        self.input_tokens += inp
        self.output_tokens += out
        self.total_tokens += total
        self.call_count += 1

        detail = {
            "call": self.call_count,
            "input": inp,
            "output": out,
            "total": total,
        }
        self._call_details.append(detail)

        if self.verbose:
            logger.info(
                f"🔢 Token: 输入={inp} 输出={out} 总计={total} "
                f"(第 {self.call_count} 次调用)"
            )

    # ═══ Token 提取逻辑 ═══
    @staticmethod
    def _extract_tokens(response: LLMResult) -> tuple[int, int, int]:
        """从 LLMResult 中提取 (input_tokens, output_tokens, total_tokens)

        按优先级依次尝试多种格式:
          1. llm_output["token_usage"]        — OpenAI/DeepSeek API
          2. generations[].usage_metadata      — LangChain 新版标准
          3. generations[].response_metadata   — 备用
        """
        inp = out = total = 0

        # 路径1: llm_output.token_usage (OpenAI / DeepSeek API 标准格式)
        llm_output = getattr(response, "llm_output", None) or {}
        usage = llm_output.get("token_usage", {})
        if usage:
            inp = usage.get("prompt_tokens", 0)
            out = usage.get("completion_tokens", 0)
            total = usage.get("total_tokens", 0)
            if total > 0:
                return inp, out, total

        # 路径2: usage_metadata (LangChain v0.3+ 统一接口)
        generations = getattr(response, "generations", None)
        if generations:
            for gen_list in generations:
                for gen in gen_list:
                    usage_meta = getattr(gen, "usage_metadata", None) or {}
                    if usage_meta:
                        inp += usage_meta.get("input_tokens", 0)
                        out += usage_meta.get("output_tokens", 0)
                        total += usage_meta.get("total_tokens", 0)
            if total > 0:
                return inp, out, total

        # 路径3: response_metadata.token_usage (备用)
        if generations:
            for gen_list in generations:
                for gen in gen_list:
                    resp_meta = getattr(gen, "response_metadata", None) or {}
                    usage = resp_meta.get("token_usage", {})
                    if usage:
                        inp += usage.get("prompt_tokens", 0)
                        out += usage.get("completion_tokens", 0)
                        total += usage.get("total_tokens", 0)

        # 如果所有路径都提取不到，保持 0（某些本地模型不返回 token 信息）
        return inp, out, total

    # ═══ 查询接口 ═══
    @property
    def last_call_tokens(self) -> dict:
        """最近一次 LLM 调用的 token 明细"""
        if self._call_details:
            return self._call_details[-1]
        return {"call": 0, "input": 0, "output": 0, "total": 0}

    @property
    def avg_input_tokens(self) -> float:
        """平均每次调用的输入 token 数"""
        if self.call_count == 0:
            return 0.0
        return self.input_tokens / self.call_count

    @property
    def avg_output_tokens(self) -> float:
        """平均每次调用的输出 token 数"""
        if self.call_count == 0:
            return 0.0
        return self.output_tokens / self.call_count

    def summary(self) -> str:
        """格式化的 token 统计摘要"""
        if self.call_count == 0:
            return "📊 Token 统计: 暂无 LLM 调用"

        return (
            f"📊 Token 统计: "
            f"LLM 调用 {self.call_count} 次 | "
            f"输入 {self.input_tokens} | "
            f"输出 {self.output_tokens} | "
            f"总计 {self.total_tokens} | "
            f"均入 {self.avg_input_tokens:.0f} | "
            f"均出 {self.avg_output_tokens:.0f}"
        )

    def to_dict(self) -> dict:
        """导出为字典"""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "call_count": self.call_count,
            "avg_input_tokens": round(self.avg_input_tokens, 1),
            "avg_output_tokens": round(self.avg_output_tokens, 1),
            "call_details": list(self._call_details),
        }

    # ═══ 维护 ═══
    def reset(self):
        """重置所有计数"""
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.call_count = 0
        self._call_details.clear()
        logger.info("🔄 Token 计数已重置")

    def __repr__(self) -> str:
        return (
            f"TokenCounterCallback(calls={self.call_count}, "
            f"input={self.input_tokens}, output={self.output_tokens}, "
            f"total={self.total_tokens})"
        )
