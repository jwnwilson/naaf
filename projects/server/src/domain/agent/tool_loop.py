"""A generic tool-call loop over the ``LLMAdapter`` port.

Shared by any agent that drives the model through repeated tool calls. The
caller supplies the tool specs and an ``execute(call) -> ToolResult`` function,
so the same loop serves file-op tools (stage runtime) and domain-action tools
(the conversational lead). Returns the model's final text plus total tokens.
"""

from collections.abc import Callable

from domain.agent.llm import (
    LLMAdapter,
    LLMMessage,
    LLMRequest,
    MessageRole,
    ToolCall,
    ToolResult,
    ToolSpec,
)


def run_tool_loop(
    llm: LLMAdapter,
    *,
    model: str,
    system: str,
    user: str,
    tool_specs: list[ToolSpec],
    execute: Callable[[ToolCall], ToolResult],
    max_iterations: int = 25,
    max_tokens: int = 8192,
) -> tuple[str, int]:
    messages: list[LLMMessage] = [LLMMessage(role=MessageRole.USER, content=user)]
    request = LLMRequest(
        model=model, system=system, messages=messages, tools=tool_specs, max_tokens=max_tokens
    )
    total_tokens = 0
    final_text = ""

    for _ in range(max_iterations):
        response = llm.complete(request.model_copy(update={"messages": messages}))
        total_tokens += response.usage.input_tokens + response.usage.output_tokens
        if response.content:
            final_text = response.content
        if response.stop_reason != "tool_use" or not response.tool_calls:
            break
        messages.append(LLMMessage(
            role=MessageRole.ASSISTANT, content=response.content, tool_calls=response.tool_calls,
        ))
        for call in response.tool_calls:
            result = execute(call)
            messages.append(LLMMessage(
                role=MessageRole.TOOL, content=result.content, tool_call_id=result.tool_call_id,
            ))

    return final_text, total_tokens
