#!/usr/bin/env bash
# One-time (and safe to re-run) set-up of the HSE platform on a fresh Ubuntu 24.04 server, for
# example an Oracle Cloud Always Free Ampere A1 (arm64) instance behind Cloudflare Tunnel.
# Plain-language walkthrough: deploy/oracle/GUIDE.md.
#
#   sudo bash setup.sh                     # asks for the web address, admin email, tunnel token
#   sudo HSE_HOSTNAME=hse.example.com ADMIN_EMAIL=me@example.com TUNNEL_TOKEN=eyJ... bash setup.sh
#
# What it does: installs Docker Engine + compose from Docker's apt repository, turns on automatic
# security updates, allows only SSH in through the host firewall, adds 4 GB swap, clones (or
# updates) the code in /opt/hse, writes /opt/hse/.env with random secrets made on this server,
# builds and starts the stack, applies the database migrations, installs the nightly backup
# timer and then opens the app's first-time setup (D-306), protected by a one-off setup code.
#
# Options:
#   --create-admin   create the first administrator from this script (POST /api/v1/setup) with a
#                    random password that is printed once, instead of on the setup web page.
#                    ORG_NAME_EN, ORG_NAME_AR, PROJECT_CODE, PROJECT_NAME_EN, PROJECT_NAME_AR,
#                    PROJECT_CITY, ADMIN_NAME and ADMIN_PASSWORD can be given as variables.
#   --demo           load the demo data (fake users and records, for trials only) instead.
#   --no-tunnel      do not start cloudflared (testing only; the site is then unreachable).
#   --skip-host      skip the operating-system steps (packages, firewall, swap, timer).
#   --skip-git       use the code already in HSE_DIR as it is.
# Variables: HSE_DIR (/opt/hse), HSE_REPO, HSE_BRANCH, HSE_HOSTNAME, ADMIN_EMAIL, TUNNEL_TOKEN.
set -Eeuo pipefail

HSE_DIR=${HSE_DIR:-/opt/hse}
HSE_REPO=${HSE_REPO:-https://github.com/urkTish/HSE.git}
HSE_BRANCH=${HSE_BRANCH:-claude/hse-platform-build-kannxy}
ENV_FILE="$HSE_DIR/.env"
SWAP_FILE=/swapfile
SWAP_SIZE_GB=4

CREATE_ADMIN=0
DEMO=0
NO_TUNNEL=0
SKIP_HOST=${HSE_SKIP_HOST:-0}
SKIP_GIT=${HSE_SKIP_GIT:-0}

usage() {
  sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --create-admin) CREATE_ADMIN=1 ;;
    --demo) DEMO=1 ;;
    --no-tunnel) NO_TUNNEL=1 ;;
    --skip-host) SKIP_HOST=1 ;;
    --skip-git) SKIP_GIT=1 ;;
    -h | --help) usage 0 ;;
    *)
      echo "Unknown option: $1" >&2
      usage 2
      ;;
  esac
  shift
done
[ "$CREATE_ADMIN" = 1 ] && [ "$DEMO" = 1 ] && {
  echo "Choose --create-admin or --demo, not both." >&2
  exit 2
}

