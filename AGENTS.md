# enk_norge — driftsmanual for agenter

Norsk ERPNext-tilpasning for norske enkeltpersonforetak. Les denne fila først.
Maskinparken og de større driftsrutinene ligger i **janitor**-repoet
(`~/git/janitor`) — særlig `hosts/tower/fixes/enk-norge-app-og-byggekjede.md`,
som forklarer hvorfor dette repoet ser ut som det gjør.

## Grunnregelen, som aldri brytes

**Dette er en Frappe-app ved siden av ERPNext. Det er ikke en fork.**

Skal vi gripe inn i ERPNexts logikk, gjøres det gjennom Frappes hooks i `enk_norge/hooks.py`
— `doc_events`, `override_doctype_class`, `override_whitelisted_methods`. Vi redigerer
**aldri** filer under `apps/erpnext/` eller `apps/frappe/`.

Grunnen: så lenge vi holder oss til vår egen app, er «hent inn nyeste ERPNext» å bytte en
branch i `apps.json` og bygge på nytt — ingen merge, ingen konflikt. Patcher noen ERPNext-kode
direkte, arver vi vedlikeholdsbyrden til et prosjekt på hundretusenvis av linjer, og da er hele
arkitekturvalget bortkastet.

Ser du deg selv i ferd med å redigere i `apps/erpnext/`: stopp, og finn hooken i stedet.

## Utviklingsmiljø

Kjøres på **devmaskin**, aldri på Tower. Tower er deploy-mål.

```bash
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev-setup.sh   # én gang
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev.sh start   # daglig
```

Miljøet er MariaDB + Redis + en frappe-bench i containere, med sitet `dev.localhost` på
`http://dev.localhost:8000` (Administrator / admin). **Arbeidskopien du redigerer og pusher
fra er `~/frappe-dev/development/frappe-bench/apps/enk_norge`** — ikke en separat klone et
annet sted.

Daglige kommandoer (`enk-dev.sh <kommando>`): `start`, `stop`, `status`, `logs`, `shell`,
`bench <args>`, `migrate`, `console`, `fixtures`.

Produksjonsdatabasen på Tower røres aldri herfra.

## Arbeidsflyten

```
rediger i apps/enk_norge  →  test på dev.localhost  →  bench migrate i dev
   →  commit + push til main  →  CI bygger ghcr.io/medpus/erpnext-enk:v16-<sha>
      →  bevisst deploy på Tower
```

`bench migrate` i dev **før** deploy er ikke valgfritt. Det er der en ERPNext-oppgradering som
brekker appen vår skal avsløres — ikke på Tower.

### Tilpasninger som lages ved å klikke

Custom fields, print formats, workflows og kontoplan-maler settes ofte opp i grensesnittet. De
finnes da **bare i dev-databasen** og forsvinner ved gjenoppbygging. Riktig løkke:

1. Klikk det på plass i `dev.localhost`.
2. Legg doctypen inn under `fixtures` i `enk_norge/hooks.py`.
3. `enk-dev.sh fixtures` — de skrives som JSON inn i appen.
4. Commit dem. Nå følger de med imaget og legges inn av `bench migrate` i produksjon.

### Migrasjoner

Endringer som må kjøres mot eksisterende data hører i `enk_norge/patches.txt` + `patches/`.
`bench migrate` kjører dem. Beregninger og valideringer skal ligge i **testbar kode** her, ikke
i vurderinger en språkmodell gjør der og da — det er hele poenget med at dette er et program og
ikke en samtale.

## Deploy

```bash
# på Tower
bash ~/git/janitor/hosts/tower/scripts/erpnext-deploy.sh v16-<sha>
```

Scriptet tar backup, bytter image, installerer nye apper, kjører `bench migrate` og verifiserer.

**ERPNext-stacken har bevisst ingen Watchtower-label.** De andre appene auto-oppdateres;
denne gjør det ikke, fordi et nytt image alltid må følges av `bench migrate`. Ikke legg på
labelen «for konsistens».

## Feller som allerede har bitt oss

- `sites/apps.txt` mangler ofte avsluttende linjeskift. Et naivt `>>` gir `erpnextenk_norge`.
- `bench get-app` på en mappe som alt finnes i `apps/` spør om å overskrive og avbryter. Appen
  klones derfor på **verten**, og registreres med `pip install -e` + en linje i `apps.txt`.
- `bench get-app` kaller remoten `upstream` og klemmer historikken med `--depth 1`. Vi kloner
  selv for å få en normal `origin`.
- En `~/.ssh`-mount inn i bench-containeren hjelper ikke: containeren kjører som uid 1000 og får
  ikke lest nøkler som eies av en annen bruker. Git-operasjoner gjøres fra verten.
- `bench new-site` skrur **av** scheduleren. I produksjon må den skrus på igjen.
- `developer_mode` må være på i dev, ellers havner nye DocTypes bare i databasen og ikke som
  filer i appen.

## Konvensjoner

- **Norsk** i dokumentasjon, commit-meldinger og kommentarer. Kode, DocType-navn og felt på
  engelsk der Frappe forventer det.
- Datoer absolutte (YYYY-MM-DD).
- Git-identitet: `85625055+Medpus@users.noreply.github.com`. **Aldri** jobb-adressen.
- Varige lærdommer hører i janitor-repoet, ikke bare her.

## Hva som gjenstår

Skjelettet står; det norske innholdet er ikke skrevet. Rekkefølgen som er planlagt: kontoplan
(NS 4102), MVA-håndtering, privatinnskudd og privat betalte kjøp, saldogrupper og avskrivninger,
fakturanummerering og sporbarhet, og til slutt SAF-T-eksport.

**Ingenting av dette er verifisert mot norske skatteregler ennå.** ERPNext ut av boksen har ingen
norsk kontoplan. Behandle systemet som et utviklingsprosjekt, ikke som et regnskap som er riktig,
helt til hver del er testet med fiktive bilag fram til avstemming og eksport.
