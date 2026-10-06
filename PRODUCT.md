# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Eiere av norske enkeltpersonforetak som bruker ERPNext til daglig bokføring. De skal kunne starte
oppsettet selv, uten at foretakets personlige opplysninger er en del av kildekoden.

## Product Purpose

ENK Norge gir ERPNext et norsk, enklere inngangspunkt for oppsett og daglig arbeid. Suksess er at
brukeren kan opprette og kontrollere sitt eget foretak før fakturaer og kjøp føres.

## Positioning

Flaten samler norske ENK-avklaringer rundt ERPNexts eksisterende hovedbok og dokumenter, framfor å
bygge et parallelt regnskap.

## Operating Context

Brukeren arbeider i Frappe Desk på skrivebord og mobil. Oppstarten ber om foretaksidentitet,
adresse, telefon, bankkonto, første bokføringsdato, MVA-status og bekreftelse på historikk. Tidligere
regnskap krever avklart inngående balanse og første fakturanummer.

## Capabilities and Constraints

`enk_norge.setup.list_companies()` lister foretak og oppsettsstatus. `create_company(data)`
oppretter foretaket med data fra oppstartsflaten. Daglig oversikt samler lagrede kladder,
oppfølging, bankavstemming og avgrensede utkast for rapportering, saldogrupper og driftsmidler.
Salg og kjøp opprettes som ERPNext-kladd og vises i ENK-sidens egen bilagsvisning med
vedlegg, kontroll og bokføring. Brukeren skal ikke trenge ERPNexts skjemaer. Foretaksdata er alltid konfigurasjon per Company og blir aldri hardkodet.

## Evidence on Hand

Produktplanen ligger i `docs/enk-produktplan.md`. Fiktive, isolerte testflyter er dokumentert i
[implementering.md](docs/implementering.md).

## Product Principles

- La brukerens egne opplysninger bli fylt inn av brukeren, én gang per foretak.
- Vær tydelig på hva oppsettet oppretter og hva som fortsatt må avklares.
- Bruk ERPNexts dokumenter og kjente Desk-mønstre når de dekker oppgaven.
- Vis bare tall, rapporter og handlinger når deres datagrunnlag finnes.

## Accessibility & Inclusion

Oppsettet skal fungere med tastatur, ha tydelige etiketter og feilbeskjeder, og tilpasse seg
smale skjermer uten å skjule nødvendig informasjon.