log() { printf '\n==> %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}
trap 'die "setup stopped at line $LINENO. Fix the problem above and run the same command again."' ERR

[ "$(id -u)" -eq 0 ] || die "run this with sudo:  sudo bash setup.sh"

# ---------------------------------------------------------------------------------------------
# .env helpers (no `source`: values may contain spaces or symbols)
# ---------------------------------------------------------------------------------------------
get_env() {
  [ -f "$ENV_FILE" ] || return 0
  K="$1" awk 'index($0, ENVIRON["K"] "=") == 1 { v = substr($0, length(ENVIRON["K"]) + 2) } END { print v }' "$ENV_FILE"
}

set_env() {
  local tmp
  tmp=$(mktemp "$ENV_FILE.XXXXXX")
  K="$1" V="$2" awk '
    index($0, ENVIRON["K"] "=") == 1 { if (!done) print ENVIRON["K"] "=" ENVIRON["V"]; done = 1; next }
    { print }
    END { if (!done) print ENVIRON["K"] "=" ENVIRON["V"] }
  ' "$ENV_FILE" >"$tmp"
  chmod 600 "$tmp"
  mv "$tmp" "$ENV_FILE"
}

ask() { # ask VAR "question" — reads from the terminal even when the script is piped in
  local answer
  [ -r /dev/tty ] || die "$1 is not set and there is no terminal to ask. Pass $1=... instead."
  read -r -p "$2" answer </dev/tty
  printf '%s' "$answer"
}

random_hex() { openssl rand -hex "$1"; }

dc() { (cd "$HSE_DIR" && docker compose "$@"); }

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

# ---------------------------------------------------------------------------------------------
# 1. Operating system
# ---------------------------------------------------------------------------------------------
install_packages() {
  log "Installing base packages and automatic security updates"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -q
  apt-get install -y -q ca-certificates curl git openssl gnupg unattended-upgrades
  cat >/etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
  systemctl enable --now unattended-upgrades >/dev/null 2>&1 || true
}

install_docker() {
  if docker compose version >/dev/null 2>&1; then
    log "Docker is already installed ($(docker --version))"
  else
    log "Installing Docker Engine and the compose plugin from Docker's repository"
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    local codename
    # shellcheck disable=SC1091
    codename=$(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $codename stable" \
      >/etc/apt/sources.list.d/docker.list
    apt-get update -q
    apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  fi
  systemctl enable --now docker >/dev/null
}

configure_firewall() {
  log "Host firewall: only SSH (port 22) may come in"
  # Oracle's Ubuntu images ship iptables rules (netfilter-persistent) that already accept only
  # SSH and reject everything else; keep them as they are. Elsewhere use ufw.
  if [ -f /etc/iptables/rules.v4 ] && grep -q -- '--dport 22' /etc/iptables/rules.v4 &&
    grep -q -- '-A INPUT -j REJECT' /etc/iptables/rules.v4; then
    echo "Oracle's built-in rules allow only SSH in; left unchanged."
  else
    apt-get install -y -q ufw
    ufw default deny incoming >/dev/null
    ufw default allow outgoing >/dev/null
    ufw allow 22/tcp >/dev/null
    ufw --force enable >/dev/null
    ufw status verbose | sed -n '1,8p'
  fi
  # No container publishes a port (docker-compose.prod.yml), so Docker opens nothing either.
}

add_swap() {
  if swapon --show=NAME --noheadings | grep -q .; then
    log "Swap already present: $(swapon --show=NAME,SIZE --noheadings | tr '\n' ' ')"
    return
  fi
  log "Adding ${SWAP_SIZE_GB} GB of swap"
  [ -f "$SWAP_FILE" ] || fallocate -l "${SWAP_SIZE_GB}G" "$SWAP_FILE"
  chmod 600 "$SWAP_FILE"
  mkswap "$SWAP_FILE" >/dev/null
  swapon "$SWAP_FILE"
  grep -q "^$SWAP_FILE " /etc/fstab || echo "$SWAP_FILE none swap sw 0 0" >>/etc/fstab
  echo 'vm.swappiness=10' >/etc/sysctl.d/90-hse-swap.conf
  sysctl -q -p /etc/sysctl.d/90-hse-swap.conf
}

install_backup_timer() {
  log "Nightly backup at 02:30 Riyadh time (systemd timer hse-backup.timer)"
  cat >/etc/systemd/system/hse-backup.service <<EOF
[Unit]
Description=HSE platform backup (database and uploads)
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
Environment=HSE_DIR=$HSE_DIR
ExecStart=/bin/bash $HSE_DIR/deploy/oracle/backup.sh
EOF
  cat >/etc/systemd/system/hse-backup.timer <<'EOF'
[Unit]
Description=Nightly HSE platform backup

[Timer]
OnCalendar=*-*-* 02:30:00 Asia/Riyadh
Persistent=true
RandomizedDelaySec=120

[Install]
WantedBy=timers.target
EOF
  systemctl daemon-reload
  systemctl enable --now hse-backup.timer >/dev/null
}

# ---------------------------------------------------------------------------------------------
# 2. Code
# ---------------------------------------------------------------------------------------------
fetch_code() {
  if [ "$SKIP_GIT" = 1 ]; then
    log "Using the code already in $HSE_DIR"
    [ -f "$HSE_DIR/docker-compose.yml" ] || die "$HSE_DIR has no docker-compose.yml."
    return
  fi
  if [ -d "$HSE_DIR/.git" ]; then
    log "Updating the code in $HSE_DIR (branch $HSE_BRANCH)"
    git -C "$HSE_DIR" fetch --quiet origin "$HSE_BRANCH"
    git -C "$HSE_DIR" checkout --quiet "$HSE_BRANCH" 2>/dev/null ||
      git -C "$HSE_DIR" checkout --quiet -b "$HSE_BRANCH" "origin/$HSE_BRANCH"
    git -C "$HSE_DIR" merge --quiet --ff-only "origin/$HSE_BRANCH"
  else
    if [ -d "$HSE_DIR" ] && [ -n "$(ls -A "$HSE_DIR")" ]; then
      die "$HSE_DIR exists and is not a copy of the code. Move it away and run again."
    fi
    log "Downloading the code to $HSE_DIR (branch $HSE_BRANCH)"
    git clone --quiet --branch "$HSE_BRANCH" "$HSE_REPO" "$HSE_DIR"
  fi
  echo "Code version: $(git -C "$HSE_DIR" log -1 --format='%h %cd' --date=short)"
}

# ---------------------------------------------------------------------------------------------
# 3. Settings (/opt/hse/.env)
# ---------------------------------------------------------------------------------------------
write_env() {
  local template="$HSE_DIR/deploy/oracle/.env.prod.example" first=0 key value
  if [ ! -f "$ENV_FILE" ]; then
    log "Creating $ENV_FILE with new random secrets"
    install -m 600 "$template" "$ENV_FILE"
    first=1
  else
    log "Keeping the settings and secrets already in $ENV_FILE"
    chmod 600 "$ENV_FILE"
  fi

  # Web address
  value=${HSE_HOSTNAME:-$(get_env HSE_HOSTNAME)}
  [ -n "$value" ] || value=$(ask HSE_HOSTNAME "Web address for the platform (for example hse.mycompany.com): ")
  value=$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]' | sed -e 's#^[a-z]*://##' -e 's#/.*$##' -e 's/[[:space:]]//g')
  printf '%s' "$value" | grep -Eq '^([a-z0-9-]+\.)+[a-z]{2,}$' || die "\"$value\" is not a web address like hse.mycompany.com."
  set_env HSE_HOSTNAME "$value"
  HSE_HOSTNAME=$value

  # First administrator's email
  value=${ADMIN_EMAIL:-$(get_env ADMIN_EMAIL)}
  [ -n "$value" ] || value=$(ask ADMIN_EMAIL "Email address of the first administrator (you): ")
  value=$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')
  printf '%s' "$value" | grep -Eq '^[^@]+@[^@]+\.[^@]+$' || die "\"$value\" is not an email address."
  set_env ADMIN_EMAIL "$value"
  ADMIN_EMAIL=$value
  [ -n "$(get_env PROJECT_DELETE_EMAILS)" ] || set_env PROJECT_DELETE_EMAILS "$ADMIN_EMAIL"

  # Cloudflare Tunnel token
  if [ "$NO_TUNNEL" = 1 ]; then
    set_env COMPOSE_PROFILES "clamav"
  else
    value=${TUNNEL_TOKEN:-$(get_env TUNNEL_TOKEN)}
    [ -n "$value" ] || value=$(ask TUNNEL_TOKEN "Paste the Cloudflare tunnel token (or the whole install command): ")
    # Accept the whole "cloudflared service install eyJ..." command: keep the token only.
    value=$(printf '%s' "$value" | tr -d '[:space:]')
    case "$value" in *eyJ*) value="eyJ${value#*eyJ}" ;; esac
    printf '%s' "$value" | grep -Eq '^eyJ[A-Za-z0-9._=+/-]{40,}$' || die "that does not look like a tunnel token (it starts with eyJ)."
    set_env TUNNEL_TOKEN "$value"
    case ",$(get_env COMPOSE_PROFILES)," in
      *,tunnel,*) ;;
      *) set_env COMPOSE_PROFILES "tunnel,clamav" ;;
    esac
  fi

  # Secrets: generated here, once; never overwritten.
  for key in POSTGRES_PASSWORD JWT_SECRET FIELD_ENCRYPTION_KEY BLIND_INDEX_KEY ATTACHMENT_URL_SECRET; do
    [ -n "$(get_env "$key")" ] || set_env "$key" "$(random_hex 32)"
  done
  if [ -z "$(get_env SETUP_TOKEN)" ]; then
    value=$(random_hex 6)
    set_env SETUP_TOKEN "${value:0:4}-${value:4:4}-${value:8:4}"
  fi
  if [ "$first" = 1 ]; then
    local cores
    cores=$(nproc)
    value=$((cores - 1))
    [ "$value" -ge 2 ] || value=2
    [ "$value" -le 6 ] || value=6
    set_env WEB_CONCURRENCY "$value"
  fi
  set_env ENVIRONMENT production
}

