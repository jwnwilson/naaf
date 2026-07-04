from adapters.agent.claude_cli.adapter import ClaudeCliLLMAdapter
from adapters.agent.secrets_resolver import SecretResolver
from adapters.database.uow import SqlUnitOfWork
from adapters.security.cipher import SecretCipher
from cryptography.fernet import Fernet
from domain.agent.llm import LLMMessage, LLMRequest, MessageRole
from domain.secrets.secret import SECRET_NAMES, Secret
from interactors.api.settings import Settings


def test_claude_oauth_token_is_an_allowed_secret():
    assert "claude_oauth_token" in SECRET_NAMES


def test_resolver_prefers_stored_oauth_token_over_env(session_factory, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "env-oat")
    cipher = SecretCipher(Fernet.generate_key().decode())
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        uow.secrets.create(Secret(
            owner_id="", name="claude_oauth_token",
            value_encrypted=cipher.encrypt("stored-oat"), hint="-oat",
        ))
        resolver = SecretResolver(uow.secrets, cipher, Settings())
        assert resolver.claude_oauth_token() == "stored-oat"


def test_resolver_falls_back_to_env_oauth_token(session_factory, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "env-oat")
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        resolver = SecretResolver(
            uow.secrets, SecretCipher(Fernet.generate_key().decode()), Settings(),
        )
        assert resolver.claude_oauth_token() == "env-oat"


def test_adapter_injects_claude_oauth_token_into_subprocess_env():
    cap = {}

    def runner(argv, *, cwd=None, env=None, timeout=None):
        cap["env"] = env
        return {"result": "ok", "usage": {}}

    adapter = ClaudeCliLLMAdapter(runner=runner, claude_oauth_token="oat-123")
    adapter.complete(LLMRequest(
        model="m", messages=[LLMMessage(role=MessageRole.USER, content="hi")],
    ))
    assert cap["env"].get("CLAUDE_CODE_OAUTH_TOKEN") == "oat-123"


def test_adapter_omits_oauth_token_when_unset():
    cap = {}

    def runner(argv, *, cwd=None, env=None, timeout=None):
        cap["env"] = env
        return {"result": "ok", "usage": {}}

    ClaudeCliLLMAdapter(runner=runner).complete(LLMRequest(
        model="m", messages=[LLMMessage(role=MessageRole.USER, content="hi")],
    ))
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in cap["env"]
