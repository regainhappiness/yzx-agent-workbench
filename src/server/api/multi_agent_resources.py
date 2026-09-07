"""Workspace and attachment endpoints for Multi-Agent sessions."""

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile

from ..deps import get_identity, get_multi_agent_workspace_service
from ..repositories.base import Identity, MultiAgentAttachment, MultiAgentWorkspace
from ..schemas import (
    MultiAgentAttachmentResponse,
    MultiAgentWorkspaceRequest,
    MultiAgentWorkspaceResponse,
    MultiAgentWorkspaceRootsResponse,
)
from ..services.multi_agent_workspace_service import MultiAgentWorkspaceService


router = APIRouter()


def _workspace_response(workspace: MultiAgentWorkspace) -> MultiAgentWorkspaceResponse:
    return MultiAgentWorkspaceResponse(
        session_id=workspace.session_id,
        root_path=workspace.root_path,
        permission=workspace.permission,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


def _attachment_response(
    service: MultiAgentWorkspaceService,
    attachment: MultiAgentAttachment,
) -> MultiAgentAttachmentResponse:
    return MultiAgentAttachmentResponse(
        attachment_id=attachment.attachment_id,
        session_id=attachment.session_id,
        turn_id=attachment.turn_id,
        filename=attachment.filename,
        mime_type=attachment.mime_type,
        file_size=attachment.file_size,
        source=attachment.source,
        kind=service.file_kind(attachment.filename, attachment.mime_type),
        created_at=attachment.created_at,
    )


@router.get(
    "/multi-agent/workspace-roots",
    response_model=MultiAgentWorkspaceRootsResponse,
)
async def list_workspace_roots(
    identity: Identity = Depends(get_identity),
    service: MultiAgentWorkspaceService = Depends(get_multi_agent_workspace_service),
):
    del identity
    return MultiAgentWorkspaceRootsResponse(
        roots=[str(root) for root in service.allowed_roots],
    )


@router.put(
    "/multi-agent/sessions/{session_id}/workspace",
    response_model=MultiAgentWorkspaceResponse,
)
async def configure_workspace(
    session_id: str,
    body: MultiAgentWorkspaceRequest,
    identity: Identity = Depends(get_identity),
    service: MultiAgentWorkspaceService = Depends(get_multi_agent_workspace_service),
):
    workspace = await service.configure_workspace(
        identity.user_id, session_id, body.root_path, body.permission,
    )
    return _workspace_response(workspace)


@router.get(
    "/multi-agent/sessions/{session_id}/workspace",
    response_model=MultiAgentWorkspaceResponse | None,
)
async def get_workspace(
    session_id: str,
    identity: Identity = Depends(get_identity),
    service: MultiAgentWorkspaceService = Depends(get_multi_agent_workspace_service),
):
    workspace = await service.get_workspace(identity.user_id, session_id)
    return _workspace_response(workspace) if workspace else None


@router.post(
    "/multi-agent/sessions/{session_id}/attachments",
    response_model=MultiAgentAttachmentResponse,
    status_code=201,
)
async def upload_attachment(
    session_id: str,
    file: UploadFile = File(...),
    source: Literal["file_picker", "clipboard"] = Form("file_picker"),
    identity: Identity = Depends(get_identity),
    service: MultiAgentWorkspaceService = Depends(get_multi_agent_workspace_service),
):
    content = await file.read(service.max_attachment_bytes + 1)
    attachment = await service.save_attachment(
        user_id=identity.user_id,
        session_id=session_id,
        filename=file.filename or "attachment.bin",
        content=content,
        mime_type=file.content_type,
        source=source,
    )
    return _attachment_response(service, attachment)


@router.get(
    "/multi-agent/sessions/{session_id}/attachments",
    response_model=list[MultiAgentAttachmentResponse],
)
async def list_attachments(
    session_id: str,
    identity: Identity = Depends(get_identity),
    service: MultiAgentWorkspaceService = Depends(get_multi_agent_workspace_service),
):
    attachments = await service.list_attachments(identity.user_id, session_id)
    return [_attachment_response(service, item) for item in attachments]


@router.delete(
    "/multi-agent/sessions/{session_id}/attachments/{attachment_id}",
    status_code=204,
)
async def delete_attachment(
    session_id: str,
    attachment_id: str,
    identity: Identity = Depends(get_identity),
    service: MultiAgentWorkspaceService = Depends(get_multi_agent_workspace_service),
):
    await service.delete_attachment(identity.user_id, session_id, attachment_id)