# ---------------------------------------------------------------------------------------------
# 4. Start
# ---------------------------------------------------------------------------------------------
start() {
  log "Building the application (the first build takes 5-15 minutes)"
  dc build --pull
  dc pull --ignore-buildable --quiet
  log "Applying database migrations"
  dc up -d db
  wait_healthy db 180 || die "the database did not start."
  dc run --rm --no-deps -T backend alembic upgrade head
  log "Starting all services"
  dc up -d --remove-orphans
  wait_healthy backend 600 || die "the backend did not become healthy."
  wait_healthy frontend 300 || die "the frontend did not become healthy."
}

api() { # api METHOD PATH [JSON] — calls the backend inside its container, prints the body
  dc exec -T -e API_METHOD="$1" -e API_PATH="$2" -e API_BODY="${3:-}" backend python -c '
import os, sys, urllib.error, urllib.request
body = os.environ["API_BODY"].encode() or None
req = urllib.request.Request("http://127.0.0.1:8000/api/v1" + os.environ["API_PATH"], data=body,
                             method=os.environ["API_METHOD"], headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        sys.stdout.write(r.read().decode())
except urllib.error.HTTPError as e:
    sys.stdout.write(e.read().decode())
    sys.exit(1)
'
}

setup_needed() {
  local status
  status=$(api GET /setup) || die "the backend did not answer: $status"
  case "$status" in *'"needed":true'*) return 0 ;; *) return 1 ;; esac
}

