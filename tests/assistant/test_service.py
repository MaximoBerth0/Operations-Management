import asyncio
import uuid

import pytest
from redis.exceptions import RedisError
from app.assistant.exceptions import AssistantQuotaExceeded, AssistantTimeout
from app.assistant.prompts import MAX_ITERATIONS_ANSWER, TRUNCATED_ANSWER
from app.assistant import usage as usage_module
from app.assistant.schemas import ChatMessage
from app.assistant.service import AssistantService
from app.assistant.usage import UsageMeter, used_today
from app.infra.llm.client import LLMResponse, LLMUsage, ToolCall

MESSAGES = [ChatMessage(role="user", content="what should I restock?")]


class FakeLLM:
    def __init__(self, responses: list[LLMResponse], delay: float = 0):
        self.responses = responses
        self.delay = delay
        self.calls = 0

    async def create(self, **kwargs) -> LLMResponse:
        self.calls += 1
        await asyncio.sleep(self.delay)
        return self.responses.pop(0)


class FakeDB:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


class FakeRBAC:
    async def get_user_permissions(self, user_id):
        return {"stock:view"}


def make_service(
    llm: FakeLLM,
    db: FakeDB | None = None,
    deadline_seconds: float = 5,
    max_cost_per_request: int = 1_000_000,
    daily_cost_per_user: int = 1_000_000,
) -> AssistantService:
    return AssistantService(
        llm=llm,  # type: ignore[arg-type]
        db=db or FakeDB(),  # type: ignore[arg-type]
        rbac_service=FakeRBAC(),  # type: ignore[arg-type]
        inventory_service=None,  # type: ignore[arg-type]
        max_iterations=5,
        deadline_seconds=deadline_seconds,
        max_cost_per_request=max_cost_per_request,
        daily_cost_per_user=daily_cost_per_user,
    )


def tool_use(usage: LLMUsage = LLMUsage()) -> LLMResponse:
    return LLMResponse(
        stop_reason="tool_use",
        text="",
        tool_calls=[ToolCall(id="t1", name="drop_tables", input={})],
        usage=usage,
    )


def end_turn(text: str = "done", usage: LLMUsage = LLMUsage()) -> LLMResponse:
    return LLMResponse(stop_reason="end_turn", text=text, tool_calls=[], usage=usage)


def test_cost_units_weight_cache_and_output():
    meter = UsageMeter()
    meter.add(LLMUsage(input_tokens=100, output_tokens=10, cache_read_input_tokens=1000, cache_creation_input_tokens=40))

    assert meter.cost_units == 100 + 50 + 50 + 50


async def test_db_released_before_each_llm_call():
    db = FakeDB()
    llm = FakeLLM([tool_use(), end_turn()])

    response = await make_service(llm, db).chat(uuid.uuid4(), uuid.uuid4(), MESSAGES)

    assert response.answer == "done"
    assert db.commits == 2  # after permissions, after the tool round


async def test_deadline_raises_timeout():
    llm = FakeLLM([end_turn("late")], delay=1)

    with pytest.raises(AssistantTimeout):
        await make_service(llm, deadline_seconds=0.05).chat(uuid.uuid4(), uuid.uuid4(), MESSAGES)


async def test_max_tokens_does_not_run_tools():
    llm = FakeLLM([
        LLMResponse(stop_reason="max_tokens", text="", tool_calls=[ToolCall(id="t1", name="get_stock_levels", input={})]),
    ])

    response = await make_service(llm).chat(uuid.uuid4(), uuid.uuid4(), MESSAGES)

    assert response.answer == TRUNCATED_ANSWER
    assert response.tools_called == []


async def test_pause_turn_continues_the_loop():
    llm = FakeLLM([LLMResponse(stop_reason="pause_turn", text="", tool_calls=[]), end_turn()])

    response = await make_service(llm).chat(uuid.uuid4(), uuid.uuid4(), MESSAGES)

    assert response.answer == "done"
    assert response.iterations == 2


async def test_request_budget_stops_before_next_call():
    llm = FakeLLM([tool_use(LLMUsage(input_tokens=500)), end_turn()])

    response = await make_service(llm, max_cost_per_request=500).chat(uuid.uuid4(), uuid.uuid4(), MESSAGES)

    assert response.answer == MAX_ITERATIONS_ANSWER
    assert llm.calls == 1


async def test_usage_is_charged_to_the_daily_quota(redis_enabled):
    user_id = uuid.uuid4()
    llm = FakeLLM([end_turn(usage=LLMUsage(input_tokens=300, output_tokens=20))])

    await make_service(llm).chat(user_id, uuid.uuid4(), MESSAGES)

    assert await used_today(user_id) == 400


async def test_timeout_is_still_charged(redis_enabled):
    user_id = uuid.uuid4()
    llm = FakeLLM([tool_use(LLMUsage(input_tokens=300)), end_turn()], delay=0.03)

    with pytest.raises(AssistantTimeout):
        await make_service(llm, deadline_seconds=0.05).chat(user_id, uuid.uuid4(), MESSAGES)

    assert await used_today(user_id) == 300


async def test_quota_exceeded_skips_the_llm(redis_enabled):
    user_id = uuid.uuid4()
    llm = FakeLLM([end_turn(usage=LLMUsage(input_tokens=100))])
    service = make_service(llm, daily_cost_per_user=100)

    await service.chat(user_id, uuid.uuid4(), MESSAGES)
    with pytest.raises(AssistantQuotaExceeded):
        await service.chat(user_id, uuid.uuid4(), MESSAGES)

    assert llm.calls == 1


async def test_quota_fails_open_when_redis_errors(monkeypatch):
    class BrokenRedis:
        async def get(self, key):
            raise RedisError("down")

        def pipeline(self, transaction=True):
            raise RedisError("down")

    monkeypatch.setattr(usage_module, "get_client", lambda: BrokenRedis())
    llm = FakeLLM([end_turn(usage=LLMUsage(input_tokens=100))])

    response = await make_service(llm).chat(uuid.uuid4(), uuid.uuid4(), MESSAGES)

    assert response.answer == "done"
