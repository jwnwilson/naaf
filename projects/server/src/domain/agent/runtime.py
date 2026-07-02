from collections.abc import Callable
from typing import Protocol

from pydantic import BaseModel, Field

from domain.agent.context import StageContext
from domain.agent.llm import LLMAdapter, LLMMessage, LLMRequest, MessageRole
from domain.agent.prompts import stage_instruction, system_prompt
from domain.agent.tools import TOOL_SPECS, execute_tool
from domain.agent.workspace import Workspace
from domain.runs.run import Stage


class AgentEvent(BaseModel):
    type: str = "log"
    message: str


class StageResult(BaseModel):
    passed: bool
    summary: str = ""
    tokens: int = 0


class StageOutcome(BaseModel):
    events: list[AgentEvent] = Field(default_factory=list)
    result: StageResult


class AgentRuntime(Protocol):
    def run_stage(self, role: str, stage: Stage, ctx: StageContext) -> StageOutcome: ...


class LlmAgentRuntime:
    """LLM-agnostic agent loop. Reaches the model only through the LLMAdapter port."""

    def __init__(
        self,
        llm: LLMAdapter,
        workspace_factory: Callable[[str], Workspace],
        max_iterations: int = 25,
    ):
        self._llm = llm
        self._workspace_factory = workspace_factory
        self._max_iterations = max_iterations

    def run_stage(self, role: str, stage: Stage, ctx: StageContext) -> StageOutcome:
        # role/stage are accepted for AgentRuntime interface compatibility; the loop
        # reads them via ctx (ctx.role / ctx.stage).
        workspace = self._workspace_factory(ctx.workspace_path)
        events: list[AgentEvent] = []
        messages = [LLMMessage(role=MessageRole.USER, content=stage_instruction(ctx))]
        request = LLMRequest(
            model=ctx.agent.model_alias or "default",
            system=system_prompt(ctx),
            messages=messages,
            tools=TOOL_SPECS,
            max_tokens=ctx.agent.token_limit,
        )
        final_text = ""
        total_tokens = 0

        for _ in range(self._max_iterations):
            response = self._llm.complete(request.model_copy(update={"messages": messages}))
            total_tokens += response.usage.input_tokens + response.usage.output_tokens

            if response.content:
                final_text = response.content
                events.append(AgentEvent(message=response.content))

            if response.stop_reason != "tool_use" or not response.tool_calls:
                return StageOutcome(
                    events=events,
                    result=StageResult(
                        passed=True, summary=final_text or "ok", tokens=total_tokens
                    ),
                )

            # Append assistant message with tool calls, then execute each tool
            messages = [
                *messages,
                LLMMessage(
                    role=MessageRole.ASSISTANT,
                    content=response.content,
                    tool_calls=response.tool_calls,
                ),
            ]
            tool_messages: list[LLMMessage] = []
            for call in response.tool_calls:
                events.append(AgentEvent(message=f"tool:{call.name} {call.args}"))
                tr = execute_tool(workspace, call)
                tool_messages.append(
                    LLMMessage(role=MessageRole.TOOL, content=tr.content, tool_call_id=call.id)
                )
            messages = [*messages, *tool_messages]

        return StageOutcome(
            events=events,
            result=StageResult(
                passed=False,
                summary="stopped: max iterations reached",
                tokens=total_tokens,
            ),
        )
