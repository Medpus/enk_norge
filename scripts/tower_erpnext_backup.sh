#!/bin/bash
# Daglig, selvstendig fullbackup av ERPNext på Tower.
set -euo pipefail
umask 077

APPDATA=/mnt/user/appdata/erpnext
ENVFILE="$APPDATA/.env"
SITE_ROOT="$APPDATA/sites"
ARCHIVE_ROOT="$APPDATA/enk-backups"
LOG_DIR="$ARCHIVE_ROOT/logs"
RETENTION_DAYS=30
LOCKFILE="$ARCHIVE_ROOT/.backup.lock"

say() { printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*"; }
die() { say "FEIL: $*" >&2; exit 1; }

[ -f "$ENVFILE" ] || die "Finner ikke ERPNext .env."
# shellcheck disable=SC1090
set -a; . "$ENVFILE"; set +a
SITE="${SITE_NAME:?SITE_NAME mangler i .env}"
SOURCE="$SITE_ROOT/$SITE/private/backups"

mkdir -p "$ARCHIVE_ROOT" "$LOG_DIR"
chmod 700 "$ARCHIVE_ROOT" "$LOG_DIR"
exec 3>&1
exec >>"$LOG_DIR/backup.log" 2>&1
exec 9>"$LOCKFILE"
flock -n 9 || die "En ERPNext-backup kjører allerede."

verify_archive() {
	local directory="$1"
	[ -f "$directory/bench-backup.tar.gz" ] || return 1
	[ -f "$directory/SHA256SUMS" ] || return 1
	( cd "$directory" && sha256sum -c SHA256SUMS >/dev/null ) || return 1
	tar -tzf "$directory/bench-backup.tar.gz" >/dev/null || return 1
}

cleanup_verified() {
	local directory source_prefix
	while IFS= read -r -d '' directory; do
		if ! verify_archive "$directory"; then
			say "Beholder uverifisert gammel backup: ${directory##*/}"
			continue
		fi
		source_prefix=$(sed -n 's/^source_prefix=//p' "$directory/metadata" | head -1)
		if [[ "$source_prefix" =~ ^[0-9]{8}_[0-9]{6}-[A-Za-z0-9_.-]+$ ]]; then
			rm -f "$SOURCE/${source_prefix}-database.sql.gz" \
			"$SOURCE/${source_prefix}-files.tar" \
			"$SOURCE/${source_prefix}-private-files.tar" \
			"$SOURCE/${source_prefix}-site_config_backup.json"
		fi
		rm -rf "$directory"
		say "Slettet verifisert backup eldre enn $RETENTION_DAYS dager: ${directory##*/}"
	done < <(find "$ARCHIVE_ROOT" -mindepth 1 -maxdepth 1 -type d -name '20??????_??????' -mtime "+$RETENTION_DAYS" -print0)
}

[ -d "$SOURCE" ] || die "Finner ikke backup-mappe for sitet."
case "${1:-backup}" in
	status)
		latest=$(find "$ARCHIVE_ROOT" -mindepth 1 -maxdepth 1 -type d -name '20??????_??????' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)
		[ -n "$latest" ] || die "Ingen verifisert ERPNext-backup finnes ennå."
		verify_archive "$latest" || die "Siste ERPNext-backup besto ikke kontrollsummen eller arkivtesten."
		printf '%s Siste verifiserte backup: %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "${latest##*/}" >&3
		exit 0
		;;
	backup) ;;
	*) die "Bruk: $0 [backup|status]" ;;
esac
docker ps --format '{{.Names}}' | grep -qx erpnext-backend || die "erpnext-backend kjører ikke."

stamp=$(date '+%Y%m%d_%H%M%S')
tmp="$ARCHIVE_ROOT/.${stamp}.tmp"
final="$ARCHIVE_ROOT/$stamp"
marker="$SOURCE/.enk-backup-${stamp}.marker"
trap 'rm -f "$marker"; rm -rf "$tmp"' EXIT
mkdir "$tmp"
touch "$marker"

say "Starter full bench-backup for $SITE."
docker exec erpnext-backend bench --site "$SITE" backup --with-files

mapfile -t databases < <(find "$SOURCE" -maxdepth 1 -type f -newer "$marker" -name '*-database.sql.gz' -printf '%f\n' | sort)
[ "${#databases[@]}" = 1 ] || die "Fant ikke nøyaktig én ny databasebackup."
source_prefix=${databases[0]%-database.sql.gz}
for suffix in database.sql.gz files.tar private-files.tar site_config_backup.json; do
	[ -f "$SOURCE/$source_prefix-$suffix" ] || die "Manglende del av bench-backup: $suffix"
done

# Test delene før de blir pakket inn. Et gyldig ytterarkiv alene beviser ikke at
# databasedumpen eller Frappes filarkiver kan leses.
gzip -t "$SOURCE/$source_prefix-database.sql.gz" || die "Databasebackupen kan ikke leses."
tar -tf "$SOURCE/$source_prefix-files.tar" >/dev/null || die "Arkivet med offentlige filer kan ikke leses."
tar -tf "$SOURCE/$source_prefix-private-files.tar" >/dev/null || die "Arkivet med private filer kan ikke leses."

tar -C "$SOURCE" -czf "$tmp/bench-backup.tar.gz" \
	"$source_prefix-database.sql.gz" \
	"$source_prefix-files.tar" \
	"$source_prefix-private-files.tar" \
	"$source_prefix-site_config_backup.json"
tar -tzf "$tmp/bench-backup.tar.gz" >/dev/null
( cd "$tmp" && sha256sum bench-backup.tar.gz > SHA256SUMS )
(
	printf 'created_at=%s\n' "$(date -Iseconds)"
	printf 'site=%s\n' "$SITE"
	printf 'source_prefix=%s\n' "$source_prefix"
	printf 'contents=database,public-files,private-files,site-config\n'
) > "$tmp/metadata"
chmod 600 "$tmp/bench-backup.tar.gz" "$tmp/SHA256SUMS" "$tmp/metadata"
verify_archive "$tmp" || die "Den nye backupen besto ikke kontrollen."
mv "$tmp" "$final"
trap 'rm -f "$marker"' EXIT
rm -f "$marker"
say "Verifisert backup: $final"
cleanup_verified
