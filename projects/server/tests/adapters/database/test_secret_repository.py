from adapters.database.uow import SqlUnitOfWork
from domain.secrets.secret import Secret


def _uow(session_factory, owner="u1"):
    return SqlUnitOfWork(session_factory, required_filters={"owner_id": owner})


def test_secret_round_trips_owner_scoped(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        s = uow.secrets.create(
            Secret(owner_id="", name="anthropic_api_key", value_encrypted="enc-blob", hint="1234")
        )
        got = uow.secrets.read(s.id)
    assert got.name == "anthropic_api_key"
    assert got.value_encrypted == "enc-blob"
    assert got.hint == "1234"
    assert got.owner_id == "u1"  # stamped


def test_find_by_name_via_filters(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        uow.secrets.create(Secret(owner_id="", name="github_token", value_encrypted="e", hint="9"))
        rows = uow.secrets.read_multi(filters={"name": "github_token"}).results
    assert [r.name for r in rows] == ["github_token"]


def test_secrets_are_owner_isolated(session_factory):
    uow_a = _uow(session_factory, "owner-a")
    with uow_a.transaction():
        uow_a.secrets.create(
            Secret(owner_id="", name="github_token", value_encrypted="e", hint="9"))
    uow_b = _uow(session_factory, "owner-b")
    with uow_b.transaction():
        rows = uow_b.secrets.read_multi(filters={"name": "github_token"}).results
    assert rows == []
