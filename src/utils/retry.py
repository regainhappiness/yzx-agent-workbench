"""
===========================================================================
重试机制 — 基于 tenacity 库
===========================================================================

封装 tenacity 的指数退避 + 随机抖动 + 不可重试异常过滤。

特性:
  - 指数退避 (multiplier × 2^attempt)
  - 自动随机抖动 (tenacity 内置 jitter)
  - 自动跳过不可重试的异常 (认证失败、配额超限、类型错误等)
  - 支持装饰器和手动调用两种方式
  - 每次重试前自动输出警告日志

使用:
    from utils.retry import with_retry, retry_call

    # 方式1: 装饰器
    @with_retry(max_retries=3, base_delay=1.0)
    def my_func():
        ...

    # 方式2: 手动调用
    result = retry_call(lambda: some_api_call(), max_retries=3)
===========================================================================
"""
from typing import Callable, Any

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
    Retrying,
    AsyncRetrying,
    RetryCallState,
)

from ..utils.logger import get_logger

logger = get_logger(__name__)

# ══════════════════════════════════════════════════════════════════
# 默认配置
# ══════════════════════════════════════════════════════════════════
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0       # 秒
DEFAULT_MAX_DELAY = 60.0        # 秒

# 不可重试的错误关键字 (检查异常消息)
FATAL_KEYWORDS = (
    "invalid api key",
    "authentication",
    "unauthorized",
    "not found",
    "insufficient",
    "quota exceeded",
    "billing",
)

# 不可重试的异常类型 (直接拒绝)
NON_RETRYABLE_TYPES = (
    ValueError,
    TypeError,
    AttributeError,
    ImportError,
    KeyboardInterrupt,
    SystemExit,
)


# ══════════════════════════════════════════════════════════════════
# 重试判断
# ══════════════════════════════════════════════════════════════════
def _is_retryable(exception: BaseException) -> bool:
    """判断异常是否可重试

    - 显式不可重试的类型直接拒绝
    - 异常消息包含致命关键字时拒绝
    - 其他情况允许重试
    """
    # 类型级别的拒绝
    if isinstance(exception, NON_RETRYABLE_TYPES):
        return False

    # 消息级别的拒绝 (如认证失败、配额超限等)
    msg = str(exception).lower()
    for kw in FATAL_KEYWORDS:
        if kw in msg:
            logger.error(f"❌ 不可重试的错误 ({kw}): {exception}")
            return False

    return True


# ══════════════════════════════════════════════════════════════════
# 重试前回调 (日志)
# ══════════════════════════════════════════════════════════════════
def _before_sleep(retry_state: RetryCallState) -> None:
    """tenacity 重试前的日志回调"""
    exception = retry_state.outcome.exception()
    attempt = retry_state.attempt_number
    # stop_after_attempt 的 max_attempt_number 是总次数
    total = retry_state.retry_object.stop.max_attempt_number  # type: ignore[union-attr]
    delay = retry_state.next_action.sleep if retry_state.next_action else 0

    logger.warning(
        f"⚠️ 第 {attempt}/{total} 次尝试失败: "
        f"{type(exception).__name__}: {exception} — {delay:.1f}s 后重试..."
    )


# ══════════════════════════════════════════════════════════════════
# 装饰器
# ══════════════════════════════════════════════════════════════════
def with_retry(
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
):
    """重试装饰器 — 自动在失败时重试 (基于 tenacity)

    参数:
        max_retries: 最大重试次数 (不含首次尝试，总共 max_retries+1 次)
        base_delay:  基础延迟 (秒)，实际延迟 = base × 2^attempt + jitter
        max_delay:   最大延迟上限 (秒)

    使用:
        @with_retry(max_retries=3, base_delay=1.0)
        def call_api():
            ...

        @with_retry(max_retries=5, base_delay=2.0, max_delay=30.0)
        def unstable_operation():
            ...
    """
    return retry(
        stop=stop_after_attempt(max_retries + 1),
        wait=wait_exponential(multiplier=base_delay, max=max_delay),
        retry=retry_if_exception(_is_retryable),
        before_sleep=_before_sleep,
        reraise=True,
    )


# ══════════════════════════════════════════════════════════════════
# 函数式接口
# ══════════════════════════════════════════════════════════════════
def retry_call(
    func: Callable,
    *args: Any,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    **kwargs: Any,
) -> Any:
    """手动调用带重试的函数 (基于 tenacity.Retrying)

    参数:
        func:        要调用的函数
        *args:       传递给 func 的位置参数
        max_retries: 最大重试次数 (不含首次，总共 max_retries+1 次)
        base_delay:  基础延迟 (秒)
        max_delay:   最大延迟上限 (秒)
        **kwargs:    传递给 func 的关键字参数

    返回:
        func 的返回值

    使用:
        # 无参函数
        result = retry_call(lambda: model.invoke(messages), max_retries=3)

        # 带参函数
        result = retry_call(api_call, arg1, arg2, max_retries=5, base_delay=2.0)

        # 关键字参数传递给目标函数
        result = retry_call(api_call, param1=val1, max_retries=3)
    """
    total_attempts = max_retries + 1
    retryer = Retrying(
        stop=stop_after_attempt(total_attempts),
        wait=wait_exponential(multiplier=base_delay, max=max_delay),
        retry=retry_if_exception(_is_retryable),
        before_sleep=_before_sleep,
        reraise=True,
    )
    try:
        return retryer(func, *args, **kwargs)
    except Exception:
        logger.error(f"❌ 重试 {total_attempts} 次后仍然失败")
        raise


# ══════════════════════════════════════════════════════════════════
# 异步函数式接口
# ══════════════════════════════════════════════════════════════════
async def async_retry_call(
    func: Callable,
    *args: Any,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    **kwargs: Any,
) -> Any:
    """手动调用带重试的异步函数 (基于 tenacity.AsyncRetrying)

    参数:
        func:        要调用的函数 (支持 sync 或 async callable)
        *args:       传递给 func 的位置参数
        max_retries: 最大重试次数 (不含首次，总共 max_retries+1 次)
        base_delay:  基础延迟 (秒)
        max_delay:   最大延迟上限 (秒)
        **kwargs:    传递给 func 的关键字参数

    返回:
        func 的返回值 (await 得到)

    使用:
        # 异步函数
        result = await async_retry_call(
            lambda: graph.ainvoke({"messages": msgs}, config),
            max_retries=3,
        )

        # 同步函数在异步上下文中重试
        result = await async_retry_call(
            lambda: some_sync_api_call(),
            max_retries=3,
        )
    """
    total_attempts = max_retries + 1
    retryer = AsyncRetrying(
        stop=stop_after_attempt(total_attempts),
        wait=wait_exponential(multiplier=base_delay, max=max_delay),
        retry=retry_if_exception(_is_retryable),
        before_sleep=_before_sleep,
        reraise=True,
    )
    try:
        return await retryer(func, *args, **kwargs)
    except Exception:
        logger.error(f"❌ 重试 {total_attempts} 次后仍然失败")
        raise
