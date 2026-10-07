import logging
from typing import Any

from pydantic import BaseModel, ValidationError

from app.assistant.tools.base import Tool, ToolContext
from app.assistant.tools.inventory_tools import INVENTORY_TOOLS
from app.common.errors import AppError

logger = logging.getLogger(__name__)

ALL_TOOLS: dict[str, Tool] = {tool.name: tool for tool in INVENTORY_TOOLS}


class ToolResult(BaseModel):
    """What goes back to the model. Errors are results too, never a 500."""

    is_error: bool = False
    content: dict[str, Any]


def tools_for(user_permissions: set[str]) -> list[Tool]:
    return [t for t in ALL_TOOLS.values() if t.permission in user_permissions]


def _error(error_code: str, detail: Any) -> ToolResult:
    return ToolResult(is_error=True, content={"error_code": error_code, "detail": detail})


async def run_tool(
    name: str,
    raw_input: dict[str, Any],
    ctx: ToolContext,
    user_permissions: set[str],
) -> ToolResult:
    tool = ALL_TOOLS.get(name)
    # checked again here: the model can name a tool it was never given
    if tool is None or tool.permission not in user_permissions:
        logger.warning("run_tool: tool not available", extra={"tool": name, "user_id": ctx.user_id})
        return _error("TOOL_NOT_AVAILABLE", f"Tool '{name}' is not available")

    try:
        args = tool.input_schema.model_validate(raw_input)
    except ValidationError as exc:
        return _error("INVALID_TOOL_INPUT", exc.errors(include_url=False, include_context=False))

    try:
        output = await tool.handler(args, ctx)
    except AppError as exc:
        return _error(exc.error_code, exc.message)

    return ToolResult(content=output.model_dump(mode="json"))
