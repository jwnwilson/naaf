from adapters.agent.chat.llm import LlmChatResponder
from adapters.agent.llm.fake import FakeLLMAdapter
from domain.agent.llm import LLMResponse
from domain.messaging.chat import ChatTurn


def test_llm_responder_returns_model_content():
    fake = FakeLLMAdapter(scripted=[LLMResponse(content="On it — checking middleware.py.")])
    r = LlmChatResponder(fake)
    out = r.respond("backend", [ChatTurn(role="user", content="@backend check auth")], "Auth task")
    assert out == "On it — checking middleware.py."


def test_llm_responder_includes_role_in_system_prompt():
    fake = FakeLLMAdapter(scripted=[LLMResponse(content="done")])
    r = LlmChatResponder(fake, model="claude-haiku-4-5")
    r.respond("qa", [], "Test task")
    req = fake.requests[0]
    assert "qa" in req.system
    assert req.model == "claude-haiku-4-5"
