"""Multi-Agent 多轮会话、任务轮次和上下文窗口回归测试。"""

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from src.agents.multi_agent.events import AgentRunCancelled
from src.agents.multi_agent.main_agent import MainAgent
from src.agents.multi_agent.states import MainAgentState
from src.server.repositories.base import (
    ConversationSummary,
    MultiAgentTurn,
    SessionMessage,
)
from src.server.repositories.memory import (
    InMemoryConversationSummaryRepo,
    InMemoryMultiAgentTurnRepo,
    InMemorySessionMessageRepo,
)
from src.server.repositories.sqlite import (
    SqliteConversationSummaryRepo,
    SqliteDb,
    SqliteMultiAgentTurnRepo,
    SqliteSessionMessageRepo,
    SqliteSessionRepo,
)
from src.server.services.multi_agent_service import MultiAgentService
from src.tools.multi_agent_planning.task_analyzer import (
    TaskAnalysisOutput,
    analyze_user_task,
)


class _ConversationAgent:
    def __init__(self):
        self.calls: list[dict] = []
        self.snapshots: dict[str, dict] = {}
        self.summary_calls: list[tuple[str, list[dict]]] = []
        self.cancel_next = False

    async def arun_stream(self, query, *, thread_id, **kwargs):
        self.calls.append({"query": query, "thread_id": thread_id, **kwargs})
        if self.cancel_next:
            self.cancel_next = False
            self.snapshots[thread_id] = {
                "intent": "new_task",
                "resolved_task": query,
                "plan": [
                    {"step_id": 1, "description": "已完成", "subagent_type": None},
                    {"step_id": 2, "description": "待继续", "subagent_type": None},
                ],
                "subagent_results": {"1": "阶段结果"},
                "subagent_statuses": {"1": "success"},
                "current_step_index": 1,
            }
            raise AgentRunCancelled("cancelled by test")

        answer = f"回答：{query}"
        self.snapshots[thread_id] = {
            "intent": "follow_up" if kwargs.get("conversation_context") else "new_task",
            "resolved_task": query,
            "plan": [],
            "subagent_results": {},
            "subagent_statuses": {},
            "current_step_index": 0,
            "synthesized_answer": answer,
            "synthesis_sources": ["test"],
            "synthesis_confidence": "high",
        }
        yield {"event": "synthesis_done", "data": {"answer": answer}}
        yield {"event": "done", "data": {}}

    async def get_run_snapshot(self, thread_id):
        return dict(self.snapshots.get(thread_id, {}))

    async def summarize_conversation(self, existing_summary, messages):
        self.summary_calls.append((existing_summary, list(messages)))
        return f"{existing_summary}|已摘要{len(messages)}条".strip("|")


async def _collect(stream):
    return [event async for event in stream]


@pytest.mark.asyncio
async def test_sqlite_message_turn_and_summary_repositories_roundtrip(tmp_path):
    db = SqliteDb(str(tmp_path / "conversation.db"))
    await db.init_schema()
    sessions = SqliteSessionRepo(db)
    messages = SqliteSessionMessageRepo(db)
    turns = SqliteMultiAgentTurnRepo(db)
    summaries = SqliteConversationSummaryRepo(db)
    session = await sessions.create("user-1", "多轮任务", "multi_agent")

    await turns.create(MultiAgentTurn(
        turn_id="turn-1",
        session_id=session.session_id,
        user_id="user-1",
        plan=[{"step_id": 1, "description": "检索"}],
    ))
    await messages.create(SessionMessage(
        message_id="message-1",
        session_id=session.session_id,
        turn_id="turn-1",
        role="user",
        content="查一下最新进展",
    ))
    await turns.update(
        "turn-1",
        status="completed",
        intent="new_task",
        resolved_task="检索最新进展",
        results={"1": "完成"},
        step_statuses={"1": "success"},
        final_answer="已完成",
    )
    await summaries.upsert(ConversationSummary(
        session_id=session.session_id,
        summary="用户需要最新进展",
        covered_message_count=1,
    ))

    stored_turn = await turns.get("turn-1")
    assert stored_turn is not None
    assert stored_turn.results == {"1": "完成"}
    assert stored_turn.step_statuses == {"1": "success"}
    assert (await messages.list_by_session(session.session_id))[0].content == "查一下最新进展"
    assert (await summaries.get(session.session_id)).covered_message_count == 1

    await sessions.delete(session.session_id)
    assert await messages.list_by_session(session.session_id) == []
    assert await turns.list_by_session(session.session_id) == []
    assert await summaries.get(session.session_id) is None
    await db.close()


