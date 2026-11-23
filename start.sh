#!/bin/sh
# Apply database migrations, then start. Demo deployments: seed sample data on first start (refuses if the database already has data).
alembic upgrade head || echo "alembic skipped"
if [ "$PROPERM_DEMO" = "1" ]; then python -m app.demo || true; fi
exec uvicorn app.main:app_from_env --factory --host 0.0.0.0 --port "${PORT:-8000}"
