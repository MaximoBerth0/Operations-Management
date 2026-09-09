import logging
from datetime import datetime, timedelta, timezone

from app.auth.exceptions import (
    AccountDisabled,
    InvalidCredentials,
    TokenExpired,
    TokenInvalid,
)
from app.auth.repositories.password_reset import PasswordResetTokenRepository
from app.auth.repositories.refresh_token import RefreshTokenRepository
from app.auth.schemas import TokenResponse
from app.infra.config import settings
from app.infra.mail.mailer import Mailer
from app.infra.security.passwords import (
    hash_password,
    verify_password,
)
from app.infra.security.tokens import (
    create_access_token,
    generate_refresh_token,
    generate_reset_token,
)
from app.users.model import User
from app.users.repository import UserRepository

logger = logging.getLogger(__name__)

class AuthService:
    def __init__(
        self,
        user_repo: UserRepository,
        refresh_repo: RefreshTokenRepository,
        reset_repo: PasswordResetTokenRepository,
        mailer: Mailer
    ):
        self.user_repo = user_repo
        self.refresh_repo = refresh_repo
        self.reset_repo = reset_repo
        self.mailer = mailer


    async def login(self, email: str, password: str) -> TokenResponse:
        user = await self.user_repo.get_by_email(email)

        if not user or not verify_password(password, user.hashed_password):
            logger.warning("login: invalid credentials", extra={"email": email})
            raise InvalidCredentials()

        if not user.is_active:
            logger.warning("login: account disabled", extra={"user_id": str(user.id)})
            raise AccountDisabled()

        access_token = create_access_token(
            user.id,
            roles=[role.name for role in user.roles],
        )

        refresh_token = generate_refresh_token()
        expires_at = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )

        await self.refresh_repo.create(
            user_id=user.id,
            token=refresh_token,
            expires_at=expires_at,
        )

        logger.info("user logged in", extra={"user_id": str(user.id)})
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        )

    async def logout(self, refresh_token: str) -> None:
        token = await self.refresh_repo.get_active(refresh_token)

        if not token:
            logger.warning("logout: token is inactive")
            raise TokenInvalid("token is inactive")

        await self.refresh_repo.revoke(token.id)
        logger.info("user logged out", extra={"user_id": str(token.user_id)})

    async def refresh_session(self, refresh_token: str) -> TokenResponse:
        token = await self.refresh_repo.get_active(refresh_token)

        if not token:
            logger.warning("refresh_session: invalid refresh token")
            raise TokenExpired("Invalid refresh token.")

        if token.expires_at < datetime.now(timezone.utc):
            logger.warning("refresh_session: refresh token expired", extra={"user_id": str(token.user_id)})
            raise TokenExpired("Invalid refresh token.")

        # resolve the user before rotating anything: a refresh token issued
        # before the account was disabled must not mint a new access token
        user = await self.user_repo.get_by_id(token.user_id)

        if not user:
            logger.warning("refresh_session: user not found", extra={"user_id": str(token.user_id)})
            raise TokenInvalid("Invalid refresh token.")

        if not user.is_active:
            logger.warning("refresh_session: account disabled", extra={"user_id": str(user.id)})
            raise AccountDisabled()

        await self.refresh_repo.revoke(token.id)

        new_refresh_token = generate_refresh_token()
        new_expires_at = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )

        await self.refresh_repo.create(
            user_id=token.user_id,
            token=new_refresh_token,
            expires_at=new_expires_at,
        )

        access_token = create_access_token(
            token.user_id,
            roles=[role.name for role in user.roles],
        )

        logger.info("session refreshed", extra={"user_id": str(token.user_id)})
        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
        )

    async def forgot_password(self, email: str) -> None:
        user = await self.user_repo.get_by_email(email)

        # same silent return for a disabled account as for an unknown address,
        # so the endpoint stays non-enumerable
        if not user or not user.is_active:
            logger.info("forgot_password: no eligible user for email", extra={"email": email})
            return

        await self.reset_repo.invalidate_all_for_user(user.id)

        token = generate_reset_token()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        await self.reset_repo.create(
            user_id=user.id,
            token=token,
            expires_at=expires_at,
        )

        await self.mailer.send_reset_email(user.email, token)
        logger.info("password reset email sent", extra={"user_id": str(user.id)})


    async def reset_password(self, token: str, new_password: str) -> None:

        reset = await self.reset_repo.get_valid(token)

        if not reset:
            logger.warning("reset_password: invalid reset token")
            raise TokenInvalid("Invalid reset token")

        if reset.expires_at < datetime.now(timezone.utc):
            logger.warning("reset_password: reset token expired", extra={"user_id": str(reset.user_id)})
            raise TokenExpired("Reset token expired")

        user = await self.user_repo.get_by_id(reset.user_id)

        if not user:
            logger.warning("reset_password: user not found", extra={"user_id": str(reset.user_id)})
            raise TokenInvalid("Invalid reset token")

        # a token issued before the account was disabled must not let the user back in
        if not user.is_active:
            logger.warning("reset_password: account disabled", extra={"user_id": str(user.id)})
            raise AccountDisabled()

        user.hashed_password = hash_password(new_password)
        await self.user_repo.save_user(user)

        await self.reset_repo.invalidate(token)
        await self.refresh_repo.revoke_all_for_user(reset.user_id)
        logger.info("password reset", extra={"user_id": str(user.id)})


    async def change_password(
        self, current_user: User, old_password: str, new_password: str
    ) -> None:
        if not verify_password(old_password, current_user.hashed_password):
            logger.warning("change_password: invalid old password", extra={"user_id": str(current_user.id)})
            raise InvalidCredentials("Invalid password")

        current_user.hashed_password = hash_password(new_password)
        await self.user_repo.save_user(current_user)

        await self.refresh_repo.revoke_all_for_user(current_user.id)
        logger.info("password changed", extra={"user_id": str(current_user.id)})