@pytest.mark.asyncio
async def test_service_reuses_session_and_passes_previous_dialogue_to_next_turn():
    message_repo = InMemorySessionMessageRepo()
    turn_repo = InMemoryMultiAgentTurnRepo()
    summary_repo = InMemoryConversationSummaryRepo()
    service = MultiAgentService(
        message_repo=message_repo,
        turn_repo=turn_repo,
        summary_repo=summary_repo,
    )
    agent = _ConversationAgent()
    service._agents["user-1"] = agent

    first = await _collect(service.chat_stream("user-1", "session-1", "先查资料"))
    second = await _collect(service.chat_stream("user-1", "session-1", "再比较一下"))

    assert agent.calls[0]["thread_id"] == "ma:v2:user-1:session-1"
    assert agent.calls[0]["conversation_context"] == []
    assert [item["content"] for item in agent.calls[1]["conversation_context"]] == [
        "先查资料", "回答：先查资料",
    ]
    assert agent.calls[1]["previous_artifacts"][0]["status"] == "completed"
    assert len({first[0]["data"]["turn_id"], second[0]["data"]["turn_id"]}) == 2
    assert [message.role for message in await message_repo.list_by_session("session-1")] == [
        "user", "assistant", "user", "assistant",
    ]
    assert len(await turn_repo.list_by_session("session-1")) == 2


@pytest.mark.asyncio
async def test_cancelled_turn_is_persisted_and_available_to_continue():
    message_repo = InMemorySessionMessageRepo()
    turn_repo = InMemoryMultiAgentTurnRepo()
    service = MultiAgentService(
        message_repo=message_repo,
        turn_repo=turn_repo,
        summary_repo=InMemoryConversationSummaryRepo(),
    )
    agent = _ConversationAgent()
    agent.cancel_next = True
    service._agents["user-1"] = agent

    cancelled_events = await _collect(
        service.chat_stream("user-1", "session-1", "执行两步任务")
    )
    cancelled_turn = (await turn_repo.list_by_session("session-1"))[0]
    assert cancelled_turn.status == "cancelled"
    assert cancelled_turn.resume_step == 1
    assert cancelled_turn.step_statuses == {"1": "success"}
    assert cancelled_events[-1]["event"] == "cancelled"
    assert (await message_repo.list_by_session("session-1"))[-1].status == "cancelled"

    await _collect(service.chat_stream("user-1", "session-1", "继续"))
    artifact = agent.calls[1]["previous_artifacts"][-1]
    assert artifact["status"] == "cancelled"
    assert artifact["resume_step"] == 1
    assert artifact["results"] == {"1": "阶段结果"}


