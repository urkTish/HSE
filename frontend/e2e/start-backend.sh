#!/usr/bin/env bash
# Starts the real backend for Playwright on a freshly created, migrated and seeded database,
# so every e2e run begins from the spec Appendix A seed (the audit log is append-only by design).
set -euo pipefail
cd "$(dirname "$0")/../../backend"

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-hse}"
export PGPASSWORD="${PGPASSWORD:-hse}"
DB="${E2E_DB_NAME:-hse_e2e}"

psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres -v ON_ERROR_STOP=1 \
  -c "DROP DATABASE IF EXISTS \"$DB\" WITH (FORCE)" \
  -c "CREATE DATABASE \"$DB\""

export DATABASE_URL="postgresql+psycopg://$PGUSER:$PGPASSWORD@$PGHOST:$PGPORT/$DB"
export JWT_SECRET="${JWT_SECRET:-e2e-only-secret-e2e-only-secret-e2e}"
export SEED_PASSWORD="${SEED_PASSWORD:-Demo-Passw0rd!2026}"
export ENVIRONMENT="${ENVIRONMENT:-development}"
export COOKIE_SECURE=false
export FRONTEND_BASE_URL="${FRONTEND_BASE_URL:-http://localhost:3000}"
export PRIVACY_NOTICE_VERSION="${PRIVACY_NOTICE_VERSION:-PN-1.0}"

uv run alembic upgrade head
uv run python -m app.seed
# Shared e2e clock (e2e/clock.ts): the API runs at the same shifted instant as the tests and browsers,
# by default the PTW seed instant 2026-10-06 10:00 Riyadh, with time moving on (HSE_CLOCK_MODE advancing).
if [ -n "${E2E_CLOCK_OFFSET_MS:-}" ]; then
  HSE_CLOCK_AT="$(python3 -c "import datetime,os; print((datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(milliseconds=int(os.environ['E2E_CLOCK_OFFSET_MS']))).isoformat())")"
  export HSE_CLOCK_AT
fi
exec uv run uvicorn app.main:app --host 127.0.0.1 --port "${E2E_BACKEND_PORT:-8000}"
