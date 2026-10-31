import logging
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import sentry_sdk
from httpx import ASGITransport, AsyncClient
from sentry_sdk.transport import Transport
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from app.infra.llm import client as llm_module
from app.observability import sentry as sentry_module
from app.observability.request_id import RequestIdMiddleware, request_id_var
from app.worker import middleware as middleware_module


class CaptureTransport(Transport):
    def __init__(self, options=None):
        super().__init__(options)
        self.envelopes = []

    def capture_envelope(self, envelope):
        self.envelopes.append(envelope)


@pytest.fixture
def sentry_events():
    transport = CaptureTransport()
    sentry_sdk.init(
        dsn="https://key@o0.ingest.sentry.io/0",
        transport=transport,
        traces_sample_rate=1.0,
        default_integrations=False,
    )
    yield transport.envelopes
    sentry_sdk.get_client().close()
    sentry_sdk.get_global_scope().set_client(None)


def _items(envelopes, kind):
    return [
        item.payload.json
        for envelope in envelopes
        for item in envelope.items
        if item.type == kind
    ]


# setup


def test_setup_without_dsn_is_a_noop(monkeypatch):
    monkeypatch.setattr(sentry_module.settings, "SENTRY_DSN", "")
    sentry_module.setup_sentry("api")
    assert not sentry_sdk.is_initialized()


def test_procrastinate_job_error_log_is_dropped():
    event = {"logger": "procrastinate.worker", "extra": {"action": "job_error"}}
    assert sentry_module._drop_procrastinate_job_error(event, {}) is None


def test_other_events_pass_through():
    event = {"logger": "app.orders.service", "extra": {}}
    assert sentry_module._drop_procrastinate_job_error(event, {}) is event


# worker middleware


def _context(retry_exception):
    job = SimpleNamespace(
        id=42,
        task_name="send_email",
        queue="default",
        attempts=0,
        lock=None,
        queueing_lock=None,
        scheduled_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    task = SimpleNamespace(get_retry_exception=lambda exception, job: retry_exception)
    return SimpleNamespace(job=job, task=task, worker_name="worker-1")


async def test_job_gets_its_own_request_id():
    seen = []

    async def call_next():
        seen.append(request_id_var.get())

    await middleware_module.job_context_middleware(call_next, _context(None), None)
    assert seen == ["job-42"]
    assert request_id_var.get() == "no-request"


async def test_final_attempt_failure_is_captured(monkeypatch):
    captured = []
    monkeypatch.setattr(middleware_module.sentry_sdk, "capture_exception", captured.append)

    async def call_next():
        raise RuntimeError("SES down")

    with pytest.raises(RuntimeError):
        await middleware_module.job_context_middleware(call_next, _context(None), None)
    assert len(captured) == 1


async def test_retried_attempt_is_not_captured(monkeypatch):
    captured = []
    monkeypatch.setattr(middleware_module.sentry_sdk, "capture_exception", captured.append)

    async def call_next():
        raise RuntimeError("SES blip")

    with pytest.raises(RuntimeError):
        await middleware_module.job_context_middleware(
            call_next, _context(retry_exception=Exception()), None
        )
    assert captured == []


# request middleware


async def test_request_is_tagged_and_timed(sentry_events, caplog):
    async def boom(request):
        sentry_sdk.capture_message("from a route")
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/boom", boom)])
    app.add_middleware(RequestIdMiddleware)

    caplog.set_level(logging.INFO, logger="app.observability.request_id")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/boom")

    request_id = response.headers["X-Request-ID"]
    [event] = _items(sentry_events, "event")
    assert event["tags"]["request_id"] == request_id

    [finished] = [r for r in caplog.records if r.getMessage() == "Request finished"]
    assert finished.duration_ms >= 0


# LLM span


class _FakeMessages:
    async def create(self, **kwargs):
        return SimpleNamespace(
            model="claude-opus-5-5",
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text="hola")],
            usage=SimpleNamespace(
                input_tokens=10,
                output_tokens=5,
                cache_read_input_tokens=100,
                cache_creation_input_tokens=0,
            ),
        )


async def test_llm_call_records_tokens_without_prompts(sentry_events):
    llm = llm_module.LLMClient(
        api_key="test", model="claude-opus-5-5", max_tokens=100, effort="low", timeout=5
    )
    llm._client = SimpleNamespace(beta=SimpleNamespace(messages=_FakeMessages()))

    with sentry_sdk.start_transaction(name="chat"):
        response = await llm.create(
            system="secret system prompt",
            messages=[{"role": "user", "content": "stock of SKU-123?"}],
            tools=[],
        )
    assert response.text == "hola"

    spans = [s for batch in _items(sentry_events, "span") for s in batch["items"]]
    [span] = [s for s in spans if s["attributes"]["sentry.op"]["value"] == "gen_ai.chat"]
    attrs = {k: v["value"] for k, v in span["attributes"].items()}
    assert attrs["gen_ai.usage.input_tokens"] == 10
    assert attrs["gen_ai.usage.output_tokens"] == 5
    assert attrs["gen_ai.usage.input_tokens.cached"] == 100

    sent = str([e.items[0].payload.json for e in sentry_events])
    assert "SKU-123" not in sent
    assert "secret system prompt" not in sent
