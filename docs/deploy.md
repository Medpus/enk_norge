# Fra push til produksjon

```
bench migrate i dev
   → push til main
      → GitHub Actions bygger og verifiserer ghcr.io/medpus/erpnext-enk:v16-<sha>
         → du deployer bevisst på Tower
```

Kjør alltid `bench migrate` i dev før en commit som skal til Tower. Bygget er ikke en deploy,
og en vellykket image-bygging erstatter ikke migrering mot dev-databasen.

## Hvorfor ikke Watchtower

De andre appene auto-oppdateres av Watchtower. **ERPNext gjør det ikke, med vilje.**

Et nytt ERPNext-image krever `bench migrate` etterpå: Frappe må synkronisere DocTypes og kjøre
patcher mot databasen. Watchtower bytter bare containeren og starter den igjen — resultatet er
ny kode mot et gammelt skjema, og det oppdager du typisk midt i noe viktig. Den ville dessuten
byttet seks containere i vilkårlig rekkefølge.

Stacken på Tower har derfor ingen `com.centurylinklabs.watchtower.enable`-label.

## Deploy

Etter at Actions-jobben har bestått commit-sjekken og `bench version` i jobbsammendraget:

```bash
# Første overgang fra offisielt frappe/erpnext-image:
bash ~/git/janitor/hosts/tower/scripts/erpnext-deploy.sh v16-<sha> ghcr.io/medpus/erpnext-enk

# Senere deployer, når .env allerede peker på ghcr.io/medpus/erpnext-enk:
bash ~/git/janitor/hosts/tower/scripts/erpnext-deploy.sh v16-<sha>
```

Scriptet gjør, i rekkefølge:

1. `bench backup --with-files` — full backup før noe røres.
2. Skriver ny tag i `/mnt/user/appdata/erpnext/.env`.
3. `docker compose pull` + `up -d`.
4. Installerer apper som finnes i imaget, men mangler på sitet.
5. `bench migrate` mot `erp.example.com`.
6. Verifiserer at sitet og API-et svarer, og sier fra hvis noe feilet.

Feiler migreringen, står backupen fra steg 1 i `sites/erp.example.com/private/backups/`.

## Hva en build-versjon betyr

`v16-<sha>` bruker SHA-en til committen som trigget Actions-jobben. Jobben leser den
versjonerte `apps.json`, erstatter bare privatappens URL med et kortlevd GitHub-token i
BuildKit-secreten, og henter så denne committen eksplisitt før den installerer appen og bygger
assets. En fil i imaget inneholder SHA-en, og jobben puller det pushete imaget og sammenligner
den maskinelt. Feiler sammenligningen, feiler jobben.

`CACHE_BUST` er den samme SHA-en. Dette er nødvendig fordi BuildKit-secrets ikke inngår i
cache-nøkkelen; uten den kunne den cachede app-laget inneholde en eldre commit. Tokenet finnes
bare i secret-mounten under build og blir ikke lagret som build-arg eller i imaget.

Frappe og ERPNext følger fortsatt `version-16` når imaget bygges. `bench version` i
Actions-sammendraget er den eksakte Frappe- og ERPNext-versjonen i dette imaget. Også taggen
`v16` er flytende og er kun en bekvemmelighetspeker. Produksjon bruker alltid den eksakte
`v16-<sha>`-taggen i `.env`.