@pytest.mark.asyncio
async def test_interruption_does_not_copy_previous_checkpoint_into_new_turn():
    turn_repo = InMemoryMultiAgentTurnRepo()
    service = MultiAgentService(
        message_repo=InMemorySessionMessageRepo(),
        turn_repo=turn_repo,
        summary_repo=InMemoryConversationSummaryRepo(),
    )
    await turn_repo.create(MultiAgentTurn(
        turn_id="turn-new",
        session_id="session-1",
        user_id="user-1",
        resolved_task="新任务",
    ))

    class StaleSnapshotAgent:
        async def get_run_snapshot(self, _thread_id):
            return {
                "turn_id": "turn-old",
                "resolved_task": "旧任务",
                "plan": [{"step_id": 1, "description": "旧计划"}],
            }

    await service._finalize_interrupted_turn(
        StaleSnapshotAgent(),
        "ma:v2:user-1:session-1",
        "session-1",
        "turn-new",
        status="cancelled",
        message="已中止",
    )

    turn = await turn_repo.get("turn-new")
    assert turn.resolved_task == "新任务"
    assert turn.plan == []
    assert turn.status == "cancelled"


def test_main_agent_resume_starts_at_first_incomplete_step():
    resumed = MainAgent._resume_previous_plan({
        "intent": "continue_task",
        "reuse_previous_artifacts": True,
        "previous_artifacts": [{
            "turn_id": "turn-old",
            "status": "cancelled",
            "plan": [
                {"step_id": 1, "description": "完成"},
                {"step_id": 2, "description": "继续"},
            ],
            "results": {"1": "已有结果"},
            "step_statuses": {"1": "success", "2": "pending"},
        }],
    })

    assert resumed is not None
    assert resumed["current_step_index"] == 1
    assert resumed["subagent_results"] == {"1": "已有结果"}
    assert resumed["resumed_from_turn_id"] == "turn-old"


def test_main_agent_visible_history_is_context_not_internal_messages():
    assert "messages" not in MainAgentState.__annotations__
    prompt = analyze_user_task(
        "把它改成表格",
        conversation_context="用户 [turn-1]: 比较 A 和 B\n助手 [turn-1]: 已完成比较",
        conversation_summary="用户偏好简洁输出",
        previous_artifacts="轮次 turn-1 [状态: completed]",
    )
    assert "比较 A 和 B" in prompt
    assert "用户偏好简洁输出" in prompt
    assert "turn-1" in prompt

    agent = MainAgent()
    messages = agent._build_context_messages({
        "conversation_summary": "较早摘要",
        "conversation_context": [
            {"role": "user", "content": "上一问"},
            {"role": "assistant", "content": "上一答"},
        ],
        "previous_artifacts": [],
        "reuse_previous_artifacts": False,
    }, "本节点指令")
    assert [type(message) for message in messages] == [
        SystemMessage, SystemMessage, HumanMessage, AIMessage, HumanMessage,
    ]
    assert messages[-1].content == "本节点指令"


@pytest.mark.asyncio
async def test_cancellation_prevents_structured_output_retry():
    cancellation_event = asyncio.Event()

    class CancellingStructuredModel:
        calls = 0

        def with_structured_output(self, _schema, **_kwargs):
            return self

        async def ainvoke(self, _messages):
            self.calls += 1
            cancellation_event.set()
            return {
                "raw": AIMessage(content="{}"),
                "parsed": None,
                "parsing_error": ValueError("invalid output"),
            }

    model = CancellingStructuredModel()
    agent = MainAgent(max_structured_retries=1)
    agent.model = model
    agent._cancellation_events["ma:v2:u:s"] = cancellation_event

    with pytest.raises(AgentRunCancelled):
        await agent._ainvoke_structured(
            TaskAnalysisOutput,
            [HumanMessage(content="分析")],
            run_config={"configurable": {"thread_id": "ma:v2:u:s"}},
        )

    assert model.calls == 1


