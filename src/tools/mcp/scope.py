"""Per-run file scope used by session-aware MCP tool guards."""

import asyncio
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ExecutionFileScope:
    session_id: str
    workspace_root: Path
    permission: str = "read_only"
    attachment_paths: frozenset[Path] = field(default_factory=frozenset)
    cancellation_event: asyncio.Event | None = field(default=None, compare=False)

    def can_read(self, path: Path) -> bool:
        resolved = path.resolve()
        return self._inside_workspace(resolved) or resolved in self.attachment_paths

    def can_write(self, path: Path) -> bool:
        return self.permission == "read_write" and self._inside_workspace(path.resolve())

    def _inside_workspace(self, path: Path) -> bool:
        try:
            path.relative_to(self.workspace_root)
            return True
        except ValueError:
            return False


_CURRENT_FILE_SCOPE: ContextVar[ExecutionFileScope | None] = ContextVar(
    "multi_agent_file_scope", default=None,
)


def current_file_scope() -> ExecutionFileScope | None:
    return _CURRENT_FILE_SCOPE.get()


def set_file_scope(scope: ExecutionFileScope) -> Token:
    return _CURRENT_FILE_SCOPE.set(scope)


def reset_file_scope(token: Token) -> None:
    _CURRENT_FILE_SCOPE.reset(token)


__all__ = [
    "ExecutionFileScope", "current_file_scope", "set_file_scope", "reset_file_scope",
]
