"""为全新 SQLite 数据库创建首位管理员及其持久化 API Key。"""

import argparse
import asyncio
import hashlib
import os
import secrets

from dotenv import load_dotenv

load_dotenv()

from .repositories.sqlite import SqliteApiKeyRepo, SqliteDb, SqliteUserRepo


async def bootstrap_admin(name: str) -> tuple[str, str]:
    """创建管理员并返回 ``(user_id, plain_api_key)``。"""
    backend = os.getenv("REPOSITORY_BACKEND", "sqlite").lower()
    if backend != "sqlite":
        raise RuntimeError("初始化管理员仅支持 REPOSITORY_BACKEND=sqlite")

    db = SqliteDb()
    try:
        await db.init_schema()
        user_repo = SqliteUserRepo(db)
        if await user_repo.list_all():
            raise RuntimeError("数据库已存在用户，请在工作台中创建新的管理员成员")

        user = await user_repo.create(name=name, role="admin")

        plain_key = f"sk-{secrets.token_hex(16)}"
        key_hash = hashlib.sha256(plain_key.encode()).hexdigest()
        prefix = plain_key[:11] + "***" + plain_key[-4:]
        await SqliteApiKeyRepo(db).create(user.user_id, key_hash, prefix)
        return user.user_id, plain_key
    finally:
        await db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="初始化首位管理员")
    parser.add_argument("--name", default="Administrator", help="管理员名称")
    args = parser.parse_args()

    user_id, api_key = asyncio.run(bootstrap_admin(args.name))
    print(f"管理员已创建，用户 ID: {user_id}")
    print(f"API Key: {api_key}")
    print("请立即妥善保存该 Key；系统不会再次显示完整内容。")


if __name__ == "__main__":
    main()
