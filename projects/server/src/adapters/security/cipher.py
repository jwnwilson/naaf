"""Fernet-based encryption for secrets at rest.

Values are encrypted before persistence and decrypted only server-side for
injection. When no key is configured the cipher fails closed on write, so a
plaintext value is never stored by accident.
"""

from cryptography.fernet import Fernet


class SecretsNotConfigured(Exception):
    """Raised when a secret operation needs the encryption key but it is unset."""


class SecretCipher:
    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode()) if key else None

    @property
    def is_configured(self) -> bool:
        return self._fernet is not None

    def encrypt(self, plaintext: str) -> str:
        if self._fernet is None:
            raise SecretsNotConfigured("secret encryption key not configured (naaf_secret_key)")
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        if self._fernet is None:
            raise SecretsNotConfigured("secret encryption key not configured (naaf_secret_key)")
        return self._fernet.decrypt(token.encode()).decode()
