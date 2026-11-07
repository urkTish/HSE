#!/usr/bin/env bash
# Update the HSE platform to the latest code on its branch and restart it.
#
#   sudo bash /opt/hse/deploy/oracle/update.sh            # backup, pull, rebuild, migrate, restart
#   sudo bash /opt/hse/deploy/oracle/update.sh --no-backup
#
# Also applies changes made by hand to /opt/hse/.env. HSE_SKIP_GIT=1 rebuilds the code as it is.
set -Eeuo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HSE_DIR=${HSE_DIR:-$(cd "$HERE/../.." && pwd)}
# shellcheck source=deploy/oracle/lib.sh
. "$HERE/lib.sh"
trap 'die "update stopped at line $LINENO; the previous version may still be running. Run it again or see GUIDE.md."' ERR

BACKUP=1
for arg in "$@"; do
  case "$arg" in
    --no-backup) BACKUP=0 ;;
    -h | --help)
      sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) die "unknown option $arg" ;;
  esac
done

need_root
[ -f "$ENV_FILE" ] || die "$ENV_FILE is missing; run setup.sh first."
exec 9>/run/hse-update.lock
flock -n 9 || die "another update is running."

if [ "$BACKUP" = 1 ] && [ -n "$(dc ps -q db 2>/dev/null)" ]; then
  log "Backup before the update"
  bash "$HERE/backup.sh"
fi

if [ "${HSE_SKIP_GIT:-0}" != 1 ]; then
  branch=$(git -C "$HSE_DIR" rev-parse --abbrev-ref HEAD)
  before=$(git -C "$HSE_DIR" rev-parse --short HEAD)
  log "Fetching the latest code (branch $branch)"
  git -C "$HSE_DIR" fetch --quiet origin "$branch"
  git -C "$HSE_DIR" merge --quiet --ff-only "origin/$branch"
  echo "Code: $before -> $(git -C "$HSE_DIR" rev-parse --short HEAD)"
fi

log "Rebuilding"
dc build --pull
dc pull --ignore-buildable --quiet

log "Applying database migrations"
migrate

log "Restarting"
start_stack

log "Removing old images"
docker image prune -f >/dev/null
docker builder prune -f --filter until=168h >/dev/null 2>&1 || true

dc ps --format 'table {{.Service}}\t{{.Status}}'
log "Update finished."
