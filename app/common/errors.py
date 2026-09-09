"""
application error hierarchy.

all custom exceptions inherit from AppError and include:
- message: human-readable error description
- status_code: HTTP status code for API responses
- error_code: machine-readable error identifier
"""

from typing import Any, Dict


class AppError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str = "INTERNAL_ERROR",
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API responses."""
        return {
            "error_code": self.error_code,
            "message": self.message,
        }
