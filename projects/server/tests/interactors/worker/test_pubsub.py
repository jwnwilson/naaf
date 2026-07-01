"""Tests for interactors.worker.pubsub.process_subscription.

All tests use pure in-memory fakes — no DB, no Celery, no broker required.
"""
from contextlib import contextmanager
from dataclasses import dataclass, field

import pytest
from domain.messaging.source import Item, PoisonOutcome
from interactors.worker.pubsub import process_subscription

# ── Fakes ──────────────────────────────────────────────────────────────────────


class FakeUoW:
    """Minimal UoW fake: transaction() re-raises so the engine's except block fires."""

    @contextmanager
    def transaction(self):
        try:
            yield self
        except Exception:
            raise


def _uow_factory():
    return FakeUoW()


class FakeSource:
    """Cursor-faithful scripted source: returns items in order, then None (drained).

    Faithfully models the MessageSource cursor contract:
    - ``fetch_next`` returns the item at ``_pos`` WITHOUT advancing the cursor.
      A real source holds the cursor fixed until ``advance()`` or the internal
      advance inside ``on_poison(CONTINUE)`` moves it.  Auto-advancing on fetch
      would hide infinite-spin regressions in tests.
    - ``advance(item, uow)`` increments ``_pos`` and records the call.
    - ``on_poison(...)`` records the call; for CONTINUE it also increments ``_pos``
      (models dead-letter-then-advance); for STOP the cursor stays put.

    Records every advance() and on_poison() call for assertion.
    """

    def __init__(self, items: list[Item], poison_outcome: PoisonOutcome = PoisonOutcome.STOP):
        self._items = list(items)
        self._pos = 0
        self._poison_outcome = poison_outcome
        self.advanced: list[Item] = []
        self.poisoned: list[tuple[Item, Exception]] = []

    def fetch_next(self, uow) -> Item | None:
        if self._pos >= len(self._items):
            return None
        return self._items[self._pos]

    def advance(self, item: Item, uow) -> None:
        self.advanced.append(item)
        self._pos += 1

    def on_poison(self, item: Item, exc: Exception, uow_factory) -> PoisonOutcome:
        self.poisoned.append((item, exc))
        if self._poison_outcome is PoisonOutcome.CONTINUE:
            self._pos += 1
        return self._poison_outcome


@dataclass
class FakeSubscription:
    source: FakeSource
    subscribers: list


class RecordingSubscriber:
    """Records every message it handles; interested in all messages."""

    def __init__(self, name: str = "recorder"):
        self.name = name
        self.handled: list = []

    def interested_in(self, message) -> bool:
        return True

    def handle(self, message, ctx) -> None:
        self.handled.append(message)


class SkippingSubscriber:
    """Never interested — to verify interested_in gating."""

    def __init__(self):
        self.name = "skipper"
        self.handled: list = []

    def interested_in(self, message) -> bool:
        return False

    def handle(self, message, ctx) -> None:  # pragma: no cover
        self.handled.append(message)


class RaisingSubscriber:
    """Always interested, always raises on handle."""

    def __init__(self, name: str = "raiser"):
        self.name = name
        self.error = ValueError("handler exploded")

    def interested_in(self, message) -> bool:
        return True

    def handle(self, message, ctx) -> None:
        raise self.error


def _ctx_factory(uow, item):
    return object()


# ── Tests ──────────────────────────────────────────────────────────────────────


def test_engine_dispatches_and_advances():
    """Happy path: fetch → dispatch → advance for each item; returns total when drained."""
    # Arrange
    item_a = Item(message="msg_a", owner_id="u1", position=1)
    item_b = Item(message="msg_b", owner_id="u1", position=2)
    source = FakeSource([item_a, item_b])
    recorder = RecordingSubscriber()
    subscription = FakeSubscription(source=source, subscribers=[recorder])

    # Act
    count = process_subscription(subscription, _uow_factory, _ctx_factory)

    # Assert
    assert count == 2
    assert source.advanced == [item_a, item_b]
    assert recorder.handled == ["msg_a", "msg_b"]
    assert source.poisoned == []


