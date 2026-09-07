"""Multi-Agent SQLite 隔离、锁释放与生命周期回归测试。"""

import asyncio
import sqlite3
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.agents.multi_agent.main_agent as main_agent_module
import src.agents.multi_agent.sub_agent as sub_agent_module
from src.agents.multi_agent.main_agent import MainAgent
from src.agents.multi_agent.sub_agent import SubAgent
from src.agents.multi_agent.sub_agent_registry import SubAgentMeta
from src.agents.multi_agent.events import (
    MultiAgentEvent,
    SubAgentExecutionError,
    emit_agent_event,
)
from src.agents.base import BaseAgent
from src.server.services.multi_agent_service import (
    MultiAgentService,
    MultiAgentSessionBusyError,
)
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from src.tools.registry import ToolRegistry
from src.tools.multi_agent_planning.subagent_matcher import PlanStepOutput
from src.tools.multi_agent_planning.task_analyzer import TaskAnalysisOutput


@pytest.fixture
def disable_models(monkeypatch):
    """禁止真实模型调用，仅验证 SQLite 基础设施。"""
    monkeypatch.setattr(main_agent_module, "CAN_RUN", False)
    monkeypatch.setattr(main_agent_module, "get_model", lambda **_kwargs: None)
    monkeypatch.setattr(sub_agent_module, "CAN_RUN", False)
    monkeypatch.setattr(sub_agent_module, "get_model", lambda **_kwargs: None)


@pytest.mark.parametrize("agent_class", [MainAgent, SubAgent])
@pytest.mark.asyncio
async def test_sqlite_store_does_not_hold_checkpoint_write_lock(
    tmp_path,
    disable_models,
    agent_class,
):
    db_path = tmp_path / f"{agent_class.__name__}.db"
    agent = agent_class(store_type="sqlite", sqlite_path=str(db_path))
    await agent.ainitialize()

    # 外部写连接能立即取得写锁，证明 Store 初始化未残留事务。
    with closing(sqlite3.connect(db_path, timeout=0.1)) as probe:
        probe.execute("BEGIN IMMEDIATE")
        probe.rollback()

    await agent.aclose()
    assert agent._async_connections == ()


@pytest.mark.asyncio
async def test_service_derives_stable_isolated_database_per_user(
    tmp_path,
    disable_models,
):
    base_path = tmp_path / "multi_agent.db"
    service = MultiAgentService(store_type="sqlite", sqlite_path=str(base_path))

    user_a_path = service._sqlite_path_for_user("user-a")
    user_b_path = service._sqlite_path_for_user("user-b")

    assert user_a_path == service._sqlite_path_for_user("user-a")
    assert user_a_path != user_b_path
    assert Path(user_a_path).parent == tmp_path
    assert "user-a" not in Path(user_a_path).name

    user_a_agent = await service._get_or_create_agent("user-a")
    user_b_agent = await service._get_or_create_agent("user-b")
    assert user_a_agent._sqlite_path == user_a_path
    assert user_b_agent._sqlite_path == user_b_path
    assert Path(user_a_path).is_file()
    assert Path(user_b_path).is_file()

    await service.close_all()
    assert service._agents == {}


class _StructuredModel:
    def __init__(self, schema):
        self.schema = schema

    async def ainvoke(self, _messages):
        if self.schema.__name__ == "DecompositionOutput":
            return SimpleNamespace(
                strategy="two steps",
                sub_plan=[
                    SimpleNamespace(step_id=1, description="first", tool_hint=None),
                    SimpleNamespace(step_id=2, description="second", tool_hint=None),
                ],
            )
        return SimpleNamespace(
            needs_revision=False,
            completeness="complete",
            accuracy="accurate",
            feedback="ok",
            ready_for_main_agent=True,
        )


class _SubAgentModel:
    def __init__(self):
        self.agent_calls = 0
        self.agent_messages = []

    def bind_tools(self, _tools):
        return self

    def with_structured_output(self, schema):
        return _StructuredModel(schema)

    async def ainvoke(self, messages):
        self.agent_calls += 1
        self.agent_messages.append(messages)
        return AIMessage(content=f"result-{self.agent_calls}")


@pytest.mark.asyncio
async def test_subagent_persists_each_planned_step_before_evaluation():
    agent = SubAgent()
    agent.model = _SubAgentModel()
    agent.tool_registry = ToolRegistry()
    agent._checkpointer = MemorySaver()
    agent._store = InMemoryStore()
    agent._initialized = True
    agent._build_graph()

    result = await agent.arun(
        "do two things", thread_id="two-steps",
        context=r"image_path=D:\attachments\picture.png",
    )

    assert "result-1" in result
    assert "result-2" in result
    assert agent.model.agent_calls == 2
    assert any(
        r"D:\attachments\picture.png" in str(message.content)
        for message in agent.model.agent_messages[0]
    )


