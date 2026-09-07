"""MCP 连接管理、工具发现与熔断。"""
import asyncio
import logging
import os
import tempfile
import time
from contextlib import AsyncExitStack, suppress
from pathlib import Path

from mcp import ClientSession
from mcp.types import Tool
from langchain_core.tools import BaseTool

from .config import McpConfig, McpServerConfig
from .transport import build_transport
from .scope import current_file_scope
from .convert import to_langchain_tool

logger = logging.getLogger(__name__)

_SESSION_FILE_AGENTS = {"workspace_file_agent", "vision_agent"}
_WRITE_TOOL_NAMES = {
    "write_file", "edit_file", "create_directory", "move_file",
    "delete_file", "remove_file", "remove_directory", "rename_file",
}
# _BLOCKED_SESSION_TOOLS = {
#     "analyze_clipboard", "extract_text_from_clipboard",
#     "describe_ui_from_clipboard", "diagnose_error_from_clipboard",
#     "code_from_clipboard", "list_allowed_directories",
# }
_BLOCKED_SESSION_TOOLS = {}
_PATH_KEYS = {
    "path", "paths", "file_path", "image_path", "source", "destination",
    "source_path", "destination_path", "directory", "root",
}

_VISION_DEFAULT_MAX_DIMENSION = 1280


def _vision_max_dimension(cfg: McpServerConfig) -> int:
    raw_value = cfg.env.get(
        "MKA_VISION_MAX_DIMENSION",
        os.getenv("MCP_VISION_MAX_DIMENSION", str(_VISION_DEFAULT_MAX_DIMENSION)),
    )
    try:
        configured = int(raw_value)
    except (TypeError, ValueError):
        configured = _VISION_DEFAULT_MAX_DIMENSION
    return max(512, min(2048, configured))


def _result_retry_limit(cfg: McpServerConfig) -> int:
    raw_value = cfg.env.get(
        "MKA_MCP_RESULT_RETRIES",
        os.getenv("MCP_RESULT_RETRIES", "1"),
    )
    try:
        configured = int(raw_value)
    except (TypeError, ValueError):
        configured = 1
    return max(0, min(2, configured))


def _is_retryable_result(text: str) -> bool:
    normalized = text.strip().lower()
    return normalized.startswith(("错误:", "error:")) and any(
        marker in normalized
        for marker in ("request timed out", "request timeout", "timed out")
    )


