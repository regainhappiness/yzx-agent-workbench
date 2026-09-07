import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.server.repositories.memory import (
    InMemoryMultiAgentAttachmentRepo,
    InMemoryMultiAgentWorkspaceRepo,
    InMemorySessionRepo,
)
from src.server.repositories.base import MultiAgentAttachment, MultiAgentWorkspace
from src.server.repositories.sqlite import (
    SqliteDb,
    SqliteMultiAgentAttachmentRepo,
    SqliteMultiAgentWorkspaceRepo,
    SqliteSessionRepo,
)
from src.server.services.multi_agent_workspace_service import (
    MultiAgentWorkspaceService,
)
from src.server.services.session_service import SessionService
from src.tools.mcp.adapter import McpConnection, _scoped_arguments
from src.tools.mcp.config import McpServerConfig
from src.tools.mcp.scope import ExecutionFileScope, reset_file_scope, set_file_scope


@pytest.mark.asyncio
async def test_sqlite_workspace_and_attachment_repositories_roundtrip(tmp_path):
    db = SqliteDb(str(tmp_path / "mka.db"))
    await db.init_schema()
    sessions = SqliteSessionRepo(db)
    workspaces = SqliteMultiAgentWorkspaceRepo(db)
    attachments = SqliteMultiAgentAttachmentRepo(db)
    session = await sessions.create("user-1", "文件任务", "multi_agent")
    root = (tmp_path / "workspace").resolve()
    root.mkdir()

    saved_workspace = await workspaces.upsert(MultiAgentWorkspace(
        session_id=session.session_id,
        user_id="user-1",
        root_path=str(root),
        permission="read_only",
    ))
    saved_attachment = await attachments.create(MultiAgentAttachment(
        attachment_id="attachment-1",
        session_id=session.session_id,
        user_id="user-1",
        filename="report.pdf",
        storage_path=str(tmp_path / "report.pdf"),
        mime_type="application/pdf",
        file_size=4,
        file_hash="hash",
    ))
    await attachments.bind_to_turn([saved_attachment.attachment_id], "turn-1")

    assert (await workspaces.get(session.session_id)) == saved_workspace
    listed = await attachments.list_by_session(session.session_id)
    assert listed[0].turn_id == "turn-1"
    await db.close()


@pytest.mark.asyncio
async def test_workspace_and_attachments_are_session_scoped(tmp_path):
    session_service = SessionService(InMemorySessionRepo())
    session = await session_service.create_session("user-1", "multi_agent", "文件任务")
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    service = MultiAgentWorkspaceService(
        workspace_repo=InMemoryMultiAgentWorkspaceRepo(),
        attachment_repo=InMemoryMultiAgentAttachmentRepo(),
        session_service=session_service,
        storage_dir=str(tmp_path / "attachments"),
        allowed_roots=[str(tmp_path)],
    )

    workspace = await service.configure_workspace(
        "user-1", session.session_id, str(workspace_root), "read_write",
    )
    attachment = await service.save_attachment(
        user_id="user-1",
        session_id=session.session_id,
        filename="notes.md",
        content=b"# Notes",
        mime_type="text/markdown",
        source="file_picker",
    )

    scope = await service.execution_scope("user-1", session.session_id)
    assert workspace.root_path == str(workspace_root.resolve())
    assert scope.can_write(workspace_root / "result.md") is True
    assert scope.can_write(Path(attachment.storage_path)) is False
    assert scope.can_read(Path(attachment.storage_path)) is True
    context = await service.build_resource_context(
        "user-1", session.session_id, [attachment],
    )
    assert "notes.md" in context
    assert "附件始终只读" in context
    assert "PDF/Office Parser 尚未接入" in context


@pytest.mark.asyncio
async def test_workspace_path_is_locked_after_conversation_starts(tmp_path):
    session_service = SessionService(InMemorySessionRepo())
    session = await session_service.create_session("user-1", "multi_agent", "锁定工作区")
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    service = MultiAgentWorkspaceService(
        workspace_repo=InMemoryMultiAgentWorkspaceRepo(),
        attachment_repo=InMemoryMultiAgentAttachmentRepo(),
        session_service=session_service,
        storage_dir=str(tmp_path / "attachments"),
        allowed_roots=[str(tmp_path)],
    )
    await service.configure_workspace(
        "user-1", session.session_id, str(first), "read_only",
    )
    await session_service.set_message_count(session.session_id, 1)

    with pytest.raises(Exception) as exc_info:
        await service.configure_workspace(
            "user-1", session.session_id, str(second), "read_only",
        )
    assert getattr(exc_info.value, "code", "") == "WORKSPACE_LOCKED"


