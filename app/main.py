import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.routers import router as auth_router
from app.common.handlers import register_exception_handlers
from app.infra.config import settings
from app.infra.redis.client import shutdown as redis_shutdown
from app.infra.redis.client import startup as redis_startup
from app.inventory.router import router as inventory_router
from app.observability.health import router as health_router
from app.observability.logging import setup_logging
from app.observability.request_id import RequestIdMiddleware
from app.orders.router import router as order_router
from app.rbac.routers import router as rbac_router
from app.users.router import router as users_router

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    await redis_startup()
    yield
    await redis_shutdown()


app = FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan,
# The documentation is shown in production intentionally
#   docs_url=None if settings.ENV == "prod" else "/docs",
#   redoc_url=None if settings.ENV == "prod" else "/redoc",
#   openapi_url=None if settings.ENV == "prod" else "/openapi.json",
)

# middleware
app.add_middleware(RequestIdMiddleware)
app.add_middleware(CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

# Exception handlers
register_exception_handlers(app)

# Routers
app.include_router(health_router)
app.include_router(users_router)
app.include_router(auth_router)
app.include_router(rbac_router)
app.include_router(inventory_router)
app.include_router(order_router)