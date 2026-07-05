from adapters.database.uow import SqlUnitOfWork
from domain.runs.run import Run, RunStatus


def _seed_run(session_factory, owner: str, *, cost: float, tokens: int, status=RunStatus.SUCCEEDED):
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": owner})
    with uow.transaction() as u:
        u.runs.create(Run(
            owner_id="", work_item_id="wi", project_id="p", autonomy_level="gated_all",
            status=status, token_usage=tokens, cost=cost,
        ))


def test_metrics_sums_cost_and_tokens_owner_scoped(client, session_factory):
    _seed_run(session_factory, "dev-user", cost=0.50, tokens=1000)
    _seed_run(session_factory, "dev-user", cost=0.25, tokens=500)
    body = client.get("/dashboard/metrics").json()
    assert body["success"] is True
    data = body["data"]
    assert data["totalSpend"] == 0.75
    assert data["totalTokens"] == 1500
    assert data["projectCount"] == 0
    assert data["workItemCount"] == 0
    assert data["activeAgents"] == 0  # both seeded runs are SUCCEEDED


def test_metrics_excludes_other_owner(client, client_other_owner, session_factory):
    _seed_run(session_factory, "dev-user", cost=9.99, tokens=9999)
    data = client_other_owner.get("/dashboard/metrics").json()["data"]
    assert data["totalSpend"] == 0.0
    assert data["totalTokens"] == 0


def test_metrics_counts_active_runs(client, session_factory):
    _seed_run(session_factory, "dev-user", cost=0.0, tokens=0, status=RunStatus.RUNNING)
    _seed_run(session_factory, "dev-user", cost=0.0, tokens=0, status=RunStatus.AWAITING_GATE)
    assert client.get("/dashboard/metrics").json()["data"]["activeAgents"] == 2


def test_budget_used_is_total_spend_and_limit_from_settings(client, session_factory):
    _seed_run(session_factory, "dev-user", cost=1.20, tokens=100)
    body = client.get("/budget").json()["data"]
    assert body["used"] == 1.20
    assert body["limit"] == 100.0  # Settings.budget_limit_usd default


def test_budget_owner_scoped(client_other_owner, session_factory):
    _seed_run(session_factory, "dev-user", cost=5.0, tokens=100)
    assert client_other_owner.get("/budget").json()["data"]["used"] == 0.0
