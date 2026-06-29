from adapters.database.engine import build_engine, build_session_factory
from crud_router import ok
from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from interactors.api.envelope_handlers import register_exception_handlers
from interactors.api.routes import register_routers
from interactors.api.settings import Settings


def create_app(
    settings: Settings | None = None,
    session_factory: sessionmaker | None = None,
) -> FastAPI:
    settings = settings or Settings()
    if session_factory is None:
        engine = build_engine(settings.db_url)
        session_factory = build_session_factory(engine)

    app = FastAPI(title="NAAF Control Plane")
    app.state.settings = settings
    app.state.session_factory = session_factory

    register_exception_handlers(app)
    register_routers(app)

    @app.get("/health")
    def health():
        return ok({"status": "ok"})

    return app
