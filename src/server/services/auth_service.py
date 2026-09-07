"""认证服务 — 持久化 Key 校验, 用户/API Key 管理"""

import hashlib
import secrets
from datetime import datetime

from ..repositories.base import (
    UserRepository, ApiKeyRepository, Identity,
)
from ..exceptions import AuthorizationError, NotFoundError


class AuthService:
    """管理持久化用户及其 API Key。"""

    def __init__(
        self,
        user_repo: UserRepository,
        api_key_repo: ApiKeyRepository,
    ):
        self._user_repo = user_repo
        self._api_key_repo = api_key_repo

    @staticmethod
    def _hash_key(key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()

    @staticmethod
    def _key_prefix(key: str) -> str:
        return key[:11] + "***" + key[-4:]

    async def validate_key(self, api_key: str) -> Identity | None:
        """校验持久化 API Key，并从用户表读取当前真实角色。"""
        identity = await self._api_key_repo.validate(api_key)
        if not identity:
            return None

        user = await self._user_repo.get_by_id(identity.user_id)
        if not user:
            return None

        return Identity(
            user_id=user.user_id,
            role=user.role,
            api_key_prefix=identity.api_key_prefix,
        )

    async def create_user(self, name: str, role: str) -> dict:
        """创建用户"""
        user = await self._user_repo.create(name=name, role=role)
        return {
            "user_id": user.user_id,
            "name": user.name,
            "role": user.role,
            "created_at": user.created_at,
        }

    async def create_api_key(self, user_id: str) -> dict:
        """为用户生成 API Key (返回完整 Key 仅此一次)"""
        user = await self._user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("用户", user_id)

        plain_key = f"sk-{secrets.token_hex(16)}"
        key_hash = self._hash_key(plain_key)
        prefix = self._key_prefix(plain_key)

        await self._api_key_repo.create(user_id, key_hash, prefix)

        return {
            "key": plain_key,
            "prefix": prefix,
            "created_at": datetime.utcnow(),
        }

    async def revoke_key(self, prefix: str) -> None:
        """撤销 API Key"""
        await self._api_key_repo.revoke(prefix)

    async def list_users(self) -> list[dict]:
        """列出所有用户"""
        users = await self._user_repo.list_all()
        return [
            {"user_id": u.user_id, "name": u.name, "role": u.role,
             "created_at": u.created_at}
            for u in users
        ]

    async def get_user(self, user_id: str) -> dict:
        """获取用户详情"""
        user = await self._user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("用户", user_id)
        return {
            "user_id": user.user_id, "name": user.name,
            "role": user.role, "created_at": user.created_at,
        }

    async def delete_user(self, user_id: str) -> None:
        """删除用户 (同步清理其 API Keys)"""
        user = await self._user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("用户", user_id)
        # 撤销该用户所有 API Key
        keys = await self._api_key_repo.list_by_user(user_id)
        for k in keys:
            if not k.revoked_at:
                await self._api_key_repo.revoke(k.prefix)
        await self._user_repo.delete(user_id)

    async def list_user_keys(self, user_id: str) -> list[dict]:
        """列出用户的所有 API Key"""
        keys = await self._api_key_repo.list_by_user(user_id)
        return [
            {"prefix": k.prefix, "user_id": k.user_id,
             "created_at": k.created_at, "revoked_at": k.revoked_at}
            for k in keys
        ]

    async def require_admin(self, user_id: str) -> None:
        """确保用户是 admin，否则抛出 AuthorizationError"""
        user = await self._user_repo.get_by_id(user_id)
        if not user or user.role != "admin":
            raise AuthorizationError("需要管理员权限")
