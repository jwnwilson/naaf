"""Resolve an owner's agent credentials, preferring stored secrets over env.

A stored, decrypted secret overrides the env value; when unset (or the cipher is
unconfigured), falls back to the existing env settings / ambient env so the
prior env-based flow keeps working.
"""

import os
from typing import Any

from domain.secrets.secret import SECRET_NAMES

from adapters.security.cipher import SecretCipher


class SecretResolver:
    def __init__(self, secrets_repo: Any, cipher: SecretCipher, settings: Any) -> None:
        self._repo = secrets_repo
        self._cipher = cipher
        self._settings = settings

    def _stored(self, name: str) -> str | None:
        if not self._cipher.is_configured:
            return None
        rows = self._repo.read_multi(filters={"name": name}).results
        if not rows:
            return None
        return self._cipher.decrypt(rows[0].value_encrypted)

    def has_any_stored(self) -> bool:
        """True if this owner has any stored secret (→ build per-owner agent deps)."""
        if not self._cipher.is_configured:
            return False
        return any(self._repo.read_multi(filters={"name": n}).results for n in SECRET_NAMES)

    def anthropic_api_key(self) -> str:
        return self._stored("anthropic_api_key") or self._settings.anthropic_api_key

    def github_token(self) -> str:
        return self._stored("github_token") or os.environ.get("GH_TOKEN", "")

    def claude_oauth_token(self) -> str:
        return self._stored("claude_oauth_token") or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
