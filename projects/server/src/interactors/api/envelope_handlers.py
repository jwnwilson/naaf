from domain.errors import (
    IntegrityConflict,
    InvalidHierarchy,
    InvalidTransition,
    RecordNotFound,
)
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError


def _envelope(status_code: int, error: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "data": None, "error": error, "meta": None},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RecordNotFound)
    async def _not_found(_: Request, exc: RecordNotFound):
        return _envelope(404, str(exc))

    @app.exception_handler(IntegrityConflict)
    async def _conflict(_: Request, exc: IntegrityConflict):
        return _envelope(409, str(exc))

    @app.exception_handler(InvalidTransition)
    async def _bad_transition(_: Request, exc: InvalidTransition):
        return _envelope(409, str(exc))

    @app.exception_handler(InvalidHierarchy)
    async def _bad_hierarchy(_: Request, exc: InvalidHierarchy):
        return _envelope(409, str(exc))

    @app.exception_handler(ValidationError)
    async def _domain_validation(_: Request, exc: ValidationError):
        return _envelope(422, str(exc))

    @app.exception_handler(RequestValidationError)
    async def _request_validation(_: Request, exc: RequestValidationError):
        return _envelope(422, str(exc))
