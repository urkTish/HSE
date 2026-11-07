# shellcheck shell=bash
# Shared helpers for update.sh, backup.sh and restore.sh (sourced, not run).
# HSE_DIR is the repository checkout that holds .env (default /opt/hse).

HSE_DIR=${HSE_DIR:-/opt/hse}
ENV_FILE="$HSE_DIR/.env"

log() { printf '\n==> %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

need_root() {
  [ "$(id -u)" -eq 0 ] || die "run this with sudo (as root)."
}

# Value of KEY in .env (last occurrence wins, like docker compose); empty when absent.
get_env() {
  [ -f "$ENV_FILE" ] || return 0
  K="$1" awk 'index($0, ENVIRON["K"] "=") == 1 { v = substr($0, length(ENVIRON["K"]) + 2) } END { print v }' "$ENV_FILE"
}

# docker compose in the checkout: COMPOSE_FILE / COMPOSE_PROFILES / project name come from .env.
dc() {
  (cd "$HSE_DIR" && docker compose "$@")
}

# Wait until a service's container reports healthy (or `running` when it has no healthcheck).
wait_healthy() {
  local service=$1 timeout=${2:-300} waited=0 cid state
  while [ "$waited" -lt "$timeout" ]; do
    cid=$(dc ps -q "$service" 2>/dev/null | head -n1)
    if [ -n "$cid" ]; then
      state=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" 2>/dev/null || true)
      case "$state" in
        healthy | running) return 0 ;;
        exited | dead) break ;;
      esac
    fi
    sleep 5
    waited=$((waited + 5))
  done
  warn "$service is not healthy after ${timeout}s. Recent log lines:"
  dc logs --tail 40 "$service" >&2 || true
  return 1
}

# Apply database migrations with the new code before the API processes start on it.
migrate() {
  dc up -d db
  wait_healthy db 180 || die "the database did not start."
  dc run --rm --no-deps -T backend alembic upgrade head
}

# Bring everything up and wait for the parts the website needs.
start_stack() {
  dc up -d --remove-orphans
  wait_healthy backend 600 || die "the backend did not become healthy."
  wait_healthy frontend 300 || die "the frontend did not become healthy."
  if [ -n "$(get_env CLAMAV_HOST)" ]; then
    wait_healthy clamav 900 || warn "ClamAV is still starting; uploads answer 'scanner unavailable' until it is ready."
  fi
}
