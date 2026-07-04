from adapters.agent.secrets_resolver import SecretResolver
from adapters.database.uow import SqlUnitOfWork
from adapters.security.cipher import SecretCipher
from cryptography.fernet import Fernet
from domain.secrets.secret import Secret
from interactors.api.settings import Settings


def _uow(session_factory):
    return SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})


def test_stored_anthropic_key_overrides_env(session_factory):
    cipher = SecretCipher(Fernet.generate_key().decode())
    uow = _uow(session_factory)
    with uow.transaction():
        uow.secrets.create(Secret(
            owner_id="", name="anthropic_api_key",
            value_encrypted=cipher.encrypt("stored-key"), hint="-key",
        ))
        resolver = SecretResolver(uow.secrets, cipher, Settings(anthropic_api_key="env-key"))
        assert resolver.anthropic_api_key() == "stored-key"


def test_anthropic_falls_back_to_env_when_unset(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        resolver = SecretResolver(
            uow.secrets, SecretCipher(Fernet.generate_key().decode()),
            Settings(anthropic_api_key="env-key"),
        )
        assert resolver.anthropic_api_key() == "env-key"


def test_github_token_falls_back_to_env(session_factory, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "env-gh")
    uow = _uow(session_factory)
    with uow.transaction():
        resolver = SecretResolver(
            uow.secrets, SecretCipher(Fernet.generate_key().decode()), Settings(),
        )
        assert resolver.github_token() == "env-gh"


def test_unconfigured_cipher_ignores_stored_and_uses_env(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        settings = Settings(anthropic_api_key="env-key")
        resolver = SecretResolver(uow.secrets, SecretCipher(""), settings)
        assert resolver.anthropic_api_key() == "env-key"
