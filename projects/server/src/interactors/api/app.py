from contextlib import asynccontextmanager

from adapters.database.engine import build_engine, build_session_factory
from adapters.storage.factory import build_storage
from crud_router import ok
from fastapi import FastAPI
from naaf_db.engine import build_async_engine, build_async_session_factory
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker

from interactors.api.envelope_handlers import register_exception_handlers
from interactors.api.routes import register_routers
from interactors.api.settings import Settings


def create_app(
    settings: Settings | None = None,
    session_factory: sessionmaker | None = None,
    async_session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> FastAPI:
    settings = settings or Settings()
    if session_factory is None:
        engine = build_engine(settings.db_url)
        session_factory = build_session_factory(engine)

    async_engine: AsyncEngine | None = None
    if async_session_factory is None:
        async_engine = build_async_engine(settings.db_url)
        async_session_factory = build_async_session_factory(async_engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        if async_engine is not None:
            await async_engine.dispose()

    app = FastAPI(title="NAAF Control Plane", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.async_session_factory = async_session_factory
    app.state.storage = build_storage(settings)

    register_exception_handlers(app)
    register_routers(app)

    @app.get("/health")
    def health():
        return ok({"status": "ok"})

    return app
