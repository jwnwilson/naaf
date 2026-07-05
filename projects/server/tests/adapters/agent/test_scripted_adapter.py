from adapters.agent.scripted.adapter import ScriptedLLMAdapter
from adapters.agent.scripted.script import (
    CHAT_TEXT_PLAN, EPIC_TITLE, FEATURE_TITLE, STAGE_TEXT_SCAN, TASK_TITLE,
)
from domain.agent.llm import LLMMessage, LLMRequest, MessageRole, ToolSpec

REPORT_TOOL = ToolSpec(name="report", description="", parameters={"type": "object", "properties": {}})
CREATE_TOOL = ToolSpec(name="create_work_item", description="", parameters={"type": "object", "properties": {}})


def _req(tools, messages):
    return LLMRequest(model="m", system="", messages=messages, tools=tools)


def test_run_stage_emits_events_and_reports_passed():
    events = []
    a = ScriptedLLMAdapter()
    a.set_event_sink(lambda k, p: events.append((k, p)))
    resp = a.complete(_req([REPORT_TOOL], [LLMMessage(role=MessageRole.USER, content="do plan")]))
    kinds = [k for k, _ in events]
    assert kinds == ["text_block", "tool_call", "tool_result", "text_block"]
    assert events[0][1]["text"] == STAGE_TEXT_SCAN
    report = next(c for c in resp.tool_calls if c.name == "report")
    assert report.args["passed"] is True


def test_lead_plan_walks_list_epic_feature_task_proposerun_then_text():
    a = ScriptedLLMAdapter()
    msgs = [LLMMessage(role=MessageRole.USER, content="build notes")]

    def next_call():
        return a.complete(_req([CREATE_TOOL], msgs))

    # step 0 → list_board
    r = next_call(); assert r.tool_calls[0].name == "list_board"
    msgs += [LLMMessage(role=MessageRole.ASSISTANT, tool_calls=r.tool_calls),
             LLMMessage(role=MessageRole.TOOL, content="board is empty", tool_call_id=r.tool_calls[0].id)]
    # step 1 → create epic
    r = next_call(); assert r.tool_calls[0].args == {"kind": "epic", "title": EPIC_TITLE}
    msgs += [LLMMessage(role=MessageRole.ASSISTANT, tool_calls=r.tool_calls),
             LLMMessage(role=MessageRole.TOOL, content="created epic 'E2E Epic' id=epic123", tool_call_id=r.tool_calls[0].id)]
    # step 2 → create feature under epic123
    r = next_call(); assert r.tool_calls[0].args == {"kind": "feature", "title": FEATURE_TITLE, "parent_id": "epic123"}
    msgs += [LLMMessage(role=MessageRole.ASSISTANT, tool_calls=r.tool_calls),
             LLMMessage(role=MessageRole.TOOL, content="created feature 'E2E Feature' id=feat456", tool_call_id=r.tool_calls[0].id)]
    # step 3 → create task under feat456
    r = next_call(); assert r.tool_calls[0].args == {"kind": "task", "title": TASK_TITLE, "parent_id": "feat456"}
    msgs += [LLMMessage(role=MessageRole.ASSISTANT, tool_calls=r.tool_calls),
             LLMMessage(role=MessageRole.TOOL, content="created task 'E2E streaming task' id=task789", tool_call_id=r.tool_calls[0].id)]
    # step 4 → propose_run on task789
    r = next_call(); assert r.tool_calls[0].name == "propose_run" and r.tool_calls[0].args == {"work_item_ids": ["task789"]}
    msgs += [LLMMessage(role=MessageRole.ASSISTANT, tool_calls=r.tool_calls),
             LLMMessage(role=MessageRole.TOOL, content="proposed run", tool_call_id=r.tool_calls[0].id)]
    # step 5 → final text, no tool calls
    r = next_call(); assert r.stop_reason == "end_turn" and not r.tool_calls and TASK_TITLE in r.content


def test_lead_plan_emits_a_chat_activity_event():
    events = []
    a = ScriptedLLMAdapter()
    a.set_event_sink(lambda k, p: events.append((k, p)))
    a.complete(_req([CREATE_TOOL], [LLMMessage(role=MessageRole.USER, content="build notes")]))
    assert ("text_block", {"text": CHAT_TEXT_PLAN}) in events
