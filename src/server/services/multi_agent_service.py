"""
===========================================================================
MultiAgentService — MainAgent 的 FastAPI 服务包装（异步）
===========================================================================

与 ChatService 相同的模式:
  - 按 user_id 缓存 MainAgent 实例
  - 异步流式输出 → SSE events
  - thread_id = "ma:v2:{user_id}:{session_id}"

使用:
    from ..agents.multi_agent import SubAgentRegistry
    registry = SubAgentRegistry()
    service = MultiAgentService(sub_agent_registry=registry)
===========================================================================
"""

import asyncio
import hashlib
import logging
import math
import uuid
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from ...agents.multi_agent.main_agent import MainAgent
from ...agents.multi_agent.sub_agent_registry import SubAgentRegistry
from ...agents.multi_agent.events import AgentRunCancelled
from ..repositories.base import (
    ConversationSummary,
    ConversationSummaryRepository,
    MultiAgentTurn,
    MultiAgentTurnRepository,
    SessionMessage,
    SessionMessageRepository,
)
from ..repositories.memory import (
    InMemoryConversationSummaryRepo,
    InMemoryMultiAgentTurnRepo,
    InMemorySessionMessageRepo,
)
from .session_service import SessionService
from .multi_agent_workspace_service import MultiAgentWorkspaceService
from ...tools.mcp.scope import reset_file_scope, set_file_scope

logger = logging.getLogger("server.multi_agent_service")


class MultiAgentSessionBusyError(RuntimeError):
    """Raised when a session is deleted while its graph is still running."""