def test_subagent_marks_mcp_permission_failure_as_non_retryable():
    message = ToolMessage(
        content="[MCP] 权限校验失败: 不能直接读取系统剪贴板",
        tool_call_id="call-1",
    )

    failure = SubAgent._tool_failure(message, str(message.content))

    assert failure == (str(message.content), False)


def test_subagent_marks_mcp_validation_text_as_non_retryable():
    message = ToolMessage(
        content="Input validation error: None is not of type 'string'",
        tool_call_id="call-2",
    )

    failure = SubAgent._tool_failure(message, str(message.content))

    assert failure == (str(message.content), False)


def test_subagent_does_not_repeat_exhausted_mcp_result_retries():
    message = ToolMessage(
        content="[MCP] 工具结果重试已耗尽: 错误: Request timed out.",
        tool_call_id="call-3",
    )

    failure = SubAgent._tool_failure(message, str(message.content))

    assert failure == (str(message.content), False)


class _MainAgentStructuredModel:
    def __init__(self, schema):
        self.schema = schema

    async def ainvoke(self, _messages):
        if self.schema.__name__ == "TaskAnalysisOutput":
            parsed = SimpleNamespace(
                intent="new_task",
                resolved_task="delegate one step",
                referenced_turn_ids=[],
                reuse_previous_artifacts=False,
                needs_subagents=True,
                task_summary="delegate one step",
                complexity="simple",
                suggested_subagents=["worker"],
                reason="test",
            )
        elif self.schema.__name__ == "SubagentMatchOutput":
            parsed = SimpleNamespace(
                overall_strategy="one step",
                plan=[SimpleNamespace(
                    step_id=1,
                    description="flaky work",
                    subagent_type="worker",
                    input_summary="",
                    depends_on=[],
                )],
            )
        elif self.schema.__name__ == "AggregationOutput":
            parsed = SimpleNamespace(
                answer="aggregated success",
                sources=["worker:1"],
                confidence="high",
                missing_info="",
            )
        else:
            raise AssertionError(f"unexpected schema: {self.schema.__name__}")
        return {
            "raw": AIMessage(content="raw structured output"),
            "parsed": parsed,
            "parsing_error": None,
        }


class _MainAgentModel:
    def with_structured_output(self, schema, **kwargs):
        assert kwargs.get("include_raw") is True
        return _MainAgentStructuredModel(schema)

    async def ainvoke(self, _messages):
        return AIMessage(content="direct")


class _RoutingStructuredModel:
    def __init__(self, owner, schema):
        self.owner = owner
        self.schema = schema

    async def ainvoke(self, _messages):
        if self.schema.__name__ == "TaskAnalysisOutput":
            parsed = SimpleNamespace(
                intent="new_task",
                resolved_task="route one step",
                referenced_turn_ids=[],
                reuse_previous_artifacts=False,
                needs_subagents=True,
                task_summary="route one step",
                complexity="simple",
                suggested_subagents=[],
                reason="test routing",
            )
        elif self.schema.__name__ == "SubagentMatchOutput":
            parsed = SimpleNamespace(
                overall_strategy="one routing step",
                plan=[SimpleNamespace(
                    step_id=1,
                    description="process intermediate result",
                    subagent_type=self.owner.planned_subagent_type,
                    input_summary="",
                    depends_on=[],
                )],
            )
        elif self.schema.__name__ == "AggregationOutput":
            parsed = SimpleNamespace(
                answer="routing complete",
                sources=["direct:1"],
                confidence="high",
                missing_info="",
            )
        else:
            raise AssertionError(f"unexpected schema: {self.schema.__name__}")
        return {
            "raw": AIMessage(content="raw structured output"),
            "parsed": parsed,
            "parsing_error": None,
        }


class _RoutingMainAgentModel:
    def __init__(self, planned_subagent_type):
        self.planned_subagent_type = planned_subagent_type
        self.direct_calls = 0

    def with_structured_output(self, schema, **kwargs):
        assert kwargs.get("include_raw") is True
        return _RoutingStructuredModel(self, schema)

    async def ainvoke(self, _messages):
        self.direct_calls += 1
        return AIMessage(content="direct result")


