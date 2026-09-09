import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.exceptions import AccountDisabled, TokenExpired, TokenInvalid
from app.auth.repositories.password_reset import PasswordResetTokenRepository
from app.auth.repositories.refresh_token import RefreshTokenRepository
from app.auth.service import AuthService
from app.infra.database.session import get_session
from app.infra.mail.mailer import Mailer
from app.infra.security.tokens import verify_access_token
from app.users.model import User
from app.users.repository import UserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_session),
) -> User:
    try:
        payload = verify_access_token(token)
    except (TokenInvalid, TokenExpired):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_uuid)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # checked on every request so disabling an account takes effect immediately,
    # rather than when its already-issued access token expires
    if not user.is_active:
        raise AccountDisabled()

    return user


def get_auth_service(session: AsyncSession = Depends(get_session)) -> AuthService:
    """Dependency injection for AuthService with all repositories."""
    return AuthService(
        user_repo=UserRepository(session),
        refresh_repo=RefreshTokenRepository(session),
        reset_repo=PasswordResetTokenRepository(session),
        mailer=Mailer() 
    )