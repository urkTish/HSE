#!/usr/bin/env bash
# Start the stack, wait for the API, then load the demo data (idempotent).
set -euo pipefail
cd "$(dirname "$0")/.."

docker compose up -d --build

echo "Waiting for the backend..."
for _ in $(seq 1 90); do
  if docker compose exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

docker compose exec -T backend python -m app.seed
echo "HSE app is running on port 3000. Demo login: faisal.harbi@example.com / Demo-Passw0rd!2026"
