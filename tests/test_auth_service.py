"""认证服务回归测试。"""

import hashlib
from datetime import datetime

import pytest

from src.server.repositories.memory import InMemoryApiKeyRepo, InMemoryUserRepo
from src.server.repositories.sqlite import SqliteApiKeyRepo, SqliteDb, SqliteUserRepo
from src.server.services.auth_service import AuthService


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["admin", "user"])
async def test_created_api_key_inherits_its_users_role(role: str):
    """动态 Key 必须继承所属用户角色，不能一律降级为 user。"""
    service = AuthService(InMemoryUserRepo(), InMemoryApiKeyRepo())
    user = await service.create_user(name=f"Test {role}", role=role)
    issued_key = await service.create_api_key(user["user_id"])

    identity = await service.validate_key(issued_key["key"])

    assert identity is not None
    assert identity.user_id == user["user_id"]
    assert identity.role == role


@pytest.mark.asyncio
async def test_api_key_without_a_persisted_user_is_rejected():
    """孤立 Key 不应绕过用户与角色校验。"""
    user_repo = InMemoryUserRepo()
    api_key_repo = InMemoryApiKeyRepo()
    service = AuthService(user_repo, api_key_repo)
    plain_key = "sk-orphaned-key"

    await api_key_repo.create(
        user_id="missing-user",
        key_hash=hashlib.sha256(plain_key.encode()).hexdigest(),
        prefix="sk-orphaned***-key",
    )

    assert await service.validate_key(plain_key) is None


@pytest.mark.asyncio
async def test_legacy_static_admin_key_is_migrated_from_sqlite(tmp_path):
    """移除环境变量加载后，已持久化的旧管理员 Key 仍应可用。"""
    db_path = str(tmp_path / "legacy-auth.db")
    plain_key = "sk-legacy-admin"
    legacy_user_id = "sk-static-admin-a1b2c3"
    prefix = plain_key[:11] + "***" + plain_key[-4:]

    old_db = SqliteDb(db_path)
    await old_db.init_schema()
    await old_db.execute(
        "INSERT INTO api_keys (prefix, key_hash, user_id, created_at) "
        "VALUES (?, ?, ?, ?)",
        (
            prefix,
            hashlib.sha256(plain_key.encode()).hexdigest(),
            legacy_user_id,
            datetime.utcnow().isoformat(),
        ),
    )
    await old_db.close()

    migrated_db = SqliteDb(db_path)
    try:
        await migrated_db.init_schema()
        service = AuthService(
            SqliteUserRepo(migrated_db),
            SqliteApiKeyRepo(migrated_db),
        )

        identity = await service.validate_key(plain_key)

        assert identity is not None
        assert identity.user_id == legacy_user_id
        assert identity.role == "admin"
    finally:
        await migrated_db.close()
