"""Owner-scoped, write-only secrets API.

Values are encrypted at rest and never returned — only `{name, isSet, hint}`
(hint = last 4 chars) is exposed.
"""

from adapters.database.uow import SqlUnitOfWork
from adapters.security.cipher import SecretCipher, SecretsNotConfigured
from crud_router import Envelope, ok
from domain.secrets.secret import SECRET_NAMES, Secret
from fastapi import APIRouter, Depends, HTTPException, Request

from interactors.api.contract import SecretOut, SecretSetIn
from interactors.api.deps import get_uow

router = APIRouter(prefix="/secrets", tags=["secrets"])


def get_cipher(request: Request) -> SecretCipher:
    return SecretCipher(request.app.state.settings.secret_key)


def _find(uow: SqlUnitOfWork, name: str) -> Secret | None:
    rows = uow.secrets.read_multi(filters={"name": name}).results
    return rows[0] if rows else None


def _out(name: str, secret: Secret | None) -> SecretOut:
    return SecretOut(name=name, isSet=secret is not None, hint=secret.hint if secret else "")


@router.get("", response_model=Envelope[list[SecretOut]])
def list_secrets(uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    return ok([_out(name, _find(uow, name)) for name in SECRET_NAMES])


@router.put("/{name}", response_model=Envelope[SecretOut])
def set_secret(
    name: str,
    body: SecretSetIn,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
    cipher: SecretCipher = Depends(get_cipher),  # noqa: B008
):
    if name not in SECRET_NAMES:
        raise HTTPException(status_code=422, detail=f"unknown secret name: {name}")
    try:
        encrypted = cipher.encrypt(body.value)
    except SecretsNotConfigured as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    hint = body.value[-4:]
    existing = _find(uow, name)
    if existing is not None:
        saved = uow.secrets.update(
            existing.id, existing.model_copy(update={"value_encrypted": encrypted, "hint": hint})
        )
    else:
        saved = uow.secrets.create(
            Secret(owner_id="", name=name, value_encrypted=encrypted, hint=hint)
        )
    return ok(_out(name, saved))


@router.delete("/{name}", response_model=Envelope[SecretOut])
def delete_secret(name: str, uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    if name not in SECRET_NAMES:
        raise HTTPException(status_code=422, detail=f"unknown secret name: {name}")
    existing = _find(uow, name)
    if existing is not None:
        uow.secrets.delete(existing.id)
    return ok(_out(name, None))
