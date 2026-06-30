#!/usr/bin/env bash
set -e

# Bring the database schema up to date before the API starts.
if [ -f alembic.ini ]; then
  if alembic upgrade head > /tmp/alembic.log 2>&1; then
    echo "[entrypoint] migrations applied (alembic upgrade head)"
  elif grep -qi "already exists" /tmp/alembic.log; then
    # Schema was created outside Alembic (e.g. an old create_all deploy on a
    # persistent volume). Adopt the existing schema, then apply newer migrations.
    echo "[entrypoint] tables exist without an alembic version -> stamp head + upgrade"
    alembic stamp head
    alembic upgrade head
  else
    echo "[entrypoint] alembic upgrade failed:"
    cat /tmp/alembic.log
    exit 1
  fi
else
  echo "[entrypoint] no alembic.ini -> create_all fallback"
  python -m app.db_init
fi

echo "[entrypoint] starting API: $*"
exec "$@"
