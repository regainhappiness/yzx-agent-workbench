from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.server.services.chat_service import ChatService


LEGACY_ENHANCED_QUERY = """请根据以下知识库内容回答用户问题。如果知识库内容不足以回答，请如实说明。


--- 知识库检索结果 ---

[1] MySQL 架构是怎样的？.md (私人 第1页)
现在大家通了吗？

---
用户问题: 你好"""


def test_visible_messages_hide_system_content_and_clean_legacy_query():
    messages = [
        SystemMessage(content="默认系统提示词"),
        HumanMessage(content=LEGACY_ENHANCED_QUERY),
        AIMessage(content="你好！"),
        SystemMessage(content="本轮知识库检索结果"),
        HumanMessage(content="继续说"),
    ]

    visible = ChatService.visible_messages(messages)

    assert [message.type for message in visible] == [
        "human", "ai", "human",
    ]
    assert [message.content for message in visible] == [
        "你好", "你好！", "继续说",
    ]


def test_visible_messages_clean_legacy_query_with_crlf_and_leading_space():
    legacy_query = "  \r\n" + LEGACY_ENHANCED_QUERY.replace("\n", "\r\n")

    visible = ChatService.visible_messages([HumanMessage(content=legacy_query)])

    assert [message.content for message in visible] == ["你好"]


def test_get_session_messages_filters_before_limiting_rounds():
    stored_messages = [
        SystemMessage(content="默认系统提示词"),
        HumanMessage(content=LEGACY_ENHANCED_QUERY),
        AIMessage(content="你好！"),
        SystemMessage(content="第二轮知识库检索结果"),
        HumanMessage(content="第二个问题"),
        AIMessage(content="第二个回答"),
    ]
    agent = SimpleNamespace(
        get_session_info=lambda _tid: {"has_state": True},
        _graph=SimpleNamespace(
            get_state=lambda _config: SimpleNamespace(
                values={"messages": stored_messages},
            ),
        ),
    )
    service = ChatService()
    service._get_or_create_agent = lambda _user_id: agent

    messages = service._get_session_messages("user-1", "session-1", max_rounds=1)

    assert [message.content for message in messages] == [
        "第二个问题", "第二个回答",
    ]


@pytest.mark.asyncio
async def test_chat_stores_raw_query_separately_from_system_context():
    agent = SimpleNamespace(achat=AsyncMock(return_value="回答"))
    service = ChatService()
    service._get_or_create_agent = lambda _user_id: agent
    service._get_knowledge_context = AsyncMock(return_value="知识库系统上下文")

    answer = await service.chat("user-1", "session-1", "你好")

    assert answer == "回答"
    agent.achat.assert_awaited_once_with(
        "你好",
        thread_id="user-1:session-1",
        extra_system_content="知识库系统上下文",
    )


@pytest.mark.asyncio
async def test_chat_stream_stores_raw_query_separately_from_system_context():
    calls = []

    async def stream(*args, **kwargs):
        calls.append((args, kwargs))
        yield "你"
        yield "好"

    agent = SimpleNamespace(achat_stream=stream)
    service = ChatService()
    service._get_or_create_agent = lambda _user_id: agent
    service._get_knowledge_context = AsyncMock(return_value="知识库系统上下文")

    chunks = [
        chunk
        async for chunk in service.chat_stream(
            "user-1", "session-1", "你好",
        )
    ]

    assert chunks == ["你", "好"]
    assert calls == [(("你好",), {
        "thread_id": "user-1:session-1",
        "extra_system_content": "知识库系统上下文",
    })]
