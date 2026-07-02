from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, Field


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCall(BaseModel):
    id: str
    name: str
    args: dict = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool_call_id: str
    content: str
    is_error: bool = False


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict  # JSON Schema for the tool's arguments


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class LLMMessage(BaseModel):
    role: MessageRole
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None  # set when role == TOOL


class LLMRequest(BaseModel):
    model: str
    system: str = ""
    messages: list[LLMMessage] = Field(default_factory=list)
    tools: list[ToolSpec] = Field(default_factory=list)
    max_tokens: int = 8192


class LLMResponse(BaseModel):
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    stop_reason: str = "end_turn"
    usage: Usage = Field(default_factory=Usage)


class LLMAdapter(Protocol):
    def complete(self, request: LLMRequest) -> LLMResponse: ...
