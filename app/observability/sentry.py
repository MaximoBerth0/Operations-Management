import sentry_sdk
from app.infra.config import settings


def setup_sentry(component: str) -> None:
    """No-op without a DSN. A second call (the API imports the worker) only retags."""
    if not settings.SENTRY_DSN:
        return

    if not sentry_sdk.is_initialized():
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENV,
            release=settings.GIT_SHA,
            send_default_pii=False,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            before_send=_drop_procrastinate_job_error,
        )
    sentry_sdk.set_tag("component", component)


def _drop_procrastinate_job_error(event, hint):
    """The worker middleware already captured it, with the job's context."""
    if event.get("logger") == "procrastinate.worker" and (
        event.get("extra", {}).get("action") == "job_error"
    ):
        return None
    return event


def cron_monitor(slug: str, cron: str, *, checkin_margin: int, max_runtime: int):
    """`cron` must match the task's `@app.periodic` schedule (UTC)."""
    return sentry_sdk.monitor(
        monitor_slug=slug,
        monitor_config={
            "schedule": {"type": "crontab", "value": cron},
            "timezone": "UTC",
            "checkin_margin": checkin_margin,
            "max_runtime": max_runtime,
        },
    )
