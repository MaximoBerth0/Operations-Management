from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.database.session import get_session
from app.users.service import UserService


async def provide_user_service(
    db: AsyncSession = Depends(get_session),
) -> UserService:
    return UserService(session=db)
