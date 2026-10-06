"""Low-stock alerts. The API only enqueues a stock id after its commit; the
worker re-reads the row, so a rolled-back change or a stock that recovered
before the job ran sends nothing. Recipients are every active user holding
the `stock:alert` permission, one email job each so retries stay per address.
"""

import logging
import uuid

from procrastinate import RetryStrategy
from procrastinate.exceptions import AlreadyEnqueued

from app.infra.database.session import get_script_session
from app.infra.mail.mailer import Mailer
from app.inventory.repositories.stock_repo import StockRepository
from app.users.repository import UserRepository
from app.worker.app import app

logger = logging.getLogger(__name__)

LOW_STOCK_ALERT_PERMISSION = "stock:alert"

_mailer = Mailer()


@app.task(
    queue="default",
    name="send_low_stock_email",
    retry=RetryStrategy(max_attempts=3, exponential_wait=5),
)
async def send_low_stock_email_job(
    *,
    email: str,
    product_name: str,
    sku: str,
    location_name: str,
    available: int,
    reorder_point: int,
) -> None:
    await _mailer.send_low_stock_email(
        email, product_name, sku, location_name, available, reorder_point
    )


@app.task(
    queue="default",
    name="low_stock_alert",
    retry=RetryStrategy(max_attempts=3, exponential_wait=5),
)
async def low_stock_alert_job(*, stock_id: str) -> None:
    async with get_script_session() as session:
        stock = await StockRepository(session).get_stock_with_details(
            uuid.UUID(stock_id)
        )
        if stock is None or stock.low_stock_alerted_at is None:
            logger.info("low stock alert skipped, stock recovered", extra={"stock_id": stock_id})
            return

        emails = await UserRepository(session).list_emails_with_permission(
            LOW_STOCK_ALERT_PERMISSION
        )

    if not emails:
        logger.warning("low stock alert has no recipients", extra={"stock_id": stock_id})
        return

    for email in emails:
        await send_low_stock_email_job.defer_async(
            email=email,
            product_name=stock.product.name,
            sku=stock.product.sku,
            location_name=stock.location.name,
            available=stock.quantity - stock.reserved_quantity,
            reorder_point=stock.reorder_point,
        )


async def defer_low_stock_alert(*, stock_id: uuid.UUID) -> None:
    """Best effort, like the reset email: the stock change is already
    committed, so a failed enqueue only costs the alert. Locked per stock so
    a burst of movements queues one job."""
    try:
        await low_stock_alert_job.configure(
            queueing_lock=f"low-stock:{stock_id}",
        ).defer_async(stock_id=str(stock_id))
    except AlreadyEnqueued:
        logger.debug("low stock alert already queued", extra={"stock_id": stock_id})
    except Exception:
        logger.warning(
            "low stock alert could not be enqueued",
            extra={"stock_id": stock_id},
            exc_info=True,
        )
