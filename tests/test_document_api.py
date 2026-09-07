"""文档 API 集成测试"""

import asyncio
import logging
from io import BytesIO

import pytest
from httpx import AsyncClient
from pypdf import PdfWriter

from src.rag.documents.service import MAX_FILE_SIZE, MAX_PDF_PAGES


def make_pdf(page_count: int) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_single_file_upload_limit_is_200_mb():
    assert MAX_FILE_SIZE == 200 * 1024 * 1024


def test_pdf_page_limit_is_200_pages():
    assert MAX_PDF_PAGES == 200


def test_logging_configuration_enables_application_info_logs(monkeypatch):
    from src.server.main import configure_logging

    application_logger = logging.getLogger("server")
    previous_level = application_logger.level
    previous_disabled = application_logger.disabled
    try:
        application_logger.setLevel(logging.WARNING)
        application_logger.disabled = True
        monkeypatch.setenv("LOG_LEVEL", "INFO")

        configure_logging()

        assert application_logger.level == logging.INFO
        assert application_logger.disabled is False
    finally:
        application_logger.setLevel(previous_level)
        application_logger.disabled = previous_disabled


@pytest.mark.asyncio
async def test_unauthenticated_upload_has_request_id_and_access_log(
    client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
):
    with caplog.at_level(logging.INFO, logger="server.access"):
        resp = await client.post(
            "/api/v1/documents",
            files={"file": ("notes.txt", b"content", "text/plain")},
        )

    assert resp.status_code == 401
    assert resp.headers["X-Request-ID"]
    assert any(
        "POST /api/v1/documents" in record.getMessage()
        and "401" in record.getMessage()
        for record in caplog.records
        if record.name == "server.access"
    )


@pytest.mark.asyncio
async def test_successful_upload_logs_document_and_task_ids(
    client: AsyncClient,
    user_headers: dict[str, str],
    caplog: pytest.LogCaptureFixture,
):
    with caplog.at_level(logging.INFO, logger="server.document_service"):
        resp = await client.post(
            "/api/v1/documents",
            files={"file": ("logged.txt", b"observable upload", "text/plain")},
            headers=user_headers,
        )

    assert resp.status_code == 201
    payload = resp.json()
    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "server.document_service"
    ]
    assert any(
        payload["document_id"] in message and payload["task_id"] in message
        for message in messages
    )


@pytest.mark.asyncio
async def test_upload_txt(
    client: AsyncClient,
    user_headers: dict[str, str],
):
    resp = await client.post(
        "/api/v1/documents",
        files={
            "file": (
                "test.txt",
                b"Hello World\n\nTest content.",
                "text/plain",
            )
        },
        data={"scope": "private"},
        headers=user_headers,
    )

    assert resp.status_code == 201

    data = resp.json()
    assert data["status"] == "queued"
    assert "task_id" in data
    assert "document_id" in data


@pytest.mark.asyncio
async def test_upload_markdown_detected_as_text_plain(
    client: AsyncClient,
    user_headers: dict[str, str],
):
    resp = await client.post(
        "/api/v1/documents",
        files={"file": ("notes.md", b"# Notes\n\nMarkdown content.", "text/plain")},
        data={"scope": "private"},
        headers=user_headers,
    )

    assert resp.status_code == 201
    assert resp.json()["mime_type"] == "text/markdown"


