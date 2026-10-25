from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.exceptions import AssistantUnavailable
from app.assistant.service import AssistantService
from app.infra.config import settings
from app.infra.database.session import get_session
from app.infra.llm.client import LLMClient, LLMError, get_llm_client
from app.inventory.dependencies import provide_inventory_service
from app.inventory.service import InventoryService
from app.rbac.dependencies import get_rbac_service
from app.rbac.service import RBACService


def provide_llm_client() -> LLMClient:
    try:
        return get_llm_client()
    except LLMError as exc:
        raise AssistantUnavailable() from exc


def get_assistant_service(
    llm: LLMClient = Depends(provide_llm_client),
    db: AsyncSession = Depends(get_session),
    rbac_service: RBACService = Depends(get_rbac_service),
    inventory_service: InventoryService = Depends(provide_inventory_service),
) -> AssistantService:
    return AssistantService(
        llm=llm,
        db=db,
        rbac_service=rbac_service,
        inventory_service=inventory_service,
        max_iterations=settings.ASSISTANT_MAX_ITERATIONS,
        deadline_seconds=settings.ASSISTANT_DEADLINE_SECONDS,
        max_cost_per_request=settings.ASSISTANT_MAX_COST_PER_REQUEST,
        daily_cost_per_user=settings.ASSISTANT_DAILY_COST_PER_USER,
    )