@pytest.mark.asyncio
async def test_main_agent_persists_intent_and_resolved_task_for_follow_up():
    class FollowUpModel:
        def __init__(self):
            self.direct_messages = []

        def with_structured_output(self, schema, **_kwargs):
            owner = self

            class Structured:
                async def ainvoke(self, _messages):
                    assert schema is TaskAnalysisOutput
                    return {
                        "raw": AIMessage(content="structured"),
                        "parsed": SimpleNamespace(
                            intent="revise_task",
                            resolved_task="将 turn-1 的比较结果改为表格输出",
                            referenced_turn_ids=["turn-1"],
                            reuse_previous_artifacts=True,
                            needs_subagents=False,
                            task_summary="修改上一轮输出格式",
                            complexity="simple",
                            suggested_subagents=[],
                            reason="可直接基于历史结果调整",
                        ),
                        "parsing_error": None,
                    }

            return Structured()

        async def ainvoke(self, messages):
            self.direct_messages = list(messages)
            return AIMessage(content="已改为表格")

    model = FollowUpModel()
    agent = MainAgent()
    agent.model = model
    agent._checkpointer = MemorySaver()
    agent._store = InMemoryStore()
    agent._initialized = True
    agent._build_graph()

    answer = await agent.arun(
        "改成表格",
        thread_id="ma:v2:user-1:session-1",
        turn_id="turn-2",
        conversation_context=[
            {"turn_id": "turn-1", "role": "user", "content": "比较 A 和 B"},
            {"turn_id": "turn-1", "role": "assistant", "content": "比较结果"},
        ],
        previous_artifacts=[{
            "turn_id": "turn-1",
            "status": "completed",
            "resolved_task": "比较 A 和 B",
            "final_answer": "比较结果",
        }],
    )
    state = await agent.get_run_snapshot("ma:v2:user-1:session-1")

    assert answer == "已改为表格"
    assert state["intent"] == "revise_task"
    assert state["resolved_task"] == "将 turn-1 的比较结果改为表格输出"
    assert state["referenced_turn_ids"] == ["turn-1"]
    assert any(message.content == "比较结果" for message in model.direct_messages)


@pytest.mark.asyncio
async def test_history_window_keeps_whole_recent_turn_and_summarizes_older_turns():
    summary_repo = InMemoryConversationSummaryRepo()
    service = MultiAgentService(
        summary_repo=summary_repo,
        max_context_tokens=512,
        max_history_turns=1,
    )
    agent = _ConversationAgent()
    start = datetime(2026, 1, 1)
    messages = []
    for turn_index in range(3):
        for offset, (role, content) in enumerate((
            ("user", f"问题 {turn_index}"),
            ("assistant", f"回答 {turn_index}"),
        )):
            messages.append(SessionMessage(
                message_id=f"m-{turn_index}-{offset}",
                session_id="session-1",
                turn_id=f"turn-{turn_index}",
                role=role,
                content=content,
                created_at=start + timedelta(seconds=turn_index * 2 + offset),
            ))

    summary, recent = await service._prepare_conversation_context(
        agent, "session-1", messages,
    )

    assert [item["content"] for item in recent] == ["问题 2", "回答 2"]
    assert len(agent.summary_calls) == 1
    assert len(agent.summary_calls[0][1]) == 4
    assert summary == "已摘要4条"
    assert (await summary_repo.get("session-1")).covered_message_count == 4


@pytest.mark.asyncio
async def test_oversized_latest_turn_is_trimmed_to_context_budget():
    service = MultiAgentService(
        summary_repo=InMemoryConversationSummaryRepo(),
        max_context_tokens=512,
        max_history_turns=2,
    )
    agent = _ConversationAgent()
    messages = [
        SessionMessage(
            message_id="m-user",
            session_id="session-1",
            turn_id="turn-1",
            role="user",
            content="问题" * 500,
        ),
        SessionMessage(
            message_id="m-assistant",
            session_id="session-1",
            turn_id="turn-1",
            role="assistant",
            content="回答" * 1000,
        ),
    ]

    summary, recent = await service._prepare_conversation_context(
        agent, "session-1", messages,
    )

    assert summary == ""
    assert [item["role"] for item in recent] == ["user", "assistant"]
    assert sum(
        service._estimate_tokens(item["content"]) + 8 for item in recent
    ) <= 512
    assert recent[0]["content"].endswith("…")
    assert recent[1]["content"].endswith("…")
