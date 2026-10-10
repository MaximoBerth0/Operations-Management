from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    """Stateless: the client sends the whole conversation every time."""

    messages: list[ChatMessage] = Field(..., min_length=1, max_length=20)

    @field_validator("messages")
    @classmethod
    def starts_and_ends_with_user(cls, messages: list[ChatMessage]) -> list[ChatMessage]:
        if messages[0].role != "user" or messages[-1].role != "user":
            raise ValueError("conversation must start and end with a user message")
        return messages


class ChatResponse(BaseModel):
    answer: str
    tools_called: list[str]
    iterations: int
