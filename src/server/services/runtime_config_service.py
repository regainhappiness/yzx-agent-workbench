"""管理员运行时配置中心，当前支持 LLM 与 MCP。"""

import asyncio
import logging
import os
import uuid
from typing import TYPE_CHECKING, Callable

from langchain_core.messages import HumanMessage

from ...agents.multi_agent import create_default_registry
from ...models.llm import PROVIDER_CONFIG, get_model, list_available_providers
from ...tools.mcp import McpAdapter, McpConfig, McpServerConfig
from ..exceptions import NotFoundError, ValidationError
from ..repositories.base import RuntimeConfigRecord, RuntimeConfigRepository
from .secret_cipher import SecretCipher

if TYPE_CHECKING:
    from .chat_service import ChatService
    from .multi_agent_service import MultiAgentService

logger = logging.getLogger("server.runtime_config")

LLM_CATEGORY = "llm"
MCP_CATEGORY = "mcp"
LLM_CONFIG_ID = "llm-default"
SECRET_MASK = "••••••••"


class RuntimeConfigService:
    """持久化配置，并把新配置发布给运行中的 Agent 服务。"""

    def __init__(
        self,
        repository: RuntimeConfigRepository,
        cipher: SecretCipher,
        *,
        model_factory: Callable = get_model,
        mcp_adapter_factory: Callable = McpAdapter,
    ):
        self._repo = repository
        self._cipher = cipher
        self._model_factory = model_factory
        self._mcp_adapter_factory = mcp_adapter_factory
        self._lock = asyncio.Lock()
        self._chat_service: ChatService | None = None
        self._multi_agent_service: MultiAgentService | None = None
        self._model_config: dict = {}
        self._mcp_adapter = None
        self._retired_mcp_adapters: list = []
        self._mcp_tools: list = []
        self._mcp_tools_meta: dict[str, dict] = {}
        self._mcp_tool_counts: dict[str, int] = {}
        self._registry = create_default_registry()

    @property
    def model_config(self) -> dict:
        return dict(self._model_config)

    @property
    def registry(self):
        return self._registry

    @property
    def mcp_tools(self) -> list:
        return list(self._mcp_tools)

    async def initialize(self, file_mcp_config: McpConfig | None = None) -> None:
        await self._seed_llm_from_environment()
        await self._seed_mcp_from_file(file_mcp_config or McpConfig())
        await self._load_llm_config()
        await self._reload_mcp()

    def bind_services(
        self,
        chat_service: "ChatService",
        multi_agent_service: "MultiAgentService",
    ) -> None:
        self._chat_service = chat_service
        self._multi_agent_service = multi_agent_service

    # ── LLM ──

    async def get_llm(self) -> dict:
        record = await self._repo.get(LLM_CONFIG_ID)
        if record is None:
            return {
                "configured": False,
                "provider": "deepseek",
                "model_name": PROVIDER_CONFIG["deepseek"]["default_model"],
                "base_url": PROVIDER_CONFIG["deepseek"]["base_url"],
                "temperature": 0.3,
                "max_tokens": None,
                "api_key_configured": False,
                "api_key_hint": None,
                "source": "none",
                "revision": 0,
                "status": "unconfigured",
                "last_error": None,
            }
        payload = self._cipher.decrypt_json(record.payload)
        api_key = payload.get("api_key", "")
        return {
            "configured": bool(api_key),
            "provider": payload.get("provider", "deepseek"),
            "model_name": payload.get("model_name", ""),
            "base_url": payload.get("base_url"),
            "temperature": payload.get("temperature", 0.3),
            "max_tokens": payload.get("max_tokens"),
            "api_key_configured": bool(api_key),
            "api_key_hint": self._secret_hint(api_key),
            "source": payload.get("source", "webui"),
            "revision": record.revision,
            "status": record.status,
            "last_error": record.last_error,
        }

    async def save_llm(self, values: dict) -> dict:
        async with self._lock:
            existing = await self._repo.get(LLM_CONFIG_ID)
            existing_payload = (
                self._cipher.decrypt_json(existing.payload) if existing else {}
            )
            provider = values["provider"]
            api_key = (values.get("api_key") or "").strip()
            if not api_key and existing_payload.get("provider") == provider:
                api_key = existing_payload.get("api_key", "")
            if not api_key:
                raise ValidationError("切换 Provider 时请填写对应的 API Key")

            provider_cfg = PROVIDER_CONFIG.get(provider)
            if provider_cfg is None:
                raise ValidationError(f"不支持的模型 Provider: {provider}")
            payload = {
                "provider": provider,
                "model_name": values.get("model_name")
                or provider_cfg["default_model"],
                "api_key": api_key,
                "base_url": (values.get("base_url") or "").strip() or None,
                "temperature": float(values.get("temperature", 0.3)),
                "max_tokens": values.get("max_tokens"),
                "source": "webui",
            }
            model = self._create_model(payload)
            if model is None:
                raise ValidationError("模型配置无法初始化，请检查 Provider 与参数")
            await self._probe_model(model)

            record = RuntimeConfigRecord(
                config_id=LLM_CONFIG_ID,
                category=LLM_CATEGORY,
                name="默认模型",
                enabled=True,
                payload=self._cipher.encrypt_json(payload),
                status="active",
                last_error=None,
            )
            await self._repo.upsert(record)
            self._model_config = self._to_model_kwargs(payload)
            await self._publish_model_change()
            logger.info(
                "运行时模型已切换: provider=%s model=%s",
                provider,
                payload["model_name"],
            )
        return await self.get_llm()

    async def test_llm(self, values: dict) -> dict:
        existing = await self._repo.get(LLM_CONFIG_ID)
        existing_payload = self._cipher.decrypt_json(existing.payload) if existing else {}
        payload = dict(existing_payload)
        requested_provider = values.get("provider")
        if (
            requested_provider
            and requested_provider != existing_payload.get("provider")
            and not (values.get("api_key") or "").strip()
        ):
            payload.pop("api_key", None)
        payload.update({key: value for key, value in values.items() if value is not None})
        if not (payload.get("api_key") or "").strip():
            raise ValidationError("请填写模型 API Key")
        model = self._create_model(payload)
        if model is None:
            raise ValidationError("模型配置无法初始化")
        response = await self._probe_model(model)
        return {"success": True, "message": str(getattr(response, "content", "OK"))}

    # ── MCP ──

    async def list_mcp(self) -> list[dict]:
        records = await self._repo.list_by_category(MCP_CATEGORY)
        return [self._mcp_view(record) for record in records]

    async def create_mcp(self, values: dict) -> dict:
        async with self._lock:
            await self._ensure_unique_mcp_name(values["name"])
            config = self._validate_mcp(values)
            record = RuntimeConfigRecord(
                config_id=f"mcp-{uuid.uuid4()}",
                category=MCP_CATEGORY,
                name=config.name,
                enabled=config.enabled,
                payload=self._cipher.encrypt_json(config.model_dump()),
                status="applying" if config.enabled else "disabled",
            )
            stored = await self._repo.upsert(record)
            await self._reload_mcp_and_publish()
        refreshed = await self._repo.get(stored.config_id)
        return self._mcp_view(refreshed or stored)

    async def update_mcp(self, config_id: str, values: dict) -> dict:
        async with self._lock:
            existing = await self._require_mcp(config_id)
            current = self._cipher.decrypt_json(existing.payload)
            if values.get("name", existing.name).casefold() != existing.name.casefold():
                await self._ensure_unique_mcp_name(values["name"], exclude_id=config_id)
            merged = {**current, **values}
            merged["env"] = self._merge_masked_secrets(
                current.get("env", {}), values.get("env", current.get("env", {})),
            )
            merged["headers"] = self._merge_masked_secrets(
                current.get("headers", {}),
                values.get("headers", current.get("headers", {})),
            )
            config = self._validate_mcp(merged)
            stored = await self._repo.upsert(RuntimeConfigRecord(
                config_id=config_id,
                category=MCP_CATEGORY,
                name=config.name,
                enabled=config.enabled,
                payload=self._cipher.encrypt_json(config.model_dump()),
                status="applying" if config.enabled else "disabled",
            ))
            await self._reload_mcp_and_publish()
        refreshed = await self._repo.get(stored.config_id)
        return self._mcp_view(refreshed or stored)

    async def set_mcp_enabled(self, config_id: str, enabled: bool) -> dict:
        existing = await self._require_mcp(config_id)
        payload = self._cipher.decrypt_json(existing.payload)
        payload["enabled"] = enabled
        return await self.update_mcp(config_id, payload)

    async def delete_mcp(self, config_id: str) -> None:
        async with self._lock:
            await self._require_mcp(config_id)
            await self._repo.delete(config_id)
            await self._reload_mcp_and_publish()

    async def test_mcp(self, config_id: str) -> dict:
        record = await self._require_mcp(config_id)
        config = McpServerConfig.model_validate(
            self._cipher.decrypt_json(record.payload)
        )
        config.enabled = True
        adapter = self._mcp_adapter_factory(McpConfig(enabled=True, servers=[config]))
        try:
            tools, _ = await adapter.discover()
            status = getattr(adapter, "server_statuses", {}).get(config.name, {})
            if status.get("status") == "error":
                raise ValidationError(status.get("error") or "MCP 连接失败")
            return {
                "success": True,
                "message": f"连接成功，发现 {len(tools)} 个工具",
                "tool_count": len(tools),
            }
        finally:
            await adapter.close()

    # ── 初始化与发布 ──

    async def _seed_llm_from_environment(self) -> None:
        if await self._repo.get(LLM_CONFIG_ID) is not None:
            return
        provider = os.getenv("LLM_PROVIDER", "auto").strip().lower() or "auto"
        if provider == "auto":
            available = list_available_providers()
            if not available:
                return
            provider = available[0]
        provider_cfg = PROVIDER_CONFIG.get(provider)
        if provider_cfg is None:
            return
        api_key = os.getenv(provider_cfg["env_key"], "").strip()
        if not api_key:
            return
        payload = {
            "provider": provider,
            "model_name": os.getenv("LLM_MODEL", "").strip()
            or provider_cfg["default_model"],
            "api_key": api_key,
            "base_url": os.getenv("LLM_BASE_URL", "").strip() or None,
            "temperature": 0.3,
            "max_tokens": None,
            "source": "environment",
        }
        await self._repo.upsert(RuntimeConfigRecord(
            config_id=LLM_CONFIG_ID,
            category=LLM_CATEGORY,
            name="默认模型",
            enabled=True,
            payload=self._cipher.encrypt_json(payload),
            status="active",
        ))

    async def _seed_mcp_from_file(self, config: McpConfig) -> None:
        if await self._repo.list_by_category(MCP_CATEGORY):
            return
        for server in config.servers:
            await self._repo.upsert(RuntimeConfigRecord(
                config_id=f"mcp-{uuid.uuid5(uuid.NAMESPACE_URL, server.name)}",
                category=MCP_CATEGORY,
                name=server.name,
                enabled=bool(config.enabled and server.enabled),
                payload=self._cipher.encrypt_json(server.model_dump()),
                status="unconfigured",
            ))

    async def _load_llm_config(self) -> None:
        record = await self._repo.get(LLM_CONFIG_ID)
        if record is None or not record.enabled:
            self._model_config = {}
            return
        payload = self._cipher.decrypt_json(record.payload)
        self._model_config = self._to_model_kwargs(payload)

    async def _reload_mcp_and_publish(self) -> None:
        await self._reload_mcp()
        if self._multi_agent_service is not None:
            await self._multi_agent_service.reconfigure(
                sub_agent_registry=self._registry,
                model_kwargs=self._model_config,
            )

    async def _reload_mcp(self) -> None:
        records = await self._repo.list_by_category(MCP_CATEGORY)
        servers = []
        for record in records:
            payload = self._cipher.decrypt_json(record.payload)
            # enabled 列是运行时开关的唯一事实源，兼容从全局停用的 mcp.json 导入。
            payload["enabled"] = record.enabled
            servers.append(McpServerConfig.model_validate(payload))
        adapter = self._mcp_adapter_factory(McpConfig(
            enabled=any(server.enabled for server in servers),
            servers=servers,
        ))
        tools, metas = await adapter.discover()
        statuses = getattr(adapter, "server_statuses", {})
        tool_counts: dict[str, int] = {}
        for record, server in zip(records, servers):
            if not server.enabled:
                status, error, count = "disabled", None, 0
            else:
                detail = statuses.get(server.name, {})
                status = detail.get("status", "connected")
                error = detail.get("error")
                count = int(detail.get("tool_count", 0))
                if not statuses:
                    count = sum(
                        1 for meta in metas.values()
                        if server.name in meta.get("tags", [])
                    )
            tool_counts[server.name] = count
            await self._repo.update_status(record.config_id, status, error)

        if self._mcp_adapter is not None:
            self._retired_mcp_adapters.append(self._mcp_adapter)
        self._mcp_adapter = adapter
        self._mcp_tools = tools
        self._mcp_tools_meta = metas
        self._mcp_tool_counts = tool_counts
        self._registry = create_default_registry(
            mcp_tools=tools,
            mcp_tools_meta=metas,
            model_kwargs=self._model_config,
        )

    async def _publish_model_change(self) -> None:
        self._registry = create_default_registry(
            mcp_tools=self._mcp_tools,
            mcp_tools_meta=self._mcp_tools_meta,
            model_kwargs=self._model_config,
        )
        if self._chat_service is not None:
            await self._chat_service.reconfigure_model(self._model_config)
        if self._multi_agent_service is not None:
            await self._multi_agent_service.reconfigure(
                sub_agent_registry=self._registry,
                model_kwargs=self._model_config,
            )

    async def close(self) -> None:
        adapters = [*self._retired_mcp_adapters]
        if self._mcp_adapter is not None:
            adapters.append(self._mcp_adapter)
        self._retired_mcp_adapters = []
        self._mcp_adapter = None
        for adapter in adapters:
            try:
                await adapter.close()
            except Exception as exc:
                logger.warning("关闭 MCP 运行时失败: %s", exc)

    # ── 辅助 ──

    def _create_model(self, payload: dict):
        return self._model_factory(**self._to_model_kwargs(payload))

    @staticmethod
    async def _probe_model(model):
        try:
            async with asyncio.timeout(30):
                return await model.ainvoke([
                    HumanMessage(content="请只回复 OK，用于验证模型连接。")
                ])
        except Exception as exc:
            raise ValidationError(f"模型连接测试失败: {exc}") from exc

    @staticmethod
    def _to_model_kwargs(payload: dict) -> dict:
        result = {
            "provider": payload["provider"],
            "model": payload.get("model_name"),
            "api_key": payload.get("api_key"),
            "base_url": payload.get("base_url"),
            "temperature": float(payload.get("temperature", 0.3)),
        }
        if payload.get("max_tokens") is not None:
            result["max_tokens"] = int(payload["max_tokens"])
        return {key: value for key, value in result.items() if value is not None}

    async def _require_mcp(self, config_id: str) -> RuntimeConfigRecord:
        record = await self._repo.get(config_id)
        if record is None or record.category != MCP_CATEGORY:
            raise NotFoundError("MCP 配置", config_id)
        return record

    async def _ensure_unique_mcp_name(
        self, name: str, exclude_id: str | None = None,
    ) -> None:
        normalized = name.strip().casefold()
        for record in await self._repo.list_by_category(MCP_CATEGORY):
            if record.config_id != exclude_id and record.name.casefold() == normalized:
                raise ValidationError(f"MCP 名称已存在: {name}")

    @staticmethod
    def _validate_mcp(values: dict) -> McpServerConfig:
        config = McpServerConfig.model_validate(values)
        config.name = config.name.strip()
        if config.transport == "stdio" and not (config.command or "").strip():
            raise ValidationError("stdio MCP 必须填写启动命令")
        if config.transport == "streamable-http" and not (config.url or "").strip():
            raise ValidationError("streamable-http MCP 必须填写 URL")
        if config.transport == "streamable-http" and not config.url.startswith(("http://", "https://")):
            raise ValidationError("MCP URL 必须使用 http:// 或 https://")
        return config

    def _mcp_view(self, record: RuntimeConfigRecord) -> dict:
        payload = self._cipher.decrypt_json(record.payload)
        payload["env"] = {key: SECRET_MASK for key in payload.get("env", {})}
        payload["headers"] = {
            key: SECRET_MASK for key in payload.get("headers", {})
        }
        return {
            "config_id": record.config_id,
            **payload,
            "enabled": record.enabled,
            "revision": record.revision,
            "status": record.status,
            "last_error": record.last_error,
            "tool_count": self._mcp_tool_counts.get(record.name, 0),
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }

    @staticmethod
    def _merge_masked_secrets(current: dict, incoming: dict) -> dict:
        merged = {}
        for key, value in (incoming or {}).items():
            if value == SECRET_MASK and key in current:
                merged[key] = current[key]
            elif value not in {None, ""}:
                merged[key] = value
        return merged

    @staticmethod
    def _secret_hint(secret: str) -> str | None:
        if not secret:
            return None
        return f"{secret[:3]}****{secret[-4:]}" if len(secret) > 8 else "已配置"