class _QueuedStructuredRunnable:
    def __init__(self, owner):
        self.owner = owner

    async def ainvoke(self, messages):
        self.owner.calls.append(list(messages))
        outcome = self.owner.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class _QueuedStructuredModel:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.structured_kwargs = None

    def with_structured_output(self, _schema, **kwargs):
        self.structured_kwargs = kwargs
        return _QueuedStructuredRunnable(self)


def _task_analysis_result():
    return TaskAnalysisOutput(
        intent="new_task",
        resolved_task="委派任务",
        referenced_turn_ids=[],
        reuse_previous_artifacts=False,
        needs_subagents=True,
        task_summary="需要委派任务",
        complexity="simple",
        suggested_subagents=["general_assistant"],
        reason="需要工具能力",
    )


@pytest.mark.asyncio
async def test_main_agent_retries_structured_parsing_failure_once():
    parsing_error = ValueError("missing required field")
    parsed = _task_analysis_result()
    model = _QueuedStructuredModel([
        {
            "raw": AIMessage(content="{}"),
            "parsed": None,
            "parsing_error": parsing_error,
        },
        {
            "raw": AIMessage(content="valid"),
            "parsed": parsed,
            "parsing_error": None,
        },
    ])
    agent = MainAgent()
    agent.model = model
    original_messages = [HumanMessage(content="analyze this")]

    result = await agent._ainvoke_structured(
        TaskAnalysisOutput,
        original_messages,
        strict=True,
    )

    assert result is parsed
    assert len(model.calls) == 2
    assert model.structured_kwargs == {"include_raw": True, "strict": True}
    assert len(original_messages) == 1
    assert "missing required field" in model.calls[1][-1].content
    assert "不得返回空对象" in model.calls[1][-1].content


@pytest.mark.asyncio
async def test_main_agent_retries_empty_structured_result():
    parsed = _task_analysis_result()
    model = _QueuedStructuredModel([
        {"raw": None, "parsed": {}, "parsing_error": None},
        {"raw": None, "parsed": parsed, "parsing_error": None},
    ])
    agent = MainAgent()
    agent.model = model

    result = await agent._ainvoke_structured(
        TaskAnalysisOutput,
        [HumanMessage(content="analyze this")],
    )

    assert result is parsed
    assert len(model.calls) == 2
    assert "返回了空的结构化结果" in model.calls[1][-1].content


@pytest.mark.asyncio
async def test_main_agent_does_not_retry_model_request_errors():
    request_error = TimeoutError("request timed out")
    model = _QueuedStructuredModel([request_error])
    agent = MainAgent(max_structured_retries=1)
    agent.model = model

    with pytest.raises(TimeoutError, match="request timed out"):
        await agent._ainvoke_structured(
            TaskAnalysisOutput,
            [HumanMessage(content="analyze this")],
        )

    assert len(model.calls) == 1


@pytest.mark.asyncio
async def test_main_agent_can_disable_structured_output_retry():
    parsing_error = ValueError("invalid structured output")
    model = _QueuedStructuredModel([{
        "raw": AIMessage(content="invalid"),
        "parsed": None,
        "parsing_error": parsing_error,
    }])
    agent = MainAgent(max_structured_retries=0)
    agent.model = model

    with pytest.raises(ValueError, match="invalid structured output"):
        await agent._ainvoke_structured(
            TaskAnalysisOutput,
            [HumanMessage(content="analyze this")],
        )

    assert len(model.calls) == 1


def test_task_analysis_strict_schema_requires_every_field():
    schema = TaskAnalysisOutput.model_json_schema()
    assert set(schema["required"]) == set(schema["properties"])


def test_plan_step_normalizes_blank_subagent_type_to_direct():
    step = PlanStepOutput(
        step_id=1,
        description="direct work",
        subagent_type="   ",
    )

    assert step.subagent_type is None


@pytest.mark.asyncio
async def test_main_agent_executes_blank_subagent_type_as_direct_step():
    agent = MainAgent(max_step_retries=2)
    model = _RoutingMainAgentModel(planned_subagent_type="   ")
    agent.model = model
    agent._checkpointer = MemorySaver()
    agent._store = InMemoryStore()
    agent._initialized = True

    async def _unexpected_subagent(_subagent_type):
        raise AssertionError("blank subagent_type must use the direct branch")

    agent._get_or_create_subagent = _unexpected_subagent
    agent._build_graph()

    result = await agent.arun("route this", thread_id="blank-direct")
    final_state = await agent._graph.aget_state({
        "configurable": {"thread_id": "blank-direct"}
    })

    assert result == "routing complete"
    assert model.direct_calls == 1
    assert final_state.values["plan"][0]["subagent_type"] is None
    assert final_state.values["subagent_statuses"] == {"1": "success"}
    assert final_state.values["step_retry_counts"] == {}


