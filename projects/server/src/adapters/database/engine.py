from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker


def build_engine(db_url: str) -> Engine:
    return create_engine(db_url, future=True)


def build_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)
