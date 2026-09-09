"""Mounting a policy on a route:

    @router.post("/login", dependencies=[rate_limit("login")])
"""

import logging
import math

from fastapi import Depends, HTTPException, Request, Response, params, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.exceptions import TokenExpired, TokenInvalid
from app.infra.config import settings
from app.infra.rate_limit.bucket import build_key, consume
from app.infra.rate_limit.policy import get_policy
from app.infra.security.tokens import verify_access_token

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


def _identity(request: Request, credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials is not None:
        try:
            payload = verify_access_token(credentials.credentials)
            return f"user:{payload['sub']}"
        except (TokenExpired, TokenInvalid):
            pass

    client = request.client
    return f"ip:{client.host}" if client else "ip:unknown"


def rate_limit(policy_name: str, cost: int = 1) -> params.Depends:

    async def dependency(
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    ) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return

        policy = get_policy(policy_name)
        identity = _identity(request, credentials)
        decision = await consume(build_key(policy.name, identity), policy, cost)

        response.headers["X-RateLimit-Limit"] = str(policy.capacity)
        response.headers["X-RateLimit-Remaining"] = str(math.floor(decision.remaining))

        if decision.allowed:
            return

        retry_after = max(1, math.ceil(decision.retry_after))
        logger.warning(
            "rate limit exceeded",
            extra={
                "policy": policy.name,
                "path": request.url.path,
                "method": request.method,
                "identity_kind": identity.split(":", 1)[0],
                "retry_after": retry_after,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error_code": "RATE_LIMITED",
                "message": "Too many requests, try again later",
            },
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(policy.capacity),
                "X-RateLimit-Remaining": "0",
            },
        )

    return Depends(dependency)
