from app.common.errors import AppError


class RbacError(AppError):
    def __init__(
        self,
        message: str,
        status_code: int = 400,
        error_code: str = "RBAC_ERROR",
    ):
        super().__init__(message, status_code, error_code)


class RoleNotFound(RbacError):
    def __init__(self, message: str = "Role not found"):
        super().__init__(
            message=message,
            status_code=404,
            error_code="ROLE_NOT_FOUND",
        )


class RoleAlreadyExists(RbacError):
    def __init__(self, message: str = "Role already exists"):
        super().__init__(
            message=message,
            status_code=409,
            error_code="ROLE_ALREADY_EXISTS",
        )


class RoleAlreadyAssignedToUser(RbacError):
    def __init__(self, message: str = "Role already assigned to user"):
        super().__init__(
            message=message,
            status_code=409,
            error_code="ROLE_ALREADY_ASSIGNED_TO_USER",
        )


class UserRoleNotFound(RbacError):
    def __init__(self, message: str = "User role not found"):
        super().__init__(
            message=message,
            status_code=404,
            error_code="USER_ROLE_NOT_FOUND",
        )


class PermissionNotFound(RbacError):
    def __init__(self, message: str = "Permission not found"):
        super().__init__(
            message=message,
            status_code=404,
            error_code="PERMISSION_NOT_FOUND",
        )


class PermissionAlreadyAssigned(RbacError):
    def __init__(self, message: str = "Permission already assigned"):
        super().__init__(
            message=message,
            status_code=409,
            error_code="PERMISSION_ALREADY_ASSIGNED",
        )


class RolePermissionNotFound(RbacError):
    def __init__(self, message: str = "Role permission not found"):
        super().__init__(
            message=message,
            status_code=404,
            error_code="ROLE_PERMISSION_NOT_FOUND",
        )


class PermissionDenied(RbacError):
    def __init__(self, message: str = "Permission denied"):
        super().__init__(
            message=message,
            status_code=403,
            error_code="PERMISSION_DENIED",
        )
