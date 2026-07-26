import inspect

from interactors.api.deps import get_async_uow


def test_get_async_uow_is_async_generator():
    # get_async_uow must be an async generator function yielding an AsyncUnitOfWork
    assert inspect.isasyncgenfunction(get_async_uow)
