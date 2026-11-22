#!/bin/sh
# Demo deployments: seed sample data on first start (refuses if the database already has data).
if [ "$PROPERM_DEMO" = "1" ]; then python -m app.demo || true; fi
exec uvicorn app.main:app_from_env --factory --host 0.0.0.0 --port "${PORT:-8000}"
