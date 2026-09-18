#!/bin/sh
# Bring the schema to head before the API accepts a request. Alembic is the
# schema's owner; main.py's create_all is a dev convenience that only creates
# missing tables and never alters existing ones.
set -e
echo "[entrypoint] alembic upgrade head"
alembic upgrade head
echo "[entrypoint] starting: $*"
exec "$@"
