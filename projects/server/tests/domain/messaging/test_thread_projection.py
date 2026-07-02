from datetime import UTC, datetime

from domain.messaging.thread import THREAD_LEAD_ROLE, ThreadView, thread_from_run
from domain.runs.run import Run


def _run() -> Run:
    return Run(
        id="a" * 32,
        owner_id="u1",
        work_item_id="w1",
        project_id="p1",
        autonomy_level="gated_all",
        created_at=datetime(2026, 7, 2, tzinfo=UTC),
    )


def test_thread_from_run_maps_fields():
    view = thread_from_run(_run())
    assert isinstance(view, ThreadView)
    assert view.id == "a" * 32
    assert view.work_item_id == "w1"
    assert view.created_at == datetime(2026, 7, 2, tzinfo=UTC)


def test_thread_agent_id_is_lead_role():
    assert thread_from_run(_run()).agent_id == THREAD_LEAD_ROLE
    assert THREAD_LEAD_ROLE == "lead"