def _prepare_vision_image(
    cfg: McpServerConfig,
    arguments: dict,
) -> tuple[dict, list[Path]]:
    """Create an internal, short-lived analysis copy for oversized images."""
    if "vision_agent" not in cfg.subagents:
        return arguments, []
    raw_path = arguments.get("image_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return arguments, []

    source = Path(raw_path).resolve()
    if not source.is_file():
        return arguments, []

    from PIL import Image, ImageOps

    max_dimension = _vision_max_dimension(cfg)
    with Image.open(source) as opened:
        original_format = opened.format or "PNG"
        image = ImageOps.exif_transpose(opened)
        width, height = image.size
        if width <= max_dimension and height <= max_dimension:
            return arguments, []

        image.thumbnail(
            (max_dimension, max_dimension),
            Image.Resampling.LANCZOS,
        )
        resized_width, resized_height = image.size
        save_format = original_format.upper()
        suffix = source.suffix.lower()
        if save_format in {"JPEG", "JPG"}:
            suffix = ".jpg"
            if image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")
        elif save_format not in {"PNG", "WEBP", "BMP", "GIF", "TIFF"}:
            save_format = "PNG"
            suffix = ".png"

        descriptor, temporary_name = tempfile.mkstemp(
            prefix="mka-vision-", suffix=suffix or ".png",
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name).resolve()
        try:
            save_kwargs = {"quality": 92} if save_format in {"JPEG", "WEBP"} else {}
            image.save(temporary_path, format=save_format, **save_kwargs)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    normalized = dict(arguments)
    normalized["image_path"] = str(temporary_path)
    logger.info(
        "Vision image resized for MCP: source=%s original=%dx%d resized=%dx%d "
        "max_dimension=%d temp=%s",
        source, width, height, resized_width, resized_height, max_dimension,
        temporary_path,
    )
    return normalized, [temporary_path]


def _is_session_file_server(cfg: McpServerConfig) -> bool:
    return bool(_SESSION_FILE_AGENTS.intersection(cfg.subagents))


def _is_blocked_session_tool(cfg: McpServerConfig, tool_name: str) -> bool:
    return _is_session_file_server(cfg) and (
        #tool_name in _BLOCKED_SESSION_TOOLS or "clipboard" in tool_name.lower()
        tool_name in _BLOCKED_SESSION_TOOLS
    )


def _log_argument_summary(arguments: dict) -> dict:
    """Keep file paths visible without dumping prompts or file contents to logs."""
    summary = {}
    for key, value in arguments.items():
        if key in _PATH_KEYS or key.endswith("_path"):
            summary[key] = value
        elif value is None or isinstance(value, (bool, int, float)):
            summary[key] = value
        elif isinstance(value, (list, tuple)):
            summary[key] = f"<{type(value).__name__}:{len(value)}>"
        else:
            summary[key] = f"<{type(value).__name__}:{len(str(value))} chars>"
    return summary


def _extract_text(result) -> str:
    parts = []
    for block in getattr(result, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", ""))
    return "\n".join(parts)


def _scoped_arguments(cfg: McpServerConfig, tool_name: str, arguments: dict):
    """Validate and normalize paths for MCPs assigned to file-aware agents."""
    if not _is_session_file_server(cfg):
        return arguments, None
    scope = current_file_scope()
    if scope is None:
        return arguments, "当前 MCP 调用缺少会话文件权限上下文"
    if _is_blocked_session_tool(cfg, tool_name):
        return arguments, "请使用对话框粘贴或上传图片，不能直接读取系统剪贴板"

    is_write = tool_name in _WRITE_TOOL_NAMES or any(
        marker in tool_name
        for marker in ("write", "edit", "create", "move", "delete", "remove", "rename")
    )
    if is_write and scope.permission != "read_write":
        return arguments, "当前工作区是只读权限，不能执行写入操作"

    normalized = dict(arguments)
    checked = 0
    for key, value in list(normalized.items()):
        if key not in _PATH_KEYS and not key.endswith("_path"):
            continue
        values = value if isinstance(value, list) else [value]
        output_values = []
        for item in values:
            if not isinstance(item, str) or not item.strip():
                output_values.append(item)
                continue
            candidate = Path(item).expanduser()
            if not candidate.is_absolute():
                candidate = scope.workspace_root / candidate
            resolved = candidate.resolve()
            allowed = scope.can_write(resolved) if is_write else scope.can_read(resolved)
            if not allowed:
                return arguments, f"路径超出当前会话授权范围: {item}"
            output_values.append(str(resolved))
            checked += 1
        normalized[key] = output_values if isinstance(value, list) else output_values[0]

    if checked == 0:
        # File-aware tools must not gain implicit access through hidden defaults.
        return arguments, "文件工具调用必须显式提供当前会话中的路径"
    return normalized, None


class McpConnection:
    """单个 MCP Server 的连接与调用封装，含熔断。"""

    def __init__(self, cfg: McpServerConfig):
        self.cfg = cfg
        self._transport = build_transport(cfg)
        self._session: ClientSession | None = None
        self._stack: AsyncExitStack | None = None
        self._reconnect_lock = asyncio.Lock()
        self._ever_connected = False
        self._closed = False
        self.available = False
        self._failures = 0

    async def connect(self):
        if self._closed:
            raise RuntimeError(f"MCP 服务器 {self.cfg.name} 已关闭")
        self._stack = AsyncExitStack()
        try:
            read, write = await self._stack.enter_async_context(self._transport.open())
            self._session = await self._stack.enter_async_context(ClientSession(read, write))
            # v2: initialize() 用于自动向下协商；纯无状态服务器可改用 discover()/adopt()
            await self._session.initialize()
        except Exception:
            await self._close_transport()
            raise
        self._ever_connected = True
        self._failures = 0
        self.available = True

    async def _close_transport(self) -> None:
        stack = self._stack
        self._stack = None
        self._session = None
        self.available = False
        if stack is not None:
            with suppress(Exception):
                await stack.aclose()

    async def _reconnect(self) -> bool:
        if self.available:
            return True
        if not self._ever_connected or self._closed:
            return False
        async with self._reconnect_lock:
            if self.available:
                return True
            logger.warning("MCP reconnecting: server=%s", self.cfg.name)
            await self._close_transport()
            try:
                async with asyncio.timeout(self.cfg.timeout_seconds):
                    await self.connect()
            except Exception as exc:
                logger.exception(
                    "MCP reconnect failed: server=%s error=%s",
                    self.cfg.name, exc,
                )
                return False
            logger.info("MCP reconnected: server=%s", self.cfg.name)
            return True

    async def list_tools(self) -> list[Tool]:
        result = await self._session.list_tools()
        return list(result.tools)

    async def call(self, tool_name: str, arguments: dict) -> str:
        if not self.available and not await self._reconnect():
            logger.warning("MCP call rejected: server=%s tool=%s unavailable", self.cfg.name, tool_name)
            return f"[MCP] 服务器 {self.cfg.name} 当前不可用"
        arguments, permission_error = _scoped_arguments(
            self.cfg, tool_name, arguments,
        )
        if permission_error:
            logger.warning(
                "MCP permission rejected: server=%s tool=%s reason=%s args=%s",
                self.cfg.name, tool_name, permission_error,
                _log_argument_summary(arguments),
            )
            return f"[MCP] 权限校验失败: {permission_error}"
        started_at = time.monotonic()
        temporary_paths: list[Path] = []
        cancel_task = None
        try:
            arguments, temporary_paths = await asyncio.to_thread(
                _prepare_vision_image, self.cfg, arguments,
            )
            scope = current_file_scope()
            cancel_task = (
                asyncio.create_task(scope.cancellation_event.wait())
                if scope is not None and scope.cancellation_event is not None
                else None
            )
            max_attempts = 1 + _result_retry_limit(self.cfg)
            for attempt in range(1, max_attempts + 1):
                logger.info(
                    "MCP call started: server=%s tool=%s attempt=%d/%d args=%s",
                    self.cfg.name, tool_name, attempt, max_attempts,
                    _log_argument_summary(arguments),
                )
                attempt_started_at = time.monotonic()
                call_task = asyncio.create_task(
                    self._session.call_tool(tool_name, arguments),
                )
                waiters = {call_task}
                if cancel_task is not None:
                    waiters.add(cancel_task)
                done, _ = await asyncio.wait(
                    waiters,
                    timeout=self.cfg.timeout_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if cancel_task is not None and cancel_task in done:
                    call_task.cancel()
                    with suppress(BaseException):
                        await call_task
                    logger.info(
                        "MCP call cancelled: server=%s tool=%s elapsed_ms=%d",
                        self.cfg.name, tool_name,
                        int((time.monotonic() - started_at) * 1000),
                    )
                    return "[MCP] 工具调用已由用户中止"
                if call_task not in done:
                    call_task.cancel()
                    with suppress(BaseException):
                        await call_task
                    raise TimeoutError(
                        f"MCP 工具调用超过 {self.cfg.timeout_seconds:g} 秒",
                    )
                result = await call_task
                self._failures = 0
                text = _extract_text(result)
                attempt_ms = int((time.monotonic() - attempt_started_at) * 1000)
                if _is_retryable_result(text):
                    if attempt < max_attempts:
                        logger.warning(
                            "MCP result retrying: server=%s tool=%s attempt=%d/%d "
                            "elapsed_ms=%d reason=%s",
                            self.cfg.name, tool_name, attempt, max_attempts,
                            attempt_ms, text,
                        )
                        continue
                    logger.error(
                        "MCP result retries exhausted: server=%s tool=%s "
                        "attempts=%d elapsed_ms=%d reason=%s",
                        self.cfg.name, tool_name, max_attempts,
                        int((time.monotonic() - started_at) * 1000), text,
                    )
                    return f"[MCP] 工具结果重试已耗尽: {text}"
                logger.info(
                    "MCP call completed: server=%s tool=%s attempt=%d/%d "
                    "elapsed_ms=%d total_elapsed_ms=%d result_chars=%d",
                    self.cfg.name, tool_name, attempt, max_attempts, attempt_ms,
                    int((time.monotonic() - started_at) * 1000), len(text),
                )
                return text
            return "[MCP] 工具调用未返回结果"
        except Exception as e:
            self._failures += 1
            if self._failures >= 3:
                self.available = False
            logger.exception(
                "MCP call failed: server=%s tool=%s elapsed_ms=%d failures=%d",
                self.cfg.name, tool_name,
                int((time.monotonic() - started_at) * 1000), self._failures,
            )
            return f"[MCP] 工具调用失败: {e}"
        finally:
            if cancel_task is not None:
                cancel_task.cancel()
                with suppress(BaseException):
                    await cancel_task
            for temporary_path in temporary_paths:
                temporary_path.unlink(missing_ok=True)

    async def close(self):
        self._closed = True
        await self._close_transport()


def _allowed(allowed: list[str], name: str) -> bool:
    return "*" in allowed or name in allowed


class McpAdapter:
    """编排多个 MCP Server：连接、发现工具、转换为内部工具描述。"""

    def __init__(self, config: McpConfig):
        self.config = config
        self._connections: list[McpConnection] = []
        self.server_statuses: dict[str, dict] = {}

    async def discover(self) -> tuple[list[BaseTool], dict[str, dict]]:
        if not self.config.enabled:
            return [], {}
        tools: list[BaseTool] = []
        metas: dict[str, dict] = {}
        for server_cfg in self.config.servers:
            if not server_cfg.enabled:
                logger.info("MCP '%s' 已禁用，跳过", server_cfg.name)
                self.server_statuses[server_cfg.name] = {
                    "status": "disabled", "error": None, "tool_count": 0,
                }
                continue
            conn = McpConnection(server_cfg)
            try:
                async with asyncio.timeout(server_cfg.timeout_seconds):
                    await conn.connect()
            except Exception as e:
                error_message = str(e) or type(e).__name__
                logger.warning("MCP '%s' 连接失败，已跳过: %s", server_cfg.name, error_message)
                self.server_statuses[server_cfg.name] = {
                    "status": "error", "error": error_message, "tool_count": 0,
                }
                try:
                    await conn.close()
                except Exception:
                    pass
                continue
            self._connections.append(conn)
            try:
                tool_count = 0
                async with asyncio.timeout(server_cfg.timeout_seconds):
                    discovered_tools = await conn.list_tools()
                for t in discovered_tools:
                    if not _allowed(server_cfg.allowed_tools, t.name):
                        continue
                    if _is_blocked_session_tool(server_cfg, t.name):
                        logger.info(
                            "MCP '%s' 不向会话文件 Agent 暴露受限工具: %s",
                            server_cfg.name, t.name,
                        )
                        continue
                    tool = to_langchain_tool(conn, t)
                    tools.append(tool)
                    tool_count += 1
                    metas[tool.name] = {"category": "mcp",
                                        "tags": ["mcp", server_cfg.name],
                                        "version": "1.0.0",
                                        "subagents": server_cfg.subagents}
                self.server_statuses[server_cfg.name] = {
                    "status": "connected", "error": None,
                    "tool_count": tool_count,
                }
            except Exception as e:
                error_message = str(e) or type(e).__name__
                logger.warning("MCP '%s' 工具发现失败: %s", server_cfg.name, error_message)
                self.server_statuses[server_cfg.name] = {
                    "status": "error", "error": error_message, "tool_count": 0,
                }
        return tools, metas

    async def close(self):
        for conn in self._connections:
            await conn.close()
        self._connections = []
