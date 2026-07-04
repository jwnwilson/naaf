"""naaf MCP server — exposes owner-scoped naaf domain operations to Claude Code.

Launched as a stdio subprocess by `claude -p --mcp-config …`. Reads
naaf_db_url + naaf_mcp_owner_id from its env, opens an owner-scoped
SqlUnitOfWork per tool call, and forwards to interactors.mcp.tools. Run:

    python -m interactors.mcp.server
"""

import os
from collections.abc import Callable
from typing import Any

from adapters.database.engine import build_engine, build_session_factory
from adapters.database.uow import SqlUnitOfWork
from mcp.server.fastmcp import FastMCP

from interactors.api.settings import Settings
from interactors.mcp import tools

_settings = Settings()
_OWNER = os.environ.get("naaf_mcp_owner_id") or _settings.dev_owner_id
_session_factory = build_session_factory(build_engine(_settings.db_url))

mcp = FastMCP("naaf")


def _run(fn: Callable[[Any], Any]) -> Any:
    uow = SqlUnitOfWork(_session_factory, required_filters={"owner_id": _OWNER})
    with uow.transaction():
        return fn(uow)


@mcp.tool()
def list_projects() -> list[dict]:
    """List the current user's projects (id + name). Call this to resolve a project id by name."""
    return _run(tools.list_projects)


@mcp.tool()
def list_board(project_id: str) -> str:
    """List a project's epic → feature → task tree so you can see what exists and pick parents."""
    return _run(lambda u: tools.list_board(u, _OWNER, project_id))


@mcp.tool()
def create_work_item(
    project_id: str, kind: str, title: str, spec: str = "", parent_id: str = "",
) -> str:
    """Create a work item. kind is 'epic'|'feature'|'task'. Epics have no parent; a feature's
    parent_id must be an epic; a task's parent_id must be a feature. Returns the new id."""
    return _run(
        lambda u: tools.create_work_item(u, _OWNER, project_id, kind, title, spec, parent_id)
    )


@mcp.tool()
def update_work_item(work_item_id: str, title: str = "", spec: str = "", priority: str = "") -> str:
    """Update a work item's title, spec, and/or priority (low|medium|high|urgent)."""
    return _run(lambda u: tools.update_work_item(u, _OWNER, work_item_id, title, spec, priority))


@mcp.tool()
def propose_run(project_id: str, work_item_ids: list[str]) -> str:
    """Propose starting development runs on the given work items. Posts an approval question in the
    project thread — does not start runs directly. Propose runs on tasks (and small features)."""
    return _run(lambda u: tools.propose_run(u, _OWNER, project_id, work_item_ids))


@mcp.tool()
def get_work_item(work_item_id: str) -> dict:
    """Get a work item's full detail (title, spec/body, status, priority, parent)."""
    return _run(lambda u: tools.get_work_item(u, work_item_id))


@mcp.tool()
def transition_status(work_item_id: str, status: str) -> dict:
    """Move a work item to a new status (backlog|todo|in_progress|in_review|done). Validated."""
    return _run(lambda u: tools.transition_status(u, work_item_id, status))


@mcp.tool()
def start_run(work_item_id: str) -> dict:
    """Start an agent development run on a work item. Returns the run id."""
    return _run(lambda u: tools.start_run(u, _OWNER, work_item_id))


@mcp.tool()
def list_runs(work_item_id: str = "") -> list[dict]:
    """List runs (optionally for a single work item): id, status, PR url."""
    return _run(lambda u: tools.list_runs(u, work_item_id))


@mcp.tool()
def get_thread(thread_id: str) -> list[dict]:
    """Get a thread's messages. thread_id is a work-item id or 'project:<id>'."""
    return _run(lambda u: tools.get_thread(u, thread_id))


if __name__ == "__main__":
    mcp.run()
