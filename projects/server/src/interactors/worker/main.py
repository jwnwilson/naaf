"""Worker entrypoint — re-exports the Celery application.

Start with:
    celery -A interactors.worker.celery_app:celery_app worker --beat --loglevel=info
"""
from interactors.worker.celery_app import celery_app as app

__all__ = ["app"]
