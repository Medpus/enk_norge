#!/bin/bash
# Daglig bruk av det lokale ERPNext-dev-miljøet. Oppsettet gjøres én gang med
# dev-setup.sh; denne er for å jobbe.
#
#   dev.sh start            # start alt og skriv ut lokal URL
#   dev.sh stop             # stopp containerne
#   dev.sh status           # hva kjører
#   dev.sh logs             # følg bench-loggen
#   dev.sh shell            # bash inne i benchen
#   dev.sh bench <args>     # kjør en vilkårlig bench-kommando
#   dev.sh migrate          # bench migrate mot dev-sitet
#   dev.sh fixtures         # eksporter klikkede tilpasninger inn i appen
#   dev.sh console          # frappe-konsoll (python) mot dev-sitet
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

WORK="${ENK_DEV_DIR:-$HOME/frappe-dev}"
SITE="${ENK_DEV_SITE:-dev.localhost}"
[ -f "$WORK/compose.yml" ] || { echo "Fant ikke $WORK/compose.yml — kjør ${SCRIPT_DIR}/dev-setup.sh først." >&2; exit 1; }

if command -v docker >/dev/null && docker info >/dev/null 2>&1; then DC="docker compose"
elif podman compose version >/dev/null 2>&1; then DC="podman compose"
else DC="podman-compose"; fi

dc()    { $DC -f "$WORK/compose.yml" "$@"; }
inbench() { dc exec -T -w /workspace/development/frappe-bench frappe bash -lc "$1"; }
inbench_tty() { dc exec -w /workspace/development/frappe-bench frappe bash -lc "$1"; }
web_port() { dc port frappe 8000 | tail -1 | awk -F: '{print $NF}'; }

cmd="${1:-start}"; shift || true

case "$cmd" in
  start)
    dc up -d
    port=$(web_port)
    # bench start kjører i forgrunnen, så den må detacheres inne i containeren
    if inbench "pgrep -f '[h]oncho start' >/dev/null"; then
      echo "bench kjører allerede"
    else
      # podman-compose videresender ikke exec -d. Frikoble prosessen inne i containeren.
      inbench "nohup bench start > /tmp/bench-start.log 2>&1 < /dev/null &"
    fi
    echo -n "venter på web"
    ready=false
    for i in $(seq 1 40); do
      code=$(curl -s -o /dev/null -w '%{http_code}' -H "Host: $SITE" "http://127.0.0.1:$port/" --max-time 5 || true)
      [ "$code" = 200 ] && { ready=true; echo; break; }
      echo -n "."; sleep 3
    done
    if [ "$ready" != true ]; then
      echo "Web kom ikke opp. Siste bench-logg:" >&2
      inbench "tail -60 /tmp/bench-start.log" >&2
      exit 1
    fi
    echo "→ http://$SITE:$port   (Administrator / admin)"
    ;;
  stop)    inbench "pkill -f '[h]oncho start' || true"; dc stop ;;
  status)
    dc ps || true
    echo
    if inbench "pgrep -f '[h]oncho start' >/dev/null" 2>/dev/null; then
      echo "bench: kjører — http://$SITE:$(web_port)"
    else
      echo "bench: kjører ikke"
    fi
    ;;
  logs)    dc exec -w /workspace/development/frappe-bench frappe bash -lc "tail -f /tmp/bench-start.log" ;;
  shell)   inbench_tty "exec bash" ;;
  bench)   dc exec -T -w /workspace/development/frappe-bench frappe bench "$@" ;;
  migrate) inbench "bench --site $SITE migrate" ;;
  console) inbench_tty "bench --site $SITE console" ;;
  fixtures)
    # Tilpasninger du har klikket inn (custom fields, print formats, workflows) ligger
    # bare i dev-databasen til de eksporteres hit. Krever at doctypen er listet i
    # `fixtures` i enk_norge/hooks.py.
    inbench "bench --site $SITE export-fixtures"
    echo "Sjekk 'git status' i apps/enk_norge — de nye JSON-filene skal commites."
    ;;
  *) sed -n '2,16p' "$0"; exit 1 ;;
esac
