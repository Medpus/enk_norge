#!/bin/bash
# Setter opp et komplett lokalt ERPNext-utviklingsmiljø med enk_norge installert.
# Kjøres én gang. Etterpå: se dev.sh (samme mappe) for daglig bruk.
#
#   bash scripts/dev-setup.sh
#
# Lager ~/frappe-dev/ med en bench i en egen mappe, MariaDB og Redis i containere, og
# klonen av enk_norge som apps/enk_norge — DET er arbeidskopien du redigerer og pusher fra.
#
# Produksjonsdatabasen røres aldri herfra. Veien til produksjon går gjennom
# et image: push → CI bygger → bevisst deploy (se docs/deploy.md).
#
# Miljøvariabler: ENK_DEV_DIR (standard ~/frappe-dev), ENK_DEV_SITE (dev.localhost),
# ENK_DEV_HTTP_PORT (8000) og ENK_DEV_SOCKETIO_PORT (9000). Sett portene til noe annet
# for å kjøre flere miljøer samtidig.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEV_SH="$SCRIPT_DIR/dev.sh"
WORK="${ENK_DEV_DIR:-$HOME/frappe-dev}"
SITE="${ENK_DEV_SITE:-dev.localhost}"
FRAPPE_BRANCH=version-16
DB_ROOT_PW=123          # kun lokalt; miljøet skal aldri eksponeres
ADMIN_PW=admin
# Appens repo hentes fra klonen dette skriptet ligger i, så forker kloner seg selv.
APP_REPO_HTTPS="https://github.com/Medpus/enk_norge.git"
APP_REPO="$(git -C "$SCRIPT_DIR/.." remote get-url origin 2>/dev/null || true)"
APP_REPO="${APP_REPO:-$APP_REPO_HTTPS}"

die() { echo "FEIL: $*" >&2; exit 1; }
say() { echo; echo "── $*"; }

# --- container-runtime ------------------------------------------------------
if command -v docker >/dev/null && docker info >/dev/null 2>&1; then
  DC="docker compose"; RT=docker
elif command -v podman >/dev/null; then
  if podman compose version >/dev/null 2>&1; then DC="podman compose"
  elif command -v podman-compose >/dev/null; then DC="podman-compose"
  else die "podman finnes, men ingen compose. Installer: sudo dnf install podman-compose"; fi
  RT=podman
else
  die "Hverken docker eller podman er tilgjengelig. Installer podman og podman-compose (for eksempel sudo dnf install podman podman-compose)"
fi
echo "Runtime: $RT ($DC)"

# --- plass ------------------------------------------------------------------
avail=$(df -BG --output=avail "$HOME" | tail -1 | tr -dc '0-9')
echo "Ledig plass i \$HOME: ${avail} GiB"
if [ "$avail" -lt 15 ]; then
  echo "ADVARSEL: under 15 GiB ledig. Benchen + images tar ~10 GiB."
fi

mkdir -p "$WORK/development"
cd "$WORK"

# Porter gitt til oppsettet lagres i .env, som compose leser, så dev.sh bruker dem senere.
for var in ENK_DEV_HTTP_PORT ENK_DEV_SOCKETIO_PORT; do
  [ -n "${!var:-}" ] || continue
  touch .env
  if grep -q "^$var=" .env; then sed -i "s/^$var=.*/$var=${!var}/" .env
  else echo "$var=${!var}" >> .env; fi
done

# --- compose ----------------------------------------------------------------
say "Skriver $WORK/compose.yml"
cat > compose.yml <<'YAML'
# Lokalt ERPNext-dev-miljø. Bare for utvikling — ingen porter ut av maskinen
# utenom web/socketio på localhost, og trivielle passord.
services:
  mariadb:
    image: docker.io/mariadb:11.8
    command:
      - --character-set-server=utf8mb4
      - --collation-server=utf8mb4_unicode_ci
      - --skip-character-set-client-handshake
    environment:
      MARIADB_ROOT_PASSWORD: "123"
      MARIADB_AUTO_UPGRADE: "1"
    volumes:
      - mariadb-data:/var/lib/mysql

  redis-cache:
    image: docker.io/redis:alpine

  redis-queue:
    image: docker.io/redis:alpine

  frappe:
    image: docker.io/frappe/bench:latest
    init: true
    command: sleep infinity
    environment:
      SHELL: /bin/bash
    working_dir: /workspace/development
    volumes:
      - ./development:/workspace/development:z
    ports:
      - "127.0.0.1:${ENK_DEV_HTTP_PORT:-8000}:8000"   # web
      - "127.0.0.1:${ENK_DEV_SOCKETIO_PORT:-9000}:9000"   # socketio

volumes:
  mariadb-data:
YAML

# Rootless Podman må mappe frappe-brukeren til vertens bruker for skrivbare filer.
if [ "$RT" = podman ]; then
  sed -i '/image: docker.io\/frappe\/bench:latest/a\    userns_mode: "keep-id:uid=1000,gid=1000"' compose.yml
fi

