# Utviklingsmiljø

Dev-miljøet kjører MariaDB, Redis og en frappe-bench i containere. Det virker med Docker
(`docker compose`) og med rootless Podman (`podman compose` eller `podman-compose`). På Podman
mappes containerens bruker til din egen, så filene i benchen blir skrivbare fra verten.

Krav: Git med tilgang til repoet, Docker eller Podman med compose, `curl` og rundt 15 GiB ledig
plass. Benchen med begge apper og containerne tar omtrent 10 GiB.

## Oppsett: én kommando

Klon repoet hvor som helst og kjør oppsettet derfra:

```bash
git clone https://github.com/Medpus/enk_norge.git
cd enk_norge
bash scripts/dev-setup.sh
```

Scriptet setter opp `~/frappe-dev/`, MariaDB, Redis, en bench på `version-16`, ERPNext og sitet
`dev.localhost` med begge apper installert. Det skrur også på `developer_mode`. Appen klones på
nytt inn i benchen fra samme remote som klonen du kjører fra. Oppsettet er idempotent og kan
kjøres igjen etter et avbrudd.

Første kjøring tar 10 til 20 minutter og laster ned noen GB.

| Variabel | Standard | Betydning |
|---|---|---|
| `ENK_DEV_DIR` | `~/frappe-dev` | Hvor miljøet ligger |
| `ENK_DEV_SITE` | `dev.localhost` | Sitet `migrate`, `console` og `fixtures` bruker |
| `ENK_DEV_HTTP_PORT` | `8000` | Webport på localhost |
| `ENK_DEV_SOCKETIO_PORT` | `9000` | Socket.IO-port på localhost |

Portene kan også settes i `~/frappe-dev/.env`, som compose leser automatisk. Er port 8000 opptatt
av noe annet, legg for eksempel `ENK_DEV_HTTP_PORT=8001` der.

Slår ikke `dev.localhost` opp, legg den i hosts-fila:

```bash
echo '127.0.0.1 dev.localhost' | sudo tee -a /etc/hosts
```

## Daglig bruk

Kommandoene kjøres fra appens rotmappe, i hvilken som helst klone:

```bash
bash scripts/dev.sh start      # start alt og skriv ut lokal URL
bash scripts/dev.sh stop
bash scripts/dev.sh status
bash scripts/dev.sh logs       # følg bench-loggen
bash scripts/dev.sh shell      # bash inne i benchen
bash scripts/dev.sh bench ...  # vilkårlig bench-kommando
bash scripts/dev.sh migrate    # bench migrate mot dev-sitet
bash scripts/dev.sh console    # frappe-konsoll mot dev-sitet
bash scripts/dev.sh fixtures   # eksporter klikkede tilpasninger inn i appen
```

Bruk URL-en scriptet skriver ut. Innlogging: `Administrator` / `admin`. Tjenesten lytter bare på
localhost, og passordene er bare for lokal bruk.

## Hvor arbeidskopien ligger

```
~/frappe-dev/development/frappe-bench/apps/enk_norge
```

Det er denne benchen kjører, og den du redigerer, committer og pusher fra. Klonen du startet
oppsettet fra, kan slettes eller brukes til lesing. Har du flere kloner, sjekk `git status` i
dem før kodeendringer og bevar ucommittert arbeid. Ikke kopier, reset eller overskriv
endringer automatisk.

`bench start` har en filovervåker, så endringer i Python og JS slår inn uten omstart. Nye
DocTypes krever `developer_mode` (allerede satt) for å bli skrevet til disk i appen.

## Kontroll og testing

```bash
bash scripts/dev.sh bench --site dev.localhost list-apps
bash scripts/dev.sh bench version
bash scripts/dev.sh migrate
```

De rene beregningstestene trenger ikke Frappe og er de samme som CI kjører. De trenger appens
avhengigheter, for eksempel i en venv med `pip install .`:

