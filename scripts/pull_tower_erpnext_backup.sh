#!/bin/bash
# Henter nyeste verifiserte Tower-backup og krypterer den lokalt med age.
set -euo pipefail
umask 077

REMOTE='root@server.example'
REMOTE_ROOT='/mnt/user/appdata/erpnext/enk-backups'
LOCAL_ROOT="$HOME/backups/erpnext"
KEY_DIR="$HOME/.config/enk_norge"
KEY_FILE="$KEY_DIR/erpnext-backup.agekey"
KEEP_DAYS=90

mkdir -p "$LOCAL_ROOT" "$KEY_DIR"
chmod 700 "$LOCAL_ROOT" "$KEY_DIR"
if [ ! -f "$KEY_FILE" ]; then
	age-keygen -o "$KEY_FILE" >/dev/null 2>&1
	chmod 600 "$KEY_FILE"
fi
recipient=$(age-keygen -y "$KEY_FILE")
latest=$(ssh -o BatchMode=yes "$REMOTE" "find '$REMOTE_ROOT' -mindepth 2 -maxdepth 2 -type f -name bench-backup.tar.gz -printf '%T@ %p\\n' | sort -nr | head -1 | cut -d' ' -f2-")
[[ "$latest" =~ ^/mnt/user/appdata/erpnext/enk-backups/20[0-9]{6}_[0-9]{6}/bench-backup\.tar\.gz$ ]] || {
	echo "Fant ingen forventet verifisert Tower-backup." >&2
	exit 1
}
stamp=$(basename "$(dirname "$latest")")
target="$LOCAL_ROOT/$stamp-bench-backup.tar.gz.age"
[ -f "$target" ] && exit 0
tmp=$(mktemp "$LOCAL_ROOT/.${stamp}.XXXXXX")
trap 'rm -f "$tmp"' EXIT
# Kontrollsummen kjøres på Tower i samme SSH-kommando som strømmer data. Dermed
# krypteres aldri et arkiv som ikke samsvarer med manifestet, og det lagres aldri
# ukryptert på Nobara.
ssh -o BatchMode=yes "$REMOTE" "set -eu; cd '$REMOTE_ROOT/$stamp'; sha256sum -c SHA256SUMS >/dev/null; cat bench-backup.tar.gz" \
	| age -r "$recipient" -o "$tmp"
age -d -i "$KEY_FILE" "$tmp" | tar -tzf - >/dev/null
mv "$tmp" "$target"
chmod 600 "$target"
find "$LOCAL_ROOT" -maxdepth 1 -type f -name '*-bench-backup.tar.gz.age' -mtime "+$KEEP_DAYS" -delete
