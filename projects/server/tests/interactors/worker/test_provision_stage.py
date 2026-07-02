"""Unit tests for the deterministic PROVISION stage inline runner."""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from domain.errors import RecordNotFound
from domain.project import Project
from domain.runs.run import Run, RunStatus, Stage
from domain.work_item import WorkItem, WorkItemKind
from interactors.worker.handlers import HandlerContext, _run_provision_inline

# ---------------------------------------------------------------------------
# Minimal in-memory fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeBus:
    published: list = field(default_factory=list)

    def publish(self, msg) -> None:
        self.published.append(msg)


class FakeRepo:
    """In-memory store keyed by entity .id."""

    def __init__(self) -> None:
        self.saved: dict = {}

    def create(self, dto):
        self.saved[dto.id] = dto
        return dto

    def update(self, id_, dto):
        self.saved[id_] = dto
        return dto

    def read(self, id_):
        try:
            return self.saved[id_]
        except KeyError:
            raise RecordNotFound(id_) from None


def _init_repo(path: Path) -> None:
    """Create a minimal git repository with one commit."""
    path.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True)
    (path / "README.md").write_text("hello")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=path, check=True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_provision_skips_when_no_projects():
    """PROVISION passes immediately (skip) when projects repo is not configured (projects=None)."""
    # Arrange
    runs = FakeRepo()
    run_events = FakeRepo()
    work_items = FakeRepo()
    run = Run(
        owner_id="u",
        work_item_id="w",
        project_id="p",
        autonomy_level="full_auto",
        status=RunStatus.RUNNING,
        current_stage=Stage.PLAN,
    )
    runs.create(run)
    ctx = HandlerContext(
        runs=runs,
        run_events=run_events,
        work_items=work_items,
        notifications=None,
        bus=FakeBus(),
        runtime=None,
        projects=None,
    )

    # Act
    result = _run_provision_inline(ctx, run)

    # Assert
    assert result.passed is True
    assert "skipped" in result.summary


def test_provision_clones_when_project_has_repo(tmp_path):
    """PROVISION clones the project repo and creates agent/<run_id> branch when configured."""
    # Arrange — real local git repo as the project source
    src = tmp_path / "src"
    _init_repo(src)

    work_items_repo = FakeRepo()
    projects_repo = FakeRepo()
    runs = FakeRepo()
    run_events = FakeRepo()

    project = Project(owner_id="u", name="P", repo_path=str(src))
    projects_repo.create(project)

    wi = WorkItem(owner_id="u", project_id=project.id, kind=WorkItemKind.TASK, title="T")
    work_items_repo.create(wi)

    run = Run(
        owner_id="u",
        work_item_id=wi.id,
        project_id=project.id,
        autonomy_level="full_auto",
        status=RunStatus.RUNNING,
        current_stage=Stage.PLAN,
    )
    runs.create(run)

    ws_root = str(tmp_path / "ws")
    ctx = HandlerContext(
        runs=runs,
        run_events=run_events,
        work_items=work_items_repo,
        notifications=None,
        bus=FakeBus(),
        runtime=None,
        projects=projects_repo,
        workspace_root=ws_root,
    )

    # Act
    result = _run_provision_inline(ctx, run)

    # Assert — stage passed and workspace exists on the agent branch
    assert result.passed is True
    ws_path = Path(ws_root) / run.id
    assert ws_path.is_dir(), f"workspace directory {ws_path} was not created"
    branch = subprocess.run(
        ["git", "-C", str(ws_path), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert branch == f"agent/{run.id}"