say "Starter databasen og redis"
$DC up -d
for i in $(seq 1 60); do
  $DC exec -T mariadb mariadb -uroot -p"$DB_ROOT_PW" -e 'select 1' >/dev/null 2>&1 && break
  [ "$i" = 60 ] && die "MariaDB kom aldri opp"
  sleep 3
done
echo "   MariaDB svarer"

bench_exec() { $DC exec -T -w /workspace/development frappe bash -lc "$1"; }

# --- bench ------------------------------------------------------------------
if [ -d "$WORK/development/frappe-bench" ]; then
  say "Benchen finnes allerede — hopper over init"
else
  say "Initialiserer bench (dette tar noen minutter)"
  bench_exec "bench init --skip-redis-config-generation --frappe-branch $FRAPPE_BRANCH frappe-bench"
fi

say "Peker benchen på databasen og redis"
bench_exec "cd frappe-bench && \
  bench set-config -g db_host mariadb && \
  bench set-config -g redis_cache redis://redis-cache:6379 && \
  bench set-config -g redis_queue redis://redis-queue:6379 && \
  bench set-config -g redis_socketio redis://redis-queue:6379"

# --- apper ------------------------------------------------------------------
if bench_exec "test -d frappe-bench/apps/erpnext"; then
  echo "   erpnext finnes allerede"
else
  say "Henter ERPNext ($FRAPPE_BRANCH)"
  bench_exec "cd frappe-bench && bench get-app --branch $FRAPPE_BRANCH erpnext"
fi

APPDIR="$WORK/development/frappe-bench/apps/enk_norge"
if [ -d "$APPDIR/.git" ]; then
  echo "   enk_norge finnes allerede"
else
  say "Kloner enk_norge"
  # Klones på VERTEN, ikke i containeren: der virker git-autentiseringen din allerede,
  # og du får `origin` som remote (bench get-app kaller den `upstream` og klemmer
  # historikken med --depth 1). Dette ER arbeidskopien du redigerer og pusher fra.
  git clone "$APP_REPO" "$APPDIR" || { [ "$APP_REPO" != "$APP_REPO_HTTPS" ] && git clone "$APP_REPO_HTTPS" "$APPDIR"; } \
    || die "fikk ikke klonet enk_norge fra $APP_REPO — sjekk git-tilgangen din"

  # Containeren kjører som uid 1000. Er du ikke uid 1000, må eierskapet justeres.
  if [ "$RT" = docker ] && [ "$(id -u)" != 1000 ]; then
    echo "   du er uid $(id -u), containeren er 1000 — setter eierskap"
    sudo chown -R 1000:1000 "$APPDIR" || die "klarte ikke sette eierskap på $APPDIR"
  fi

fi

say "Registrerer enk_norge i benchen"
# Kjøres også etter avbrutt oppsett. Linjeskift før appnavnet hindrer sammenliming.
bench_exec "cd frappe-bench && env/bin/pip install -q -e apps/enk_norge"
bench_exec "cd frappe-bench && \
  { cat sites/apps.txt; printf '\\nenk_norge\\n'; } | awk 'NF && !seen[\$0]++' > sites/apps.txt.tmp && mv sites/apps.txt.tmp sites/apps.txt"

# --- site -------------------------------------------------------------------
if bench_exec "test -d frappe-bench/sites/$SITE"; then
  say "Sitet $SITE finnes allerede — hopper over"
else
  say "Lager sitet $SITE med erpnext + enk_norge"
  bench_exec "cd frappe-bench && bench new-site $SITE \
    --mariadb-user-host-login-scope='%' \
    --db-root-username root --db-root-password $DB_ROOT_PW \
    --admin-password $ADMIN_PW \
    --install-app erpnext --install-app enk_norge --set-default"
fi

# Fullfør også et oppsett som ble avbrutt etter at sitet var opprettet.
bench_exec "cd frappe-bench && bench --site $SITE install-app erpnext && bench --site $SITE install-app enk_norge"

say "Rydder sites/apps.txt"
# Fila mangler ofte avsluttende linjeskift, og et naivt tillegg gir 'erpnextenk_norge'.
bench_exec "cd frappe-bench && awk 'NF' sites/apps.txt | awk '!seen[\$0]++' > /tmp/a && mv /tmp/a sites/apps.txt && cat sites/apps.txt"

say "Skrur på developer_mode"
# Uten dette havner nye DocTypes bare i databasen, ikke som filer i appen din.
bench_exec "cd frappe-bench && bench --site $SITE set-config developer_mode 1 && bench --site $SITE clear-cache"

cat <<EOF

Ferdig.

  Arbeidskopi:  $WORK/development/frappe-bench/apps/enk_norge   ← rediger og push herfra
  Start:        bash $DEV_SH start
  Nettleser:    se adressen fra dev.sh start (bruker: Administrator / $ADMIN_PW)

Legg til i /etc/hosts hvis $SITE ikke slår opp:
  echo '127.0.0.1 $SITE' | sudo tee -a /etc/hosts
EOF
