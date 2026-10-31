"""Per-job log id, Sentry scope and transaction. Task args stay out of Sentry."""

import asyncio

import sentry_sdk
from procrastinate import JobContext
from procrastinate.exceptions import JobAborted

from app.observability.request_id import request_id_var


async def job_context_middleware(call_next, context: JobContext, worker):
    job = context.job
    token = request_id_var.set(f"job-{job.id}")
    try:
        with sentry_sdk.isolation_scope() as scope:
            scope.set_tag("component", "worker")
            scope.set_tag("task", job.task_name)
            scope.set_tag("queue", job.queue)
            scope.set_tag("job_id", str(job.id))
            scope.set_context(
                "job",
                {
                    "id": job.id,
                    "task": job.task_name,
                    "attempt": job.attempts + 1,
                    "lock": job.lock,
                    "queueing_lock": job.queueing_lock,
                    "scheduled_at": job.scheduled_at.isoformat()
                    if job.scheduled_at
                    else None,
                    "worker": context.worker_name,
                },
            )
            with sentry_sdk.start_transaction(
                op="queue.task", name=job.task_name, source="task"
            ):
                try:
                    return await call_next()
                except (JobAborted, asyncio.CancelledError):
                    raise
                except Exception as exc:
                    # only the last attempt reports
                    if context.task.get_retry_exception(exception=exc, job=job) is None:
                        sentry_sdk.capture_exception(exc)
                    raise
    finally:
        request_id_var.reset(token)
