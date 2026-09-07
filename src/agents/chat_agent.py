"""
===========================================================================
ChatAgent — 基于 LangGraph ReAct 的通用对话 Agent
===========================================================================

特性:
  - 自动集成工具调用 (ReAct 循环)
  - 使用 LangGraph Checkpointer 管理短期记忆 (会话对话历史)
  - 使用 LangGraph Store 管理长期记忆 (跨会话信息)
  - 通过 thread_id 实现会话隔离
  - 支持流式输出 (stream=True)
  - 防死循环保护 (max_steps)
  - 优雅降级 (无 API Key 时可用模拟模式)

记忆架构:
  ┌─────────────────────────────────────────────────┐
  │  短期记忆 (Checkpointer)                          │
  │  - 对话历史，按 thread_id 隔离                    │
  │  - MemorySaver / SqliteSaver / PostgresSaver       │
  ├─────────────────────────────────────────────────┤
  │  长期记忆 (Store)                                 │
  │  - 跨会话的用户偏好、事实、知识                     │
  │  - InMemoryStore / SqliteStore / PostgresStore      │
  └─────────────────────────────────────────────────┘

使用:
    from agents import ChatAgent

    # 默认: 内存存储 (MemorySaver + InMemoryStore)
    agent = ChatAgent()
    agent.chat("你好")

    # 通过 thread_id 实现会话隔离
    agent.chat("你好，我叫小明", thread_id="user-001")
    agent.chat("我叫什么名字？", thread_id="user-001")  # 会记住

    # SQLite 持久化存储
    agent = ChatAgent(
        store_type="sqlite",
        sqlite_path="./data/chat_agent.db",
    )

    # PostgreSQL 持久化存储
    agent = ChatAgent(
        store_type="postgres",
        postgres_conn="postgresql://user:pass@localhost:5432/mydb",
    )

    # 流式输出
    for chunk in agent.chat_stream("讲个笑话"):
        print(chunk, end="", flush=True)
===========================================================================
"""

import asyncio
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from langchain_core.messages import (
    HumanMessage, AIMessage, AIMessageChunk, SystemMessage, BaseMessage
)

from .base import BaseAgent
from ..models import get_model, CAN_RUN
from ..tools import ToolRegistry, BUILTIN_TOOLS, BUILTIN_TOOLS_META
from ..callbacks import TokenCounterCallback
from ..utils.logger import get_logger
from ..utils.retry import retry_call

logger = get_logger(__name__)

# ══════════════════════════════════════════════════════════════════
# 默认系统提示词
# ══════════════════════════════════════════════════════════════════
DEFAULT_SYSTEM_PROMPT = """你是一个智能助手，可以:
1. 回答用户的各种问题
2. 使用工具 (获取时间等)
3. 记住对话历史，根据上下文提供更好的回答

请用简洁、准确的中文回答用户的问题。"""


# ══════════════════════════════════════════════════════════════════
# LangGraph State 定义
# ══════════════════════════════════════════════════════════════════
class AgentState(TypedDict):
    """Agent 的状态定义 (LangGraph 标准格式)"""
    messages: Annotated[list[BaseMessage], add_messages]  # 消息自动累加


