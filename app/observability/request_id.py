import logging
import time
import uuid
from contextvars import ContextVar

import sentry_sdk
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

request_id_var: ContextVar[str] = ContextVar("request_id", default="no-request")

logger = logging.getLogger(__name__)


class RequestIdFilter(logging.Filter):
    # stamp every log record with the current request_id from the ContextVar

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request_id_var.set(request_id)
        sentry_sdk.set_tag("request_id", request_id)
        started = time.perf_counter()

        logger.info(
            "Request started",
            extra={
                "method": request.method,
                "path": request.url.path,
            }
        )

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        logger.info(
            "Request finished",
            extra={
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        )

        return response