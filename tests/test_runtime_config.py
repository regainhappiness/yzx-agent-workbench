from types import SimpleNamespace

import pytest

from src.server.exceptions import ValidationError
from src.server.repositories.memory import InMemoryRuntimeConfigRepo
from src.server.repositories.base import RuntimeConfigRecord
from src.server.repositories.sqlite import SqliteDb, SqliteRuntimeConfigRepo
from src.server.services.runtime_config_service import RuntimeConfigService
from src.server.services.secret_cipher import SecretCipher
from src.tools.mcp import McpConfig


class _FakeModel:
    async def ainvoke(self, _messages):
        return SimpleNamespace(content="OK")


class _ModelFactory:
    def __init__(self):
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeModel()


class _FakeMcpAdapter:
    instances = []

    def __init__(self, config):
        self.config = config
        self.closed = False
        self.server_statuses = {}
        self.__class__.instances.append(self)

    async def discover(self):
        tools = []
        metas = {}
        for server in self.config.servers:
            if not server.enabled:
                self.server_statuses[server.name] = {
                    "status": "disabled", "error": None, "tool_count": 0,
                }
                continue
            tool = SimpleNamespace(name=f"{server.name}_search")
            tools.append(tool)
            metas[tool.name] = {
                "category": "mcp",
                "tags": ["mcp", server.name],
                "version": "1.0.0",
                "subagents": server.subagents,
            }
            self.server_statuses[server.name] = {
                "status": "connected", "error": None, "tool_count": 1,
            }
        return tools, metas

    async def close(self):
        self.closed = True


class _FakeChatService:
    def __init__(self):
        self.configs = []

    async def reconfigure_model(self, config):
        self.configs.append(config)


class _FakeMultiAgentService:
    def __init__(self):
        self.configs = []

    async def reconfigure(self, **kwargs):
        self.configs.append(kwargs)


