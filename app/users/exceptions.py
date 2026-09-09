from app.common.errors import AppError


class UserError(AppError):
    def __init__(
        self,
        message: str,
        status_code: int = 400,
        error_code: str = "USER_ERROR",
    ):
        super().__init__(message, status_code, error_code)


class UserNotFound(UserError):
    def __init__(self, message: str = "User not found"):
        super().__init__(
            message=message,
            status_code=404,
            error_code="USER_NOT_FOUND",
        )


class UserAlreadyExists(UserError):
    def __init__(self, message: str = "User already exists"):
        super().__init__(
            message=message,
            status_code=409,
            error_code="USER_ALREADY_EXISTS",
        )


class UserInactive(UserError):
    def __init__(self, message: str = "User account is inactive"):
        super().__init__(
            message=message,
            status_code=403,
            error_code="USER_INACTIVE",
        )