class MultiAgentService:
    """MainAgent 服务包装

    管理 MainAgent 实例的缓存和生命周期。
    """

    def __init__(
        self,
        sub_agent_registry: SubAgentRegistry | None = None,
        store_type: str = "memory",
        sqlite_path: str | None = None,
        model_kwargs: dict | None = None,
        message_repo: SessionMessageRepository | None = None,
        turn_repo: MultiAgentTurnRepository | None = None,
        summary_repo: ConversationSummaryRepository | None = None,
        session_service: SessionService | None = None,
        workspace_service: MultiAgentWorkspaceService | None = None,
        max_context_tokens: int = 6000,
        max_history_turns: int = 10,
    ):
        self._agents: dict[str, MainAgent] = {}
        self._retired_agents: list[MainAgent] = []
        self._registry = sub_agent_registry or SubAgentRegistry()
        self._store_type = store_type
        self._sqlite_path = sqlite_path
        self._model_kwargs = dict(model_kwargs or {})
        self._message_repo = message_repo or InMemorySessionMessageRepo()
        self._turn_repo = turn_repo or InMemoryMultiAgentTurnRepo()
        self._summary_repo = summary_repo or InMemoryConversationSummaryRepo()
        self._session_service = session_service
        self._workspace_service = workspace_service
        self._max_context_tokens = max(512, int(max_context_tokens))
        self._max_history_turns = max(1, int(max_history_turns))
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._active_runs: dict[str, asyncio.Event] = {}

    # ── Agent 管理 ──

    async def _get_or_create_agent(self, user_id: str) -> MainAgent:
        """按需获取或创建用户的 MainAgent 实例"""
        if user_id not in self._agents:
            agent = MainAgent(
                name=f"orchestrator-{user_id[:8]}",
                sub_agent_registry=self._registry,
                store_type=self._store_type,
                sqlite_path=self._sqlite_path_for_user(user_id),
                model_kwargs=self._model_kwargs,
            )
            await agent.ainitialize()
            self._agents[user_id] = agent
            logger.info("新 MainAgent 实例: user=%s", user_id[:8])
        return self._agents[user_id]

    async def close_user(self, user_id: str):
        """释放用户的 MainAgent 实例"""
        prefix = f"ma:v2:{user_id}:"
        for thread_id in [key for key in self._active_runs if key.startswith(prefix)]:
            self.cancel_run(thread_id)
        agent = self._agents.pop(user_id, None)
        if agent:
            await agent.aclose()
        for thread_id in [key for key in self._session_locks if key.startswith(prefix)]:
            self._session_locks.pop(thread_id, None)

    # ── 流式执行 ──

    async def chat_stream(
        self,
        user_id: str,
        session_id: str,
        query: str,
        attachment_ids: list[str] | None = None,
    ) -> AsyncGenerator[dict, None]:
        """异步流式问答 — 逐事件 yield SSE dict

        Yields:
            dict: {event: str, data: dict}
        """
        agent = await self._get_or_create_agent(user_id)
        tid = self._make_tid(user_id, session_id)

        # 同一会话只允许一个图执行，避免重复提交造成 checkpoint 写竞争。
        session_lock = self._session_locks.setdefault(tid, asyncio.Lock())
        async with session_lock:
            current_attachments = []
            resource_context = ""
            execution_scope = None
            if self._workspace_service is not None:
                await self._workspace_service.require_workspace(user_id, session_id)
                current_attachments = await self._workspace_service.validate_attachments(
                    user_id, session_id, attachment_ids or [],
                )
                resource_context = await self._workspace_service.build_resource_context(
                    user_id, session_id, current_attachments,
                )
                execution_scope = await self._workspace_service.execution_scope(
                    user_id, session_id,
                )
            existing_messages = await self._message_repo.list_by_session(session_id)
            summary, conversation_context = await self._prepare_conversation_context(
                agent, session_id, existing_messages,
            )
            previous_turns = await self._turn_repo.list_by_session(session_id)
            previous_artifacts = [
                self._turn_to_artifact(turn) for turn in previous_turns[-3:]
            ]
            turn_id = str(uuid.uuid4())
            now = datetime.utcnow()
            await self._turn_repo.create(MultiAgentTurn(
                turn_id=turn_id,
                session_id=session_id,
                user_id=user_id,
                status="running",
                resolved_task=query,
                created_at=now,
                updated_at=now,
            ))
            await self._message_repo.create(SessionMessage(
                message_id=str(uuid.uuid4()),
                session_id=session_id,
                turn_id=turn_id,
                role="user",
                content=query,
                status="complete",
                metadata={
                    "attachments": [
                        {
                            "attachment_id": item.attachment_id,
                            "filename": item.filename,
                            "mime_type": item.mime_type,
                        }
                        for item in current_attachments
                    ],
                },
                created_at=now,
            ))
            if self._workspace_service is not None:
                await self._workspace_service.bind_attachments_to_turn(
                    current_attachments, turn_id,
                )
            await self._sync_message_count(session_id)

            cancellation_event = asyncio.Event()
            self._active_runs[tid] = cancellation_event
            finalized = False
            if execution_scope is not None:
                execution_scope = replace(
                    execution_scope, cancellation_event=cancellation_event,
                )
            scope_token = set_file_scope(execution_scope) if execution_scope else None
            try:
                yield {
                    "event": "turn_started",
                    "data": {"turn_id": turn_id, "session_id": session_id},
                }
                async for event in agent.arun_stream(
                    query,
                    thread_id=tid,
                    cancellation_event=cancellation_event,
                    turn_id=turn_id,
                    conversation_context=conversation_context,
                    conversation_summary=summary,
                    previous_artifacts=previous_artifacts,
                    resource_context=resource_context,
                ):
                    if event.get("event") == "done":
                        continue
                    yield event
                snapshot = await agent.get_run_snapshot(tid)
                await self._finalize_turn(
                    session_id, turn_id, snapshot, status="completed",
                )
                finalized = True
                yield {
                    "event": "done",
                    "data": {"session_id": session_id, "turn_id": turn_id},
                }
            except (asyncio.CancelledError, GeneratorExit):
                cancellation_event.set()
                if not finalized:
                    await asyncio.shield(self._finalize_interrupted_turn(
                        agent, tid, session_id, turn_id, status="cancelled",
                        message="本轮任务已中止。你可以发送“继续”恢复未完成步骤。",
                    ))
                raise
            except AgentRunCancelled:
                logger.info("Multi-agent run cancelled for user=%s", user_id[:8])
                await self._finalize_interrupted_turn(
                    agent, tid, session_id, turn_id, status="cancelled",
                    message="本轮任务已中止。你可以发送“继续”恢复未完成步骤。",
                )
                finalized = True
                yield {
                    "event": "cancelled",
                    "data": {
                        "turn_id": turn_id,
                        "message": "本轮任务已中止，可继续执行未完成步骤。",
                    },
                }
            except Exception as e:
                logger.exception("Multi-agent stream error for user=%s", user_id[:8])
                await self._finalize_interrupted_turn(
                    agent, tid, session_id, turn_id, status="failed",
                    message=f"本轮任务执行失败：{e}",
                    error_message=str(e),
                )
                finalized = True
                yield {
                    "event": "error",
                    "data": {
                        "code": "AGENT_ERROR",
                        "message": str(e),
                        "agent": "main",
                        "turn_id": turn_id,
                    },
                }
            finally:
                if scope_token is not None:
                    reset_file_scope(scope_token)
                cancellation_event.set()
                if self._active_runs.get(tid) is cancellation_event:
                    self._active_runs.pop(tid, None)

    def cancel_run(self, thread_id: str) -> bool:
        """Cooperatively stop the active graph run for a thread."""
        cancellation_event = self._active_runs.get(thread_id)
        if cancellation_event is None:
            return False
        cancellation_event.set()
        return True

    async def get_session_messages(self, user_id: str, session_id: str) -> list:
        """返回中央消息仓储中的完整可见对话，不暴露编排内部状态。"""
        del user_id
        return await self._message_repo.list_by_session(session_id)

    async def delete_session_state(self, user_id: str, session_id: str) -> None:
        """Delete the MainAgent checkpoint associated with a session."""
        tid = self._make_tid(user_id, session_id)
        if tid in self._active_runs:
            raise MultiAgentSessionBusyError("运行中的 Multi-Agent 会话不能删除")

        agent = await self._get_or_create_agent(user_id)
        checkpointer = agent._checkpointer
        if checkpointer is not None:
            if hasattr(checkpointer, "adelete_thread"):
                await checkpointer.adelete_thread(tid)
            elif hasattr(checkpointer, "delete_thread"):
                checkpointer.delete_thread(tid)
        await self._message_repo.delete_by_session(session_id)
        await self._turn_repo.delete_by_session(session_id)
        await self._summary_repo.delete(session_id)
        if self._workspace_service is not None:
            await self._workspace_service.delete_session_resources(user_id, session_id)
        self._session_locks.pop(tid, None)
        logger.info("Multi-Agent 会话状态已删除: thread_id=%s", tid)

    async def _prepare_conversation_context(
        self,
        agent: MainAgent,
        session_id: str,
        messages: list[SessionMessage],
    ) -> tuple[str, list[dict]]:
        """按轮数与 Token 预算裁剪最近消息，并增量更新较早历史摘要。"""
        summary_record = await self._summary_repo.get(session_id)
        summary_text = summary_record.summary if summary_record else ""
        covered = summary_record.covered_message_count if summary_record else 0
        recent_budget = self._max_context_tokens
        summary_budget = 0
        recent = self._select_recent_messages(messages, recent_budget)
        if summary_record is not None or len(recent) < len(messages):
            summary_budget = max(128, self._max_context_tokens // 3)
            recent_budget = max(128, self._max_context_tokens - summary_budget)
            recent = self._select_recent_messages(messages, recent_budget)
        cutoff = len(messages) - len(recent)
        if cutoff > covered:
            older_context = [
                self._message_to_context(message)
                for message in messages[covered:cutoff]
            ]
            try:
                summary_text = await agent.summarize_conversation(
                    summary_text, older_context,
                )
                await self._summary_repo.upsert(ConversationSummary(
                    session_id=session_id,
                    summary=summary_text,
                    covered_message_count=cutoff,
                ))
            except Exception as exc:
                logger.warning("Multi-Agent 会话摘要更新失败: %s", exc)
        if summary_budget:
            summary_text = self._truncate_to_token_budget(
                summary_text, summary_budget,
            )
        return summary_text, self._fit_messages_to_budget(recent, recent_budget)

    def _select_recent_messages(
        self,
        messages: list[SessionMessage],
        token_budget: int | None = None,
    ) -> list[SessionMessage]:
        budget = token_budget or self._max_context_tokens
        turns: list[list[SessionMessage]] = []
        for message in messages:
            if not turns or turns[-1][0].turn_id != message.turn_id:
                turns.append([])
            turns[-1].append(message)

        candidates = turns[-self._max_history_turns:]
        selected_turns: list[list[SessionMessage]] = []
        used_tokens = 0
        for turn_messages in reversed(candidates):
            estimated = sum(
                self._estimate_tokens(message.content) + 8
                for message in turn_messages
            )
            if selected_turns and used_tokens + estimated > budget:
                break
            selected_turns.append(turn_messages)
            used_tokens += estimated
        return [
            message
            for turn_messages in reversed(selected_turns)
            for message in turn_messages
        ]

    def _fit_messages_to_budget(
        self,
        messages: list[SessionMessage],
        token_budget: int,
    ) -> list[dict]:
        if not messages:
            return []
        estimates = [max(1, self._estimate_tokens(item.content)) for item in messages]
        if sum(estimates) + 8 * len(messages) <= token_budget:
            return [self._message_to_context(message) for message in messages]

        content_budget = max(len(messages), token_budget - 8 * len(messages))
        total = sum(estimates)
        allocations = [
            max(1, content_budget * estimate // total)
            for estimate in estimates
        ]
        contexts = []
        for message, allocation in zip(messages, allocations):
            context = self._message_to_context(message)
            context["content"] = self._truncate_to_token_budget(
                message.content, allocation,
            )
            contexts.append(context)
        return contexts

    @classmethod
    def _truncate_to_token_budget(cls, text: str, token_budget: int) -> str:
        if token_budget <= 0:
            return ""
        if cls._estimate_tokens(text) <= token_budget:
            return text
        marker = "…"
        marker_tokens = cls._estimate_tokens(marker)
        if marker_tokens >= token_budget:
            return marker
        low, high = 0, len(text)
        while low < high:
            middle = (low + high + 1) // 2
            if cls._estimate_tokens(text[:middle]) + marker_tokens <= token_budget:
                low = middle
            else:
                high = middle - 1
        return text[:low] + marker

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """不依赖特定 tokenizer 的保守估算：CJK 按字符，其他文本约 4 字符/token。"""
        cjk = sum(1 for char in text if "\u3400" <= char <= "\u9fff")
        other = max(0, len(text) - cjk)
        return cjk + math.ceil(other / 4)

    @staticmethod
    def _message_to_context(message: SessionMessage) -> dict:
        return {
            "message_id": message.message_id,
            "turn_id": message.turn_id,
            "role": message.role,
            "content": message.content,
            "status": message.status,
        }

    @staticmethod
    def _turn_to_artifact(turn: MultiAgentTurn) -> dict:
        return {
            "turn_id": turn.turn_id,
            "status": turn.status,
            "intent": turn.intent,
            "resolved_task": turn.resolved_task,
            "plan": turn.plan,
            "results": turn.results,
            "step_statuses": turn.step_statuses,
            "sources": turn.sources,
            "resume_step": turn.resume_step,
            "final_answer": turn.final_answer,
        }

    async def _finalize_turn(
        self,
        session_id: str,
        turn_id: str,
        snapshot: dict,
        *,
        status: str,
        assistant_message: str | None = None,
        error_message: str | None = None,
    ) -> None:
        existing = await self._turn_repo.get(turn_id)
        answer = assistant_message or str(snapshot.get("synthesized_answer", ""))
        await self._turn_repo.update(
            turn_id,
            status=status,
            intent=str(snapshot.get("intent") or (
                existing.intent if existing else "new_task"
            )),
            resolved_task=str(
                snapshot.get("resolved_task")
                or snapshot.get("user_task")
                or (existing.resolved_task if existing else "")
            ),
            plan=list(snapshot.get("plan") or (existing.plan if existing else [])),
            results=dict(snapshot.get("subagent_results") or (
                existing.results if existing else {}
            )),
            step_statuses=dict(snapshot.get("subagent_statuses") or (
                existing.step_statuses if existing else {}
            )),
            sources=list(snapshot.get("synthesis_sources") or (
                existing.sources if existing else []
            )),
            resume_step=int(snapshot.get("current_step_index", (
                existing.resume_step if existing else 0
            ))),
            final_answer=answer if status == "completed" else "",
            error_message=error_message,
            completed_at=datetime.utcnow(),
        )
        if answer:
            await self._message_repo.create(SessionMessage(
                message_id=str(uuid.uuid4()),
                session_id=session_id,
                turn_id=turn_id,
                role="assistant",
                content=answer,
                status=(
                    "complete" if status == "completed"
                    else "cancelled" if status == "cancelled"
                    else "failed"
                ),
                metadata={
                    "sources": list(snapshot.get("synthesis_sources", [])),
                    "confidence": snapshot.get("synthesis_confidence", "medium"),
                },
            ))
        await self._sync_message_count(session_id)

    async def _finalize_interrupted_turn(
        self,
        agent: MainAgent,
        thread_id: str,
        session_id: str,
        turn_id: str,
        *,
        status: str,
        message: str,
        error_message: str | None = None,
    ) -> None:
        try:
            snapshot = await agent.get_run_snapshot(thread_id)
            snapshot_turn_id = str(snapshot.get("turn_id", ""))
            if snapshot_turn_id and snapshot_turn_id != turn_id:
                logger.info(
                    "忽略上一轮编排快照: expected_turn=%s snapshot_turn=%s",
                    turn_id,
                    snapshot_turn_id,
                )
                snapshot = {}
        except Exception as exc:
            logger.warning("读取中断任务快照失败: %s", exc)
            snapshot = {}
        await self._finalize_turn(
            session_id,
            turn_id,
            snapshot,
            status=status,
            assistant_message=message,
            error_message=error_message,
        )

    async def _sync_message_count(self, session_id: str) -> None:
        if self._session_service is None:
            return
        await self._session_service.set_message_count(
            session_id,
            await self._message_repo.count_by_session(session_id),
        )

    # ── 注册 subagent ──

    @property
    def registry(self) -> SubAgentRegistry:
        return self._registry

    async def reconfigure(
        self,
        *,
        sub_agent_registry: SubAgentRegistry,
        model_kwargs: dict,
    ) -> None:
        """发布新的模型与工具 Registry，后续请求创建新 Agent。"""
        self._registry = sub_agent_registry
        self._model_kwargs = dict(model_kwargs)
        self._retired_agents.extend(self._agents.values())
        self._agents = {}
        logger.info("Multi-Agent 运行时配置已刷新")

    # ── 辅助 ──

    @staticmethod
    def _make_tid(user_id: str, session_id: str) -> str:
        """构造 LangGraph thread_id"""
        return f"ma:v2:{user_id}:{session_id}"

    def _sqlite_path_for_user(self, user_id: str) -> str | None:
        """从配置的基础文件名派生稳定的用户独立 SQLite 文件。"""
        if self._store_type != "sqlite":
            return self._sqlite_path

        configured_path = self._sqlite_path or "./data/multi_agent.db"
        if configured_path == ":memory:":
            return configured_path

        base_path = Path(configured_path)
        suffix = base_path.suffix or ".db"
        user_key = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:16]
        return str(base_path.with_name(f"{base_path.stem}-{user_key}{suffix}"))

    async def close_all(self):
        """关闭所有用户实例"""
        for user_id in list(self._agents.keys()):
            await self.close_user(user_id)
        retired_agents = self._retired_agents
        self._retired_agents = []
        for agent in retired_agents:
            try:
                await agent.aclose()
            except Exception as exc:
                logger.warning("关闭退役 MainAgent 失败: %s", exc)
        self._session_locks.clear()
        for cancellation_event in self._active_runs.values():
            cancellation_event.set()
        self._active_runs.clear()
