"""有并发上限、支持恢复和优雅关闭的进程内任务队列。"""

import asyncio
import uuid
import logging
from datetime import datetime

from .base import TaskStatus, TaskInfo
from .worker import TaskWorker
from ...server.repositories.base import TaskRepository

logger = logging.getLogger("server.task_queue")


class InProcessTaskQueue:

    def __init__(
        self,
        worker: TaskWorker,
        task_repo: TaskRepository,
        max_concurrency: int = 2,
    ):
        self._worker = worker
        self._repo = task_repo
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._handles: set[asyncio.Task] = set()
        self._scheduled_ids: set[str] = set()
        self._accepting = True

    async def enqueue(self, document_id: str) -> str:
        if not self._accepting:
            raise RuntimeError("任务队列正在关闭，暂不接受新任务")
        task_id = str(uuid.uuid4())[:8]
        task = TaskInfo(task_id=task_id, document_id=document_id)
        await self._repo.save(task)
        self._schedule(task)
        return task_id

    async def get(self, task_id: str) -> TaskInfo | None:
        return await self._repo.get(task_id)

    async def get_many(self, task_ids: list[str]) -> list[TaskInfo]:
        return await self._repo.get_many(task_ids)

    async def recover(self) -> int:
        """恢复上次异常退出时未完成的任务，并修正文档/任务状态偏差。"""
        recovered = 0
        for task in await self._repo.list_incomplete():
            status = await self._worker.get_document_status(task.document_id)
            if status == "indexed":
                task.status = TaskStatus.DONE.value
                task.progress = 1.0
                task.error_message = None
                task.updated_at = datetime.utcnow()
                await self._repo.save(task)
                continue
            if status == "cleanup_pending":
                cleanup_failed = getattr(self._worker, "cleanup_failed", None)
                if callable(cleanup_failed):
                    try:
                        await cleanup_failed(task.document_id)
                    except Exception:
                        # 文档保持 cleanup_pending，下次启动继续补偿。
                        logger.exception(
                            "恢复未完成的补偿清理失败: task=%s",
                            task.task_id,
                        )
                task.status = TaskStatus.FAILED.value
                task.error_message = task.error_message or "文档处理失败，正在清理残留数据"
                task.updated_at = datetime.utcnow()
                await self._repo.save(task)
                continue
            if status in {None, "failed"}:
                task.status = TaskStatus.FAILED.value
                task.error_message = task.error_message or (
                    "文档不存在" if status is None else "文档处理失败"
                )
                task.updated_at = datetime.utcnow()
                await self._repo.save(task)
                continue
            self._schedule(task)
            recovered += 1

        if recovered:
            logger.info("已恢复 %d 个未完成的文档任务", recovered)
        return recovered

    async def close(self) -> None:
        """停止接收任务，等待已经排队和运行中的任务完成。"""
        self._accepting = False
        while self._handles:
            handles = tuple(self._handles)
            logger.info("等待 %d 个文档任务完成后关闭", len(handles))
            await asyncio.gather(*handles, return_exceptions=True)

    def _schedule(self, task: TaskInfo) -> None:
        if task.task_id in self._scheduled_ids:
            return
        self._scheduled_ids.add(task.task_id)
        handle = asyncio.create_task(
            self._run_limited(task),
            name=f"document-index-{task.task_id}",
        )
        self._handles.add(handle)

        def _finished(done: asyncio.Task) -> None:
            self._handles.discard(done)
            self._scheduled_ids.discard(task.task_id)

        handle.add_done_callback(_finished)

    async def _run_limited(self, task: TaskInfo) -> None:
        async with self._semaphore:
            await self._run(task)

    async def _run(self, task: TaskInfo):
        try:
            await self._worker.execute(task.document_id, task.task_id)
            task.status = TaskStatus.DONE.value
            task.progress = 1.0
            task.error_message = None
        except asyncio.CancelledError:
            task.status = TaskStatus.INTERRUPTED.value
            task.error_message = "服务关闭时任务被中断，将在下次启动时恢复"
            raise
        except Exception as e:
            logger.exception("任务失败: task=%s, error=%s", task.task_id, e)
            task.status = TaskStatus.FAILED.value
            task.error_message = str(e)
        finally:
            task.updated_at = datetime.utcnow()
            try:
                await asyncio.shield(self._repo.save(task))
            except Exception:
                logger.exception("保存任务最终状态失败: task=%s", task.task_id)