@pytest.fixture
def runtime_service(monkeypatch):
    for key in (
        "LLM_PROVIDER", "OPENAI_API_KEY", "DEEPSEEK_API_KEY",
        "ANTHROPIC_API_KEY", "LLM_MODEL", "LLM_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    _FakeMcpAdapter.instances = []
    factory = _ModelFactory()
    service = RuntimeConfigService(
        repository=InMemoryRuntimeConfigRepo(),
        cipher=SecretCipher("runtime-config-tests"),
        model_factory=factory,
        mcp_adapter_factory=_FakeMcpAdapter,
    )
    return service, factory


@pytest.mark.asyncio
async def test_llm_runtime_config_switches_services_without_environment(runtime_service):
    service, factory = runtime_service
    await service.initialize(McpConfig())
    chat = _FakeChatService()
    multi = _FakeMultiAgentService()
    service.bind_services(chat, multi)

    saved = await service.save_llm({
        "provider": "deepseek",
        "model_name": "deepseek-chat",
        "api_key": "sk-runtime-secret",
        "base_url": "https://api.deepseek.com",
        "temperature": 0.2,
        "max_tokens": 2048,
    })

    assert saved["configured"] is True
    assert saved["api_key_hint"].endswith("cret")
    assert factory.calls[-1]["api_key"] == "sk-runtime-secret"
    assert chat.configs[-1]["provider"] == "deepseek"
    assert multi.configs[-1]["model_kwargs"]["model"] == "deepseek-chat"

    # 留空密钥代表保留原密钥，而不是清空配置。
    await service.save_llm({
        "provider": "deepseek",
        "model_name": "deepseek-reasoner",
        "api_key": None,
        "base_url": None,
        "temperature": 0.1,
        "max_tokens": None,
    })
    assert factory.calls[-1]["api_key"] == "sk-runtime-secret"


@pytest.mark.asyncio
async def test_llm_provider_switch_requires_a_new_provider_key(runtime_service):
    service, _ = runtime_service
    await service.initialize(McpConfig())
    await service.save_llm({
        "provider": "deepseek",
        "model_name": "deepseek-chat",
        "api_key": "sk-deepseek",
        "base_url": "https://api.deepseek.com",
        "temperature": 0.2,
        "max_tokens": None,
    })

    with pytest.raises(ValidationError, match="Provider"):
        await service.save_llm({
            "provider": "openai",
            "model_name": "gpt-4o-mini",
            "api_key": None,
            "base_url": None,
            "temperature": 0.2,
            "max_tokens": None,
        })


@pytest.mark.asyncio
async def test_environment_llm_is_imported_and_encrypted(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-environment-secret")
    repo = InMemoryRuntimeConfigRepo()
    cipher = SecretCipher("environment-import-test")
    service = RuntimeConfigService(
        repository=repo,
        cipher=cipher,
        model_factory=_ModelFactory(),
        mcp_adapter_factory=_FakeMcpAdapter,
    )

    await service.initialize(McpConfig())

    view = await service.get_llm()
    stored = await repo.get("llm-default")
    assert view["source"] == "environment"
    assert stored is not None
    assert "sk-environment-secret" not in stored.payload
    assert cipher.decrypt_json(stored.payload)["api_key"] == "sk-environment-secret"


@pytest.mark.asyncio
async def test_mcp_config_can_be_created_toggled_listed_and_deleted(runtime_service):
    service, _ = runtime_service
    await service.initialize(McpConfig())
    multi = _FakeMultiAgentService()
    service.bind_services(_FakeChatService(), multi)

    created = await service.create_mcp({
        "name": "knowledge",
        "transport": "streamable-http",
        "enabled": True,
        "url": "https://example.com/mcp",
        "headers": {"Authorization": "Bearer secret"},
        "env": {},
        "args": [],
        "timeout_seconds": 20,
        "allowed_tools": ["*"],
        "subagents": ["general_assistant"],
    })

    assert created["status"] == "connected"
    assert created["tool_count"] == 1
    assert created["headers"] == {"Authorization": "••••••••"}
    assert multi.configs[-1]["sub_agent_registry"].count == 3

    disabled = await service.set_mcp_enabled(created["config_id"], False)
    assert disabled["enabled"] is False
    assert disabled["status"] == "disabled"

    await service.delete_mcp(created["config_id"])
    assert await service.list_mcp() == []


@pytest.mark.asyncio
async def test_mcp_file_config_is_imported_only_when_database_is_empty(runtime_service):
    service, _ = runtime_service
    await service.initialize(McpConfig.model_validate({
        "enabled": True,
        "servers": [{
            "name": "web",
            "transport": "streamable-http",
            "url": "https://example.com/mcp",
        }],
    }))

    imported = await service.list_mcp()
    assert [item["name"] for item in imported] == ["web"]
    assert imported[0]["status"] == "connected"


@pytest.mark.asyncio
async def test_globally_disabled_mcp_file_does_not_connect(runtime_service):
    service, _ = runtime_service
    await service.initialize(McpConfig.model_validate({
        "enabled": False,
        "servers": [{
            "name": "disabled-by-root",
            "transport": "streamable-http",
            "enabled": True,
            "url": "https://example.com/mcp",
        }],
    }))

    configs = await service.list_mcp()
    assert configs[0]["enabled"] is False
    assert configs[0]["status"] == "disabled"
    assert _FakeMcpAdapter.instances[-1].config.enabled is False


@pytest.mark.asyncio
async def test_sqlite_runtime_config_repository_roundtrip(tmp_path):
    db = SqliteDb(str(tmp_path / "runtime-config.db"))
    await db.init_schema()
    repo = SqliteRuntimeConfigRepo(db)

    first = await repo.upsert(RuntimeConfigRecord(
        config_id="llm-default",
        category="llm",
        name="默认模型",
        enabled=True,
        payload="encrypted-payload",
        status="active",
    ))
    second = await repo.upsert(RuntimeConfigRecord(
        config_id="llm-default",
        category="llm",
        name="默认模型",
        enabled=True,
        payload="new-encrypted-payload",
        status="active",
    ))

    assert first.revision == 1
    assert second.revision == 2
    assert (await repo.list_by_category("llm"))[0].payload == "new-encrypted-payload"
    await db.close()
