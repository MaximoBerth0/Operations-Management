from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from app.infra.secrets import AWSSecretsManagerSettingsSource


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Management"
    ENV: str = "prod"
    DEBUG: bool = False
    AWS_REGION: str
    # Name/ARN of the AWS Secrets Manager secret holding the config JSON.
    # When set (prod/ECS), its values populate the settings below.
    AWS_SECRETS_NAME: str | None = None
    SENDER_EMAIL: str
    APP_BASE_URL: str

    # Database (Postgres)
    DATABASE_URL: str

    # Connection pool
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 3600
    DB_POOL_PRE_PING: bool = True
    DB_ECHO: bool = False

    # Connection Timeouts
    DB_CONNECT_TIMEOUT: int = 10
    DB_COMMAND_TIMEOUT: int = 60
    DB_STATEMENT_TIMEOUT: int = 30000

    # Security / Auth
    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Server
    UVICORN_WORKERS: int = 1
    GUNICORN_WORKERS: int = 4

    # CORS
    CORS_ALLOW_ORIGINS: list[str]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list[str] = ["GET", "POST", "PUT", "PATCH", "DELETE"]
    CORS_ALLOW_HEADERS: list[str] = ["Authorization", "Content-Type"]

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=".env",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Precedence (highest first): explicit env vars, then AWS Secrets
        # Manager, then a local .env, then file secrets. This lets ECS-injected
        # env vars override the bundle, while the bundle covers everything else.
        return (
            init_settings,
            env_settings,
            AWSSecretsManagerSettingsSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )

    @model_validator(mode="after")
    def validate_prod_settings(self) -> "Settings":
        if self.ENV == "prod":
            assert self.CORS_ALLOW_ORIGINS != ["*"], \
                "Wildcard CORS origins are not allowed in prod"
            assert len(self.SECRET_KEY) >= 32, \
                "SECRET_KEY must be at least 32 characters in prod"
            assert not self.DEBUG, \
                "DEBUG must be False in prod"
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings() # type:ignore


settings = get_settings()