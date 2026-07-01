from typing import Any, Protocol


class HandlerContext(Protocol):
    """Capability port passed to each subscriber's handle() method.

    The concrete instance is built by the worker/engine layer and supplies
    owner-scoped repositories and runtime services. All attributes are typed
    Any here so the domain protocol stays free of adapter imports.
    """

    runs: Any
    run_events: Any
    work_items: Any
    notifications: Any
    bus: Any
    runtime: Any
