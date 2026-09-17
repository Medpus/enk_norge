# Utviklingsmiljø

Kjøres på **devmaskin**, ikke på Tower. Tower er deploy-mål.

## Oppsett — én kommando

```bash
bash ~/git/janitor/hosts/devmaskin/scripts/enk-dev-setup.sh
```

Scriptet finner selv om du har docker eller podman, lager `~/frappe-dev/`, starter MariaDB og
Redis, initialiserer en bench på `version-16`, henter ERPNext, kloner denne appen, lager sitet
`dev.localhost` med begge apper installert, og skrur på `developer_mode`. Det er idempotent —
kjør det på nytt når som helst.

Første kjøring tar 10–20 minutter og laster ned noen GB.

> Verifisert ende-til-ende 2026-09-17 ved å kjøre hele oppsettet på Tower og rive det etterpå.

Slår ikke `dev.localhost` opp, legg den i hosts-fila:

```bash
echo '127.0.0.1 dev.localhost' | sudo tee -a /etc/hosts
```

## Daglig bruk

```bash
enk-dev.sh start      # starter alt, server på http://dev.localhost:8000
enk-dev.sh stop
enk-dev.sh status
enk-dev.sh logs       # følg bench-loggen
enk-dev.sh shell      # bash inne i benchen
enk-dev.sh bench ...  # vilkårlig bench-kommando
enk-dev.sh migrate
enk-dev.sh console    # python-konsoll mot dev-sitet
enk-dev.sh fixtures   # eksporter klikkede tilpasninger inn i appen
```

Innlogging: `Administrator` / `admin`. Miljøet lytter bare på `127.0.0.1`, og de trivielle
passordene er greie nettopp fordi det aldri eksponeres.

## Hvor arbeidskopien ligger

```
~/frappe-dev/development/frappe-bench/apps/enk_norge
```

**Det er denne du redigerer og pusher fra** — en vanlig klone med `origin` mot GitHub. Ikke lag
en egen klone et annet sted; da redigerer du noe benchen ikke kjører.

`bench start` har en filovervåker, så endringer i Python og JS slår inn uten omstart. Nye
DocTypes krever `developer_mode` (allerede satt) for å bli skrevet til disk i appen.

## Plass

Benchen med begge apper og containerne tar rundt 10 GiB. Nobara hadde 190 GiB ledig
2026-09-17, så det er god margin.

## Testing før deploy

```bash
enk-dev.sh migrate
```

Det er her en ERPNext-oppgradering som brekker appen vår skal avsløres. Aldri på Tower.