```bash
python -m unittest enk_norge.tests.test_norway_rules enk_norge.tests.test_saft \
  enk_norge.tests.test_posting_contract enk_norge.tests.test_year_end enk_norge.tests.test_vat \
  enk_norge.tests.test_deferrals enk_norge.tests.test_settlement
```

Regnskapstestene bruker egne fiktive foretak og tilbakefører databasetransaksjonene.
Den samlede runneren nekter å kjøre på andre sites enn `test.localhost`. Opprett det
én gang:

```bash
bash scripts/dev.sh bench new-site test.localhost \
  --mariadb-user-host-login-scope=% --db-root-username root --db-root-password 123 \
  --admin-password admin --install-app erpnext --install-app enk_norge
bash scripts/dev.sh bench --site test.localhost set-config allow_tests true
bash scripts/dev.sh bench --site test.localhost execute enk_norge.tests.runner.run
```

Kjør migrering før testene når metadata eller hooks er endret. Testene bygger på den
pinnede ERPNext-versjonen og omfatter ekte dokumenter og hovedbok, i tillegg til rene
beregninger. Resultat og avgrensninger står i [implementering og verifisering](implementering.md).

For en avgrenset kontroll kan runneren få modulnavn:

```bash
bash scripts/dev.sh bench --site test.localhost execute \
  enk_norge.tests.runner.run --kwargs '{"modules":["test_billing","test_access"]}'
```

Når benchen har flere lokale sites, skal `serve_default_site` være `false` og `default_site` være
tom i den globale bench-konfigurasjonen. Ellers starter `bench serve` med `dev.localhost` låst som
site og sender HTTP-kall dit, også når nettleseren åpner et separat testsite. Bekreft alltid
`frappe.boot.sitename` før en browser-test oppretter data.

Ved PDF-test fra et lokalt site må sitets `host_name` peke til containerens interne webport,
for eksempel `http://onboarding.localhost:8000`. Nettleseren bruker fortsatt vertsporten fra
`ENK_DEV_HTTP_PORT`. Uten dette prøver wkhtmltopdf i containeren å hente utskriftsressurser på
vertsporten og feiler med `ConnectionRefusedError` når den er en annen enn 8000.

Dette er en site-konfigurasjon, ikke en endring i faktura- eller PDF-koden:

```bash
bash scripts/dev.sh bench --site onboarding.localhost \
  set-config host_name http://onboarding.localhost:8000
bash scripts/dev.sh bench --site onboarding.localhost clear-cache
```

Frappe bygger utskriftens URL-er fra `host_name`, mens wkhtmltopdf kjører inne i
bench-containeren og når webserveren på port 8000. Vertsporten finnes bare utenfor
containeren. Ikke kopier denne lokale URL-en til produksjon; bruk produksjonens interne,
tilgjengelige URL etter egen verifisering.

Headless Playwright må bruke en gyldig nettleser-locale, for eksempel
`browser.newContext({ locale: "nb-NO" })`. En POSIX-locale som `en-US@posix` kan ellers havne i
`navigator.language` og krasje Frappes `Intl.Locale`-kall. Test uten innsprøytet fallback.
Punktum-desimaltekst fra API-et må gjøres til et JavaScript-tall før `format_currency`;
den norske parseren kan ellers tolke punktum som tusenskille og vise feil beløp.

Ved klikkede tilpasninger registreres DocType og eventuelle filtre under `fixtures` i
`enk_norge/hooks.py`. Kjør deretter `bash scripts/dev.sh fixtures` for å eksportere JSON til
appen. Bruk et separat testsite og fiktive bilag for regnskapsflyter. Produksjonsdata skal
aldri brukes i dev.

## Testing før deploy

```bash
bash scripts/dev.sh migrate
```

Det er her en ERPNext-oppgradering som brekker appen vår skal avsløres. En oppgradering krever
versjonskontroll, bygging, tester og `bench migrate`. Gjør aldri denne kontrollen mot produksjon.
