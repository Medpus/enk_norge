# Utviklingsmiljø

Kjøres på **devmaskin**, ikke på Tower. Tower er deploy-mål. Nobara bruker rootless
Podman, og `podman-compose` installeres med `uv tool install podman-compose`.

## Oppsett: én kommando

```bash
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev-setup.sh
```

Scriptet setter opp `~/frappe-dev/`, MariaDB, Redis, en bench på `version-16`, ERPNext og sitet
`dev.localhost` med begge apper installert. Det skrur også på `developer_mode`. Oppsettet er
idempotent.

Første kjøring tar 10 til 20 minutter og laster ned noen GB.

Verifisert på Nobara 2026-09-17: full installasjon, gjentatt oppsett, `list-apps`, migrering,
innlogging, autentisert API og HTTP 200 fra `/app`. Start, gjentatt start og stopp besto også.

Slår ikke `dev.localhost` opp, legg den i hosts-fila:

```bash
echo '127.0.0.1 dev.localhost' | sudo tee -a /etc/hosts
```

## Daglig bruk

Port 8000 er opptatt av et annet program. `~/frappe-dev/.env` setter derfor
`ENK_DEV_HTTP_PORT=8001`. Bruk URL-en scriptet skriver ut. Den er normalt
`http://dev.localhost:8001`, og tjenesten lytter bare på localhost.

```bash
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev.sh start
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev.sh stop
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev.sh status
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev.sh logs
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev.sh shell
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev.sh bench ...
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev.sh migrate
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev.sh console
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev.sh fixtures
```

Innlogging: `Administrator` / `admin`.

## Hvor arbeidskopien ligger

```
~/frappe-dev/development/frappe-bench/apps/enk_norge
```

Det er denne du redigerer og pusher fra. Det finnes også en separat inngangsklone for dokumentasjon
og koordinering. Bytt til bench-kopien før kodeendringer, sjekk `git status`, og bevar eller
sammenlign ucommittert arbeid. Ikke kopier, reset eller overskriv endringer automatisk.

`bench start` har en filovervåker, så endringer i Python og JS slår inn uten omstart. Nye
DocTypes krever `developer_mode` (allerede satt) for å bli skrevet til disk i appen.

## Kort oppstartsrutine

```bash
cd ~/git/enk_norge
git status --short
git -C ~/git/janitor pull --ff-only
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev-setup.sh  # ved behov
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev.sh start
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev.sh status
cd ~/frappe-dev/development/frappe-bench/apps/enk_norge
git status --short
```

En shell-funksjon eller alias kan korte ned kommandoene, men `enk-dev.sh` ligger ikke
nødvendigvis i `PATH`.

## Kontroll og testing

```bash
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev.sh bench --site dev.localhost list-apps
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev.sh bench version
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev.sh migrate
```

Regnskapstestene bruker egne fiktive foretak og tilbakefører databasetransaksjonene.
Den samlede runneren nekter å kjøre på andre sites enn `test.localhost`. Opprett det
én gang på en ny maskin:

```bash
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev.sh bench new-site test.localhost \
  --mariadb-user-host-login-scope=% --db-root-username root --db-root-password 123 \
  --admin-password admin --install-app erpnext --install-app enk_norge
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev.sh bench --site test.localhost set-config allow_tests true
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev.sh bench --site test.localhost execute enk_norge.tests.runner.run
```

Kjør migrering før testene når metadata eller hooks er endret. Testene bygger på den
pinnede ERPNext-versjonen og omfatter ekte dokumenter og hovedbok, i tillegg til rene
beregninger. Resultat og avgrensninger står i [implementering og verifisering](implementering.md).

For en avgrenset kontroll kan runneren få modulnavn:

```bash
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev.sh bench --site test.localhost execute \
  enk_norge.tests.runner.run --kwargs '{"modules":["test_billing","test_access"]}'
```

Når benchen har flere lokale sites, skal `serve_default_site` være `false` og `default_site` være
tom i den globale bench-konfigurasjonen. Ellers starter `bench serve` med `dev.localhost` låst som
site og sender HTTP-kall dit, også når nettleseren åpner et separat testsite. Bekreft alltid
`frappe.boot.sitename` før en browser-test oppretter data.

Ved PDF-test fra et separat lokalt site må sitets `host_name` peke til containerens interne
webport, for eksempel `http://onboarding.localhost:8000`. Det gjelder også `dev.localhost` og
`fersk.localhost`, som begge har innstillingen. Nettleseren bruker fortsatt
vertsporten 8001. Uten dette prøver wkhtmltopdf i containeren å hente utskriftsressurser på
vertsporten og feiler med `ConnectionRefusedError`. Dette er bare en lokal testinnstilling;
produksjonens interne URL må verifiseres separat.

Dette er en site-konfigurasjon, ikke en endring i faktura- eller PDF-koden:

```bash
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev.sh bench --site onboarding.localhost \
  set-config host_name http://onboarding.localhost:8000
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev.sh bench --site onboarding.localhost clear-cache
```

Frappe bygger utskriftens URL-er fra `host_name`, mens wkhtmltopdf kjører inne i
bench-containeren og når webserveren på port 8000. Vertens port 8001 finnes bare utenfor
containeren. Ikke kopier denne lokale URL-en til produksjon; bruk produksjonens interne,
tilgjengelige URL etter egen verifisering.

Headless Playwright må bruke en gyldig nettleser-locale, for eksempel
`browser.newContext({ locale: "nb-NO" })`. Miljøets `en-US@posix` kan ellers havne i
`navigator.language` og krasje Frappes `Intl.Locale`-kall. Test uten innsprøytet fallback.
Punktum-desimaltekst fra API-et må gjøres til et JavaScript-tall før `format_currency`;
den norske parseren kan ellers tolke punktum som tusenskille og vise feil beløp.

Ved klikkede tilpasninger registreres DocType og eventuelle filtre under `fixtures` i `enk_norge/hooks.py`, og
kjør `bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev.sh fixtures` for å eksportere JSON
til appen. Bruk et separat testsite og fiktive bilag for regnskapsflyter. Produksjonsdata på Tower
skal aldri brukes i dev.

## Plass

Benchen med begge apper og containerne tar rundt 10 GiB. Nobara hadde 190 GiB ledig
2026-09-17, så det er god margin.

## Testing før deploy

```bash
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev.sh migrate
```

Det er her en ERPNext-oppgradering som brekker appen vår skal avsløres. En oppgradering krever
versjonskontroll, bygging, tester og `bench migrate`. Aldri gjør denne kontrollen på Tower.
