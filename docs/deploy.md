# Fra push til produksjon

```
push til main
   → GitHub Actions bygger ghcr.io/medpus/erpnext-enk:v16-<sha>
      → du deployer bevisst på Tower
```

## Hvorfor ikke Watchtower

De andre appene auto-oppdateres av Watchtower. **ERPNext gjør det ikke, med vilje.**

Et nytt ERPNext-image krever `bench migrate` etterpå: Frappe må synkronisere DocTypes og kjøre
patcher mot databasen. Watchtower bytter bare containeren og starter den igjen — resultatet er
ny kode mot et gammelt skjema, og det oppdager du typisk midt i noe viktig. Den ville dessuten
byttet seks containere i vilkårlig rekkefølge.

Stacken på Tower har derfor ingen `com.centurylinklabs.watchtower.enable`-label.

## Deploy

På Tower:

```bash
bash ~/git/janitor/hosts/tower/scripts/erpnext-deploy.sh v16-<sha>
```

Scriptet gjør, i rekkefølge:

1. `bench backup --with-files` — full backup før noe røres.
2. Skriver ny tag i `/mnt/user/appdata/erpnext/.env`.
3. `docker compose pull` + `up -d`.
4. `bench migrate` mot `erp.example.com`.
5. Verifiserer at sitet svarer, og sier fra hvis noe feilet.

Feiler migreringen, står backupen fra steg 1 i `sites/erp.example.com/private/backups/`.

## Hvilken ERPNext-versjon havnet i imaget

`apps.json` peker på **grenen** `version-16`, ikke en tagg, så det eksakte innholdet avgjøres
når CI bygger. Byggejobben skriver derfor `bench version` inn i sitt eget sammendrag i GitHub
Actions. Det er fasiten for hva en gitt image-tag inneholder.

Produksjon pinner alltid en eksakt tag (`v16-<sha>`) i `.env`. Det flytende ligger i byggingen,
det faste i det som er rullet ut.
