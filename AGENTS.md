# enk_norge: driftsmanual for agenter

Gjenbrukbar norsk ERPNext-tilpasning for enkeltpersonforetak. Konsulentvirksomhet
og SaaS-prosjekter er de første brukstilfellene. Les denne fila først.
Maskinparken og de større driftsrutinene ligger i **janitor**-repoet
(`~/git/janitor`), særlig `hosts/tower/fixes/enk-norge-app-og-byggekjede.md`,
som forklarer hvorfor dette repoet ser ut som det gjør.

## Grunnregelen, som aldri brytes

**Dette er en Frappe-app ved siden av ERPNext. Det er ikke en fork.**

Skal vi gripe inn i ERPNexts logikk, gjøres det gjennom Frappes hooks i `enk_norge/hooks.py`
(`doc_events`, `override_doctype_class`, `override_whitelisted_methods`). Vi redigerer
**aldri** filer under `apps/erpnext/` eller `apps/frappe/`.

Grunnen: så lenge vi holder oss til vår egen app, kan vi oppgradere ERPNext ved å endre versjon
i `apps.json`, bygge, teste og kjøre `bench migrate`. Bygge-workflowen leser `apps.json`,
verifiserer at ERPNext-grenen samsvarer med `FRAPPE_BRANCH`, og bruker den versjonerte kontrakten.
Det krever versjonskontroll og verifisering. Patcher noen ERPNext-kode direkte, arver vi
vedlikeholdsbyrden til et prosjekt på hundretusenvis av linjer, og da er hele arkitekturvalget
bortkastet.

Ser du deg selv i ferd med å redigere i `apps/erpnext/`: stopp, og finn hooken i stedet.

## Utviklingsmiljø

Kjøres på **devmaskin**, aldri på Tower. Tower er deploy-mål. Nobara bruker rootless
Podman. `podman-compose` installeres med `uv tool install podman-compose` (for tiden 1.6.0).

```bash
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev-setup.sh   # ved behov
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev.sh start   # daglig
```

Oppsettsskriptet ligger i janitor-repoet. Miljøet er MariaDB, Redis og en frappe-bench i rootless
containere. Arbeidskopien benchen bruker er
`~/frappe-dev/development/frappe-bench/apps/enk_norge`. Det finnes også en separat inngangsklone
for dokumentasjon og koordinering. Før kodeendringer skal agenten bytte til bench-kopien, sjekke
git-status og bevare eller sammenligne ucommittert arbeid. Ikke kopier, reset eller overskriv
endringer automatisk.

Port 8000 brukes av et annet program. I `~/frappe-dev/.env` er derfor `ENK_DEV_HTTP_PORT=8001` satt,
slik at URL-en normalt er `http://dev.localhost:8001` (Administrator / admin). Scriptet har
8000 som standard og skriver faktisk port i `start` og `status`. Tjenesten skal bare lytte på
localhost.

Daglige kommandoer bruker den absolutte scriptstien, med mindre du selv lager en shell-funksjon:
`start`, `stop`, `status`, `logs`, `shell`, `bench <args>`, `migrate`, `console` og `fixtures`.
Se [docs/utvikling.md](docs/utvikling.md) for rutinen og kontrollkommandoene.

Produksjonsdatabasen på Tower røres aldri herfra.

## Arbeidsflyten

```
les instruks og sjekk status  →  rediger i bench/apps/enk_norge  →  test på dev.localhost
   →  bench migrate i dev  →  commit + push til main  →  CI bygger image
      →  bevisst deploy på Tower
```

`bench migrate` i dev **før** deploy er ikke valgfritt. Det er der en ERPNext-oppgradering som
brekker appen vår skal avsløres før deploy, ikke på Tower.

### Tilpasninger som lages ved å klikke

Custom fields, print formats, workflows og kontoplan-maler settes ofte opp i grensesnittet. De
finnes da **bare i dev-databasen** og forsvinner ved gjenoppbygging. Riktig løkke:

1. Klikk det på plass i dev-sitet.
2. Legg doctypen inn under `fixtures` i `enk_norge/hooks.py`, med filtre når bare et avgrenset
   utvalg skal eksporteres.
3. Kjør `bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev.sh fixtures`. De skrives som
   JSON inn i appen.
4. Commit dem. Nå følger de med imaget og legges inn av `bench migrate` i produksjon.

### Migrasjoner

Endringer som må kjøres mot eksisterende data hører i `enk_norge/patches.txt` + `patches/`.
`bench migrate` kjører dem. Beregninger og valideringer skal ligge i **testbar kode** her, ikke
i vurderinger en språkmodell gjør der og da. Det er hele poenget med at dette er et program og
ikke en samtale.

### Arbeid mot Tower

Når en oppgave faktisk krever tilgang til Tower, bruk en native subagent med SSH og koordinér
kommandoene og resultatet tilbake hit. Oppgi vert, arbeidsmappe og avgrensning tydelig. Dev-arbeid
og tester kjøres fortsatt på Nobara.

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
- Rootless Podman bruker `userns_mode: keep-id:uid=1000,gid=1000` for å gi containerprosessen
  riktig uid og gid på host-filer. `:z` er en separat SELinux-merking for mounts. Nobara har
  SELinux Disabled, så den er ikke nødvendig der.
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

## Norske regnskapsfunksjoner

Les [regelgrunnlaget](docs/norske-enk-krav.md) og [utviklingsplanen](docs/enk-produktplan.md)
før regnskapsarbeid. Krav og lokal ERPNext-kode er undersøkt 2026-09-17, men norske
regnskapsfunksjoner er ennå ikke implementert eller verifisert med bilag.

Gjenbruk ERPNexts fakturaer, betalinger og hovedbok. Norsk kontoplan, MVA-regler,
eiertransaksjoner, saldogrupper og rapportmapping hører i denne appen. Avklar lisens for
kontoplan/kodelister før kopiering. SAF-T, kontrollspor, fakturanummerering og arkiv skal
inngå før ordinær bokføring tas i bruk; SAF-T er ikke en valgfri sluttfase.

Skattemelding, MVA-melding og SAF-T er forskjellige leveranser. Ikke lov direkte innsending
uten en verifisert integrasjon. Regler, satser og skjema må knyttes til riktig inntektsår.
Bruk fiktive bilag og separat testsite, test eksakte terskler og avstem eksport mot hovedbok.
Virksomhetstype og registreringsstatus må avklares før automatiske skatteregler velges.
Foretaksnavn, organisasjonsnummer, eier, bank og avgiftsstatus skal være konfigurasjon per
foretak, aldri hardkodet. Gjenbruk også ERPNexts prosjekt-, time- og
abonnementsfunksjoner der de dekker behovet. Støtte for andre bransjer skal være eksplisitt;
en generell ENK-modul betyr ikke at alle særregler allerede er dekket.
