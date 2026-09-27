#!/bin/sh
# Apply database migrations once, then hand PID 1 to the app server.
set -e

alembic upgrade head

exec "$@"
