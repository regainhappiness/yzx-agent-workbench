import asyncio
from types import SimpleNamespace
from typing import get_origin

from mcp.types import Tool
from pydantic import BaseModel

from src.tools.mcp.convert import json_schema_to_pydantic, to_langchain_tool


def test_scalar_and_required_optional():
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索词"},
            "limit": {"type": "integer", "description": "条数"},
        },
        "required": ["query"],
    }
    M = json_schema_to_pydantic(schema, "Search")
    assert issubclass(M, BaseModel)
    assert "query" in M.model_fields
    assert M.model_fields["query"].is_required()
    assert not M.model_fields["limit"].is_required()


def test_nested_object_and_array():
    schema = {
        "type": "object",
        "properties": {
            "filter": {
                "type": "object",
                "properties": {"min": {"type": "number"}},
                "required": ["min"],
            },
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["filter", "tags"],
    }
    M = json_schema_to_pydantic(schema, "Complex")
    assert M.model_fields["filter"].annotation.__name__ == "Complex_filter"
    assert get_origin(M.model_fields["tags"].annotation) is list


def test_enum_and_unknown_fallback():
    schema = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["a", "b"]},
            "opaque": {"$ref": "#/defs/X"},
        },
        "required": ["kind", "opaque"],
    }
    M = json_schema_to_pydantic(schema, "EnumCase")
    assert M.model_fields["kind"].annotation.__name__ == "Literal"
    assert M.model_fields["opaque"].annotation is not None


class _FakeConn:
    cfg = SimpleNamespace(name="knowledge")

    def __init__(self):
        self.calls = []

    async def call(self, name, args):
        self.calls.append((name, args))
        return "hit"


def test_to_langchain_tool_namespace_and_invoke():
    mcp_tool = Tool(
        name="search",
        description="搜索知识库",
        input_schema={"type": "object",
                      "properties": {"q": {"type": "string"}},
                      "required": ["q"]},
    )
    lt = to_langchain_tool(_FakeConn(), mcp_tool)
    assert lt.name == "knowledge_search"          # 下划线命名空间，满足模型名约束
    result = asyncio.run(lt.ainvoke({"q": "x"}))
    assert result == "hit"


def test_to_langchain_tool_omits_optional_none_arguments():
    connection = _FakeConn()
    mcp_tool = Tool(
        name="analyze_image",
        description="分析图片",
        input_schema={
            "type": "object",
            "properties": {
                "image_path": {"type": "string"},
                "prompt": {"type": "string"},
            },
            "required": ["image_path"],
        },
    )
    langchain_tool = to_langchain_tool(connection, mcp_tool)

    result = asyncio.run(langchain_tool.ainvoke({
        "image_path": "picture.png",
        "prompt": None,
    }))

    assert result == "hit"
    assert connection.calls == [
        ("analyze_image", {"image_path": "picture.png"}),
    ]
