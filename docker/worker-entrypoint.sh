#!/bin/sh
set -e
# Authenticate git (HTTPS) + gh with GH_TOKEN so `git clone`/`push` and `gh pr create` work.
if [ -n "$GH_TOKEN" ]; then
  gh auth setup-git
fi
cd /app/projects/server
exec uv run celery -A interactors.worker.celery_app:celery_app worker --beat --loglevel=info
