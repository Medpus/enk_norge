# Utviklingsmiljø

Utvikling skjer på utviklingsmaskinen (devmaskin), ikke på Tower. Tower er deploy-mål.

## Oppsett

Frappe har en ferdig devcontainer i `frappe_docker`:

```bash
git clone https://github.com/frappe/frappe_docker
cd frappe_docker
cp -R devcontainer-example .devcontainer
cp -R development/vscode-example development/.vscode
```

Åpne mappa i VS Code og «Reopen in Container». Inne i containeren:

```bash
bench init --skip-redis-config-generation --frappe-branch version-16 frappe-bench
cd frappe-bench
bench set-config -g db_host mariadb
bench set-config -g redis_cache redis://redis-cache:6379
bench set-config -g redis_queue redis://redis-queue:6379
bench set-config -g redis_socketio redis://redis-queue:6379

bench new-site dev.localhost --mariadb-user-host-login-scope='%' --db-root-password 123 --admin-password admin
bench get-app --branch version-16 erpnext
bench get-app git@github.com:Medpus/enk_norge.git
bench --site dev.localhost install-app erpnext enk_norge
bench --site dev.localhost set-config developer_mode 1
bench start
```

Sitet svarer da på `http://dev.localhost:8000`.

> Denne oppskriften er hentet fra frappe_dockers egen dokumentasjon og er **ikke kjørt gjennom
> på nobara ennå**. Første gjennomkjøring bør rette opp det som eventuelt skurrer, og oppdatere
> denne fila.

## Hvorfor et eget site

Produksjonsdatabasen på Tower røres aldri under utvikling. Du jobber mot `dev.localhost` med
fiktive bilag, og endringene når produksjon først gjennom et image + `bench migrate`.

`developer_mode` må være på for at nye DocTypes skal skrives til disk i appen din i stedet for
bare å ligge i databasen.

## Testing før deploy

Kjør migreringen i dev før du ruller ut:

```bash
bench --site dev.localhost migrate
```

Det er her en ERPNext-oppgradering som brekker appen vår skal avsløres — ikke på Tower.
