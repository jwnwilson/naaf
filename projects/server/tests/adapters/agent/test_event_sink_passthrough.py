from adapters.agent.chat.echo import EchoChatResponder
from adapters.agent.chat.llm import LlmChatResponder


class _SinkAdapter:
    def __init__(self):
        self.sink = "unset"

    def set_event_sink(self, emit):
        self.sink = emit


def test_llm_responder_forwards_sink_to_adapter():
    adapter = _SinkAdapter()
    responder = LlmChatResponder(adapter)
    sentinel = lambda k, p: None
    responder.set_event_sink(sentinel)
    assert adapter.sink is sentinel


def test_echo_responder_set_event_sink_is_noop():
    EchoChatResponder().set_event_sink(lambda k, p: None)  # must not raise
