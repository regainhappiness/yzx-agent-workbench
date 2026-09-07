"""API Key 管理"""

from fastapi import APIRouter, Depends

from ..schemas import CreateApiKeyRequest, ApiKeyResponse
from ..deps import require_admin, get_auth_service
from ..services.auth_service import AuthService

router = APIRouter()


@router.post(
    "/api-keys",
    response_model=ApiKeyResponse,
    status_code=201,
)
async def create_api_key(
    body: CreateApiKeyRequest,
    auth_service: AuthService = Depends(get_auth_service),
    _admin=Depends(require_admin),
):
    """为指定用户生成 API Key (仅 admin, 返回完整 Key 仅此一次)"""
    result = await auth_service.create_api_key(body.user_id)
    return ApiKeyResponse(**result)


@router.delete(
    "/api-keys/{prefix}",
    status_code=204,
)
async def revoke_api_key(
    prefix: str,
    auth_service: AuthService = Depends(get_auth_service),
    _admin=Depends(require_admin),
):
    """撤销 API Key (仅 admin)"""
    await auth_service.revoke_key(prefix)
