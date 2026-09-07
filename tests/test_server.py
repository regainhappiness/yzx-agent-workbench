"""FastAPI 集成测试 — 使用持久化动态 Key"""

import pytest
from httpx import AsyncClient


# ═══════════════════════════════════════════════════════════════
# 健康检查 (无认证)
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_health_live(client: AsyncClient):
    resp = await client.get("/health/live")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_health_ready(client: AsyncClient):
    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ═══════════════════════════════════════════════════════════════
# 认证
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_no_auth_returns_401(client: AsyncClient):
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 401
    data = resp.json()
    assert data["error"]["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.asyncio
async def test_invalid_key_returns_401(client: AsyncClient):
    resp = await client.get(
        "/api/v1/me",
        headers={"Authorization": "Bearer sk-invalid"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_valid_admin_key_works(client: AsyncClient, admin_headers):
    resp = await client.get("/api/v1/me", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "admin"


@pytest.mark.asyncio
async def test_valid_user_key_works(client: AsyncClient, user_headers):
    resp = await client.get("/api/v1/me", headers=user_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "user"


# ═══════════════════════════════════════════════════════════════
# 会话
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_session(client: AsyncClient, user_headers):
    resp = await client.post(
        "/api/v1/sessions",
        json={"title": "测试会话", "session_type": "chat"},
        headers=user_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "session_id" in data
    assert data["title"] == "测试会话"
    assert data["session_type"] == "chat"
    assert data["message_count"] == 0


@pytest.mark.asyncio
async def test_list_sessions(client: AsyncClient, user_headers):
    # 先创建一个
    await client.post(
        "/api/v1/sessions",
        json={"session_type": "chat"},
        headers=user_headers,
    )
    resp = await client.get(
        "/api/v1/sessions?session_type=chat", headers=user_headers,
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_session_type_is_required(client: AsyncClient, user_headers):
    resp = await client.post(
        "/api/v1/sessions",
        json={"title": "缺少类型"},
        headers=user_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_session_lists_are_filtered_by_type(
    client: AsyncClient, user_headers,
):
    chat = await client.post(
        "/api/v1/sessions",
        json={"title": "Chat", "session_type": "chat"},
        headers=user_headers,
    )
    multi_agent = await client.post(
        "/api/v1/sessions",
        json={"title": "Multi-Agent", "session_type": "multi_agent"},
        headers=user_headers,
    )

    chat_sessions = await client.get(
        "/api/v1/sessions?session_type=chat", headers=user_headers,
    )
    multi_agent_sessions = await client.get(
        "/api/v1/sessions?session_type=multi_agent", headers=user_headers,
    )

    assert {item["session_id"] for item in chat_sessions.json()} == {
        chat.json()["session_id"],
    }
    assert {item["session_id"] for item in multi_agent_sessions.json()} == {
        multi_agent.json()["session_id"],
    }


@pytest.mark.asyncio
async def test_chat_rejects_multi_agent_session(
    client: AsyncClient, user_headers,
):
    session = await client.post(
        "/api/v1/sessions",
        json={"title": "Multi-Agent", "session_type": "multi_agent"},
        headers=user_headers,
    )

    resp = await client.post(
        "/api/v1/chat",
        json={"query": "你好", "session_id": session.json()["session_id"]},
        headers=user_headers,
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_multi_agent_rejects_chat_session(
    client: AsyncClient, user_headers,
):
    session = await client.post(
        "/api/v1/sessions",
        json={"title": "Chat", "session_type": "chat"},
        headers=user_headers,
    )

    resp = await client.post(
        "/api/v1/multi-agent/chat/stream",
        json={"query": "分析任务", "session_id": session.json()["session_id"]},
        headers=user_headers,
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_messages_route_to_multi_agent_service(
    client: AsyncClient, user_headers, monkeypatch,
):
    from langchain_core.messages import AIMessage, HumanMessage
    from src.server.main import app

    session = await client.post(
        "/api/v1/sessions",
        json={"title": "Multi-Agent", "session_type": "multi_agent"},
        headers=user_headers,
    )
    session_id = session.json()["session_id"]

    async def multi_agent_messages(user_id: str, requested_session_id: str):
        assert user_id
        assert requested_session_id == session_id
        return [
            HumanMessage(content="分析任务"),
            AIMessage(content="最终结果"),
        ]

    def unexpected_chat_messages(*_args):
        raise AssertionError("multi-agent history must not use ChatService")

    monkeypatch.setattr(
        app.state.multi_agent_service,
        "get_session_messages",
        multi_agent_messages,
    )
    monkeypatch.setattr(
        app.state.chat_service,
        "get_session_messages",
        unexpected_chat_messages,
    )

    resp = await client.get(
        f"/api/v1/sessions/{session_id}/messages",
        headers=user_headers,
    )

    assert resp.status_code == 200
    assert [(item["role"], item["content"]) for item in resp.json()] == [
        ("user", "分析任务"),
        ("assistant", "最终结果"),
    ]


@pytest.mark.asyncio
async def test_regular_user_can_rename_own_session(
    client: AsyncClient, user_headers,
):
    resp = await client.post(
        "/api/v1/sessions",
        json={"title": "旧标题", "session_type": "chat"},
        headers=user_headers,
    )
    session_id = resp.json()["session_id"]

    resp = await client.patch(
        f"/api/v1/sessions/{session_id}",
        json={"title": "新标题"},
        headers=user_headers,
    )

    assert resp.status_code == 200
    assert resp.json()["title"] == "新标题"


@pytest.mark.asyncio
async def test_cannot_rename_another_users_session(
    client: AsyncClient, user_headers, admin_headers,
):
    resp = await client.post(
        "/api/v1/sessions",
        json={"title": "用户会话", "session_type": "chat"},
        headers=user_headers,
    )
    session_id = resp.json()["session_id"]

    resp = await client.patch(
        f"/api/v1/sessions/{session_id}",
        json={"title": "越权修改"},
        headers=admin_headers,
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_session(client: AsyncClient, user_headers):
    resp = await client.post(
        "/api/v1/sessions",
        json={"session_type": "chat"},
        headers=user_headers,
    )
    session_id = resp.json()["session_id"]

    resp = await client.delete(
        f"/api/v1/sessions/{session_id}",
        headers=user_headers,
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_multi_agent_session_cleans_checkpoint(
    client: AsyncClient, user_headers, monkeypatch,
):
    from src.server.main import app

    resp = await client.post(
        "/api/v1/sessions",
        json={"title": "待删除任务", "session_type": "multi_agent"},
        headers=user_headers,
    )
    session_id = resp.json()["session_id"]
    deleted = []

    async def _record_delete(user_id, requested_id):
        deleted.append((user_id, requested_id))
    monkeypatch.setattr(
        app.state.multi_agent_service,
        "delete_session_state",
        _record_delete,
    )

    resp = await client.delete(
        f"/api/v1/sessions/{session_id}", headers=user_headers,
    )

    assert resp.status_code == 204
    assert deleted and deleted[0][1] == session_id
    list_resp = await client.get(
        "/api/v1/sessions?session_type=multi_agent", headers=user_headers,
    )
    assert session_id not in {
        item["session_id"] for item in list_resp.json()
    }


@pytest.mark.asyncio
async def test_delete_running_multi_agent_session_keeps_history(
    client: AsyncClient, user_headers, monkeypatch,
):
    from src.server.main import app
    from src.server.services.multi_agent_service import (
        MultiAgentSessionBusyError,
    )

    resp = await client.post(
        "/api/v1/sessions",
        json={"title": "运行中任务", "session_type": "multi_agent"},
        headers=user_headers,
    )
    session_id = resp.json()["session_id"]

    async def reject_delete(_user_id, _session_id):
        raise MultiAgentSessionBusyError("运行中的 Multi-Agent 会话不能删除")

    monkeypatch.setattr(
        app.state.multi_agent_service,
        "delete_session_state",
        reject_delete,
    )

    resp = await client.delete(
        f"/api/v1/sessions/{session_id}", headers=user_headers,
    )

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "SESSION_BUSY"
    list_resp = await client.get(
        "/api/v1/sessions?session_type=multi_agent", headers=user_headers,
    )
    assert session_id in {
        item["session_id"] for item in list_resp.json()
    }


@pytest.mark.asyncio
async def test_cannot_access_other_user_session(
    client: AsyncClient, user_headers, admin_headers,
):
    """验证用户隔离: user 创建会话, admin 不能访问"""
    # user 创建会话
    resp = await client.post(
        "/api/v1/sessions",
        json={"session_type": "chat"},
        headers=user_headers,
    )
    session_id = resp.json()["session_id"]

    # 另一个用户 (admin) 尝试访问 → 应返回 404 (不暴露存在性)
    resp = await client.get(
        f"/api/v1/sessions/{session_id}/messages",
        headers=admin_headers,
    )
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════
# MCP 工具接线
# ═══════════════════════════════════════════════════════════════

class _FakeMcpAdapter:
    def __init__(self, config):
        self.config = config

    async def discover(self):
        if not self.config.enabled:
            return [], {}
        from langchain_core.tools import tool

        @tool
        async def k_search(q: str) -> str:
            """fake mcp tool"""
            return "x"
        k_search.name = "k_search"
        return [k_search], {"k_search": {"category": "mcp", "tags": ["mcp", "k"], "version": "1.0.0"}}

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_lifespan_wires_mcp_tools_when_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("REPOSITORY_BACKEND", "memory")
    monkeypatch.setenv("BAILIAN_API_KEY", "")
    monkeypatch.setenv("MILVUS_HOST", "")
    monkeypatch.setenv("MCP_CONFIG_PATH", str(tmp_path / "mcp.json"))
    (tmp_path / "mcp.json").write_text(
        '{"enabled": true, "servers": [{"name": "k", "transport": "stdio", "command": "python"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr("src.server.main.McpAdapter", _FakeMcpAdapter)

    from src.server.main import app
    async with app.router.lifespan_context(app):
        assert len(app.state.mcp_tools) == 1
        assert app.state.multi_agent_service is not None


# ═══════════════════════════════════════════════════════════════
# 问答 (fallback 模式 — 无外部 LLM)
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_chat_sync(client: AsyncClient, user_headers):
    """同步问答 — 在无 API Key 时使用 fallback 模式"""
    resp = await client.post(
        "/api/v1/chat",
        json={"query": "你好"},
        headers=user_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "session_id" in data


@pytest.mark.asyncio
async def test_chat_with_existing_session(
    client: AsyncClient, user_headers,
):
    """在已有会话中问答"""
    # 创建会话
    resp = await client.post(
        "/api/v1/sessions",
        json={"title": "Chat", "session_type": "chat"},
        headers=user_headers,
    )
    session_id = resp.json()["session_id"]

    # 在该会话中问答
    resp = await client.post(
        "/api/v1/chat",
        json={"query": "你好", "session_id": session_id},
        headers=user_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session_id


@pytest.mark.asyncio
async def test_chat_stream(client: AsyncClient, user_headers):
    """SSE 流式问答 — 验证事件类型"""
    resp = await client.post(
        "/api/v1/chat/stream",
        json={"query": "你好"},
        headers=user_headers,
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")

    # 解析 SSE 事件
    import json
    events = []
    current_event = None
    for line in resp.text.split("\n"):
        line = line.strip()
        if line.startswith("event: "):
            current_event = line[7:]
        elif line.startswith("data: ") and current_event:
            data = json.loads(line[6:])
            events.append((current_event, data))
            current_event = None

    # 验证事件顺序: start → token* → done
    assert len(events) >= 2
    assert events[0][0] == "start"
    assert events[-1][0] == "done"


@pytest.mark.asyncio
async def test_chat_query_too_long(client: AsyncClient, user_headers):
    """验证 query 长度限制"""
    resp = await client.post(
        "/api/v1/chat",
        json={"query": "x" * 5000},
        headers=user_headers,
    )
    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════
# 用户管理 (admin only)
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_admin_can_create_user(client: AsyncClient, admin_headers):
    resp = await client.post(
        "/api/v1/users",
        json={"name": "Test User", "role": "user"},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test User"
    assert data["role"] == "user"


@pytest.mark.asyncio
async def test_key_created_for_admin_member_has_admin_permissions(
    client: AsyncClient,
    admin_headers,
):
    """管理员成员的新 Key 应能继续访问管理员接口。"""
    create_user_resp = await client.post(
        "/api/v1/users",
        json={"name": "Second Admin", "role": "admin"},
        headers=admin_headers,
    )
    assert create_user_resp.status_code == 201

    create_key_resp = await client.post(
        "/api/v1/api-keys",
        json={"user_id": create_user_resp.json()["user_id"]},
        headers=admin_headers,
    )
    assert create_key_resp.status_code == 201

    new_admin_headers = {
        "Authorization": f"Bearer {create_key_resp.json()['key']}"
    }
    list_users_resp = await client.get(
        "/api/v1/users",
        headers=new_admin_headers,
    )
    assert list_users_resp.status_code == 200


@pytest.mark.asyncio
async def test_user_cannot_create_user(client: AsyncClient, user_headers):
    """普通用户不能创建用户"""
    resp = await client.post(
        "/api/v1/users",
        json={"name": "Hacker", "role": "admin"},
        headers=user_headers,
    )
    assert resp.status_code == 403
