"""Tests for build_stage_context helper in handlers."""

from dataclasses import dataclass, field

from domain.errors import RecordNotFound
from domain.runs.run import Run, Stage
from domain.work_item import AcceptanceCriterion, WorkItem, WorkItemKind
from interactors.worker.handlers import HandlerContext, build_stage_context
from storage import StorageError

# ---------------------------------------------------------------------------
# Minimal fakes
# ---------------------------------------------------------------------------


class _FakeRepo:
    def __init__(self) -> None:
        self.saved: dict = {}

    def create(self, dto):
        self.saved[dto.id] = dto
        return dto

    def read(self, id_):
        try:
            return self.saved[id_]
        except KeyError:
            raise RecordNotFound(id_) from None


@dataclass
class _FakeBus:
    published: list = field(default_factory=list)

    def publish(self, msg) -> None:
        self.published.append(msg)


def _make_ctx(**kwargs) -> HandlerContext:
    return HandlerContext(
        runs=_FakeRepo(),
        run_events=_FakeRepo(),
        work_items=_FakeRepo(),
        notifications=None,
        bus=_FakeBus(),
        runtime=None,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_build_stage_context_populates_work_item_title():
    """build_stage_context reads the work item title from the repository."""
    ctx = _make_ctx()
    wi = WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.TASK, title="Add login")
    ctx.work_items.create(wi)
    run = Run(owner_id="u", work_item_id=wi.id, project_id="p", autonomy_level="full_auto")

    sc = build_stage_context(ctx, run, "engineer", Stage.IMPLEMENT)

    assert sc.work_item.title == "Add login"


def test_build_stage_context_workspace_path_is_root_slash_run_id():
    """workspace_path is exactly workspace_root + "/" + run id."""
    ctx = _make_ctx(workspace_root="/data/ws")
    wi = WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.TASK, title="T")
    ctx.work_items.create(wi)
    run = Run(owner_id="u", work_item_id=wi.id, project_id="p", autonomy_level="full_auto")

    sc = build_stage_context(ctx, run, "engineer", Stage.IMPLEMENT)

    assert sc.workspace_path == f"/data/ws/{run.id}"


def test_build_stage_context_verify_attempts_matches_run():
    """verify_attempts in the context mirrors run.verify_attempts."""
    ctx = _make_ctx()
    wi = WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.TASK, title="T")
    ctx.work_items.create(wi)
    run = Run(
        owner_id="u", work_item_id=wi.id, project_id="p",
        autonomy_level="full_auto", verify_attempts=2,
    )

    sc = build_stage_context(ctx, run, "qa", Stage.VERIFY)

    assert sc.verify_attempts == run.verify_attempts


def test_build_stage_context_role_aliases_applied_to_agent():
    """When role_aliases contains a mapping for the role, agent.model_alias is set."""
    ctx = _make_ctx(role_aliases={"engineer": "sonnet"})
    wi = WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.TASK, title="T")
    ctx.work_items.create(wi)
    run = Run(owner_id="u", work_item_id=wi.id, project_id="p", autonomy_level="full_auto")

    sc = build_stage_context(ctx, run, "engineer", Stage.IMPLEMENT)

    assert sc.agent.model_alias == "sonnet"


def test_build_stage_context_missing_work_item_returns_empty_brief():
    """If work item is not found, brief has empty title rather than raising."""
    ctx = _make_ctx()
    run = Run(
        owner_id="u", work_item_id="nonexistent", project_id="p", autonomy_level="full_auto"
    )

    sc = build_stage_context(ctx, run, "engineer", Stage.IMPLEMENT)

    assert sc.work_item.title == ""


def test_build_stage_context_storage_error_yields_empty_attachments():
    """A StorageError from ctx.storage.list must not propagate out of build_stage_context.

    Real storage (S3) can fail transiently. The stage must still build with
    attachments=[] rather than crashing the run.
    """
    class _FailingStorage:
        def list(self, _prefix):
            raise StorageError("s3 unavailable")

    ctx = _make_ctx(storage=_FailingStorage())
    wi = WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.TASK, title="T")
    ctx.work_items.create(wi)
    run = Run(owner_id="u", work_item_id=wi.id, project_id="p", autonomy_level="full_auto")

    # Must not raise — storage failure is fault-isolated
    sc = build_stage_context(ctx, run, "engineer", Stage.IMPLEMENT)

    assert sc.work_item.attachments == []


def test_build_stage_context_maps_acceptance_criteria_to_strings():
    """AcceptanceCriterion objects on the WorkItem map to a list[str] on the brief.

    Regression: WorkItem.acceptance_criteria is list[AcceptanceCriterion] while
    WorkItemBrief.acceptance_criteria is list[str]; passing the objects through
    raises a Pydantic ValidationError. The mapping must extract .text.
    """
    ctx = _make_ctx()
    wi = WorkItem(
        owner_id="u",
        project_id="p",
        kind=WorkItemKind.TASK,
        title="T",
        acceptance_criteria=[
            AcceptanceCriterion(text="does X"),
            AcceptanceCriterion(text="does Y", done=True),
        ],
    )
    ctx.work_items.create(wi)
    run = Run(owner_id="u", work_item_id=wi.id, project_id="p", autonomy_level="full_auto")

    sc = build_stage_context(ctx, run, "engineer", Stage.IMPLEMENT)

    assert sc.work_item.acceptance_criteria == ["does X", "does Y"]
