"""ChatAgent 模型消息块流回归测试。"""

import logging

import pytest
from langchain_core.messages import AIMessageChunk

import src.agents.chat_agent as chat_agent_module
from src.agents.chat_agent import ChatAgent


class _EmptyState:
    values = {}


class _StreamingGraph:
    def __init__(self):
        self.stream_mode = None

    def get_state(self, _config):
        return _EmptyState()

    async def astream(self, _input, _config, stream_mode=None):
        self.stream_mode = stream_mode
        yield AIMessageChunk(content="第一段"), {"langgraph_node": "agent"}
        yield AIMessageChunk(content=[{"type": "text", "text": "第二段"}]), {
            "langgraph_node": "agent",
        }
        yield AIMessageChunk(content="工具输出"), {"langgraph_node": "tools"}


@pytest.mark.asyncio
async def test_async_chat_stream_yields_model_chunks(monkeypatch):
    """流式方法必须使用 messages 模式，并忽略非 Agent 节点输出。"""
    monkeypatch.setattr(chat_agent_module, "CAN_RUN", True)
    graph = _StreamingGraph()
    agent = object.__new__(ChatAgent)
    agent._initialized = True
    agent._graph = graph
    agent._thread_id = "test-thread"
    agent._token_counter = object()
    agent.model = object()
    agent.max_agent_steps = 10
    agent.system_prompt = "test system"
    agent.logger = logging.getLogger("test.chat_stream")

    chunks = [
        chunk
        async for chunk in agent.achat_stream("你好", thread_id="session-1")
    ]

    assert graph.stream_mode == "messages"
    assert chunks == ["第一段", "第二段"]
