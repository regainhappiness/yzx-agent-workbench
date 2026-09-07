"""管理员运行时配置 API。"""

from fastapi import APIRouter, Depends, Response, status

from ..deps import get_runtime_config_service, require_admin
from ..schemas import (
    ConfigTestResponse,
    LlmConfigRequest,
    LlmConfigResponse,
    McpEnabledRequest,
    McpServerConfigRequest,
    McpServerConfigResponse,
)
from ..services.runtime_config_service import RuntimeConfigService

router = APIRouter(
    prefix="/admin/config",
    dependencies=[Depends(require_admin)],
)


@router.get("/llm", response_model=LlmConfigResponse)
async def get_llm_config(
    service: RuntimeConfigService = Depends(get_runtime_config_service),
):
    return await service.get_llm()


@router.put("/llm", response_model=LlmConfigResponse)
async def save_llm_config(
    body: LlmConfigRequest,
    service: RuntimeConfigService = Depends(get_runtime_config_service),
):
    return await service.save_llm(body.model_dump())


@router.post("/llm/test", response_model=ConfigTestResponse)
async def test_llm_config(
    body: LlmConfigRequest,
    service: RuntimeConfigService = Depends(get_runtime_config_service),
):
    return await service.test_llm(body.model_dump())


@router.get("/mcp", response_model=list[McpServerConfigResponse])
async def list_mcp_configs(
    service: RuntimeConfigService = Depends(get_runtime_config_service),
):
    return await service.list_mcp()


@router.post(
    "/mcp",
    response_model=McpServerConfigResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_mcp_config(
    body: McpServerConfigRequest,
    service: RuntimeConfigService = Depends(get_runtime_config_service),
):
    return await service.create_mcp(body.model_dump())


@router.put("/mcp/{config_id}", response_model=McpServerConfigResponse)
async def update_mcp_config(
    config_id: str,
    body: McpServerConfigRequest,
    service: RuntimeConfigService = Depends(get_runtime_config_service),
):
    return await service.update_mcp(config_id, body.model_dump())


@router.patch("/mcp/{config_id}/enabled", response_model=McpServerConfigResponse)
async def set_mcp_enabled(
    config_id: str,
    body: McpEnabledRequest,
    service: RuntimeConfigService = Depends(get_runtime_config_service),
):
    return await service.set_mcp_enabled(config_id, body.enabled)


@router.post("/mcp/{config_id}/test", response_model=ConfigTestResponse)
async def test_mcp_config(
    config_id: str,
    service: RuntimeConfigService = Depends(get_runtime_config_service),
):
    return await service.test_mcp(config_id)


@router.delete("/mcp/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp_config(
    config_id: str,
    service: RuntimeConfigService = Depends(get_runtime_config_service),
):
    await service.delete_mcp(config_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
