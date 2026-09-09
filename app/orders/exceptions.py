from app.common.errors import AppError


class OrderError(AppError):
    def __init__(
        self,
        message: str,
        status_code: int = 400,
        error_code: str = "ORDER_ERROR",
    ):
        super().__init__(message, status_code, error_code)


class OrderNotFound(OrderError):
    def __init__(self, message: str = "Order not found"):
        super().__init__(
            message=message,
            status_code=404,
            error_code="ORDER_NOT_FOUND",
        )

class InvalidOrderStatus(OrderError):
    def __init__(self, message: str = "Order status is incorrect"):
        super().__init__(
            message=message,
            status_code=409,
            error_code="INVALID_ORDER_STATUS",
        )


class OrderItemNotFound(OrderError):
    def __init__(self, message: str = "Item not found in order"):
        super().__init__(
            message=message,
            status_code=404,
            error_code="ORDER_ITEM_NOT_FOUND",
        )


class InvalidQuantity(OrderError):
    def __init__(self, message: str = "Quantity must be greater than zero"):
        super().__init__(
            message=message,
            status_code=422,
            error_code="INVALID_QUANTITY",
        )


class OrderCodeGenerationError(OrderError):
    def __init__(self, message:str = "A unique code could not be generated after several attempts."):
        super().__init__(
            message=message,
            status_code=500,
            error_code="ORDER_GENERATION_CODE_FAILED",
        )