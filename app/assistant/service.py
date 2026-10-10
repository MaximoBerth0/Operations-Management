"""Agent loop: message -> LLM -> tools -> answer. The LLM only explains; every
number comes from a tool, and tools only call services."""

import json
import logging
import uuid
from typing import Any

from app.assistant.exceptions import AssistantUnavailable
from app.assistant.prompts import (
    EMPTY_ANSWER,
    MAX_ITERATIONS_ANSWER,
    REFUSAL_ANSWER,
    SYSTEM_PROMPT,
)
from app.assistant.schemas import ChatMessage, ChatResponse
from app.assistant.tools.base import ToolContext
from app.assistant.tools.registry import run_tool, tools_for
from app.infra.llm.client import LLMClient, LLMError
from app.inventory.service import InventoryService
from app.rbac.service import RBACService

logger = logging.getLogger(__name__)


class AssistantService:
    def __init__(
        self,
        llm: LLMClient,
        rbac_service: RBACService,
        inventory_service: InventoryService,
        max_iterations: int,
    ):
        self.llm = llm
        self.rbac_service = rbac_service
        self.inventory_service = inventory_service
        self.max_iterations = max_iterations

    async def chat(
        self,
        user_id: uuid.UUID,
        location_id: uuid.UUID,
        messages: list[ChatMessage],
    ) -> ChatResponse:
        permissions = await self.rbac_service.get_user_permissions(user_id)
        definitions = [tool.definition() for tool in tools_for(permissions)]
        ctx = ToolContext(
            inventory_service=self.inventory_service,
            user_id=user_id,
            location_id=location_id,
        )

        conversation: list[dict[str, Any]] = [
            {"role": m.role, "content": m.content} for m in messages
        ]
        tools_called: list[str] = []
        input_tokens = output_tokens = 0
        answer = MAX_ITERATIONS_ANSWER
        stop_reason: str | None = None
        iterations = 0

        for iterations in range(1, self.max_iterations + 1):
            try:
                response = await self.llm.create(
                    system=SYSTEM_PROMPT, messages=conversation, tools=definitions
                )
            except LLMError as exc:
                raise AssistantUnavailable() from exc

            input_tokens += response.usage.input_tokens
            output_tokens += response.usage.output_tokens
            stop_reason = response.stop_reason

            if stop_reason == "refusal":
                answer = REFUSAL_ANSWER
                break

            if not response.tool_calls:
                answer = response.text or EMPTY_ANSWER
                break

            conversation.append({"role": "assistant", "content": response.content})

            # sequential on purpose: every tool shares one AsyncSession
            results = []
            for call in response.tool_calls:
                result = await run_tool(call.name, call.input, ctx, permissions)
                tools_called.append(call.name)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": json.dumps(result.content),
                    "is_error": result.is_error,
                })
            # all results in one user turn, even for parallel calls
            conversation.append({"role": "user", "content": results})
        else:
            logger.warning(
                "assistant hit the iteration limit",
                extra={"user_id": user_id, "max_iterations": self.max_iterations},
            )

        logger.info(
            "assistant chat finished",
            extra={
                "user_id": user_id,
                "location_id": location_id,
                "tools_called": tools_called,
                "iterations": iterations,
                "stop_reason": stop_reason,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
        )

        return ChatResponse(
            answer=answer, tools_called=tools_called, iterations=iterations
        )
