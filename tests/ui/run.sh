#!/bin/sh
# Seeds a throwaway demo database, starts the server, runs the browser test, stops the server.
# Needs: pip deps, `npm i playwright axe-core` (or PLAYWRIGHT_PATH and AXE_PATH), Chrome (or CHROME_PATH).
set -e
cd "$(dirname "$0")/../.."
DB=$(mktemp -u /tmp/properm-ui-XXXXXX.db)
export PROPERM_LOGIN_MAX_PER_WINDOW=100000 DATABASE_URL="sqlite:///$DB" PROPERM_SECRET="ui-test-secret-ui-test-secret-1234567" PROPERM_DEMO=1 PROPERM_DEMO_PASSWORD="demo-pass-1" PROPERM_DEMO_LOGIN=1 PROPERM_BUILD_PASSWORD="ui-build-pass"
PORT=${PORT:-8765}
python3 -m app.demo >/dev/null
uvicorn app.main:app_from_env --factory --port "$PORT" >/dev/null 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null; rm -f "$DB"' EXIT
sleep 3
BASE_URL="http://localhost:$PORT" node tests/ui/ui.test.mjs
