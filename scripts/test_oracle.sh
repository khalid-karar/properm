#!/bin/sh
# Runs the whole test-suite against an Oracle TEST schema. The schema is wiped and rebuilt for every test, so use a dedicated empty one.
#   ORACLE_TEST_URL='oracle+oracledb://TESTUSER:PASSWORD@HOST:1521/?service_name=SVC' sh scripts/test_oracle.sh [pytest args]
set -e
[ -n "$ORACLE_TEST_URL" ] || { echo "Set ORACLE_TEST_URL first (see docs/DEPLOY_ORACLE.md)"; exit 2; }
python - <<'PY'
import os
from sqlalchemy import create_engine, text
e = create_engine(os.environ["ORACLE_TEST_URL"])
with e.connect() as c:
    print("Connected:", c.execute(text("select banner from v$version fetch first 1 rows only")).scalar())
PY
echo "WARNING: every table in this schema will be dropped and recreated for each test."
PROPERM_TEST_DATABASE_URL="$ORACLE_TEST_URL" python -m pytest -x -q "$@" 2>&1 | tee /tmp/oracle_pytest.log
echo "Failures that mention ORA- or empty strings are the Oracle-specific ones to fix first."
