"""AWS Secrets Manager integration for application settings.

When `AWS_SECRETS_NAME` is unset (local dev, tests) the source is a no-op and
configuration falls back to environment variables / a local `.env`.
"""

import json
import logging
import os
from typing import Any

from pydantic.fields import FieldInfo
from pydantic_settings import PydanticBaseSettingsSource

logger = logging.getLogger(__name__)


class AWSSecretsManagerSettingsSource(PydanticBaseSettingsSource):
    """Pydantic settings source backed by an AWS Secrets Manager JSON secret."""

    def __init__(self, settings_cls: type) -> None:
        super().__init__(settings_cls)
        self._secrets: dict[str, Any] = self._load_secret()

    def _load_secret(self) -> dict[str, Any]:
        secret_name = os.environ.get("AWS_SECRETS_NAME")
        if not secret_name:
            return {}

        # Imported lazily so local dev / tests never need boto3 configured.
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError

        region = os.environ.get("AWS_REGION")
        try:
            client = boto3.client("secretsmanager", region_name=region)
            response = client.get_secret_value(SecretId=secret_name)
        except (BotoCoreError, ClientError) as exc:
            # Fail fast and loud: without secrets the app cannot start in prod.
            raise RuntimeError(
                f"Failed to load secret '{secret_name}' from AWS Secrets Manager"
            ) from exc

        raw = response.get("SecretString")
        if not raw:
            return {}

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Secret '{secret_name}' is not valid JSON"
            ) from exc

        if not isinstance(data, dict):
            raise RuntimeError(
                f"Secret '{secret_name}' must be a JSON object of key/value pairs"
            )

        logger.info(
            "loaded %d setting(s) from AWS Secrets Manager", len(data),
            extra={"secret_name": secret_name},
        )
        return data

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[Any, str, bool]:
        value = self._secrets.get(field_name)
        return value, field_name, False

    def __call__(self) -> dict[str, Any]:
        return self._secrets
