# Fra push til produksjon

```
bench migrate i dev
   → push til main
      → GitHub Actions bygger og verifiserer ghcr.io/<eier>/erpnext-enk:v16-<sha>
         → du deployer bevisst
```

Kjør alltid `bench migrate` i dev før en commit som skal i produksjon. Bygget er ikke en deploy,
og en vellykket image-bygging erstatter ikke migrering mot dev-databasen.

Produksjon forutsettes å være en Docker Compose-stack av typen
[frappe_docker](https://github.com/frappe/frappe_docker) bygger opp: backend, frontend,
websocket, køarbeidere, scheduler, MariaDB og Redis, der app-containerne bruker samme image.

## Bygg ditt eget image

Workflowen `.github/workflows/publish.yml` kjører ved hver push til `main`. Den kjører de rene
testene, bygger et komplett bench-image med Frappe, ERPNext og denne appen og pusher det til
`ghcr.io/<eier>/erpnext-enk`, der `<eier>` er GitHub-kontoen eller organisasjonen som eier
repoet. En fork bygger derfor til sitt eget register uten endringer. Nye pakker i GHCR er
private som standard; gi serveren lesetilgang eller gjør pakken offentlig.

Vil du bygge uten GitHub Actions, bruk frappe_docker sin `images/layered/Containerfile` med
`apps.json` fra dette repoet som BuildKit-secret. Se frappe_docker sin dokumentasjon om egne
apper. Da mister du kildeverifiseringen workflowen gjør, beskrevet under.

## Hvorfor ikke automatisk oppdatering

Et nytt ERPNext-image krever `bench migrate` etterpå: Frappe må synkronisere DocTypes og kjøre
patcher mot databasen. Verktøy som Watchtower bytter bare containeren og starter den igjen.
Resultatet er ny kode mot et gammelt skjema, og det oppdager du typisk midt i noe viktig. De
ville dessuten byttet app-containerne i vilkårlig rekkefølge.

Produksjonsstacken skal derfor ikke ha automatisk image-oppdatering.

## Deploy

Vent til Actions-jobben har bestått, og kontroller commitene og `bench version` i
jobbsammendraget. Deretter, på serveren, i mappa med stackens compose-fil:

1. **Backup før noe røres:**
   `docker compose exec backend bench --site <site> backup --with-files`
2. **Pek på det nye imaget.** Sett den eksakte taggen `v16-<sha>` der compose-fila henter
   image og versjon, vanligvis i `.env`. Bruk aldri den flytende `v16`-taggen i produksjon.
3. **Hent og start:** `docker compose pull` og `docker compose up -d`. Kontroller med
   `docker compose config --images` og `docker inspect` at alle app-containerne kjører den nye
   taggen.
4. **Installer apper som mangler på sitet.** Første gang appen tas i bruk på et eksisterende
   site: `docker compose exec backend bench --site <site> install-app enk_norge`.
5. **Migrer:** `docker compose exec backend bench --site <site> migrate`
6. **Verifiser** at sitet svarer HTTP 200 og at `/api/method/ping` gir `pong`.

Feiler migreringen, ligger backupen fra steg 1 i `sites/<site>/private/backups/`. Rull tilbake
ved å sette forrige tagg og gjenopprette data med `bench --site <site> restore`.

Bruker du tjenestenavn og containernavn som avviker fra frappe_docker, tilpass kommandoene.
Det lønner seg å samle stegene i et eget deployskript for serveren din.

## Hva en build-versjon betyr

`v16-<sha>` bruker SHA-en til committen som trigget Actions-jobben. Jobben leser den
versjonerte `apps.json`, krever én ERPNext-oppføring og én `enk_norge`-oppføring, og erstatter
URL-en til appen med repoet som bygger, med et kortlevd GitHub-token i BuildKit-secreten. Så
henter den denne committen eksplisitt før den installerer appen og bygger assets. Tokenfila
opprettes under runnerens midlertidige katalog og sendes bare som BuildKit-secret. Tokenet gjør
at byggingen også virker når repoet er privat.

Frappe er låst til taggen `v16.34.0` og committen `c1f1e8ec3708750d7254f7f99d869ffb9886f19f`.
ERPNext er låst i `apps.json` til `v16.35.0` og committen
`12cd563fb9a79731f75ae2a45b1446a0a2dd9e74`. Før bygg henter jobben taggene fra de offisielle
GitHub-repoene med `git ls-remote` og krever at de fortsatt peker på disse committene. Under bygg
verifiseres den faktiske checkouten før Git-metadata fjernes. Tre filer i imaget inneholder
Frappe-, ERPNext- og appcommit, og jobben puller det pushete imaget og sammenligner dem maskinelt.
Feiler en sammenligning, feiler jobben. En oppgradering krever at alle disse pinnene endres
bevisst etter lokal verifisering.

`CACHE_BUST` er den samme SHA-en. Dette er nødvendig fordi BuildKit-secrets ikke inngår i
cache-nøkkelen; uten den kunne den cachede app-laget inneholde en eldre commit. Tokenet finnes
bare i runnerens midlertidige secret-fil under build og blir ikke lagret som build-arg, cache
eller image-lag.

`bench version` i Actions-sammendraget er en ekstra, menneskelesbar kontroll. Taggen `v16` er
flytende og er kun en bekvemmelighetspeker. Produksjon bruker alltid den eksakte
`v16-<sha>`-taggen.

## PDF bak en innloggingsproxy

Står sitet bak en proxy som krever innlogging, for eksempel Cloudflare Access, sperrer den også
serverens egne kall etter CSS når PDF-en lages. For ENK-fakturaer kan serveren derfor hente
statiske utskriftsressurser fra en intern origin, typisk frontend-containeren på stackens
interne nett. Frontend må svare for riktig site, for eksempel ved å sette site-headeren.
Konfigurasjonen er per site:

```bash
# Kjøres i backend-containerens bench.
bench --site <site> set-config enk_pdf_asset_origin http://<frontend-container>:8080
bench --site <site> clear-cache
```

Dette gjelder PDF-nedlasting av ENK-salgsfakturaer. Appen skriver om egne
`/assets/`-ressurser i utskrifts-HTML før PDF-generering. Offentlige lenker og
`host_name` endres ikke, og innloggingscookies videresendes ikke til intern origin.
Serverens innstilling styrer origin; klienten kan ikke velge den i PDF-kallet.

Kontroller at den interne frontend-adressen returnerer CSS med HTTP 200 fra backend,
at PDF-en har riktig stil, og at offentlig URL fortsatt krever innlogging. En PDF-header
alene beviser ikke at stilfilene ble hentet. Direkte kall til Frappes interne
`get_print(as_pdf=True)` og andre dokumenttyper går fortsatt gjennom standardflyten.