@pytest.mark.asyncio
async def test_main_agent_rejects_unknown_subagent_before_execute_retries():
    agent = MainAgent(max_step_retries=2)
    model = _RoutingMainAgentModel(planned_subagent_type="missing_agent")
    agent.model = model
    agent._checkpointer = MemorySaver()
    agent._store = InMemoryStore()
    agent._initialized = True
    agent._build_graph()

    with pytest.raises(
        ValueError,
        match="执行计划包含未注册的 SubAgent 类型: missing_agent",
    ):
        await agent.arun("route this", thread_id="unknown-subagent")

    assert model.direct_calls == 0


def _register_worker(agent: MainAgent) -> None:
    agent.sub_agent_registry.register(SubAgentMeta(
        subagent_type="worker",
        display_name="Worker",
        description="Test worker",
    ))


class _FlakySubAgent:
    def __init__(self):
        self.calls = 0

    async def arun(self, *_args, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary failure")
        return "recovered result"


class _ObservableSubAgent:
    async def arun(self, *_args, **_kwargs):
        await emit_agent_event(MultiAgentEvent.SUBAGENT_PLAN, {
            "subagent_type": "worker",
            "plan": [{"step_id": 1, "description": "inspect workspace"}],
        })
        await emit_agent_event(MultiAgentEvent.TOOL_CALL, {
            "agent": "worker",
            "tool_name": "read_file",
            "args": {"path": "demo/index.html"},
        })
        await emit_agent_event(MultiAgentEvent.TOOL_RESULT, {
            "agent": "worker",
            "tool_name": "read_file",
            "result_summary": "file read",
        })
        return "observable result"


class _FailingSubAgent:
    def __init__(self):
        self.calls = 0

    async def arun(self, *_args, **_kwargs):
        self.calls += 1
        raise RuntimeError("persistent failure")


class _NonRetryableSubAgent:
    def __init__(self):
        self.calls = 0

    async def arun(self, *_args, **_kwargs):
        self.calls += 1
        raise SubAgentExecutionError("file permission rejected", retryable=False)


@pytest.mark.asyncio
async def test_main_agent_retries_failed_execute_step_without_replanning():
    agent = MainAgent(max_step_retries=2)
    _register_worker(agent)
    agent.model = _MainAgentModel()
    agent._checkpointer = MemorySaver()
    agent._store = InMemoryStore()
    agent._initialized = True
    flaky_subagent = _FlakySubAgent()

    async def _get_sub(_subagent_type):
        return flaky_subagent
    agent._get_or_create_subagent = _get_sub
    agent._build_graph()

    result = await agent.arun("delegate this", thread_id="execute-retry")
    final_state = await agent._graph.aget_state({
        "configurable": {"thread_id": "execute-retry"}
    })

    assert result == "aggregated success"
    assert flaky_subagent.calls == 2
    assert final_state.values["current_step_index"] == 1
    assert final_state.values["subagent_statuses"] == {"1": "success"}
    assert final_state.values["subagent_results"] == {"1": "recovered result"}
    assert final_state.values["step_retry_counts"] == {}


@pytest.mark.asyncio
async def test_main_agent_stream_forwards_execution_progress_events():
    agent = MainAgent(max_step_retries=0)
    _register_worker(agent)
    agent.model = _MainAgentModel()
    agent._checkpointer = MemorySaver()
    agent._store = InMemoryStore()
    agent._initialized = True

    async def _get_sub(_subagent_type):
        return _ObservableSubAgent()

    agent._get_or_create_subagent = _get_sub
    agent._build_graph()

    events = [
        event async for event in agent.arun_stream(
            "delegate this", thread_id="observable-stream", turn_id="turn-1",
        )
    ]
    event_types = [str(event["event"]) for event in events]

    assert event_types == [
        "analyzing",
        "analysis_done",
        "status",
        "plan_created",
        "dispatching",
        "subagent_start",
        "subagent_step",
        "subagent_plan",
        "tool_call",
        "tool_result",
        "subagent_done",
        "synthesizing",
        "synthesis_done",
        "done",
    ]
    assert events[1]["data"]["task_summary"] == "delegate one step"
    assert events[3]["data"]["plan"][0]["description"] == "flaky work"
    assert events[4]["data"]["step_id"] == "1"
    assert events[-2]["data"]["answer"] == "aggregated success"


@pytest.mark.asyncio
async def test_main_agent_stops_retrying_step_after_configured_limit():
    agent = MainAgent(max_step_retries=2)
    _register_worker(agent)
    agent.model = _MainAgentModel()
    agent._checkpointer = MemorySaver()
    agent._store = InMemoryStore()
    agent._initialized = True
    failing_subagent = _FailingSubAgent()

    async def _get_sub(_subagent_type):
        return failing_subagent
    agent._get_or_create_subagent = _get_sub
    agent._build_graph()

    await agent.arun("delegate this", thread_id="execute-retry-limit")
    final_state = await agent._graph.aget_state({
        "configurable": {"thread_id": "execute-retry-limit"}
    })

    assert failing_subagent.calls == 3
    assert final_state.values["current_step_index"] == 1
    assert final_state.values["subagent_statuses"] == {"1": "failed"}
    assert final_state.values["step_retry_counts"] == {"1": 3}


@pytest.mark.asyncio
async def test_main_agent_does_not_retry_non_retryable_subagent_failure():
    agent = MainAgent(max_step_retries=2)
    _register_worker(agent)
    agent.model = _MainAgentModel()
    agent._checkpointer = MemorySaver()
    agent._store = InMemoryStore()
    agent._initialized = True
    failing_subagent = _NonRetryableSubAgent()

    async def _get_sub(_subagent_type):
        return failing_subagent
    agent._get_or_create_subagent = _get_sub
    agent._build_graph()

    await agent.arun("delegate this", thread_id="execute-non-retryable")
    final_state = await agent._graph.aget_state({
        "configurable": {"thread_id": "execute-non-retryable"}
    })

    assert failing_subagent.calls == 1
    assert final_state.values["current_step_index"] == 1
    assert final_state.values["subagent_statuses"] == {"1": "failed"}


def test_service_cancel_run_sets_active_cancellation_event():
    service = MultiAgentService()
    cancellation_event = asyncio.Event()
    service._active_runs["user:session"] = cancellation_event

    assert service.cancel_run("user:session") is True
    assert cancellation_event.is_set()
    assert service.cancel_run("missing") is False


@pytest.mark.asyncio
async def test_service_deletes_multi_agent_session_checkpoint():
    service = MultiAgentService()
    deleted_threads = []
    fake_agent = SimpleNamespace(
        _checkpointer=SimpleNamespace(
            delete_thread=lambda thread_id: deleted_threads.append(thread_id)
        )
    )
    service._agents["user-1"] = fake_agent
    service._session_locks["ma:v2:user-1:session-1"] = object()

    await service.delete_session_state("user-1", "session-1")

    assert deleted_threads == ["ma:v2:user-1:session-1"]
    assert "ma:v2:user-1:session-1" not in service._session_locks


@pytest.mark.asyncio
async def test_service_rejects_deleting_active_multi_agent_session():
    service = MultiAgentService()
    service._active_runs["ma:v2:user-1:session-1"] = asyncio.Event()

    with pytest.raises(MultiAgentSessionBusyError, match="运行中的"):
        await service.delete_session_state("user-1", "session-1")


class _AsyncInitAgent(BaseAgent):
    def _setup(self, **kwargs):
        self.setup_called = True


@pytest.mark.asyncio
async def test_base_agent_ainitialize_delegates_to_setup():
    a = _AsyncInitAgent(name="t")
    await a.ainitialize()
    assert a.setup_called is True
    assert a.is_initialized


@pytest.mark.asyncio
async def test_async_sqlite_checkpoint_roundtrip(tmp_path):
    """钉住 AsyncSqliteSaver 的 API：connect → ainvoke → aget_state。"""
    from langgraph.graph import StateGraph, END
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from langchain_core.messages import HumanMessage

    db = tmp_path / "ckpt.db"
    async with AsyncSqliteSaver.from_conn_string(str(db)) as saver:
        g = StateGraph(dict)
        g.add_node("n", lambda s: {"messages": s.get("messages", []) + [HumanMessage(content="hi")]})
        g.set_entry_point("n")
        g.add_edge("n", END)
        graph = g.compile(checkpointer=saver)
        await graph.ainvoke({"messages": []}, {"configurable": {"thread_id": "t1"}})
        state = await graph.aget_state({"configurable": {"thread_id": "t1"}})
        assert len(state.values["messages"]) == 1
