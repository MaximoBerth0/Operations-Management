import logging
import logging.config

from app.infra.config import settings


def setup_logging() -> None:
    log_level = logging.DEBUG if settings.ENV != "prod" else logging.INFO

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request_id": {
                "()": "app.observability.request_id.RequestIdFilter",
            },
        },
        "formatters": {
            "json": {
                "()": "pythonjsonlogger.json.JsonFormatter",
                "fmt": "%(asctime)s %(name)s %(levelname)s %(request_id)s %(message)s",
                "rename_fields": {
                    "asctime": "timestamp",
                    "levelname": "level",
                    "name": "logger",
                },
            },
            "plain": {
                "format": "%(asctime)s %(name)s %(levelname)s [%(request_id)s] %(message)s",
            },
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "json" if settings.ENV == "prod" else "plain",
                "filters": ["request_id"],
            },
        },
        "root": {
            "level": log_level,
            "handlers": ["stdout"],
        },
        "loggers": {
            "uvicorn": {"propagate": True},
            "uvicorn.access": {"propagate": True},
            "uvicorn.error": {"propagate": True},
            "sqlalchemy.engine": {
                "level": "WARNING",
                "propagate": True,
            },
        },
    }

    logging.config.dictConfig(config)