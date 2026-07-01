import json
from datetime import date, datetime

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker


def _json_default(obj: object) -> str:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def build_engine(db_url: str, **kwargs: object) -> Engine:
    return create_engine(
        db_url,
        future=True,
        json_serializer=lambda o: json.dumps(o, default=_json_default),
        **kwargs,
    )


def build_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)
