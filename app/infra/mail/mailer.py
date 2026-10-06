import asyncio
import html
import logging

import boto3
from botocore.exceptions import ClientError

from app.infra.config import settings

logger = logging.getLogger(__name__)


class MailerError(Exception):
    pass


class Mailer:
    def __init__(self):
        self.sender = settings.SENDER_EMAIL
        self.base_url = settings.APP_BASE_URL
        # Credentials resolve through boto3's default chain, which on
        # ECS/Fargate is the task's IAM role.
        self.ses_client = boto3.client(
            "ses",
            region_name=settings.AWS_REGION,
        )

    async def send_reset_email(self, email: str, token: str) -> None:
        reset_link = f"{self.base_url}/reset-password?token={token}"

        subject = "Password Reset Request"

        body_text = (
            "You requested a password reset.\n\n"
            "Click the link below to set a new password. "
            "This link expires in 10 minutes.\n\n"
            f"{reset_link}\n\n"
            "If you did not request this, you can safely ignore this email.\n"
            "Your password will not be changed."
        )

        body_html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2>Password Reset Request</h2>
                <p>You requested a password reset.</p>
                <p>Click the button below to set a new password.
                   This link expires in <strong>10 minutes</strong>.</p>
                <p style="margin: 32px 0;">
                    <a href="{reset_link}"
                       style="background-color: #1a1a1a; color: #ffffff;
                              padding: 12px 24px; text-decoration: none;
                              border-radius: 4px; font-size: 14px;">
                        Reset Password
                    </a>
                </p>
                <p>Or copy and paste this link into your browser:</p>
                <p style="color: #555; font-size: 13px; word-break: break-all;">
                    {reset_link}
                </p>
                <hr style="border: none; border-top: 1px solid #eee; margin: 32px 0;">
                <p style="color: #999; font-size: 12px;">
                    If you did not request this, you can safely ignore this email.
                    Your password will not be changed.
                </p>
            </body>
        </html>
        """

        await self._send(
            to=email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )

        logger.info("reset email sent", extra={"email": email})

    async def send_low_stock_email(
        self,
        email: str,
        product_name: str,
        sku: str,
        location_name: str,
        available: int,
        reorder_point: int,
    ) -> None:
        product = html.escape(product_name)
        location = html.escape(location_name)

        subject = f"Low stock: {sku} at {location_name}"

        body_text = (
            "Available stock has dropped to or below its reorder point.\n\n"
            f"Product: {product_name} ({sku})\n"
            f"Location: {location_name}\n"
            f"Available: {available}\n"
            f"Reorder point: {reorder_point}\n"
        )

        body_html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2>Low Stock Alert</h2>
                <p>Available stock has dropped to or below its reorder point.</p>
                <table style="border-collapse: collapse; font-size: 14px;">
                    <tr><td style="padding: 4px 16px 4px 0; color: #555;">Product</td>
                        <td><strong>{product}</strong> ({html.escape(sku)})</td></tr>
                    <tr><td style="padding: 4px 16px 4px 0; color: #555;">Location</td>
                        <td>{location}</td></tr>
                    <tr><td style="padding: 4px 16px 4px 0; color: #555;">Available</td>
                        <td><strong>{available}</strong></td></tr>
                    <tr><td style="padding: 4px 16px 4px 0; color: #555;">Reorder point</td>
                        <td>{reorder_point}</td></tr>
                </table>
            </body>
        </html>
        """

        await self._send(
            to=email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )

        logger.info("low stock email sent", extra={"email": email, "sku": sku})

    async def _send(
        self,
        to: str,
        subject: str,
        body_text: str,
        body_html: str,
    ) -> None:
        message = {
            "Source": self.sender,
            "Destination": {
                "ToAddresses": [to],
            },
            "Message": {
                "Subject": {
                    "Data": subject,
                    "Charset": "UTF-8",
                },
                "Body": {
                    "Text": {
                        "Data": body_text,
                        "Charset": "UTF-8",
                    },
                    "Html": {
                        "Data": body_html,
                        "Charset": "UTF-8",
                    },
                },
            },
        }

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.ses_client.send_email(**message),
            )
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            logger.error(
                "SES send_email failed",
                extra={
                    "to": to,
                    "error_code": error_code,
                },
            )
            raise MailerError("Failed to send email") from e