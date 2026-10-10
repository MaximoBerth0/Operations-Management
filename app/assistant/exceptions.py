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
