"""Session workspaces and read-only conversation attachments for Multi-Agent."""

import hashlib
import mimetypes
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path

import aiofiles

from ...tools.mcp.scope import ExecutionFileScope
from ..exceptions import AppError, NotFoundError, ValidationError
from ..repositories.base import (
    MultiAgentAttachment,
    MultiAgentAttachmentRepository,
    MultiAgentWorkspace,
    MultiAgentWorkspaceRepository,
)
from .session_service import SessionService


IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff",
}
PDF_OFFICE_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
}
TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".jsonl",
    ".yaml", ".yml", ".xml", ".html", ".htm", ".css", ".js", ".ts",
    ".tsx", ".jsx", ".vue", ".py", ".java", ".go", ".rs", ".c", ".h",
    ".cpp", ".hpp", ".cs", ".php", ".rb", ".sh", ".ps1", ".sql",
    ".toml", ".ini", ".cfg", ".conf", ".log", ".env",
}


class MultiAgentWorkspaceService:
    def __init__(
        self,
        *,
        workspace_repo: MultiAgentWorkspaceRepository,
        attachment_repo: MultiAgentAttachmentRepository,
        session_service: SessionService,
        storage_dir: str,
        allowed_roots: list[str] | None = None,
        max_attachment_bytes: int = 50 * 1024 * 1024,
    ):
        self._workspace_repo = workspace_repo
        self._attachment_repo = attachment_repo
        self._session_service = session_service
        self._storage_root = Path(storage_dir).expanduser().resolve()
        self._storage_root.mkdir(parents=True, exist_ok=True)
        roots = allowed_roots or [os.getcwd()]
        self._allowed_roots = tuple(
            Path(item).expanduser().resolve()
            for item in roots if str(item).strip()
        )
        self._max_attachment_bytes = max(1, int(max_attachment_bytes))

    @property
    def allowed_roots(self) -> tuple[Path, ...]:
        return self._allowed_roots

    @property
    def max_attachment_bytes(self) -> int:
        return self._max_attachment_bytes

    async def configure_workspace(
        self,
        user_id: str,
        session_id: str,
        root_path: str,
        permission: str,
    ) -> MultiAgentWorkspace:
        session = await self._session_service.require_session(
            user_id, session_id, "multi_agent",
        )
        if permission not in {"read_only", "read_write"}:
            raise ValidationError("工作区权限必须是只读或读写")
        try:
            resolved = Path(root_path).expanduser().resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ValidationError("工作区文件夹不存在或无法访问") from exc
        if not resolved.is_dir():
            raise ValidationError("工作区必须是一个文件夹")
        existing = await self._workspace_repo.get(session_id)
        if (
            existing is not None
            and session.message_count > 0
            and Path(existing.root_path).resolve() != resolved
        ):
            raise AppError(
                "WORKSPACE_LOCKED",
                "会话开始后不能更换工作区，请新建 Multi-Agent 会话",
                409,
            )
        if not any(self._is_within(resolved, root) for root in self._allowed_roots):
            raise AppError(
                code="WORKSPACE_OUTSIDE_ALLOWED_ROOTS",
                message="所选文件夹不在后端允许的工作区范围内",
                status_code=403,
                details={"allowed_roots": [str(root) for root in self._allowed_roots]},
            )
        if not os.access(resolved, os.R_OK):
            raise AppError("WORKSPACE_NOT_READABLE", "所选工作区不可读", 403)
        if permission == "read_write" and not os.access(resolved, os.W_OK):
            raise AppError("WORKSPACE_NOT_WRITABLE", "所选工作区不可写", 403)
        return await self._workspace_repo.upsert(MultiAgentWorkspace(
            session_id=session_id,
            user_id=user_id,
            root_path=str(resolved),
            permission=permission,
        ))

    async def get_workspace(
        self, user_id: str, session_id: str,
    ) -> MultiAgentWorkspace | None:
        await self._session_service.require_session(user_id, session_id, "multi_agent")
        workspace = await self._workspace_repo.get(session_id)
        if workspace is not None and workspace.user_id != user_id:
            raise NotFoundError("工作区", session_id)
        return workspace

    async def require_workspace(
        self, user_id: str, session_id: str,
    ) -> MultiAgentWorkspace:
        workspace = await self.get_workspace(user_id, session_id)
        if workspace is None:
            raise AppError(
                code="WORKSPACE_REQUIRED",
                message="请先为当前 Multi-Agent 会话选择工作区",
                status_code=409,
            )
        return workspace

    async def save_attachment(
        self,
        *,
        user_id: str,
        session_id: str,
        filename: str,
        content: bytes,
        mime_type: str | None,
        source: str,
    ) -> MultiAgentAttachment:
        await self.require_workspace(user_id, session_id)
        if source not in {"file_picker", "clipboard"}:
            raise ValidationError("附件来源无效")
        safe_name = self._safe_filename(filename)
        if not content:
            raise ValidationError("不能上传空文件")
        if len(content) > self._max_attachment_bytes:
            raise AppError(
                "ATTACHMENT_TOO_LARGE",
                f"单个附件不能超过 {self._max_attachment_bytes // (1024 * 1024)} MB",
                413,
            )
        attachment_id = str(uuid.uuid4())
        target_dir = self._storage_root / self._safe_component(user_id) / session_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target = (target_dir / f"{attachment_id}-{safe_name}").resolve()
        if not self._is_within(target, self._storage_root):
            raise ValidationError("附件文件名无效")
        async with aiofiles.open(target, "wb") as handle:
            await handle.write(content)
        detected_mime = (
            (mime_type or "").strip()
            or mimetypes.guess_type(safe_name)[0]
            or "application/octet-stream"
        )
        attachment = MultiAgentAttachment(
            attachment_id=attachment_id,
            session_id=session_id,
            user_id=user_id,
            filename=safe_name,
            storage_path=str(target),
            mime_type=detected_mime,
            file_size=len(content),
            file_hash=hashlib.sha256(content).hexdigest(),
            source=source,
        )
        try:
            return await self._attachment_repo.create(attachment)
        except Exception:
            target.unlink(missing_ok=True)
            raise

    async def list_attachments(
        self, user_id: str, session_id: str,
    ) -> list[MultiAgentAttachment]:
        await self._session_service.require_session(user_id, session_id, "multi_agent")
        return [
            item for item in await self._attachment_repo.list_by_session(session_id)
            if item.user_id == user_id
        ]

    async def validate_attachments(
        self, user_id: str, session_id: str, attachment_ids: list[str],
    ) -> list[MultiAgentAttachment]:
        if len(attachment_ids) > 20:
            raise ValidationError("单次消息最多选择 20 个附件")
        unique_ids = list(dict.fromkeys(attachment_ids))
        attachments = []
        for attachment_id in unique_ids:
            item = await self._attachment_repo.get(attachment_id)
            if item is None or item.user_id != user_id or item.session_id != session_id:
                raise NotFoundError("附件", attachment_id)
            if not Path(item.storage_path).is_file():
                raise NotFoundError("附件文件", attachment_id)
            attachments.append(item)
        return attachments

    async def bind_attachments_to_turn(
        self, attachments: list[MultiAgentAttachment], turn_id: str,
    ) -> None:
        await self._attachment_repo.bind_to_turn(
            [item.attachment_id for item in attachments], turn_id,
        )

    async def delete_attachment(
        self, user_id: str, session_id: str, attachment_id: str,
    ) -> None:
        item = await self._attachment_repo.get(attachment_id)
        if item is None or item.user_id != user_id or item.session_id != session_id:
            raise NotFoundError("附件", attachment_id)
        if item.turn_id:
            raise AppError(
                "ATTACHMENT_IN_USE", "已经发送的附件不能单独删除", 409,
            )
        path = Path(item.storage_path).resolve()
        if self._is_within(path, self._storage_root):
            path.unlink(missing_ok=True)
        await self._attachment_repo.delete(attachment_id)

    async def execution_scope(
        self, user_id: str, session_id: str,
    ) -> ExecutionFileScope:
        workspace = await self.require_workspace(user_id, session_id)
        attachments = await self.list_attachments(user_id, session_id)
        return ExecutionFileScope(
            session_id=session_id,
            workspace_root=Path(workspace.root_path).resolve(),
            permission=workspace.permission,
            attachment_paths=frozenset(
                Path(item.storage_path).resolve() for item in attachments
            ),
        )

    async def build_resource_context(
        self,
        user_id: str,
        session_id: str,
        current_attachments: list[MultiAgentAttachment],
    ) -> str:
        workspace = await self.require_workspace(user_id, session_id)
        all_attachments = await self.list_attachments(user_id, session_id)
        current_ids = {item.attachment_id for item in current_attachments}
        permission_label = "可读写" if workspace.permission == "read_write" else "只读"
        lines = [
            "当前会话文件资源（这是受后端权限校验的可信上下文）：",
            f"- 工作区: {workspace.root_path}",
            f"- 工作区权限: {permission_label}",
            "- 对话附件始终只读；只能使用下列明确提供的绝对路径。",
            "- PDF/Office Parser 尚未接入：可以管理这些文件，但不得声称已读取其内容。",
        ]
        if not all_attachments:
            lines.append("- 当前会话没有附件。")
        else:
            lines.append("- 会话附件：")
            for item in all_attachments[-50:]:
                kind = self.file_kind(item.filename, item.mime_type)
                marker = "本轮" if item.attachment_id in current_ids else "历史"
                lines.append(
                    f"  - [{marker}][{kind}] {item.filename} | "
                    f"attachment_id={item.attachment_id} | path={item.storage_path}"
                )
        return "\n".join(lines)

    async def delete_session_resources(self, user_id: str, session_id: str) -> None:
        await self._session_service.require_session(user_id, session_id, "multi_agent")
        attachments = await self.list_attachments(user_id, session_id)
        await self._attachment_repo.delete_by_session(session_id)
        await self._workspace_repo.delete(session_id)
        for item in attachments:
            path = Path(item.storage_path).resolve()
            if self._is_within(path, self._storage_root):
                path.unlink(missing_ok=True)
        session_dir = (
            self._storage_root / self._safe_component(user_id) / session_id
        ).resolve()
        if self._is_within(session_dir, self._storage_root) and session_dir.is_dir():
            shutil.rmtree(session_dir)

    @staticmethod
    def file_kind(filename: str, mime_type: str) -> str:
        extension = Path(filename).suffix.lower()
        if mime_type.startswith("image/") or extension in IMAGE_EXTENSIONS:
            return "image"
        if extension in PDF_OFFICE_EXTENSIONS:
            return "pdf_office_unparsed"
        if mime_type.startswith("text/") or extension in TEXT_EXTENSIONS:
            return "text"
        return "binary"

    @staticmethod
    def _safe_filename(filename: str) -> str:
        normalized = Path((filename or "").replace("\\", "/")).name.strip()
        if not normalized or normalized in {".", ".."} or "\x00" in normalized:
            raise ValidationError("附件文件名无效")
        return normalized[:240]

    @staticmethod
    def _safe_component(value: str) -> str:
        return "".join(char for char in value if char.isalnum() or char in "-_")[:80]

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False


__all__ = [
    "MultiAgentWorkspaceService", "IMAGE_EXTENSIONS", "PDF_OFFICE_EXTENSIONS",
    "TEXT_EXTENSIONS",
]
