#!/bin/bash
# Henter nyeste verifiserte serverbackup (laget av server_backup.sh) og krypterer
# den lokalt med age. Oppsettet leses fra ${ENK_BACKUP_CONFIG:-~/.config/enk_norge/backup.env};
# se backup.env.example i samme mappe.
set -euo pipefail
umask 077

KEY_DIR="$HOME/.config/enk_norge"
CONFIG="${ENK_BACKUP_CONFIG:-$KEY_DIR/backup.env}"
[ -f "$CONFIG" ] || { echo "Fant ikke $CONFIG. Kopier backup.env.example dit og fyll ut." >&2; exit 1; }
# shellcheck disable=SC1090
. "$CONFIG"
REMOTE="${BACKUP_REMOTE:-}"
REMOTE_ROOT="${BACKUP_REMOTE_ROOT:-}"
[ -n "$REMOTE" ] || { echo "BACKUP_REMOTE mangler i $CONFIG." >&2; exit 1; }
[ -n "$REMOTE_ROOT" ] || { echo "BACKUP_REMOTE_ROOT mangler i $CONFIG." >&2; exit 1; }
LOCAL_ROOT="${BACKUP_LOCAL_ROOT:-$HOME/backups/erpnext}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-90}"
KEY_FILE="$KEY_DIR/erpnext-backup.agekey"

mkdir -p "$LOCAL_ROOT" "$KEY_DIR"
chmod 700 "$LOCAL_ROOT" "$KEY_DIR"
if [ ! -f "$KEY_FILE" ]; then
	age-keygen -o "$KEY_FILE" >/dev/null 2>&1
	chmod 600 "$KEY_FILE"
fi
recipient=$(age-keygen -y "$KEY_FILE")
latest=$(ssh -o BatchMode=yes "$REMOTE" "find '$REMOTE_ROOT' -mindepth 2 -maxdepth 2 -type f -name bench-backup.tar.gz -printf '%T@ %p\\n' | sort -nr | head -1 | cut -d' ' -f2-")
# Stien må være nøyaktig <BACKUP_REMOTE_ROOT>/<YYYYMMDD_HHMMSS>/bench-backup.tar.gz
[[ "$latest" =~ ^"${REMOTE_ROOT%/}"/[0-9]{8}_[0-9]{6}/bench-backup\.tar\.gz$ ]] || {
	echo "Fant ingen forventet verifisert serverbackup." >&2
	exit 1
}
stamp=$(basename "$(dirname "$latest")")
target="$LOCAL_ROOT/$stamp-bench-backup.tar.gz.age"
[ -f "$target" ] && exit 0
tmp=$(mktemp "$LOCAL_ROOT/.${stamp}.XXXXXX")
trap 'rm -f "$tmp"' EXIT
# Kontrollsummen kjøres på serveren i samme SSH-kommando som strømmer data. Dermed
# krypteres aldri et arkiv som ikke samsvarer med manifestet, og det lagres aldri
# ukryptert lokalt.
ssh -o BatchMode=yes "$REMOTE" "set -eu; cd '$REMOTE_ROOT/$stamp'; sha256sum -c SHA256SUMS >/dev/null; cat bench-backup.tar.gz" \
	| age -r "$recipient" -o "$tmp"
age -d -i "$KEY_FILE" "$tmp" | tar -tzf - >/dev/null
mv "$tmp" "$target"
chmod 600 "$target"
find "$LOCAL_ROOT" -maxdepth 1 -type f -name '*-bench-backup.tar.gz.age' -mtime "+$KEEP_DAYS" -delete
