from app.common.errors import AppError


class AssistantError(AppError):
    def __init__(
        self,
        message: str,
        status_code: int = 400,
        error_code: str = "ASSISTANT_ERROR",
    ):
        super().__init__(message, status_code, error_code)


class AssistantUnavailable(AssistantError):
    def __init__(self, message: str = "The assistant is unavailable, try again later"):
        super().__init__(
            message=message,
            status_code=503,
            error_code="ASSISTANT_UNAVAILABLE",
        )


class AssistantTimeout(AssistantError):
    def __init__(self, message: str = "The assistant took too long, try a more specific question"):
        super().__init__(
            message=message,
            status_code=504,
            error_code="ASSISTANT_TIMEOUT",
        )


class AssistantQuotaExceeded(AssistantError):
    def __init__(self, message: str = "Daily assistant quota reached, try again tomorrow"):
        super().__init__(
            message=message,
            status_code=429,
            error_code="ASSISTANT_QUOTA_EXCEEDED",
        )
