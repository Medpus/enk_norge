# ERPNext-backup på Tower

Tower kjører `tower_erpnext_backup.sh` hver dag 03:15 gjennom Unraids User Scripts-plugin.
Skriptet kjører `bench --site erp.example.com backup --with-files`, pakker databasen,
offentlige og private filer samt `site_config_backup.json` i ett arkiv. Før pakking
testes databasedumpen med `gzip -t` og begge filarkivene med `tar -tf`; deretter
kontrolleres ytterarkivet med tar og SHA-256 før noe eldre slettes. `site_config_backup.json` inneholder
site-konfigurasjonen, inkludert krypteringsnøkkelen som kreves for å lese krypterte
Frappe-data, og behandles derfor som hemmelig.

Lokalt på Nobara kjører `enk_norge_offsite_backup.timer` 04:30. Timeren har
`Persistent=true`, så systemd kjører den etter oppstart dersom en planlagt kjøring ble
misset. Den kjører `pull_tower_erpnext_backup.sh` direkte fra bench-appen. Skriptet
verifiserer `SHA256SUMS` på Tower i samme SSH-kommando som arkivet strømmer før det
krypteres med en lokal age-nøkkel. Nøkkelen ligger
med modus 0600 i `~/.config/enk_norge/erpnext-backup.agekey`; backupene ligger med
modus 0600 i `~/backups/erpnext/`. Tower beholder 30 dager, Nobara 90 dager. Oppbevar også age-nøkkelen i en
separat, beskyttet nøkkelbackup. Uten den kan Nobara-arkivene ikke dekrypteres.

Kontroller Tower-status uten å vise data:

```bash
ssh root@server.example \
  '/mnt/user/appdata/erpnext/enk-backups/bin/tower_erpnext_backup.sh status'
```

Kjør backup manuelt på Tower:

```bash
bash /boot/config/plugins/user.scripts/scripts/erpnext_full_backup/script
```

Se siste kjøring og feil på Tower i
`/mnt/user/appdata/erpnext/enk-backups/logs/backup.log`; User Scripts viser også
utdata fra den planlagte kjøringen. Se Nobara-timeren med
`systemctl --user status enk_norge_offsite_backup.timer` og siste kopiering med
`journalctl --user -u enk_norge_offsite_backup.service`.

En restore skal først skje på et isolert testsite med scheduler og e-postutsending av.
Age kontrollerer integriteten ved dekryptering av Nobara-kopien. Tower-kopien har et
separat `SHA256SUMS` ved siden av arkivet; det er ikke inne i det krypterte arkivet.
Pakk ut med private filrettigheter og bruk:

```bash
bench --site <testsite> restore <database.sql.gz> \
  --with-public-files <files.tar> --with-private-files <private-files.tar>
```

Bevar testsiteets databaseforbindelse og interne URL. Gjenopprett den opprinnelige
`encryption_key` fra konfigurasjonsbackupen uten å skrive nøkkelen i terminal eller
logger. Ikke erstatt hele testkonfigurasjonen med produksjonskonfigurasjonen. Kjør
migrering med riktig appversjon, og kontroller vedlegg, rapporter og signerte bilag.
Produksjon brukes aldri som restore-test.
