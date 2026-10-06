# Backup og gjenoppretting

Regnskapsmateriale må kunne gjenopprettes i flere år, og en backup på samme disk beskytter ikke
mot tap av maskinen. Appen har to skript for en frappe_docker-stack: en daglig fullbackup på
serveren og en kryptert kopi til en annen maskin. Bruk dem som de er, eller som utgangspunkt
for din egen rutine.

## Fullbackup på serveren

`scripts/server_backup.sh` kjøres daglig på serveren, for eksempel fra cron eller en
planlegger i serverens administrasjon. Det leser `SITE_NAME` fra stackens `.env` og kjører
`bench --site <site> backup --with-files` i backend-containeren. Deretter pakker det databasen,
offentlige og private filer samt `site_config_backup.json` i ett arkiv.

Før pakking testes databasedumpen med `gzip -t` og begge filarkivene med `tar -tf`. Deretter
kontrolleres ytterarkivet med tar og SHA-256 før noe eldre slettes. Verifiserte backuper eldre
enn 30 dager slettes; en backup som ikke består kontrollen, beholdes.

| Variabel | Standard | Betydning |
|---|---|---|
| `ERPNEXT_DIR` | `/mnt/user/appdata/erpnext` | Stackens mappe med `.env` og `sites/` |
| `ERPNEXT_BACKEND_CONTAINER` | `erpnext-backend` | Navnet på backend-containeren |

Arkivene havner i `<ERPNEXT_DIR>/enk-backups/<tidsstempel>/` og loggen i
`<ERPNEXT_DIR>/enk-backups/logs/backup.log`. `server_backup.sh status` kontrollerer siste
backup uten å vise data.

`site_config_backup.json` inneholder site-konfigurasjonen, inkludert krypteringsnøkkelen som
kreves for å lese krypterte Frappe-data. Behandle backupene som hemmelige.

## Kryptert kopi til en annen maskin

`scripts/pull_backup.sh` henter nyeste verifiserte backup over SSH og krypterer den lokalt med
[age](https://age-encryption.org). Kontrollsummen sjekkes på serveren i samme SSH-kommando som
strømmer arkivet, så et arkiv som ikke stemmer med manifestet blir aldri kryptert, og ingenting
lagres ukryptert lokalt. Etterpå prøves dekryptering og tar-lesing før fila tas i bruk.

Oppsett:

```bash
mkdir -p ~/.config/enk_norge
cp scripts/backup.env.example ~/.config/enk_norge/backup.env
chmod 600 ~/.config/enk_norge/backup.env
# Fyll inn BACKUP_REMOTE og BACKUP_REMOTE_ROOT.
```

SSH-innloggingen må virke uten passord (`BatchMode`). Første kjøring lager age-nøkkelen
`~/.config/enk_norge/erpnext-backup.agekey` (modus 0600). Arkivene havner i `~/backups/erpnext/`
og beholdes i 90 dager. Begge kan endres i konfigurasjonsfila. **Ta vare på age-nøkkelen i en
separat, beskyttet nøkkelbackup.** Uten den kan kopiene ikke dekrypteres.

`scripts/enk_norge_offsite_backup.service` og `.timer` kjører skriptet daglig 04:30 som
systemd-brukertjeneste. Timeren har `Persistent=true`, så en kjøring som ble misset tas igjen
etter oppstart. Tjenesten peker på skriptet i bench-klonen; juster `ExecStart` hvis appen
ligger et annet sted.

```bash
cp scripts/enk_norge_offsite_backup.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now enk_norge_offsite_backup.timer
systemctl --user status enk_norge_offsite_backup.timer
journalctl --user -u enk_norge_offsite_backup.service
```

## Gjenoppretting

En restore skal først skje på et isolert testsite med scheduler og e-postutsending av.
age kontrollerer integriteten ved dekryptering av den lokale kopien. Serverkopien har et
separat `SHA256SUMS` ved siden av arkivet; det er ikke inne i det krypterte arkivet.
Pakk ut med private filrettigheter og bruk:

```bash
bench --site <testsite> restore <database.sql.gz> \
  --with-public-files <files.tar> --with-private-files <private-files.tar>
```

Bevar testsitets databaseforbindelse og interne URL. Gjenopprett den opprinnelige
`encryption_key` fra konfigurasjonsbackupen uten å skrive nøkkelen i terminal eller
logger. Ikke erstatt hele testkonfigurasjonen med produksjonskonfigurasjonen. Kjør
migrering med riktig appversjon, og kontroller vedlegg, rapporter og signerte bilag.
Produksjon brukes aldri som restore-test.
