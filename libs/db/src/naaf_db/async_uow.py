from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class AsyncUnitOfWorkBase:
    """Async sibling of SqlUnitOfWorkBase. Owns one AsyncSession + transaction."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        required_filters: dict[str, Any] | None = None,
    ):
        self._session_factory = session_factory
        self._required_filters = required_filters or {}
        self._session: AsyncSession | None = None
        self._repos: dict[str, Any] = {}

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            self._session = self._session_factory()
        return self._session

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["AsyncUnitOfWorkBase"]:
        session = self.session
        try:
            yield self
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
            self._session = None
            self._repos = {}

    def _repo(self, name: str, cls: type) -> Any:
        if name not in self._repos:
            self._repos[name] = cls(self.session, required_filters=self._required_filters)
        return self._repos[name]