# ══════════════════════════════════════════════════════════════════
# ChatAgent 实现
# ══════════════════════════════════════════════════════════════════
class ChatAgent(BaseAgent):
    """通用对话 Agent —— LangGraph ReAct 循环封装

    架构:
      User Input → Checkpointer(load state by thread_id) → ReAct Loop → Response
                        ↓
                   Checkpointer(save state) ← ← ← ← ← ← ← ← ← ← ┘

    使用方式:
        # 方式1: 默认配置 (内存存储, 自动 thread_id)
        agent = ChatAgent()
        agent.chat("你好")

        # 方式2: 指定 thread_id 做会话隔离
        agent = ChatAgent()
        agent.chat("你好，我叫小明", thread_id="alice")
        agent.chat("我叫什么？", thread_id="alice")        # 记得
        agent.chat("你好", thread_id="bob")                 # 独立会话

        # 方式3: SQLite 持久化
        agent = ChatAgent(
            store_type="sqlite",
            sqlite_path="./data/chat_agent.db",
        )

        # 方式4: PostgreSQL 持久化
        agent = ChatAgent(
            name="MyBot",
            store_type="postgres",
            postgres_conn="postgresql://user:pass@localhost:5432/mydb",
            provider="openai",
            temperature=0.7,
            system_prompt="你是一个客服助手...",
        )
    """

    def _setup(self, **kwargs):
        """初始化 ChatAgent 组件

        可配置参数 (通过 __init__ 的 **kwargs 传入):
            provider:           模型 Provider (auto/openai/deepseek/anthropic)
            model_name:         具体模型名
            temperature:        生成温度
            max_agent_steps:    Agent 最大推理步数
            system_prompt:      自定义系统提示
            stream:             默认使用流式输出
            load_builtin_tools: 是否加载内置工具
            custom_tools:       自定义工具列表

            --- 存储配置 (替代原来 memory_strategy / max_turns) ---
            store_type:         存储类型 ("memory" | "sqlite" | "postgres",
                                默认 "memory")
                                - "memory":  MemorySaver + InMemoryStore (进程内)
                                - "sqlite":  SqliteSaver + SqliteStore (本地持久化)
                                - "postgres": PostgresSaver + PostgresStore (持久化)
            sqlite_path:        SQLite 数据库文件路径
                                (默认 "./data/chat_agent.db")
            postgres_conn:      PostgreSQL 连接字符串 (store_type="postgres" 时必需)
            thread_id:          默认线程 ID (不指定则自动生成)

            --- 重试配置 ---
            max_retries:        最大重试次数 (默认 3，含首次共 4 次尝试)
            retry_base_delay:   重试基础延迟/秒 (默认 1.0，指数退避: 1→2→4→8...)
            retry_max_delay:    重试最大延迟/秒 (默认 30.0)

            --- Token 计数 ---
            verbose_tokens:     是否在每次 LLM 调用后打印 token 消耗 (默认 False)
        """
        # --- 1. 模型 ---
        provider = kwargs.get("provider", "auto")
        temperature = kwargs.get("temperature", 0.3)
        model_name = kwargs.get("model_name") or kwargs.get("model")
        model_options = {
            key: kwargs[key]
            for key in ("api_key", "base_url", "max_tokens")
            if kwargs.get(key) is not None
        }
        if model_name:
            model_options["model"] = model_name

        self.model = get_model(
            provider=provider,
            temperature=temperature,
            **model_options,
        )

        # --- 2. 工具 ---
        self.tool_registry = ToolRegistry()
        if kwargs.get("load_builtin_tools", True):
            self.tool_registry.register_with_meta(BUILTIN_TOOLS, BUILTIN_TOOLS_META)
        # 注册自定义工具
        custom_tools = kwargs.get("custom_tools", [])
        if custom_tools:
            self.tool_registry.register_many(custom_tools, category="custom")

        # --- 3. Token 计数 ---
        self._token_counter = TokenCounterCallback(
            verbose=kwargs.get("verbose_tokens", False)
        )

        # --- 4. 重试配置 ---
        self.max_retries = kwargs.get("max_retries", 3)
        self.retry_base_delay = kwargs.get("retry_base_delay", 1.0)
        self.retry_max_delay = kwargs.get("retry_max_delay", 30.0)

        # --- 5. 存储配置 (短期记忆 + 长期记忆) ---
        store_type = kwargs.get("store_type", "sqlite")
        self.system_prompt = kwargs.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
        self.store_type = store_type
        self.sqlite_path = None
        self._sqlite_connections: tuple[sqlite3.Connection, ...] = ()

        if store_type == "memory":
            self._checkpointer = MemorySaver()
            self._store = InMemoryStore()
            self.logger.info("📦 使用内存存储 (MemorySaver + InMemoryStore)")

        elif store_type == "sqlite":
            try:
                from langgraph.checkpoint.sqlite import SqliteSaver
                from langgraph.store.sqlite import SqliteStore
            except ImportError as e:
                raise ImportError(
                    "使用 SQLite 存储需要安装: "
                    "pip install 'langgraph-checkpoint-sqlite>=3.0.1'\n"
                    f"原始错误: {e}"
                ) from e

            sqlite_path = kwargs.get("sqlite_path", "./data/chat_agent.db")
            if not sqlite_path:
                raise ValueError("store_type='sqlite' 时 sqlite_path 不能为空")

            if str(sqlite_path) == ":memory:":
                conn_string = ":memory:"
            else:
                db_path = Path(sqlite_path).expanduser()
                db_path.parent.mkdir(parents=True, exist_ok=True)
                conn_string = str(db_path)

            checkpointer_conn = sqlite3.connect(
                conn_string,
                check_same_thread=False,
            )
            store_conn = None
            try:
                store_conn = sqlite3.connect(
                    conn_string,
                    check_same_thread=False,
                    isolation_level=None,
                )
                self._checkpointer = SqliteSaver(checkpointer_conn)
                self._checkpointer.setup()
                self._store = SqliteStore(store_conn)
                self._store.setup()
            except Exception:
                checkpointer_conn.close()
                if store_conn is not None:
                    store_conn.close()
                raise

            self.sqlite_path = conn_string
            self._sqlite_connections = (checkpointer_conn, store_conn)
            self.logger.info(
                f"🗃️ 使用 SQLite 持久化存储 "
                f"(SqliteSaver + SqliteStore): {conn_string}"
            )

        elif store_type == "postgres":
            try:
                from langgraph.checkpoint.postgres import PostgresSaver
                from langgraph.store.postgres import PostgresStore
            except ImportError as e:
                raise ImportError(
                    f"使用 PostgreSQL 存储需要安装: "
                    f"pip install langgraph-checkpoint-postgres langgraph-store-postgres\n"
                    f"原始错误: {e}"
                )

            conn_string = kwargs.get("postgres_conn")
            if not conn_string:
                raise ValueError(
                    "store_type='postgres' 需要提供 postgres_conn 参数，例如:\n"
                    "  postgres_conn='postgresql://user:pass@localhost:5432/mydb'"
                )

            self._checkpointer = PostgresSaver.from_conn_string(conn_string)
            self._checkpointer.setup()  # 自动创建检查点表
            self._store = PostgresStore.from_conn_string(conn_string)
            self._store.setup()  # 自动创建存储表
            self.logger.info("🐘 使用 PostgreSQL 持久化存储 (PostgresSaver + PostgresStore)")

        else:
            raise ValueError(
                f"不支持的 store_type: '{store_type}'，"
                "可选: memory / sqlite / postgres"
            )

        # --- 6. Agent 配置 ---
        self.max_agent_steps = kwargs.get("max_agent_steps", 10)
        self.stream = kwargs.get("stream", True)

        # --- 7. 构建 LangGraph ---
        self._graph = None
        if self.model:
            self._build_graph()

        self.logger.info(
            f"✅ ChatAgent 初始化: model={self.model}, "
            f"tools={self.tool_registry.tool_count}, "
            f"store_type={store_type}, thread_id={self._thread_id}"
        )

    def _build_graph(self):
        """构建 LangGraph ReAct 图 (含 Checkpointer + Store)"""
        tools = self.tool_registry.list_all()

        # 绑定工具到模型
        if tools:
            model_with_tools = self.model.bind_tools(tools)
        else:
            model_with_tools = self.model

        # 定义节点
        def agent_node(state: AgentState) -> dict:
            """Agent 思考节点: 调用 LLM 决定下一步"""
            messages = state["messages"]
            response = model_with_tools.invoke(messages)
            return {"messages": [response]}

        def tools_node(state: AgentState) -> dict:
            """工具执行节点: 执行 LLM 请求的工具调用"""
            # 使用 LangGraph 预置的 ToolNode
            tool_node = ToolNode(tools)
            return tool_node.invoke({"messages": state["messages"]})

        # 路由逻辑
        def should_continue(state: AgentState) -> str:
            """判断下一步: 继续调用工具 / 结束"""
            last_message = state["messages"][-1]
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                return "tools"
            return END

        # 构建图
        workflow = StateGraph(AgentState)
        workflow.add_node("agent", agent_node)
        workflow.add_node("tools", tools_node)

        workflow.set_entry_point("agent")
        workflow.add_conditional_edges(
            "agent", should_continue, {"tools": "tools", END: END}
        )
        workflow.add_edge("tools", "agent")  # 工具执行后回到 agent 继续思考

        # 编译图: 绑定 Checkpointer (短期记忆) + Store (长期记忆)
        self._graph = workflow.compile(
            checkpointer=self._checkpointer,
            store=self._store,
        )
        self.logger.info(
            f"🔨 LangGraph 图构建完成 "
            f"({len(tools)} 个工具, checkpointer + store)"
        )

    # ══════════════════════════════════════════════════════════════
    # 同步对话
    # ══════════════════════════════════════════════════════════════
    def chat(
        self, user_input: str, thread_id: str = None,
        extra_system_content: str | None = None,
    ) -> str:
        """与 Agent 对话 (同步)

        参数:
            user_input: 用户输入文本
            thread_id:  会话线程 ID (不指定则使用默认的 self._thread_id)
            extra_system_content: 按请求注入的额外系统上下文

        返回:
            Agent 的文本响应
        """
        if not self._initialized:
            self.initialize()
        self.logger.info(f"💬 收到: {user_input[:50]}...")
        response = self._execute(
            user_input, thread_id=thread_id,
            extra_system_content=extra_system_content,
        )
        self.logger.info(f"🤖 回复: {response[:50]}...")
        return response

    # ══════════════════════════════════════════════════════════════
    # 核心执行
    # ══════════════════════════════════════════════════════════════
    def _execute(
        self, user_input: str, thread_id: str = None,
        extra_system_content: str | None = None,
    ) -> str:
        """执行 Agent 核心逻辑

        参数:
            user_input: 用户输入文本
            thread_id:  会话线程 ID (不指定则使用默认的 self._thread_id)
            extra_system_content: 按请求注入的额外系统上下文
                (如知识库检索结果)，作为 SystemMessage 存储，不会
                出现在用户聊天记录中。

        返回:
            Agent 的文本响应

        会话隔离机制:
            - 首次使用某个 thread_id 调用时，自动注入 system_prompt
            - 后续使用相同 thread_id 调用时，Checkpointer 自动加载历史消息
            - 不同 thread_id 之间的会话完全隔离

        重试机制:
            自动在 API 错误、超时、连接错误时重试 (指数退避 + 随机抖动)
        """
        if not self.model:
            return self._fallback_response(user_input)

        tid = thread_id or self._thread_id

        # 检查是否是新会话
        config_for_check = {"configurable": {"thread_id": tid}}
        current_state = self._graph.get_state(config_for_check)

        if current_state and current_state.values:
            messages = [HumanMessage(content=user_input)]
        else:
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=user_input),
            ]
            self.logger.info(f"🆕 新会话: thread_id={tid}")

        # 按请求注入知识库上下文 (在 HumanMessage 之前，确保 LLM 先看到指令)
        if extra_system_content:
            messages.insert(-1, SystemMessage(content=extra_system_content))

        # 诊断: 确认存入 checkpointer 的消息结构
        self.logger.info(
            "_execute: thread_id=%s msg_count=%d types=%s",
            tid,
            len(messages),
            [type(m).__name__ for m in messages],
        )

        # 执行配置: thread_id + token 计数回调
        config = {
            "configurable": {"thread_id": tid},
            "callbacks": [self._token_counter],
            "recursion_limit": self.max_agent_steps * 2,
        }

        try:
            # 带重试的 LangGraph 调用 (指数退避 + 随机抖动)
            result = retry_call(
                lambda: self._graph.invoke({"messages": messages}, config),
                max_retries=self.max_retries,
                base_delay=self.retry_base_delay,
                max_delay=self.retry_max_delay,
            )

            # 提取最后一个 AI 消息作为回复
            for msg in reversed(result.get("messages", [])):
                if isinstance(msg, AIMessage) and msg.content:
                    return str(msg.content)

            return "抱歉，我没有生成有效的回复。"

        except Exception as e:
            self.logger.error(f"❌ Agent 执行错误 (重试 {self.max_retries + 1} 次后): {e}")
            return f"抱歉，处理请求时出错: {e}"

    def chat_stream(
        self, user_input: str, thread_id: str = None,
        extra_system_content: str | None = None,
    ):
        """流式对话 (生成器) — 逐 chunk 返回响应

        使用:
            for chunk in agent.chat_stream("你好"):
                print(chunk, end="", flush=True)

        参数:
            user_input: 用户输入文本
            thread_id:  会话线程 ID (不指定则使用默认的 self._thread_id)
            extra_system_content: 按请求注入的额外系统上下文
        """
        if not self._initialized:
            self.initialize()

        tid = thread_id or self._thread_id

        if not self.model:
            fallback = self._fallback_response(user_input)
            yield fallback
            return

        # 检查是否是新会话
        config_for_check = {"configurable": {"thread_id": tid}}
        current_state = self._graph.get_state(config_for_check)

        if current_state and current_state.values:
            messages = [HumanMessage(content=user_input)]
        else:
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=user_input),
            ]
            self.logger.info(f"🆕 新会话 (stream): thread_id={tid}")

        # 按请求注入知识库上下文
        if extra_system_content:
            messages.insert(-1, SystemMessage(content=extra_system_content))

        # 流式调用配置 (带 token 计数回调)
        config = {
            "configurable": {"thread_id": tid},
            "callbacks": [self._token_counter],
        }

        # 带重试的流式调用 (重试仅包裹 graph.stream() 创建，不缓冲)
        attempt = 0
        max_attempts = self.max_retries + 1
        last_error = None

        while attempt < max_attempts:
            try:
                full_response = ""
                for message_chunk, metadata in self._graph.stream(
                    {"messages": messages},
                    config,
                    stream_mode="messages",
                ):
                    if metadata.get("langgraph_node") != "agent":
                        continue
                    if not isinstance(message_chunk, AIMessageChunk):
                        continue

                    chunk = self._message_chunk_text(message_chunk.content)
                    if chunk:
                        full_response += chunk
                        yield chunk
                return  # 成功完成

            except Exception as e:
                last_error = e
                attempt += 1
                if attempt < max_attempts:
                    delay = min(
                        self.retry_base_delay * (2 ** (attempt - 1)),
                        self.retry_max_delay,
                    )
                    self.logger.warning(
                        f"⚠️ 流式调用第 {attempt}/{max_attempts} 次失败: "
                        f"{type(e).__name__}: {e} — {delay:.1f}s 后重试..."
                    )
                    time.sleep(delay)
                    # 如果已输出部分内容，先输出错误提示
                    if full_response:
                        yield f"\n[重试中...]"
                else:
                    self.logger.error(
                        f"❌ 流式输出错误 (重试 {self.max_retries + 1} 次后): {e}"
                    )
                    yield f"抱歉，处理请求时出错: {e}"
                    return

    # ══════════════════════════════════════════════════════════════
    # 长期记忆操作 (Store API)
    # ══════════════════════════════════════════════════════════════
    def save_memory(self, key: str, value: dict,
                    namespace: tuple = ("default",)) -> None:
        """保存长期记忆到 Store (跨会话持久化)

        参数:
            key:       记忆的键
            value:     记忆的值 (dict)
            namespace: 命名空间 (默认 ("default",))

        使用:
            agent.save_memory("user_pref", {"language": "zh", "theme": "dark"})
        """
        self._store.put(namespace, key, value)
        self.logger.info(f"💾 长期记忆已保存: ns={namespace}, key={key}")

    def get_memory(self, key: str, namespace: tuple = ("default",)) -> dict | None:
        """从 Store 获取长期记忆

        参数:
            key:       记忆的键
            namespace: 命名空间 (默认 ("default",))

        返回:
            记忆值 (dict)，不存在时返回 None

        使用:
            pref = agent.get_memory("user_pref")
        """
        item = self._store.get(namespace, key)
        if item:
            self.logger.info(f"📖 长期记忆已加载: ns={namespace}, key={key}")
            return item.value
        return None

    def delete_memory(self, key: str, namespace: tuple = ("default",)) -> None:
        """从 Store 删除长期记忆

        参数:
            key:       记忆的键
            namespace: 命名空间 (默认 ("default",))
        """
        self._store.delete(namespace, key)
        self.logger.info(f"🗑️ 长期记忆已删除: ns={namespace}, key={key}")

    def search_memory(self, query: str, namespace: tuple = ("default",),
                      limit: int = 10) -> list:
        """搜索长期记忆 (语义搜索)

        参数:
            query:     搜索查询
            namespace: 命名空间 (默认 ("default",))
            limit:     返回结果上限

        返回:
            匹配的记忆列表
        """
        results = self._store.search(namespace, query=query, limit=limit)
        return results

    # ══════════════════════════════════════════════════════════════
    # Token 统计
    # ══════════════════════════════════════════════════════════════
    def get_token_stats(self) -> dict:
        """获取 Token 消耗统计

        返回:
            {
                "input_tokens": int,
                "output_tokens": int,
                "total_tokens": int,
                "call_count": int,
                "avg_input_tokens": float,
                "avg_output_tokens": float,
                "last_call": dict | None,
                "summary": str,
            }

        使用:
            stats = agent.get_token_stats()
            print(stats["summary"])  # 📊 Token 统计: ...
        """
        tc = self._token_counter
        return {
            "input_tokens": tc.input_tokens,
            "output_tokens": tc.output_tokens,
            "total_tokens": tc.total_tokens,
            "call_count": tc.call_count,
            "avg_input_tokens": round(tc.avg_input_tokens, 1),
            "avg_output_tokens": round(tc.avg_output_tokens, 1),
            "last_call": tc.last_call_tokens,
            "summary": tc.summary(),
        }

    def reset_token_stats(self):
        """重置 Token 计数"""
        self._token_counter.reset()
        self.logger.info("🔄 Token 计数已重置")

    # ══════════════════════════════════════════════════════════════
    # 会话管理
    # ══════════════════════════════════════════════════════════════
    def reset(self, thread_id: str = None):
        """重置 Agent 会话状态

        参数:
            thread_id: 要重置的 thread_id (不指定则重置默认线程)

        注意:
            - MemorySaver: 旧状态仍在内存中但不再被引用
            - SqliteSaver / PostgresSaver: 通过 delete_thread() 清理
        """
        tid = thread_id or self._thread_id

        if self.store_type in {"sqlite", "postgres"}:
            backend_name = "SQLite" if self.store_type == "sqlite" else "Postgres"
            try:
                if hasattr(self._checkpointer, 'delete_thread'):
                    self._checkpointer.delete_thread(tid)
                self.logger.info(f"🔄 {backend_name} 会话已重置: thread_id={tid}")
            except Exception as e:
                self.logger.warning(f"⚠️ {backend_name} 会话重置失败: {e}")

        # 生成新的默认 thread_id
        if thread_id is None:
            old_tid = self._thread_id
            self._thread_id = str(uuid.uuid4())[:8]
            self.logger.info(f"🔄 会话已重置: {old_tid} → {self._thread_id}")
        else:
            self.logger.info(f"🔄 会话已重置: thread_id={tid}")

    # ══════════════════════════════════════════════════════════════
    # 信息查询
    # ══════════════════════════════════════════════════════════════
    def get_session_info(self, thread_id: str = None) -> dict:
        """获取会话信息

        返回:
            {
                "thread_id": str,
                "store_type": str,
                "sqlite_path": str,  # 仅 SQLite 存储时提供
                "message_count": int | None,
                "has_state": bool,
            }
        """
        tid = thread_id or self._thread_id
        config = {"configurable": {"thread_id": tid}}

        info = {
            "thread_id": tid,
            "store_type": self.store_type,
            "message_count": None,
            "has_state": False,
        }
        if self.store_type == "sqlite":
            info["sqlite_path"] = self.sqlite_path

        if self._graph:
            state = self._graph.get_state(config)
            if state and state.values:
                info["has_state"] = True
                messages = state.values.get("messages", [])
                info["message_count"] = len(messages)

        return info

    def get_session_summary(self, thread_id: str = None) -> str:
        """获取会话摘要 (对话历史概览)

        参数:
            thread_id: 会话 ID (不指定则用默认)

        返回:
            会话摘要文本
        """
        info = self.get_session_info(thread_id)

        if not info["has_state"]:
            return "暂无对话"

        # 从 checkpointer 获取消息
        tid = thread_id or self._thread_id
        config = {"configurable": {"thread_id": tid}}
        state = self._graph.get_state(config)

        messages = state.values.get("messages", [])
        parts = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                continue  # 跳过系统提示
            role = "👤" if isinstance(msg, HumanMessage) else "🤖"
            content = str(msg.content)[:80]
            parts.append(f"{role}: {content}")
        return "\n".join(parts)

    # ══════════════════════════════════════════════════════════════
    # 兼容属性 (用于 main.py 等外部代码)
    # ══════════════════════════════════════════════════════════════
    @property
    def memory(self):
        """兼容旧的 memory 属性 — 返回自身 (提供 get_summary 等方法)"""
        return self

    def get_summary(self) -> str:
        """兼容旧 MemoryManager.get_summary() 接口"""
        return self.get_session_summary()

    # ══════════════════════════════════════════════════════════════
    # 异步对话 (FastAPI 用)
    # ══════════════════════════════════════════════════════════════
    async def achat(
        self, user_input: str, thread_id: str = None,
        extra_system_content: str | None = None,
    ) -> str:
        """异步对话 — 内部调用 self._graph.ainvoke()

        参数:
            user_input: 用户输入文本
            thread_id:  会话线程 ID
            extra_system_content: 按请求注入的额外系统上下文

        返回:
            Agent 的文本响应
        """
        if not self._initialized:
            self.initialize()

        # 同步 SqliteSaver/SqliteStore 不实现 LangGraph 的异步接口。
        # 放到工作线程中执行同步图，避免阻塞 FastAPI 事件循环。
        if getattr(self, "store_type", "memory") == "sqlite":
            return await asyncio.to_thread(
                self._execute, user_input, thread_id, extra_system_content,
            )

        tid = thread_id or self._thread_id
        config_for_check = {"configurable": {"thread_id": tid}}
        current_state = self._graph.get_state(config_for_check)

        if current_state and current_state.values:
            messages = [HumanMessage(content=user_input)]
        else:
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=user_input),
            ]
            self.logger.info(f"🆕 新会话 (async): thread_id={tid}")

        if extra_system_content:
            messages.insert(-1, SystemMessage(content=extra_system_content))

        config = {
            "configurable": {"thread_id": tid},
            "callbacks": [self._token_counter],
            "recursion_limit": self.max_agent_steps * 2,
        }

        try:
            result = await self._graph.ainvoke({"messages": messages}, config)

            for msg in reversed(result.get("messages", [])):
                if isinstance(msg, AIMessage) and msg.content:
                    return str(msg.content)

            return "抱歉，我没有生成有效的回复。"

        except Exception as e:
            self.logger.error(f"❌ Agent 异步执行错误: {e}")
            return f"抱歉，处理请求时出错: {e}"

    async def achat_stream(
        self, user_input: str, thread_id: str = None,
        extra_system_content: str | None = None,
    ):
        """异步流式对话，逐模型消息块返回文本。

        使用:
            async for chunk in agent.achat_stream("你好"):
                print(chunk, end="", flush=True)

        参数:
            user_input: 用户输入文本
            thread_id:  会话线程 ID
            extra_system_content: 按请求注入的额外系统上下文
        """
        if not self._initialized:
            self.initialize()

        if getattr(self, "store_type", "memory") == "sqlite":
            stream = self.chat_stream(
                user_input, thread_id=thread_id,
                extra_system_content=extra_system_content,
            )
            while True:
                has_chunk, chunk = await asyncio.to_thread(
                    self._next_stream_chunk,
                    stream,
                )
                if not has_chunk:
                    return
                yield chunk

        tid = thread_id or self._thread_id

        if not self.model or not self._graph:
            yield self._fallback_response(user_input)
            return

        config_for_check = {"configurable": {"thread_id": tid}}
        current_state = self._graph.get_state(config_for_check)

        if current_state and current_state.values:
            messages = [HumanMessage(content=user_input)]
        else:
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=user_input),
            ]
            self.logger.info(f"🆕 新会话 (async stream): thread_id={tid}")

        if extra_system_content:
            messages.insert(-1, SystemMessage(content=extra_system_content))

        # 诊断: 确认存入 checkpointer 的消息结构
        self.logger.info(
            "achat_stream: thread_id=%s msg_count=%d types=%s",
            tid,
            len(messages),
            [type(m).__name__ for m in messages],
        )

        config = {
            "configurable": {"thread_id": tid},
            "callbacks": [self._token_counter],
            "recursion_limit": self.max_agent_steps * 2,
        }

        try:
            async for message_chunk, metadata in self._graph.astream(
                {"messages": messages},
                config,
                stream_mode="messages",
            ):
                if metadata.get("langgraph_node") != "agent":
                    continue
                if not isinstance(message_chunk, AIMessageChunk):
                    continue

                text = self._message_chunk_text(message_chunk.content)
                if text:
                    yield text

        except Exception as e:
            self.logger.error(f"❌ Agent 异步流式错误: {e}")
            yield f"抱歉，处理请求时出错: {e}"

    @staticmethod
    def _next_stream_chunk(stream) -> tuple[bool, str | None]:
        """从同步流中取一块，避免 StopIteration 跨越 Future 边界。"""
        try:
            return True, next(stream)
        except StopIteration:
            return False, None

    @staticmethod
    def _message_chunk_text(content) -> str:
        """从不同 Provider 的消息块结构中提取可展示文本。"""
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ""

        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)

    def close(self) -> None:
        """关闭 ChatAgent 持有的 SQLite 连接。"""
        connections = getattr(self, "_sqlite_connections", ())
        self._sqlite_connections = ()
        for connection in connections:
            try:
                connection.close()
            except sqlite3.Error as e:
                self.logger.warning(f"⚠️ 关闭 SQLite 连接失败: {e}")

    # ══════════════════════════════════════════════════════════════
    # 兜底
    # ══════════════════════════════════════════════════════════════
    def _fallback_response(self, user_input: str) -> str:
        """无 API Key 时的模拟回复"""
        self.logger.warning("⚠️ 使用模拟模式 (无 API Key)")
        responses = [
            f"你好！我收到了你的消息: '{user_input[:30]}...'",
            f"这是一个模拟回复。要获得真正的 AI 回答，请配置 .env 中的 API Key。",
            f"支持的 Provider: OpenAI (OPENAI_API_KEY) / DeepSeek (DEEPSEEK_API_KEY)",
        ]
        return "\n\n".join(responses)
