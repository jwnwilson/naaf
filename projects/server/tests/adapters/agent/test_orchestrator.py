from adapters.agent.chat.orchestrator_echo import EchoOrchestrator
from adapters.agent.chat.orchestrator_llm import LlmOrchestrator
from domain.agent.llm import LLMResponse, ToolCall, Usage
from domain.messaging.chat import ChatTurn


class FakeTools:
    def __init__(self):
        self.calls = []

    def list_board(self):
        self.calls.append(("list_board",))
        return "(empty)"

    def create_work_item(self, kind, title, spec="", parent_id=""):
        self.calls.append(("create", kind, title))
        return f"created {kind} '{title}' id=wi1"

    def update_work_item(self, work_item_id, title="", spec="", priority=""):
        self.calls.append(("update", work_item_id))
        return "updated"

    def propose_run(self, work_item_ids):
        self.calls.append(("propose", tuple(work_item_ids)))
        return "proposed"


class ScriptedLLM:
    def __init__(self, responses):
        self._responses = list(responses)

    def complete(self, request):
        return self._responses.pop(0)


def test_echo_orchestrator_creates_an_epic_from_the_last_user_message():
    tools = FakeTools()
    text = EchoOrchestrator().respond(
        [ChatTurn(role="user", content="Build OAuth login")], "naaf", tools,
    )
    assert ("create", "epic", "Build OAuth login") in tools.calls
    assert text.strip() != ""


def test_llm_orchestrator_runs_tools_then_returns_summary():
    create_call = ToolCall(id="t1", name="create_work_item", args={"kind": "epic", "title": "Auth"})
    llm = ScriptedLLM([
        LLMResponse(content="", tool_calls=[create_call], stop_reason="tool_use",
                    usage=Usage(input_tokens=5, output_tokens=5)),
        LLMResponse(content="Created the Auth epic.", tool_calls=[], stop_reason="end_turn",
                    usage=Usage(input_tokens=2, output_tokens=2)),
    ])
    tools = FakeTools()
    history = [ChatTurn(role="user", content="build auth")]
    text = LlmOrchestrator(llm).respond(history, "naaf", tools)
    assert ("create", "epic", "Auth") in tools.calls
    assert text == "Created the Auth epic."
