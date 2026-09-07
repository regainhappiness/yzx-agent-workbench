import sqlite3

import pytest

from src.server.exceptions import NotFoundError
from src.server.repositories.memory import InMemorySessionRepo
from src.server.repositories.sqlite import SqliteDb, SqliteSessionRepo
from src.server.services.session_service import SessionService


@pytest.mark.asyncio
async def test_regular_user_can_rename_own_session():
    service = SessionService(InMemorySessionRepo())
    session = await service.create_session("user-1", "chat", "旧标题")

    updated = await service.rename_session(
        "user-1", session.session_id, "新标题",
    )

    assert updated.title == "新标题"


@pytest.mark.asyncio
async def test_user_cannot_rename_another_users_session():
    service = SessionService(InMemorySessionRepo())
    session = await service.create_session("user-1", "chat", "原标题")

    with pytest.raises(NotFoundError):
        await service.rename_session(
            "user-2", session.session_id, "越权修改",
        )

    unchanged = await service.get_session(session.session_id)
    assert unchanged.title == "原标题"


@pytest.mark.asyncio
async def test_sqlite_migrates_and_classifies_legacy_sessions(tmp_path):
    db_path = tmp_path / "mka.db"
    with sqlite3.connect(db_path) as legacy_db:
        legacy_db.execute(
            "CREATE TABLE sessions ("
            "session_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT, "
            "message_count INTEGER NOT NULL DEFAULT 0, "
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        legacy_db.executemany(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("chat-session", "user-1", "Chat", 2, "2026-01-01", "2026-01-01"),
                ("multi-session", "user-1", "Multi", 2, "2026-01-01", "2026-01-01"),
            ],
        )

    agent_db_path = tmp_path / "multi_agent-0123456789abcdef.db"
    with sqlite3.connect(agent_db_path) as agent_db:
        agent_db.execute("CREATE TABLE checkpoints (thread_id TEXT)")
        agent_db.execute(
            "INSERT INTO checkpoints VALUES (?)", ("user-1:multi-session",),
        )

    db = SqliteDb(str(db_path))
    await db.init_schema()
    service = SessionService(SqliteSessionRepo(db))

    assert [session.session_id for session in await service.list_sessions(
        "user-1", "chat",
    )] == ["chat-session"]
    assert [session.session_id for session in await service.list_sessions(
        "user-1", "multi_agent",
    )] == ["multi-session"]
    await db.close()