create_admin() {
  log "Creating the first administrator ($ADMIN_EMAIL) through the first-time setup"
  local password=${ADMIN_PASSWORD:-} body
  [ -n "$password" ] || password="Hse-$(random_hex 5)-$(random_hex 5)!A"
  body=$(
    ORG_EN=${ORG_NAME_EN:-HSE Platform} ORG_AR=${ORG_NAME_AR:-منصة السلامة} \
      P_CODE=${PROJECT_CODE:-MAIN} P_EN=${PROJECT_NAME_EN:-Main project} \
      P_AR=${PROJECT_NAME_AR:-المشروع الرئيسي} P_CITY=${PROJECT_CITY:-Riyadh} \
      A_NAME=${ADMIN_NAME:-Administrator} A_EMAIL=$ADMIN_EMAIL A_PW=$password \
      NOTICE=$(get_env PRIVACY_NOTICE_VERSION) TOKEN=$(get_env SETUP_TOKEN) python3 -c '
import datetime, json, os
e = os.environ
print(json.dumps({
    "setup_token": e["TOKEN"],
    "organisation_name_en": e["ORG_EN"], "organisation_name_ar": e["ORG_AR"],
    "project": {"code": e["P_CODE"], "name_en": e["P_EN"], "name_ar": e["P_AR"],
                "project_type": "other", "client_name_en": e["ORG_EN"],
                "client_name_ar": e["ORG_AR"], "city": e["P_CITY"],
                "start_date": datetime.date.today().isoformat()},
    "admin": {"email": e["A_EMAIL"], "full_name_en": e["A_NAME"], "password": e["A_PW"]},
    "privacy_notice_version": e.get("NOTICE") or "PN-1.0",
}, ensure_ascii=False))'
  )
  local out
  if ! out=$(api POST /setup "$body"); then
    die "the first-time setup was refused: $out"
  fi
  local note=/root/hse-first-admin.txt
  umask 077
  printf 'HSE first administrator\nemail: %s\npassword: %s\n' "$ADMIN_EMAIL" "$password" >"$note"
  ADMIN_CREATED_PASSWORD=$password
}

