"""Out-of-app delivery for transactional email. The request path only
enqueues, the worker is what actually talks to SES, so a slow or failing
provider never holds an HTTP response open.
"""

import hashlib
import logging

from procrastinate import RetryStrategy
from procrastinate.exceptions import AlreadyEnqueued

from app.infra.mail.mailer import Mailer
from app.worker.app import app

logger = logging.getLogger(__name__)

_mailer = Mailer()


@app.task(
    queue="default",
    name="send_reset_email",
    retry=RetryStrategy(max_attempts=3, exponential_wait=5),
)
async def send_reset_email_job(*, email: str, token: str) -> None:
    await _mailer.send_reset_email(email, token)


async def defer_reset_email(*, email: str, token: str) -> None:
    """Best effort: a job that never got enqueued costs one email, and the
    caller's own flow (the reset token itself) has already been created
    either way. Locked on a hash of the token, never the token itself, so a
    retried request can't queue the same email twice."""
    idempotency_key = f"password-reset:{hashlib.sha256(token.encode()).hexdigest()}"
    try:
        await send_reset_email_job.configure(
            queueing_lock=idempotency_key,
        ).defer_async(email=email, token=token)
    except AlreadyEnqueued:
        logger.debug(
            "reset email already queued", extra={"idempotency_key": idempotency_key}
        )
    except Exception:
        logger.warning(
            "reset email could not be enqueued",
            extra={"email": email},
            exc_info=True,
        )