def test_engine_skips_uninterested_subscribers():
    """Subscribers that return False from interested_in are not called."""
    # Arrange
    item = Item(message="msg", owner_id="u1", position=1)
    source = FakeSource([item])
    skipper = SkippingSubscriber()
    subscription = FakeSubscription(source=source, subscribers=[skipper])

    # Act
    count = process_subscription(subscription, _uow_factory, _ctx_factory)

    # Assert
    assert count == 1
    assert skipper.handled == []
    assert source.advanced == [item]


def test_engine_isolates_handler_failure_stop():
    """Handler raises → source.on_poison called; STOP returns current count without advancing."""
    # Arrange
    item_a = Item(message="msg_a", owner_id="u1", position=1)
    item_b = Item(message="msg_b", owner_id="u1", position=2)
    source = FakeSource([item_a, item_b], poison_outcome=PoisonOutcome.STOP)
    raiser = RaisingSubscriber()
    subscription = FakeSubscription(source=source, subscribers=[raiser])

    # Act
    count = process_subscription(subscription, _uow_factory, _ctx_factory)

    # Assert: STOP → return immediately; item_a not counted; cursor not advanced
    assert count == 0
    assert len(source.poisoned) == 1
    assert source.poisoned[0][0] is item_a
    assert isinstance(source.poisoned[0][1], ValueError)
    assert source.advanced == []  # advance not called on error path


def test_engine_isolates_handler_failure_continue():
    """Handler raises → on_poison CONTINUE: cursor advances internally, loop drains all items."""
    # Arrange
    item_a = Item(message="msg_a", owner_id="u1", position=1)
    item_b = Item(message="msg_b", owner_id="u1", position=2)
    source = FakeSource([item_a, item_b], poison_outcome=PoisonOutcome.CONTINUE)
    raiser = RaisingSubscriber()
    subscription = FakeSubscription(source=source, subscribers=[raiser])

    # Act
    count = process_subscription(subscription, _uow_factory, _ctx_factory)

    # Assert: CONTINUE → both items poisoned and counted; advance() never called by engine
    assert count == 2
    assert len(source.poisoned) == 2
    assert source.poisoned[0][0] is item_a
    assert source.poisoned[1][0] is item_b
    assert source.advanced == []  # advance not called on error path


def test_engine_propagates_infra_error_when_fetch_raises():
    """If fetch_next raises (item is None at that point), the exception propagates."""
    # Arrange: source raises on first fetch
    class ErrorSource:
        def fetch_next(self, uow):
            raise RuntimeError("db gone")
        def advance(self, item, uow): ...
        def on_poison(self, item, exc, uow_factory): ...

    @dataclass
    class ErrorSubscription:
        source: object
        subscribers: list = field(default_factory=list)

    subscription = ErrorSubscription(source=ErrorSource())

    # Act / Assert
    with pytest.raises(RuntimeError, match="db gone"):
        process_subscription(subscription, _uow_factory, _ctx_factory)


def test_engine_spin_safety_cap():
    """A contract-violating source (on_poison CONTINUE but no cursor advance) is bounded.

    Without max_items this loop would spin forever.  With max_items=5 the engine
    returns after exactly 5 handled items, proving the safety cap works.
    """
    # Arrange: source always returns the same item; on_poison returns CONTINUE
    # without advancing _pos — a deliberate contract violation.
    item = Item(message="bad_msg", owner_id="u1", position=1)

    class NonAdvancingSource:
        """Contract-violating source: on_poison CONTINUE but never moves cursor."""

        def __init__(self):
            self.poison_count = 0

        def fetch_next(self, uow) -> Item | None:
            return item  # always returns the same item (cursor stuck)

        def advance(self, item, uow) -> None:
            pass  # never called on error path

        def on_poison(self, itm, exc, uow_factory) -> PoisonOutcome:
            self.poison_count += 1
            return PoisonOutcome.CONTINUE  # advance NOT called → spin without cap

    source = NonAdvancingSource()
    subscription = FakeSubscription(source=source, subscribers=[RaisingSubscriber()])

    # Act
    count = process_subscription(subscription, _uow_factory, _ctx_factory, max_items=5)

    # Assert: bounded at max_items — did NOT hang
    assert count == 5
    assert source.poison_count == 5
