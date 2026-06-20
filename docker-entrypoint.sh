#!/usr/bin/env bash
set -e

# Bring the database schema up to date before the API starts.
# Once Alembic is configured (issue #9), this uses real migrations automatically;
# until then it falls back to create_all so the tables exist.
if [ -f alembic.ini ]; then
  echo "[entrypoint] alembic.ini found -> alembic upgrade head"
  alembic upgrade head
else
  echo "[entrypoint] no alembic.ini yet -> ensuring tables via create_all (temporary, until issue #9)"
  python -m app.db_init
fi

echo "[entrypoint] starting API: $*"
exec "$@"
