"""
POST /assistant/chat                 - ask the assistant (read-only tools)

(tools default to the current branch, resolved from the X-Location-Id header;
 the tools offered depend on the user's permissions)
"""
import logging

from fastapi import APIRouter, Depends

from app.assistant.dependencies import get_assistant_service
from app.assistant.schemas import ChatRequest, ChatResponse
from app.assistant.service import AssistantService
from app.auth.dependencies import get_current_user
from app.infra.rate_limit.dependencies import rate_limit
from app.inventory.dependencies import get_current_location
from app.inventory.models.location import Location
from app.users.model import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["ASSISTANT"])


@router.post(
    "/chat",
    response_model=ChatResponse,
    dependencies=[rate_limit("assistant")],
)
async def chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    location: Location = Depends(get_current_location),
    service: AssistantService = Depends(get_assistant_service),
) -> ChatResponse:
    logger.info("chat endpoint called", extra={"user_id": current_user.id})
    return await service.chat(
        user_id=current_user.id,
        location_id=location.id,
        messages=body.messages,
    )
