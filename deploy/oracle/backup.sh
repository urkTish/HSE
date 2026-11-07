#!/usr/bin/env bash
# Back up the HSE platform: database (pg_dump, compressed), uploaded files and the settings file
# with its encryption keys, as one archive in BACKUP_DIR (default /var/backups/hse). Keeps the
# newest BACKUP_KEEP_DAYS archives (default 14). Runs every night at 02:30 Riyadh time through
# the hse-backup.timer that setup.sh installs; run it by hand at any time:
#
#   sudo bash /opt/hse/deploy/oracle/backup.sh
#
# With OCI_BACKUP_PAR_URL in .env (a pre-authenticated request URL of an Oracle Object Storage
# bucket, ending in /o/) each archive is also copied there (GUIDE.md "Extra: off-server copy").
set -Eeuo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HSE_DIR=${HSE_DIR:-$(cd "$HERE/../.." && pwd)}
# shellcheck source=deploy/oracle/lib.sh
. "$HERE/lib.sh"
trap 'die "backup failed at line $LINENO."' ERR

need_root
[ -f "$ENV_FILE" ] || die "$ENV_FILE is missing; run setup.sh first."

BACKUP_DIR=$(get_env BACKUP_DIR)
BACKUP_DIR=${BACKUP_DIR:-/var/backups/hse}
KEEP=$(get_env BACKUP_KEEP_DAYS)
KEEP=${KEEP:-14}
PG_USER=$(get_env POSTGRES_USER)
PG_USER=${PG_USER:-hse}
PG_DB=$(get_env POSTGRES_DB)
PG_DB=${PG_DB:-hse}
PAR_URL=$(get_env OCI_BACKUP_PAR_URL)

install -d -m 700 "$BACKUP_DIR"
stamp=$(TZ=Asia/Riyadh date +%Y-%m-%d_%H%M%S)
work=$(mktemp -d "$BACKUP_DIR/.work-$stamp.XXXXXX")
trap 'rm -rf "$work"' EXIT
archive="$BACKUP_DIR/hse-backup-$stamp.tar"

log "Database dump ($PG_DB)"
dc exec -T db pg_dump -U "$PG_USER" -d "$PG_DB" --format=custom --compress=6 >"$work/db.dump"
[ -s "$work/db.dump" ] || die "the database dump is empty."

log "Uploaded files"
dc run --rm --no-deps -T storage-init tar czf - -C /app/var/storage . >"$work/uploads.tar.gz"

log "Settings and keys"
install -m 600 "$ENV_FILE" "$work/env"
git -C "$HSE_DIR" rev-parse HEAD >"$work/code-version" 2>/dev/null || echo unknown >"$work/code-version"
(cd "$work" && sha256sum db.dump uploads.tar.gz env code-version >SHA256SUMS)

tar cf "$archive.part" -C "$work" .
chmod 600 "$archive.part"
mv "$archive.part" "$archive"
echo "Saved $archive ($(du -h "$archive" | cut -f1))"

# Keep the newest $KEEP archives.
mapfile -t old < <(find "$BACKUP_DIR" -maxdepth 1 -name 'hse-backup-*.tar' -printf '%T@ %p\n' | sort -rn | tail -n +"$((KEEP + 1))" | cut -d' ' -f2-)
for f in "${old[@]}"; do
  rm -f -- "$f"
  echo "Removed old backup $f"
done

if [ -n "$PAR_URL" ]; then
  log "Copying to Oracle Object Storage"
  case "$PAR_URL" in */) ;; *) PAR_URL="$PAR_URL/" ;; esac
  if curl -fsS --retry 5 --retry-delay 10 -T "$archive" "$PAR_URL$(basename "$archive")" >/dev/null; then
    echo "Copied."
  else
    warn "the off-server copy failed; the local backup is fine."
  fi
fi

free_kb=$(df -Pk "$BACKUP_DIR" | awk 'NR==2 {print $4}')
[ "$free_kb" -gt 2097152 ] || warn "less than 2 GB of disk left in $BACKUP_DIR."
