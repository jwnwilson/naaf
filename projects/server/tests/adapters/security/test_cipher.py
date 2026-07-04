import pytest
from adapters.security.cipher import SecretCipher, SecretsNotConfigured
from cryptography.fernet import Fernet


def _key() -> str:
    return Fernet.generate_key().decode()


def test_encrypt_decrypt_round_trips():
    cipher = SecretCipher(_key())
    token = cipher.encrypt("sk-ant-secret")
    assert token != "sk-ant-secret"
    assert cipher.decrypt(token) == "sk-ant-secret"


def test_ciphertext_is_non_deterministic():
    cipher = SecretCipher(_key())
    assert cipher.encrypt("same") != cipher.encrypt("same")


def test_unconfigured_cipher_fails_closed_on_encrypt():
    cipher = SecretCipher("")
    with pytest.raises(SecretsNotConfigured):
        cipher.encrypt("nope")


def test_is_configured_reflects_key_presence():
    assert SecretCipher(_key()).is_configured is True
    assert SecretCipher("").is_configured is False