def test_session_scoped_mcp_guard_enforces_paths_and_write_permission(tmp_path):
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir()
    attachment = (tmp_path / "attachment.png").resolve()
    attachment.write_bytes(b"image")
    cfg = McpServerConfig(
        name="filesystem",
        transport="stdio",
        command="filesystem-server",
        subagents=["workspace_file_agent"],
    )
    token = set_file_scope(ExecutionFileScope(
        session_id="session-1",
        workspace_root=workspace,
        permission="read_only",
        attachment_paths=frozenset({attachment}),
    ))
    try:
        arguments, error = _scoped_arguments(
            cfg, "read_file", {"path": str(attachment)},
        )
        assert error is None
        assert arguments["path"] == str(attachment)

        _, error = _scoped_arguments(
            cfg, "write_file", {"path": "result.md", "content": "ok"},
        )
        assert "只读权限" in str(error)

        _, error = _scoped_arguments(
            cfg, "read_file", {"path": str(tmp_path / "outside.txt")},
        )
        assert "超出当前会话授权范围" in str(error)
    finally:
        reset_file_scope(token)


@pytest.mark.asyncio
async def test_session_cancel_interrupts_running_mcp_call(tmp_path):
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir()
    cancel_event = asyncio.Event()

    class SlowSession:
        async def call_tool(self, _name, _arguments):
            await asyncio.Event().wait()
            return SimpleNamespace(content=[])

    cfg = McpServerConfig(
        name="filesystem",
        transport="stdio",
        command="filesystem-server",
        subagents=["workspace_file_agent"],
    )
    connection = McpConnection(cfg)
    connection._session = SlowSession()
    connection.available = True
    token = set_file_scope(ExecutionFileScope(
        session_id="session-1",
        workspace_root=workspace,
        permission="read_only",
        attachment_paths=frozenset(),
        cancellation_event=cancel_event,
    ))
    try:
        call = asyncio.create_task(connection.call("read_file", {"path": "notes.md"}))
        await asyncio.sleep(0)
        cancel_event.set()
        assert "用户中止" in await asyncio.wait_for(call, timeout=1)
    finally:
        reset_file_scope(token)


@pytest.mark.asyncio
async def test_workspace_api_accepts_general_files_without_parsing_pdf(
    client, user_headers,
):
    session_response = await client.post(
        "/api/v1/sessions",
        json={"title": "附件任务", "session_type": "multi_agent"},
        headers=user_headers,
    )
    session_id = session_response.json()["session_id"]
    roots = await client.get(
        "/api/v1/multi-agent/workspace-roots", headers=user_headers,
    )
    root_path = roots.json()["roots"][0]
    configured = await client.put(
        f"/api/v1/multi-agent/sessions/{session_id}/workspace",
        json={"root_path": root_path, "permission": "read_only"},
        headers=user_headers,
    )
    assert configured.status_code == 200

    text_upload = await client.post(
        f"/api/v1/multi-agent/sessions/{session_id}/attachments",
        files={"file": ("config.yaml", b"enabled: true", "application/yaml")},
        data={"source": "file_picker"},
        headers=user_headers,
    )
    pdf_upload = await client.post(
        f"/api/v1/multi-agent/sessions/{session_id}/attachments",
        files={"file": ("report.pdf", b"%PDF-1.7\n", "application/pdf")},
        data={"source": "file_picker"},
        headers=user_headers,
    )

    assert text_upload.status_code == 201
    assert text_upload.json()["kind"] == "text"
    assert pdf_upload.status_code == 201
    assert pdf_upload.json()["kind"] == "pdf_office_unparsed"
    assert "storage_path" not in pdf_upload.json()


@pytest.mark.asyncio
async def test_multi_agent_stream_requires_configured_workspace(client, user_headers):
    session_response = await client.post(
        "/api/v1/sessions",
        json={"title": "尚未选目录", "session_type": "multi_agent"},
        headers=user_headers,
    )
    response = await client.post(
        "/api/v1/multi-agent/chat/stream",
        json={"query": "分析任务", "session_id": session_response.json()["session_id"]},
        headers=user_headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "WORKSPACE_REQUIRED"
