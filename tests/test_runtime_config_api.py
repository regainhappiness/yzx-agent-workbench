"""Runtime configuration API integration tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_runtime_config_requires_admin(
    client: AsyncClient,
    user_headers: dict[str, str],
):
    response = await client.get("/api/v1/admin/config/llm", headers=user_headers)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_manage_a_disabled_mcp_config(
    client: AsyncClient,
    admin_headers: dict[str, str],
):
    llm_response = await client.get(
        "/api/v1/admin/config/llm",
        headers=admin_headers,
    )
    assert llm_response.status_code == 200
    assert "api_key" not in llm_response.json()

    create_response = await client.post(
        "/api/v1/admin/config/mcp",
        headers=admin_headers,
        json={
            "name": "disabled-test-server",
            "transport": "streamable-http",
            "enabled": False,
            "url": "https://example.com/mcp",
            "headers": {"Authorization": "Bearer test-secret"},
            "timeout_seconds": 10,
            "allowed_tools": ["*"],
            "subagents": ["general_assistant"],
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["status"] == "disabled"
    assert created["headers"]["Authorization"] == "••••••••"

    list_response = await client.get(
        "/api/v1/admin/config/mcp",
        headers=admin_headers,
    )
    assert list_response.status_code == 200
    assert any(item["config_id"] == created["config_id"] for item in list_response.json())

    delete_response = await client.delete(
        f"/api/v1/admin/config/mcp/{created['config_id']}",
        headers=admin_headers,
    )
    assert delete_response.status_code == 204
