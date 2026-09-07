"""MCP 传输层：协议 + 两种传输实现（MCP 2.0 / SDK v2）。"""
from contextlib import asynccontextmanager
from typing import Protocol

import httpx2
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from .config import McpServerConfig


class McpTransport(Protocol):
    def open(self):
        """异步上下文管理器，yield (read_stream, write_stream)。"""
        ...


class StdioTransport:
    def __init__(self, cfg: McpServerConfig):
        if not cfg.command:
            raise ValueError("stdio 传输需要 command")
        self._params = StdioServerParameters(
            command=cfg.command, args=cfg.args, env=cfg.env or None)

    @asynccontextmanager
    async def open(self):
        async with stdio_client(self._params) as (read, write):
            yield read, write


class StreamableHttpTransport:
    """v2：`streamable_http_client`（正确拼写）需自建 httpx2.AsyncClient，返回 2 元组。"""

    def __init__(self, cfg: McpServerConfig):
        if not cfg.url:
            raise ValueError("streamable-http 传输需要 url")
        self._url = cfg.url
        self._headers = cfg.headers or None
        self._timeout = httpx2.Timeout(cfg.timeout_seconds)

    @asynccontextmanager
    async def open(self):
        async with httpx2.AsyncClient(headers=self._headers, timeout=self._timeout) as client:
            async with streamable_http_client(self._url, http_client=client) as (read, write):
                yield read, write


def build_transport(cfg: McpServerConfig) -> McpTransport:
    if cfg.transport == "stdio":
        return StdioTransport(cfg)
    if cfg.transport == "streamable-http":
        return StreamableHttpTransport(cfg)
    raise ValueError(f"未知 MCP 传输类型: {cfg.transport}")
