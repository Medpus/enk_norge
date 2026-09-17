# ENK Norge

Gjenbrukbar norsk tilpasning av ERPNext for enkeltpersonforetak: kontoplan, MVA,
privatinnskudd og uttak, saldogrupper og SAF-T. Konsulenttjenester og SaaS er de første
brukstilfellene. Alt norsk bor her; ERPNext selv røres aldri.

## Grunnregelen

**Dette er en Frappe-app ved siden av ERPNext, ikke en fork av ERPNext.**

ERPNext er en avhengighet vi peker på med et versjonsnummer. Skal vi gripe inn i deres logikk,
gjør vi det gjennom Frappes hooks: `doc_events`, `override_doctype_class`,
`override_whitelisted_methods` i `enk_norge/hooks.py`. Vi redigerer aldri filer under
`apps/erpnext/`.

Grunnen er enkel: så lenge vi holder oss til vår egen app, oppgraderer vi ERPNext ved å endre
versjon i `apps.json`, bygge, teste og kjøre `bench migrate`. Bygge-workflowen leser `apps.json`
og verifiserer at ERPNext-grenen samsvarer med `FRAPPE_BRANCH`. I det øyeblikket noen patcher
ERPNext-kode direkte, arver vi hele vedlikeholdsbyrden til et prosjekt på hundretusenvis av linjer.

## Hva som ligger hvor

```
enk_norge/
├── hooks.py          ← inngripen i ERPNext (doc_events, overrides, fixtures)
├── patches.txt       ← migrasjoner som kjøres av `bench migrate`
├── patches/
└── enk_norge/        ← modulen «ENK Norge»: DocTypes, rapporter, sider
apps.json             ← hvilke apper som bygges inn i imaget, og hvilken ERPNext-gren
docs/utvikling.md     ← dev-miljø
docs/deploy.md        ← hvordan det havner i produksjon
```

Se [docs/utvikling.md](docs/utvikling.md) for faktisk dev-flyt på Nobara, arbeidskopien i
frappe-bench og kontrollkommandoene.

## Tilpasninger som lages ved å klikke

Mye i ERPNext settes opp i grensesnittet: custom fields, print formats, workflows,
kontoplan-maler. De skal **ikke** bare klikkes inn i produksjon. Da finnes de bare der, og
forsvinner ved en gjenoppbygging.

Riktig løkke:

1. Klikk det på plass i dev-sitet.
2. Registrer doctypen i `fixtures` i `hooks.py`.
3. `bench --site dev.localhost export-fixtures`. De havner som JSON i denne appen.
4. Commit. Nå følger de med imaget og legges inn av `bench migrate` i produksjon.

## Status

Skjelettet er generert med `bench new-app` fra `frappe/erpnext:v16.35.0`. Norske
regnskapsfunksjoner er ikke implementert ennå. Regelverket og ERPNexts dekning er undersøkt
2026-09-17:

- [Norske ENK-krav](docs/norske-enk-krav.md): bokføring, MVA, eiendeler, skattemelding og kilder.
- [Utviklingsplan](docs/enk-produktplan.md): gjenbruk av ERPNext, enkel arbeidsflyt,
  integrasjoner og tester før reell bruk.

Kontrollspor, fakturakrav, arkiv og SAF-T inngår i grunnlaget før ordinær bokføring.
Direkte innsending av skattemelding er en egen integrasjon. Se janitor-repoet,
`hosts/tower/fixes/erpnext-oppsett.md`, for driftsbakgrunnen.

## Lisens

MIT
