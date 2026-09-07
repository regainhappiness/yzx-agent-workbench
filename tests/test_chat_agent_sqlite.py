"""ChatAgent SQLite 存储回归测试。"""

import sqlite3
import threading

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import StateGraph

import src.agents.chat_agent as chat_agent_module
from src.agents.chat_agent import AgentState, ChatAgent


@pytest.fixture
def sqlite_agent_factory(monkeypatch):
    """禁用真实模型，仅验证 ChatAgent 的存储初始化。"""
    monkeypatch.setattr(chat_agent_module, "CAN_RUN", False)
    monkeypatch.setattr(chat_agent_module, "get_model", lambda **_kwargs: None)

    agents = []

    def create(path):
        agent = ChatAgent(
            store_type="sqlite",
            sqlite_path=path,
            load_builtin_tools=False,
        )
        agent.initialize()
        agents.append(agent)
        return agent

    yield create

    for agent in agents:
        agent.close()


def test_sqlite_storage_initializes_checkpointer_and_store(
    tmp_path,
    sqlite_agent_factory,
):
    db_path = tmp_path / "nested" / "chat-agent.db"

    agent = sqlite_agent_factory(db_path)

    assert db_path.is_file()
    assert agent.store_type == "sqlite"
    assert agent.sqlite_path == str(db_path)

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert {"checkpoints", "writes", "store"} <= tables


def test_sqlite_storage_persists_long_term_memory(
    tmp_path,
    sqlite_agent_factory,
):
    db_path = tmp_path / "chat-agent.db"
    first = sqlite_agent_factory(db_path)
    first.save_memory("preferences", {"language": "zh-CN"}, ("user", "1"))
    first.close()

    second = sqlite_agent_factory(db_path)

    assert second.get_memory("preferences", ("user", "1")) == {
        "language": "zh-CN"
    }


def test_sqlite_storage_persists_and_resets_checkpoints(
    tmp_path,
    sqlite_agent_factory,
):
    db_path = tmp_path / "chat-agent.db"
    config = {"configurable": {"thread_id": "session-1"}}

    def compile_graph(agent):
        workflow = StateGraph(AgentState)
        workflow.add_node(
            "answer",
            lambda _state: {"messages": [AIMessage(content="stored answer")]},
        )
        workflow.set_entry_point("answer")
        workflow.set_finish_point("answer")
        return workflow.compile(
            checkpointer=agent._checkpointer,
            store=agent._store,
        )

    first = sqlite_agent_factory(db_path)
    compile_graph(first).invoke(
        {"messages": [HumanMessage(content="stored question")]},
        config,
    )
    first.close()

    second = sqlite_agent_factory(db_path)
    second._graph = compile_graph(second)
    state = second._graph.get_state(config)

    assert [message.content for message in state.values["messages"]] == [
        "stored question",
        "stored answer",
    ]

    second.reset("session-1")

    assert not second._graph.get_state(config).values


@pytest.mark.asyncio
async def test_sqlite_async_methods_use_sync_graph_in_worker_thread():
    agent = object.__new__(ChatAgent)
    agent._initialized = True
    agent.store_type = "sqlite"
    event_loop_thread = threading.get_ident()

    def execute(user_input, thread_id, extra_system_content=None):
        assert threading.get_ident() != event_loop_thread
        assert extra_system_content is None
        return f"{thread_id}:{user_input}"

    def chat_stream(user_input, thread_id=None, extra_system_content=None):
        assert extra_system_content is None
        return iter([f"{thread_id}:", user_input])

    agent._execute = execute
    agent.chat_stream = chat_stream

    assert await agent.achat("你好", thread_id="session-1") == "session-1:你好"
    assert [
        chunk
        async for chunk in agent.achat_stream("你好", thread_id="session-1")
    ] == ["session-1:", "你好"]
