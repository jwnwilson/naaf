from adapters.agent.chat.echo import EchoChatResponder
from adapters.agent.chat.llm import LlmChatResponder
from adapters.agent.chat.orchestrator_echo import EchoOrchestrator
from adapters.agent.chat.orchestrator_llm import LlmOrchestrator
from domain.agent.runtime import LlmAgentRuntime


class _SinkAdapter:
    def __init__(self):
        self.sink = "unset"

    def set_event_sink(self, emit):
        self.sink = emit


def test_llm_responder_forwards_sink_to_adapter():
    adapter = _SinkAdapter()
    responder = LlmChatResponder(adapter)
    def sentinel(k, p):
        pass
    responder.set_event_sink(sentinel)
    assert adapter.sink is sentinel


def test_echo_responder_set_event_sink_is_noop():
    EchoChatResponder().set_event_sink(lambda k, p: None)  # must not raise


def test_llm_orchestrator_forwards_sink_to_adapter():
    adapter = _SinkAdapter()
    orchestrator = LlmOrchestrator(adapter)
    def sentinel(k, p):
        pass
    orchestrator.set_event_sink(sentinel)
    assert adapter.sink is sentinel


def test_llm_agent_runtime_forwards_sink_to_adapter():
    adapter = _SinkAdapter()
    runtime = LlmAgentRuntime(adapter, workspace_factory=lambda path: None)
    def sentinel(k, p):
        pass
    runtime.set_event_sink(sentinel)
    assert adapter.sink is sentinel


def test_echo_orchestrator_set_event_sink_is_noop():
    EchoOrchestrator().set_event_sink(lambda k, p: None)  # must not raise


def test_llm_backed_class_set_event_sink_does_not_raise_when_adapter_lacks_method():
    # An adapter with NO set_event_sink — the getattr fallback must swallow it silently.
    class _NoSinkAdapter:
        pass  # deliberately no set_event_sink

    orchestrator = LlmOrchestrator(_NoSinkAdapter())
    orchestrator.set_event_sink(lambda k, p: None)  # must not raise
