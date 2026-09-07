"""ObjectStorage 测试 — 本地存储 + 分片上传 + 断点续传"""

import os
import tempfile
import pytest


@pytest.fixture
def local_storage():
    from src.rag.storage import LocalStorage
    with tempfile.TemporaryDirectory() as tmp:
        storage = LocalStorage(base_dir=tmp)
        yield storage


# ═══════════════════════════════════════════════════════════════
# 基础操作
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_save_and_read(local_storage):
    key = await local_storage.save(b"hello world", "txt")
    assert key.endswith(".txt")
    data = await local_storage.read(key)
    assert data == b"hello world"


@pytest.mark.asyncio
async def test_exists(local_storage):
    key = await local_storage.save(b"test", "md")
    assert await local_storage.exists(key) is True
    assert await local_storage.exists("nonexistent") is False


@pytest.mark.asyncio
async def test_delete_idempotent(local_storage):
    key = await local_storage.save(b"test", "txt")
    await local_storage.delete(key)
    assert await local_storage.exists(key) is False
    await local_storage.delete(key)  # 不抛异常


@pytest.mark.asyncio
async def test_resolve_path(local_storage):
    key = await local_storage.save(b"test", "txt")
    path = local_storage.resolve_path(key)
    assert os.path.exists(path)
    with open(path, "rb") as f:
        assert f.read() == b"test"


@pytest.mark.asyncio
async def test_unique_keys(local_storage):
    key1 = await local_storage.save(b"a", "txt")
    key2 = await local_storage.save(b"b", "txt")
    assert key1 != key2


# ═══════════════════════════════════════════════════════════════
# presigned_url
# ═══════════════════════════════════════════════════════════════

def test_presigned_url_local_returns_none(local_storage):
    """本地存储无法生成外部可访问的 URL"""
    url = local_storage.presigned_url("some/key.txt")
    assert url is None


# ═══════════════════════════════════════════════════════════════
# 分片上传 (本地退化)
# ═══════════════════════════════════════════════════════════════

def test_multipart_upload_local(local_storage):
    """本地分片上传退化为简单拼接写入"""
    from src.rag.storage.base import MultipartUpload

    key = "test/multipart.bin"
    upload = local_storage.initiate_multipart_upload(key)
    assert upload.upload_id == "local"
    assert upload.key == key

    # 上传 3 个分片
    p1 = local_storage.upload_part(key, upload.upload_id, 1, b"AAA")
    p2 = local_storage.upload_part(key, upload.upload_id, 2, b"BBB")
    p3 = local_storage.upload_part(key, upload.upload_id, 3, b"CCC")
    assert p1.part_number == 1
    assert p2.part_number == 2
    assert p3.part_number == 3

    upload.uploaded_parts = [p1, p2, p3]
    result_key = local_storage.complete_multipart_upload(upload)
    assert result_key == key

    # 验证合并后的内容
    import asyncio
    data = asyncio.run(local_storage.read(key))
    assert data == b"AAABBBCCC"


def test_abort_multipart_upload_local(local_storage):
    """取消分片上传应删除已写入的文件"""
    key = "test/abort.bin"
    upload = local_storage.initiate_multipart_upload(key)
    local_storage.upload_part(key, upload.upload_id, 1, b"test")

    local_storage.abort_multipart_upload(key, upload.upload_id)

    import asyncio
    assert asyncio.run(local_storage.exists(key)) is False


def test_list_parts_local(local_storage):
    """列出已上传分片"""
    key = "test/listparts.bin"
    upload = local_storage.initiate_multipart_upload(key)
    local_storage.upload_part(key, upload.upload_id, 1, b"data")

    parts = local_storage.list_parts(key, upload.upload_id)
    assert len(parts) >= 1
    assert parts[0].part_number >= 1


# ═══════════════════════════════════════════════════════════════
# 断点续传 (本地退化)
# ═══════════════════════════════════════════════════════════════

def test_resumable_upload_local(local_storage):
    """本地断点续传退化为直接文件拷贝"""
    import tempfile

    with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".bin") as f:
        f.write(b"X" * 1000)
        tmp_path = f.name

    try:
        key = local_storage.resumable_upload(tmp_path, "test/resumable.bin")
        assert key == "test/resumable.bin"
    finally:
        os.unlink(tmp_path)


def test_resumable_upload_checkpoint_cleanup(local_storage):
    """完成后 checkpoint 文件应被清理"""
    import tempfile

    with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".bin") as f:
        f.write(b"Y" * 500)
        tmp_path = f.name

    checkpoint = tmp_path + ".oss_checkpoint"
    try:
        key = local_storage.resumable_upload(
            tmp_path, "test/ck.bin",
            checkpoint_file=checkpoint,
        )
        # checkpoint 应该已清理
        assert not os.path.exists(checkpoint)
    finally:
        os.unlink(tmp_path)
        if os.path.exists(checkpoint):
            os.unlink(checkpoint)
