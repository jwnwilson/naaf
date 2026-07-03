"""Composition root — the SUBSCRIPTIONS registry.

This module is the one place that imports domain subscribers, interactor
subscribers, and adapter sources together.  It is intentionally the only
file that does this cross-layer wiring; everything else stays layer-clean.

Import rules:
  * domain/  → allowed (NotificationSubscriber)
  * adapters/ → allowed (BusSource, EventLogSource)
  * interactors/worker/ → allowed (AgentSubscriber)
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from adapters.database.event_log_source import EventLogSource
from domain.messaging.subscribers.notifications import NotificationSubscriber

from interactors.api.settings import Settings
from interactors.worker.agent_subscriber import AgentSubscriber
from interactors.worker.bus_source import BusSource


@dataclass
class Subscription:
    """Descriptor for a single pub/sub subscription.

    ``source_factory`` is called once per drain tick to obtain a fresh
    ``MessageSource`` instance.  ``subscribers`` is the list of ``Subscriber``
    objects that will receive messages from that source.
    """

    name: str
    source_factory: Callable[[], Any]
    subscribers: list = field(default_factory=list)


SUBSCRIPTIONS: list[Subscription] = [
    Subscription(
        name="agent-bus",
        source_factory=lambda: BusSource(Settings().worker_roles_list or None),
        subscribers=[AgentSubscriber()],
    ),
    Subscription(
        name="notifications",
        source_factory=lambda: EventLogSource("notifications"),
        subscribers=[NotificationSubscriber()],
    ),
]
