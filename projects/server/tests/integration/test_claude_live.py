import os

import pytest
from adapters.agent.llm.claude import ClaudeLLMAdapter
from domain.agent.llm import LLMMessage, LLMRequest, MessageRole

pytestmark = pytest.mark.integration


@pytest.mark.skipif(not os.getenv("naaf_anthropic_api_key"), reason="no key")
def test_real_claude_completes_a_prompt():
    adapter = ClaudeLLMAdapter(api_key=os.environ["naaf_anthropic_api_key"],
                               aliases={"opus": "claude-opus-4-8"})
    resp = adapter.complete(LLMRequest(model="opus", system="Reply with the single word OK.",
                                       messages=[LLMMessage(role=MessageRole.USER, content="go")],
                                       max_tokens=16))
    assert "OK" in resp.content.upper()
