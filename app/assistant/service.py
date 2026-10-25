"""Agent loop: message -> LLM -> tools -> answer. The LLM only explains; every
number comes from a tool, and tools only call services."""

import asyncio
import json
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.exceptions import (
    AssistantQuotaExceeded,
    AssistantTimeout,
    AssistantUnavailable,
)
from app.assistant.prompts import (
    EMPTY_ANSWER,
    MAX_ITERATIONS_ANSWER,
    REFUSAL_ANSWER,
    SYSTEM_PROMPT,
    TRUNCATED_ANSWER,
)
from app.assistant.schemas import ChatMessage, ChatResponse
from app.assistant.tools.base import ToolContext
from app.assistant.tools.registry import run_tool, tools_for
from app.assistant.usage import UsageMeter, charge, used_today
from app.infra.llm.client import LLMClient, LLMError
from app.inventory.service import InventoryService
from app.rbac.service import RBACService

logger = logging.getLogger(__name__)


class AssistantService:
    def __init__(
        self,
        llm: LLMClient,
        db: AsyncSession,
        rbac_service: RBACService,
        inventory_service: InventoryService,
        max_iterations: int,
        deadline_seconds: float,
        max_cost_per_request: int,
        daily_cost_per_user: int,
    ):
        self.llm = llm
        self.db = db
        self.rbac_service = rbac_service
        self.inventory_service = inventory_service
        self.max_iterations = max_iterations
        self.deadline_seconds = deadline_seconds
        self.max_cost_per_request = max_cost_per_request
        self.daily_cost_per_user = daily_cost_per_user

    async def chat(
        self,
        user_id: uuid.UUID,
        location_id: uuid.UUID,
        messages: list[ChatMessage],
    ) -> ChatResponse:
        if await used_today(user_id) >= self.daily_cost_per_user:
            logger.warning(
                "assistant daily quota exceeded",
                extra={"user_id": user_id, "daily_cost_per_user": self.daily_cost_per_user},
            )
            raise AssistantQuotaExceeded()

        meter = UsageMeter()
        # one deadline for the whole loop, below the ALB idle timeout
        try:
            return await asyncio.wait_for(
                self._chat(user_id, location_id, messages, meter),
                timeout=self.deadline_seconds,
            )
        except asyncio.TimeoutError as exc:
            logger.warning(
                "assistant hit the deadline",
                extra={"user_id": user_id, "deadline_seconds": self.deadline_seconds},
            )
            raise AssistantTimeout() from exc
        finally:
            # tokens are billed even when the loop timed out or the LLM failed
            await charge(user_id, meter.cost_units)

    async def _chat(
        self,
        user_id: uuid.UUID,
        location_id: uuid.UUID,
        messages: list[ChatMessage],
        meter: UsageMeter,
    ) -> ChatResponse:
        permissions = await self.rbac_service.get_user_permissions(user_id)
        # read-only: end the transaction so the connection isn't held while the LLM runs
        await self.db.commit()
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
        answer = MAX_ITERATIONS_ANSWER
        stop_reason: str | None = None
        iterations = 0

        for _ in range(self.max_iterations):
            if meter.cost_units >= self.max_cost_per_request:
                logger.warning(
                    "assistant hit the request budget",
                    extra={"user_id": user_id, "cost_units": meter.cost_units},
                )
                break

            try:
                response = await self.llm.create(
                    system=SYSTEM_PROMPT, messages=conversation, tools=definitions
                )
            except LLMError as exc:
                raise AssistantUnavailable() from exc

            iterations += 1
            meter.add(response.usage)
            stop_reason = response.stop_reason

            if stop_reason == "refusal":
                answer = REFUSAL_ANSWER
                break

            # a cut tool_use block has incomplete input, a cut text is a partial answer
            if stop_reason == "max_tokens":
                logger.warning(
                    "assistant response hit max_tokens",
                    extra={"user_id": user_id, "output_tokens": response.usage.output_tokens},
                )
                answer = TRUNCATED_ANSWER
                break

            if stop_reason == "pause_turn":
                conversation.append({"role": "assistant", "content": response.content})
                continue

            if stop_reason != "tool_use":
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
            await self.db.commit()
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
                "input_tokens": meter.input_tokens,
                "output_tokens": meter.output_tokens,
                "cache_read_input_tokens": meter.cache_read_input_tokens,
                "cache_creation_input_tokens": meter.cache_creation_input_tokens,
                "cost_units": meter.cost_units,
            },
        )

        return ChatResponse(
            answer=answer, tools_called=tools_called, iterations=iterations
        )