load_demo() {
  local pw
  pw=$(get_env SEED_PASSWORD)
  if [ -z "$pw" ]; then
    pw="Demo-$(random_hex 5)-$(random_hex 3)!A"
    set_env SEED_PASSWORD "$pw"
  fi
  log "Loading the demo data (fake people and records, for trials only)"
  # The seed refuses ENVIRONMENT=production on purpose; this one-off process runs it as `demo`.
  dc exec -T -e ENVIRONMENT=demo -e SEED_PASSWORD="$pw" backend python -m app.seed
  DEMO_PASSWORD=$pw
}

main() {
  if [ "$SKIP_HOST" != 1 ]; then
    install_packages
    install_docker
    configure_firewall
    add_swap
  else
    log "Skipping the operating-system steps (--skip-host)"
    command -v docker >/dev/null || die "Docker is not installed."
    command -v openssl >/dev/null || die "openssl is not installed."
  fi
  fetch_code
  write_env
  start
  [ "$SKIP_HOST" = 1 ] || install_backup_timer

  ADMIN_CREATED_PASSWORD=""
  DEMO_PASSWORD=""
  if [ "$DEMO" = 1 ]; then
    load_demo
  elif [ "$CREATE_ADMIN" = 1 ] && setup_needed; then
    create_admin
  fi

  if [ -n "$(get_env CLAMAV_HOST)" ] && ! wait_healthy clamav 30 >/dev/null 2>&1; then
    echo "Note: the virus scanner is still downloading its signatures (a few minutes)."
  fi

  local url="https://$HSE_HOSTNAME"
  printf '\n=====================================================================\n'
  printf ' HSE platform is running.\n\n'
  if [ -n "$ADMIN_CREATED_PASSWORD" ]; then
    printf ' Open %s and sign in as %s\n' "$url" "$ADMIN_EMAIL"
    printf ' Password (shown once, also in /root/hse-first-admin.txt): %s\n' "$ADMIN_CREATED_PASSWORD"
  elif [ -n "$DEMO_PASSWORD" ]; then
    printf ' Open %s and sign in as faisal.harbi@example.com (HSE Manager)\n' "$url"
    printf ' Demo password for every demo user: %s\n' "$DEMO_PASSWORD"
  elif setup_needed; then
    printf ' Open %s  - the first-time setup page opens.\n' "$url"
    printf ' Setup code:  %s\n' "$(get_env SETUP_TOKEN)"
    printf ' Use this email for the administrator: %s\n' "$ADMIN_EMAIL"
  else
    printf ' Open %s and sign in.\n' "$url"
  fi
  printf '\n Update: sudo bash %s/deploy/oracle/update.sh\n' "$HSE_DIR"
  printf ' Backup now: sudo bash %s/deploy/oracle/backup.sh\n' "$HSE_DIR"
  printf '=====================================================================\n'
}

main
