"""用户管理 API — CRUD + 查询"""

from fastapi import APIRouter, Depends

from ..schemas import (
    CreateUserRequest, UserResponse, MeResponse, ApiKeyInfo,
)
from ..deps import require_admin, get_identity, get_auth_service
from ..repositories.base import Identity
from ..services.auth_service import AuthService

router = APIRouter()


# ── 当前用户 ──

@router.get("/me", response_model=MeResponse)
async def get_me(
    identity: Identity = Depends(get_identity),
    auth_service: AuthService = Depends(get_auth_service),
):
    """获取当前用户身份"""
    user = await auth_service._user_repo.get_by_id(identity.user_id)
    name = user.name if user else identity.user_id
    return MeResponse(
        user_id=identity.user_id,
        name=name,
        role=identity.role,
        api_key_prefix=identity.api_key_prefix,
    )


# ── Admin: 用户管理 ──

@router.get(
    "/users",
    response_model=list[UserResponse],
    dependencies=[Depends(require_admin)],
)
async def list_users(
    auth_service: AuthService = Depends(get_auth_service),
):
    """列出所有用户 (仅 admin)"""
    users = await auth_service.list_users()
    return [UserResponse(**u) for u in users]


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=201,
)
async def create_user(
    body: CreateUserRequest,
    auth_service: AuthService = Depends(get_auth_service),
    _admin=Depends(require_admin),
):
    """创建用户 (仅 admin)"""
    result = await auth_service.create_user(name=body.name, role=body.role)
    return UserResponse(**result)


@router.get(
    "/users/{user_id}",
    response_model=UserResponse,
    dependencies=[Depends(require_admin)],
)
async def get_user(
    user_id: str,
    auth_service: AuthService = Depends(get_auth_service),
):
    """获取用户详情 (仅 admin)"""
    user = await auth_service.get_user(user_id)
    return UserResponse(**user)


@router.delete(
    "/users/{user_id}",
    status_code=204,
)
async def delete_user(
    user_id: str,
    auth_service: AuthService = Depends(get_auth_service),
    _admin=Depends(require_admin),
):
    """删除用户 (仅 admin, 同步撤销其所有 API Key)"""
    await auth_service.delete_user(user_id)


@router.get(
    "/users/{user_id}/api-keys",
    response_model=list[ApiKeyInfo],
    dependencies=[Depends(require_admin)],
)
async def list_user_api_keys(
    user_id: str,
    auth_service: AuthService = Depends(get_auth_service),
):
    """列出用户的所有 API Key (仅 admin)"""
    keys = await auth_service.list_user_keys(user_id)
    return [ApiKeyInfo(**k) for k in keys]
