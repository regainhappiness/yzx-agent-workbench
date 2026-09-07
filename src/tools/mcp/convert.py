"""MCP 工具转换：JSON Schema → Pydantic，MCP Tool → LangChain BaseTool。"""
from typing import Any, Literal

from pydantic import BaseModel, Field, create_model
from langchain_core.tools import BaseTool, StructuredTool

_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def json_schema_to_pydantic(schema: dict, name: str) -> type[BaseModel]:
    """把 JSON Schema 映射为 Pydantic 模型（供 bind_tools 生成参数 schema）。

    不支持的构造（$ref / anyOf / 未知 type）降级为 Any，保证不抛异常。
    """
    props = schema.get("properties", {})
    required = set(schema.get("required") or [])
    fields: dict[str, tuple] = {}
    for key, prop in props.items():
        t = prop.get("type")
        if t == "object" and "properties" in prop:
            py = json_schema_to_pydantic(prop, f"{name}_{key}")
        elif t == "array" and isinstance(prop.get("items"), dict):
            item_schema = prop["items"]
            if item_schema.get("type") == "object":
                item = json_schema_to_pydantic(item_schema, f"{name}_{key}Item")
            else:
                item = _TYPE_MAP.get(item_schema.get("type"), Any)
            py = list[item]
        elif "enum" in prop:
            enum_vals = tuple(prop["enum"])
            if enum_vals and all(isinstance(v, str) for v in enum_vals):
                py = Literal[enum_vals]
            else:
                py = str
        else:
            py = _TYPE_MAP.get(t, Any)
        desc = prop.get("description")
        if key in required:
            fields[key] = (py, Field(description=desc))
        else:
            fields[key] = (py | None, Field(default=None, description=desc))
    return create_model(name, **fields)


def to_langchain_tool(conn, mcp_tool) -> BaseTool:
    """把 MCP Tool 转成 async-only 的 LangChain StructuredTool。

    工具名用 `{server}_{tool}`（下划线）：OpenAI/DeepSeek 函数名不允许 `/`。
    """
    full_name = f"{conn.cfg.name}_{mcp_tool.name}"
    model_name = "".join(c if c.isalnum() else "_" for c in full_name)
    args_model = json_schema_to_pydantic(mcp_tool.input_schema or {}, model_name)

    async def _arun(**kwargs) -> str:
        # Pydantic includes omitted optional fields as ``None``. MCP JSON Schema
        # treats an optional string as either absent or a string, never null.
        clean_kwargs = {key: value for key, value in kwargs.items() if value is not None}
        return await conn.call(mcp_tool.name, clean_kwargs)

    return StructuredTool(
        name=full_name,
        description=mcp_tool.description or "",
        args_schema=args_model,
        coroutine=_arun,
    )
