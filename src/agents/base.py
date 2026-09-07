"""
===========================================================================
Agent 基类 — 纯基础设施，不约定执行接口
===========================================================================

BaseAgent 只提供:
  - 生命周期管理 (_setup / initialize)
  - 线程隔离 (thread_id)
  - 日志 (self.logger)
  - 会话重置 (reset / areset)

子类自行定义执行接口:
  - ChatAgent:  chat() / chat_stream()
  - AsyncAgent: achat() / achat_stream()
  - 自定义:    run() / invoke() / 任意方法名

使用:
    from agents import BaseAgent

    class MyAgent(BaseAgent):
        def _setup(self):
            self.model = get_model()
            self._checkpointer = MemorySaver()
            self._store = InMemoryStore()

        # 子类自行定义执行方法，签名和返回类型完全自由
        def chat(self, user_input: str, thread_id: str = None) -> str:
            ...
            return response

        async def achat(self, user_input: str, thread_id: str = None) -> str:
            ...
            return response
===========================================================================
"""

import uuid
from abc import ABC, abstractmethod

from ..utils.logger import get_logger


class BaseAgent(ABC):
    """Agent 抽象基类 — 只管理基础设施，不定义执行接口

    要求子类:
      1. 实现 _setup() — 初始化模型/工具/存储等
      2. 自行定义执行方法 (签名自由)

    提供:
      - thread_id 会话隔离
      - 延迟初始化 (initialize)
      - 同步/异步 reset
      - 统一日志
    """

    def __init__(self, name: str = "BaseAgent", **kwargs):
        """
        参数:
            name: Agent 名称 (用于日志和标识)
            **kwargs: 传递给 _setup() 的配置参数
        """
        self.name = name
        self.logger = get_logger(f"Agent.{name}")

        # 初始化状态
        self._initialized = False
        self._setup_kwargs = kwargs

        # 子类在 _setup() 中设置这些属性
        self.model = None
        self.tools = None

        # 线程 ID (默认自动生成，可被子类或用户覆盖)
        self._thread_id: str = kwargs.get("thread_id") or str(uuid.uuid4())[:8]

    # ═══ 生命周期 ═══
    def initialize(self):
        """初始化 Agent (延迟初始化，可在创建后配置再调用)"""
        if self._initialized:
            return
        self.logger.info(f"🔧 初始化 Agent...")
        self._setup(**self._setup_kwargs)
        self._initialized = True
        self.logger.info(f"✅ Agent 就绪")

    async def ainitialize(self):
        """异步初始化（默认等价于同步 initialize；子类可为异步 store 覆盖）。"""
        if self._initialized:
            return
        self.initialize()

    async def aclose(self):
        """异步关闭（默认等价于同步 close，若子类实现了 close）。"""
        close = getattr(self, "close", None)
        if callable(close):
            close()

    @abstractmethod
    def _setup(self, **kwargs):
        """初始化 Agent 组件 (子类实现)

        典型实现:
            self.model = get_model()
            self._checkpointer = MemorySaver()
            self._store = InMemoryStore()
            self.tools = ToolRegistry()
        """
        ...

    # ═══ 会话管理 ═══
    def reset(self):
        """重置会话状态 — 生成新的 thread_id"""
        old_tid = self._thread_id
        self._thread_id = str(uuid.uuid4())[:8]
        self.logger.info(f"🔄 会话已重置 (旧 thread_id={old_tid})")

    async def areset(self):
        """重置会话状态 (异步)"""
        self.reset()

    # ═══ 信息 ═══
    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def thread_id(self) -> str:
        """当前默认线程 ID (用于会话隔离)"""
        return self._thread_id

    def __repr__(self) -> str:
        status = "✅" if self._initialized else "🔧"
        return f"{self.name}({status}, thread_id={self._thread_id})"
