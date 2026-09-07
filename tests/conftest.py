import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient


# 测试使用每次生命周期重新创建的内存仓储，不读取真实数据库或静态 Key。
os.environ["REPOSITORY_BACKEND"] = "memory"

_test_keys: dict[str, str] = {}


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_LOCAL_DIR", str(tmp_path / "files"))
    monkeypatch.setenv("BAILIAN_API_KEY", "")
    monkeypatch.setenv("MILVUS_HOST", "")
    monkeypatch.setenv("MINERU_API_KEY", "")
    monkeypatch.setenv("MULTI_AGENT_WORKSPACE_ROOTS", str(tmp_path))
    monkeypatch.setenv("MULTI_AGENT_ATTACHMENT_DIR", str(tmp_path / "multi-agent-attachments"))

    from src.server.main import app
    from src.rag.documents import DocumentService
    from src.server.repositories.memory import (
        InMemoryChunkRepo,
        InMemoryDocumentRepo,
        InMemoryTaskRepo,
    )
    from src.rag.storage import LocalStorage
    from src.rag.tasks import InProcessTaskQueue

    class TestTaskWorker:
        async def execute(self, document_id: str, task_id: str | None = None) -> None:
            return None

        async def get_document_status(self, document_id: str) -> str | None:
            return "queued"

    async with LifespanManager(app) as manager:
        storage = LocalStorage(str(tmp_path / "files"))
        task_queue = InProcessTaskQueue(TestTaskWorker(), InMemoryTaskRepo())
        app.state.storage = storage
        app.state.task_queue = task_queue
        app.state.doc_service = DocumentService(
            doc_repo=InMemoryDocumentRepo(),
            chunk_repo=InMemoryChunkRepo(),
            storage=storage,
            task_queue=task_queue,
            milvus_client=None,
        )

        auth_service = app.state.auth_service
        admin = await auth_service.create_user("Test Admin", "admin")
        user = await auth_service.create_user("Test User", "user")
        admin_key = await auth_service.create_api_key(admin["user_id"])
        user_key = await auth_service.create_api_key(user["user_id"])
        _test_keys.update(admin=admin_key["key"], user=user_key["key"])

        transport = ASGITransport(app=manager.app)

        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as async_client:
            yield async_client

        _test_keys.clear()


@pytest.fixture
def user_headers(client: AsyncClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {_test_keys['user']}"}


@pytest.fixture
def admin_headers(client: AsyncClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {_test_keys['admin']}"}
