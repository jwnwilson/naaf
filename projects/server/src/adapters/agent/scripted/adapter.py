"""A deterministic LLMAdapter for e2e tests. Fakes ONLY the model: it plugs into
the real LlmOrchestrator / LlmChatResponder / LlmAgentRuntime, so the genuine
tool loop and set_event_sink → agent_events → SSE → UI pipeline run unchanged.
"""
import re

from domain.agent.llm import LLMMessage, LLMRequest, LLMResponse, MessageRole, ToolCall, Usage

from adapters.agent.scripted.script import (
    CHAT_TEXT_PLAN,
    EPIC_TITLE,
    FEATURE_TITLE,
    STAGE_TEXT_DONE,
    STAGE_TEXT_SCAN,
    TASK_TITLE,
)

_ID_RE = re.compile(r"id=(\w+)")


class ScriptedLLMAdapter:
    def __init__(self) -> None:
        self._emit = None

    def set_event_sink(self, emit) -> None:
        self._emit = emit

    def complete(self, request: LLMRequest) -> LLMResponse:
        tool_names = {t.name for t in request.tools}
        if "report" in tool_names:
            return self._run_stage()
        if "create_work_item" in tool_names:
            return self._lead_plan(request.messages)
        return self._plain_chat()

    def _run_stage(self) -> LLMResponse:
        if self._emit is not None:
            self._emit("text_block", {"text": STAGE_TEXT_SCAN})
            self._emit("tool_call", {"name": "edit_file", "input": {}})
            self._emit("tool_result", {"result": "ok"})
            self._emit("text_block", {"text": STAGE_TEXT_DONE})
        return LLMResponse(
            content=STAGE_TEXT_DONE,
            tool_calls=[ToolCall(id="report-1", name="report",
                                 args={"passed": True, "summary": "scripted stage ok"})],
            stop_reason="tool_use",
            usage=Usage(output_tokens=10),
        )

    def _lead_plan(self, messages: list[LLMMessage]) -> LLMResponse:
        results = [m for m in messages if m.role == MessageRole.TOOL]
        step = len(results)

        def tool(name: str, args: dict) -> LLMResponse:
            return LLMResponse(
                tool_calls=[ToolCall(id=f"c{step}", name=name, args=args)],
                stop_reason="tool_use", usage=Usage(output_tokens=5),
            )

        if step == 0:
            if self._emit is not None:
                self._emit("text_block", {"text": CHAT_TEXT_PLAN})
            return tool("list_board", {})
        if step == 1:
            return tool("create_work_item", {"kind": "epic", "title": EPIC_TITLE})
        if step == 2:
            args = {"kind": "feature", "title": FEATURE_TITLE, "parent_id": self._last_id(results)}
            return tool("create_work_item", args)
        if step == 3:
            if self._emit is not None:
                emit_payload = {"name": "create_work_item", "input": {"title": TASK_TITLE}}
                self._emit("tool_call", emit_payload)
            args = {"kind": "task", "title": TASK_TITLE, "parent_id": self._last_id(results)}
            return tool("create_work_item", args)
        if step == 4:
            return tool("propose_run", {"work_item_ids": [self._last_id(results)]})
        return LLMResponse(
            content=f"Created the plan and proposed a run on '{TASK_TITLE}'.",
            stop_reason="end_turn", usage=Usage(output_tokens=8),
        )

    @staticmethod
    def _last_id(results: list[LLMMessage]) -> str:
        m = _ID_RE.search(results[-1].content)
        return m.group(1) if m else ""

    def _plain_chat(self) -> LLMResponse:
        if self._emit is not None:
            self._emit("text_block", {"text": "Acknowledged."})
        return LLMResponse(
            content="Acknowledged.", stop_reason="end_turn", usage=Usage(output_tokens=4)
        )
