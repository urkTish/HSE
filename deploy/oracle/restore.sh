#!/usr/bin/env bash
# Restore the HSE platform from an archive made by backup.sh. Everything in the database and the
# uploaded files is REPLACED by the backup's content. A safety backup of the current state is made
# first (unless --no-safety-backup).
#
#   sudo bash /opt/hse/deploy/oracle/restore.sh                    # list the backups
#   sudo bash /opt/hse/deploy/oracle/restore.sh /var/backups/hse/hse-backup-2026-11-07_023000.tar
#   ... --yes                                                     # no confirmation question
#
# The backup's encryption keys and session secret are put back into .env (stored ID numbers can
# only be read with the keys they were written with); the database password, web address and
# tunnel token of this server are kept.
set -Eeuo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HSE_DIR=${HSE_DIR:-$(cd "$HERE/../.." && pwd)}
# shellcheck source=deploy/oracle/lib.sh
. "$HERE/lib.sh"
trap 'die "restore failed at line $LINENO. The safety backup (if made) is in the backup folder."' ERR

need_root
[ -f "$ENV_FILE" ] || die "$ENV_FILE is missing; run setup.sh first."

ARCHIVE=""
YES=0
SAFETY=1
for arg in "$@"; do
  case "$arg" in
    --yes) YES=1 ;;
    --no-safety-backup) SAFETY=0 ;;
    -h | --help)
      sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    -*) die "unknown option $arg" ;;
    *) ARCHIVE=$arg ;;
  esac
done

BACKUP_DIR=$(get_env BACKUP_DIR)
BACKUP_DIR=${BACKUP_DIR:-/var/backups/hse}
if [ -z "$ARCHIVE" ]; then
  echo "Backups in $BACKUP_DIR (newest first):"
  find "$BACKUP_DIR" -maxdepth 1 -name 'hse-backup-*.tar' -printf '%T@ %p\n' 2>/dev/null | sort -rn | cut -d' ' -f2- | sed 's/^/  /'
  echo
  echo "Restore one with: sudo bash $0 <file>"
  exit 0
fi
[ -f "$ARCHIVE" ] || die "$ARCHIVE not found."
ARCHIVE=$(cd "$(dirname "$ARCHIVE")" && pwd)/$(basename "$ARCHIVE")

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
tar xf "$ARCHIVE" -C "$work"
for f in db.dump uploads.tar.gz env; do
  [ -f "$work/$f" ] || die "$ARCHIVE is not an HSE backup (no $f)."
done
(cd "$work" && sha256sum --quiet -c SHA256SUMS) || die "$ARCHIVE is damaged (checksum mismatch)."

if [ "$YES" != 1 ]; then
  echo "This REPLACES all current data with the backup $(basename "$ARCHIVE")."
  [ -r /dev/tty ] || die "no terminal to confirm; add --yes."
  read -r -p "Type RESTORE to continue: " answer </dev/tty
  [ "$answer" = RESTORE ] || die "cancelled."
fi

if [ "$SAFETY" = 1 ]; then
  log "Safety backup of the current state"
  bash "$HERE/backup.sh"
fi

log "Putting the backup's keys into .env"
for key in JWT_SECRET FIELD_ENCRYPTION_KEY BLIND_INDEX_KEY ATTACHMENT_URL_SECRET SETUP_TOKEN; do
  value=$(K="$key" awk 'index($0, ENVIRON["K"] "=") == 1 { v = substr($0, length(ENVIRON["K"]) + 2) } END { print v }' "$work/env")
  [ -n "$value" ] || continue
  tmp=$(mktemp "$ENV_FILE.XXXXXX")
  K="$key" V="$value" awk '
    index($0, ENVIRON["K"] "=") == 1 { if (!done) print ENVIRON["K"] "=" ENVIRON["V"]; done = 1; next }
    { print }
    END { if (!done) print ENVIRON["K"] "=" ENVIRON["V"] }
  ' "$ENV_FILE" >"$tmp"
  chmod 600 "$tmp"
  mv "$tmp" "$ENV_FILE"
done

PG_USER=$(get_env POSTGRES_USER)
PG_USER=${PG_USER:-hse}
PG_DB=$(get_env POSTGRES_DB)
PG_DB=${PG_DB:-hse}

log "Stopping the application"
# One at a time: a service whose profile is off (cloudflared with --no-tunnel) must not stop the rest.
for service in cloudflared frontend scheduler backend; do
  dc stop "$service" >/dev/null 2>&1 || true
done
dc up -d db
wait_healthy db 180 || die "the database did not start."

log "Restoring the database"
dc exec -T db psql -v ON_ERROR_STOP=1 -q -U "$PG_USER" -d postgres \
  -c "DROP DATABASE IF EXISTS \"$PG_DB\" WITH (FORCE)" \
  -c "CREATE DATABASE \"$PG_DB\" OWNER \"$PG_USER\""
dc exec -T db pg_restore -U "$PG_USER" -d "$PG_DB" --no-owner --exit-on-error <"$work/db.dump"

log "Restoring the uploaded files"
dc run --rm --no-deps -T storage-init sh -c \
  'find /app/var/storage -mindepth 1 -delete && tar xzf - -C /app/var/storage && chown -R 10001 /app/var/storage' \
  <"$work/uploads.tar.gz"

log "Applying migrations and starting"
migrate
start_stack
log "Restore finished from $(basename "$ARCHIVE")."
