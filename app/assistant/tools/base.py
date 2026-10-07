"""Tool and ToolContext live here, not in registry.py, so tool modules can
import them without a cycle (the registry imports every tool module)."""
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.inventory.service import InventoryService


@dataclass(frozen=True)
class ToolContext:
    inventory_service: InventoryService
    user_id: uuid.UUID
    location_id: uuid.UUID  # current branch, used when the model does not pick one


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: type[BaseModel]
    permission: str
    handler: Callable[[Any, ToolContext], Awaitable[BaseModel]]

    def definition(self) -> dict[str, Any]:
        """Provider-agnostic shape: name, description, JSON schema of the input."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema.model_json_schema(),
        }
