# ENK Norge

Norsk tilpasning av [ERPNext](https://github.com/frappe/erpnext) for enkeltpersonforetak.
Appen gir en egen arbeidsflate for daglig bokføring: oppstartsveiviser, kjøp og fakturaer,
betalinger, bankimport, norsk MVA, eiertransaksjoner, saldogrupper, årsgrunnlag og SAF-T.
ERPNext gjør selve bokføringen i bakgrunnen, så brukeren slipper ERPNexts egne skjemaer.

Konsulenttjenester og SaaS er de første brukstilfellene. Foretaksnavn, organisasjonsnummer,
bank og avgiftsstatus legges inn av brukeren per foretak og er aldri hardkodet.

## Status og ansvar

Versjon 0.1.0 er i produksjonsbruk med Frappe 16.34.0 og ERPNext 16.35.0. Regelsettet gjelder
inntektsåret 2026; nye år krever gjennomgang av satser og rapportkoder.

Appen er ikke revisorgodkjent. Skattemelding og MVA-melding leveres manuelt: appen lager
grunnlaget og lagrer kvitteringen, men sender ingenting til Skatteetaten. Du er selv ansvarlig
for regnskapet ditt. Les [verifisering og avgrensninger](docs/implementering.md) før du tar
appen i bruk; der står hva som er testet og hva som ikke er dekket, for eksempel lønn,
varelager og særnæringer.

## Kom i gang

Appen krever Frappe og ERPNext versjon 16 og Python 3.14. Byggene er låst til versjonene over.

### Prøv lokalt

Med Docker eller Podman setter ett skript opp en komplett bench med ERPNext og appen:

```bash
git clone https://github.com/Medpus/enk_norge.git
cd enk_norge
bash scripts/dev-setup.sh
bash scripts/dev.sh start
```

Åpne URL-en skriptet skriver ut og logg inn som `Administrator` / `admin`. Første gang tar
oppsettet 10 til 20 minutter. Se [utviklingsmiljøet](docs/utvikling.md) for detaljer, testsite
og tester.

### Installer på en eksisterende bench

```bash
bench get-app https://github.com/Medpus/enk_norge
bench new-site <site> --install-app erpnext --install-app enk_norge
```

Appen er laget for et nytt site der ENK-veiviseren gjør førstegangsoppsettet. Bruk et eget
site, ikke et som allerede har et ERPNext-oppsett. Scheduleren er av på nye sites; skru den på
i produksjon med `bench --site <site> enable-scheduler`.

### Produksjon med Docker

GitHub Actions bygger et komplett image med Frappe, ERPNext og appen ved hver push til `main`.
I en fork havner det automatisk i forkens eget register. Se [deploy](docs/deploy.md) for
bygging, utrulling og oppsett bak en innloggingsproxy, og [backup](docs/backup.md) for daglig
backup og kryptert kopi.

## Grunnregelen

**Dette er en Frappe-app ved siden av ERPNext, ikke en fork av ERPNext.**

ERPNext er en avhengighet vi peker på med et versjonsnummer. Skal vi gripe inn i deres logikk,
gjør vi det gjennom Frappes hooks: `doc_events`, `override_doctype_class`,
`override_whitelisted_methods` i `enk_norge/hooks.py`. Vi redigerer aldri filer under
`apps/erpnext/`.

Så lenge vi holder oss til vår egen app, oppgraderer vi ERPNext ved å endre
versjon i `apps.json` og kildepinnene i bygge-workflowen, bygge, teste og kjøre `bench migrate`.
Bygget verifiserer kildecommittene for Frappe og ERPNext. I det øyeblikket noen patcher
ERPNext-kode direkte, arver vi hele vedlikeholdsbyrden til et prosjekt på hundretusenvis av linjer.

## Hva som ligger hvor

```
enk_norge/
├── hooks.py          ← inngripen i ERPNext (doc_events, overrides, fixtures)
├── patches.txt       ← migrasjoner som kjøres av `bench migrate`
├── patches/
├── tests/            ← rene regeltester og integrasjonstester med fiktive foretak
└── enk_norge/        ← modulen «ENK Norge»: arbeidsflaten og sidene
apps.json             ← hvilke apper som bygges inn i imaget, og hvilken ERPNext-versjon
scripts/              ← dev-miljø og backup
docs/                 ← bruk, regelgrunnlag, utvikling, deploy og backup
```

## Tilpasninger som lages ved å klikke

Mye i ERPNext settes opp i grensesnittet: custom fields, print formats, workflows,
kontoplan-maler. De skal ikke bare klikkes inn i produksjon. Da finnes de bare der, og
forsvinner ved en gjenoppbygging.

Riktig løkke:

1. Klikk det på plass i dev-sitet.
2. Registrer doctypen i `fixtures` i `hooks.py`.
3. `bash scripts/dev.sh fixtures`. De havner som JSON i denne appen.
4. Commit. Nå følger de med imaget og legges inn av `bench migrate` i produksjon.

## Dokumentasjon

- [Kom i gang med ENK Norge](docs/bruk.md): eget oppsett, kjøp, faktura og kontroll av bilag.
- [Norske ENK-krav](docs/norske-enk-krav.md): bokføring, MVA, eiendeler, skattemelding og kilder,
  undersøkt 2026-09-17.
- [Utviklingsplan](docs/enk-produktplan.md): gjenbruk av ERPNext, enkel arbeidsflyt,
  integrasjoner og tester før reell bruk.
- [Implementering og verifisering](docs/implementering.md): testbevis og avgrensninger.
- [Utviklingsmiljø](docs/utvikling.md), [deploy](docs/deploy.md) og [backup](docs/backup.md).

Kontrollspor, fakturakrav, arkiv og SAF-T inngår i grunnlaget før ordinær bokføring.
Direkte innsending av skattemelding er en egen integrasjon.

## Bidra

Dokumentasjon, kommentarer og commit-meldinger skrives på norsk. Kode, DocType-navn og felt
er på engelsk der Frappe forventer det. Arbeidsregler og kjente feller står i
[AGENTS.md](AGENTS.md), som også er instruksen for kodeagenter. Bruk bare fiktive foretak og
bilag i tester og eksempler.

## Lisens

Appens kode er MIT-lisensiert, se [license.txt](license.txt). Det medleverte
[SAF-T-skjemaet](enk_norge/schemas/README.md) er publisert av Skatteetaten og beholder sin
opphavsrettsangivelse.