@pytest.mark.asyncio
async def test_upload_pdf_over_200_pages_is_rejected(
    client: AsyncClient,
    user_headers: dict[str, str],
):
    resp = await client.post(
        "/api/v1/documents",
        files={"file": ("too-many-pages.pdf", make_pdf(201), "application/pdf")},
        headers=user_headers,
    )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "PDF_PAGE_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_batch_upload_returns_per_file_results(
    client: AsyncClient,
    user_headers: dict[str, str],
):
    resp = await client.post(
        "/api/v1/documents/batch",
        files=[
            ("files", ("first.txt", b"first document", "text/plain")),
            ("files", ("second.md", b"# Second document", "text/plain")),
            ("files", ("blocked.exe", b"not allowed", "application/octet-stream")),
        ],
        data={"scope": "private"},
        headers=user_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert data["succeeded"] == 2
    assert data["failed"] == 1
    assert [item["success"] for item in data["results"]] == [True, True, False]
    assert data["results"][1]["document"]["mime_type"] == "text/markdown"
    assert data["results"][2]["error_code"] == "UNSUPPORTED_FORMAT"


@pytest.mark.asyncio
async def test_upload_invalid_extension(
    client: AsyncClient,
    user_headers: dict[str, str],
):
    resp = await client.post(
        "/api/v1/documents",
        files={
            "file": (
                "test.exe",
                b"malware",
                "application/octet-stream",
            )
        },
        headers=user_headers,
    )

    assert resp.status_code in (400, 422)


@pytest.mark.asyncio
async def test_list_documents(
    client: AsyncClient,
    user_headers: dict[str, str],
):
    for index in range(5):
        create_resp = await client.post(
            "/api/v1/documents",
            files={
                "file": (
                    f"doc-{index}.txt",
                    f"content-{index}".encode(),
                    "text/plain",
                )
            },
            headers=user_headers,
        )
        assert create_resp.status_code == 201

    resp = await client.get(
        "/api/v1/documents",
        params={"page": 2, "page_size": 2},
        headers=user_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["page"] == 2
    assert data["page_size"] == 2
    assert data["total"] == 5
    assert data["total_pages"] == 3
    assert len(data["items"]) == 2

    last_page = await client.get(
        "/api/v1/documents",
        params={"page": 3, "page_size": 2},
        headers=user_headers,
    )
    assert last_page.status_code == 200
    assert len(last_page.json()["items"]) == 1


@pytest.mark.asyncio
async def test_list_documents_filters_before_pagination(
    client: AsyncClient,
    user_headers: dict[str, str],
):
    for filename in ("alpha-notes.txt", "beta-notes.txt", "alpha-guide.txt"):
        response = await client.post(
            "/api/v1/documents",
            files={"file": (filename, filename.encode(), "text/plain")},
            headers=user_headers,
        )
        assert response.status_code == 201

    response = await client.get(
        "/api/v1/documents",
        params={"search": "alpha", "status": "processing", "page_size": 1},
        headers=user_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["total_pages"] == 2
    assert len(data["items"]) == 1
    assert "alpha" in data["items"][0]["filename"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page_size": 0},
        {"page_size": 101},
        {"scope": "hybrid"},
        {"status": "queued"},
    ],
)
async def test_list_documents_rejects_invalid_pagination_and_filters(
    client: AsyncClient,
    user_headers: dict[str, str],
    params: dict[str, int | str],
):
    response = await client.get(
        "/api/v1/documents",
        params=params,
        headers=user_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_document(
    client: AsyncClient,
    user_headers: dict[str, str],
):
    create_resp = await client.post(
        "/api/v1/documents",
        files={
            "file": (
                "doc.txt",
                b"content",
                "text/plain",
            )
        },
        headers=user_headers,
    )

    assert create_resp.status_code == 201
    doc_id = create_resp.json()["document_id"]

    resp = await client.get(
        f"/api/v1/documents/{doc_id}",
        headers=user_headers,
    )

    assert resp.status_code == 200
    assert resp.json()["document_id"] == doc_id


@pytest.mark.asyncio
async def test_delete_document(
    client: AsyncClient,
    user_headers: dict[str, str],
):
    create_resp = await client.post(
        "/api/v1/documents",
        files={
            "file": (
                "doc.txt",
                b"content",
                "text/plain",
            )
        },
        headers=user_headers,
    )

    assert create_resp.status_code == 201
    doc_id = create_resp.json()["document_id"]

    resp = await client.delete(
        f"/api/v1/documents/{doc_id}",
        headers=user_headers,
    )

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_user_isolation(
    client: AsyncClient,
    user_headers: dict[str, str],
    admin_headers: dict[str, str],
):
    """user A 的文档 user B 看不到"""
    create_resp = await client.post(
        "/api/v1/documents",
        files={
            "file": (
                "secret.txt",
                b"secret",
                "text/plain",
            )
        },
        headers=user_headers,
    )

    assert create_resp.status_code == 201
    doc_id = create_resp.json()["document_id"]

    resp = await client.get(
        f"/api/v1/documents/{doc_id}",
        headers=admin_headers,
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_task_query(
    client: AsyncClient,
    user_headers: dict[str, str],
):
    create_resp = await client.post(
        "/api/v1/documents",
        files={
            "file": (
                "doc.txt",
                b"content",
                "text/plain",
            )
        },
        headers=user_headers,
    )

    assert create_resp.status_code == 201
    task_id = create_resp.json()["task_id"]

    await asyncio.sleep(0.5)

    resp = await client.get(
        f"/api/v1/tasks/{task_id}",
        headers=user_headers,
    )

    assert resp.status_code == 200

    data = resp.json()
    assert data["status"] in {
        "queued",
        "parsing",
        "chunking",
        "done",
        "failed",
    }


@pytest.mark.asyncio
async def test_batch_task_query(
    client: AsyncClient,
    user_headers: dict[str, str],
):
    task_ids = []
    for name in ("one.txt", "two.txt"):
        response = await client.post(
            "/api/v1/documents",
            files={"file": (name, name.encode(), "text/plain")},
            headers=user_headers,
        )
        assert response.status_code == 201
        task_ids.append(response.json()["task_id"])

    response = await client.get(
        "/api/v1/tasks",
        params=[("task_ids", task_id) for task_id in task_ids],
        headers=user_headers,
    )

    assert response.status_code == 200
    assert [task["task_id"] for task in response.json()] == task_ids


@pytest.mark.asyncio
async def test_task_not_found(
    client: AsyncClient,
    user_headers: dict[str, str],
):
    resp = await client.get(
        "/api/v1/tasks/nonexistent",
        headers=user_headers,
    )

    assert resp.status_code == 404
