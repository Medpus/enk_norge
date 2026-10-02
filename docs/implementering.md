# Implementering og verifisering

ENK Norge gir norske enkeltpersonforetak en oppstartsveiviser og en daglig flate for
kjøp, fakturaer, betalinger og regnskapskontroll. Brukeren fyller selv ut foretaksopplysninger,
bank og fakturadata. Utviklingen bruker fiktive foretak og bilag.

## Omfang

Regelsettet gjelder 2026. Nye inntektsår krever gjennomgang av satser og rapportkoder.
Betaling av en eksisterende 2026-faktura og periodisering av en dokumentert
2026-avtale kan fortsette i 2027. Det åpner ikke generell bokføring med antatte 2027-regler.

Appen bruker ERPNexts fakturaer, hovedbok, betalinger og timegrunnlag. Egen kode håndterer
norske avgiftsvalg, dokumentasjon, eiertransaksjoner, saldogrupper og rapportgrunnlag.
Ingen filer i ERPNext eller Frappe endres.

| Arbeidsflyt | Implementasjon og kontroll |
|---|---|
| Oppstart | Veiviser med foretak, adresse, bank, registreringsstatus og regnskapshistorikk. Foretaksdata er konfigurasjon. Eieren får rollene som trengs for kunder og leverandører. |
| Arbeidsflate | ENK-siden er eneste flate for daglig bruk: bilagsliste med søk og filtre, bilagsvisning med bokføring, vedlegg, PDF, betaling og kreditnota, og egne skjemaer for kunde, leverandør, timer og MVA-status. Sidemenyen viser bare ENK-sidene, og ERPNexts lagerveileder og versjonsvarsler er slått av. |
| Kjøp og salg | Bilagsvedlegg, privat betaling, fradragsfordeling, fakturaserie, levering, kreditnota og periodestenging. |
| MVA | Norske satser, registreringsgrense, registreringsovergang, utenlandske tjenester og rapportgrunnlag med kildebilag. |
| Bank | CSV-import med bevart privat kildefil, delbetaling, gebyr, valuta og duplikatvern. Tilknyttede valutaposteringer bokføres og reverseres sammen med betalingen. |
| Eksterne oppgjør | Avstemming av eksisterende fakturaer og kreditnotaer mot nettooppgjør og dokumenterte gebyrer i NOK. |
| Konsulenttimer | Timer føres per kunde i ERPNext Timesheet og faktureres samlet med bevart timekobling og vern mot dobbeltfakturering. |
| Abonnement | Dokumentert tjenesteperiode, utsatt inntekt, periodiseringsutkast og full refusjon. Neste periode lages fra forrige bokførte faktura. ERPNexts Subscription brukes ikke i flaten, fordi den lager fakturakladder automatisk. |
| Driftsmidler | Regelmotoren avgjør aktivering. Aktiverte kjøp legges i saldogruppe a eller d fra kjøpet, avskrivning og avgrenset salg/uttak med avstemming av bokført verdi og skattesaldo. |
| Årsoppgjør | Hovedbok fordelt på rapportkoder, skatteavstemming, saldoberegning og grunnlag for beregnet personinntekt. |
| Rapportarkiv | Versjoner av MVA- og årsgrunnlag, avstemming og brukerens innleveringskvittering. MVA-siden dekker ordinær melding og omvendt avgiftsplikt for uregistrerte. |
| SAF-T | Eksport mot Skatteetatens offisielle XSD 1.40 og avstemming mot hovedbok. |

## Testmiljø og bevis

Integrasjonstestene kjører bare på `test.localhost` og tilbakefører databasetransaksjonene.
Nettlesertestene bruker egne sites med fiktive foretak: `onboarding.localhost`, `dev.localhost` og
`fersk.localhost`, som ble satt opp fra tomt med veiviseren.
Testene omfatter blant annet rettigheter mellom foretak, endrede kildebilag, duplikater,
stengte perioder og avstemming mot hovedbok. Rene beregningstester kjører også i CI.

Veiviseren er gjennomført fra tomt site. På desktop og mobil er påkrevde felt,
fullføring og åpning av ENK-siden kontrollert. Avslutningen er kjørt på nytt fra et tomt
`dev.localhost`: `desktop:home_page` ble `enk-norge`, `setup_complete` ble satt, og Frappes
egen bootrutine leverte ENK-siden som startside. Systemspråket ble `nb`. En faktisk faktura-PDF er hentet og
verifisert som PDF. Full backup av testsite er gjenopprettet på isolert site; database,
vedlegg og signert regnskapsutkast er kontrollert etter gjenoppretting.

Arbeidsflaten er gått gjennom i nettleseren 2026-10-01, på PC og mobil, som eierbruker uten
ERPNext-kunnskap. Et nytt `fersk.localhost` ble satt opp med veiviseren. Fakturaen gikk fra ny kunde
via kladd, bokføring og PDF til registrert innbetaling. Et AI-abonnement fra en leverandør i USA ble
ført med kvitteringsbilde fra mobil, bokført og betalt privat. En Mac til 35 000 kr ble aktivert
automatisk og lagt i saldogruppe a med 10 500 kr i avskrivning. Timer ble ført og fakturert samlet.
Abonnementsfakturaen fikk neste periode og inntektsføring. En Stripe-utbetaling med gebyr gjorde
fakturaen betalt. Omvendt avgiftsplikt ble beregnet, postert, beregnet på nytt og markert levert med
kvittering. Overgangen til MVA-registrert ga ordinær MVA-melding. Årsrapporten ble bygget med
skattemessig avskrivning, og fakturaen fra det nye sitet ble hentet som PDF og kontrollert visuelt.

Etter tilbakemeldinger fra bruk i produksjon ble dette lagt til og prøvd i nettleseren
2026-10-02, på PC og mobil, som eierbruker på `fersk.localhost` og `dev.localhost`. Fakturaen
fikk flere linjer, fakturanummer fra 1001 og et norsk oppsett med betalingsinformasjon og
foretaksopplysninger fast nederst, også over flere sider. En faktura på 40 linjer ga tre sider
med bunnteksten på hver. Kladder for salg og kjøp kan redigeres og beholder nummeret, og
redigert forfallsdato lagres. Kortkjøp betales i samme steg som bokføringen, både med egne
penger og fra foretakskontoen. Datoer vises og skrives som dd.mm.åååå, og beløp rundes ikke
av til hele kroner. Oversikten viser inntekter og kostnader per måned, kostnader per type,
klikkbare tall, MVA-grensen siste 12 måneder og forfalte fakturaer. Kunder, leverandører og
foretakets kontaktinformasjon kan rettes.

Tower har daglig fullbackup og Nobara mottar en kryptert kopi. Begge kjøringene er
prøvd. Se [backup og gjenoppretting](backup.md) for tidspunkt, bevaring og nøkkelbehov.
Gjenoppretting i produksjon er ikke brukt som test.

Sluttkontroll lokalt:

- Samlet suite: 185 av 185 testtilfeller besto uten hoppede tester. De enkle flytene kjører
  som en vanlig eierbruker, ikke som Administrator, så manglende roller og rettigheter synes.
- Rene Python-tester uten Frappe: 61 besto, 24 integrasjonstester ble eksplisitt hoppet over.
- `ruff check`, Python-kompilering, JavaScript-syntaks og `git diff --check` besto.
- `bench migrate` på `dev.localhost`, `test.localhost` og `onboarding.localhost` besto.
- PDF-rettelsen har seks egne tester. Samlet kontroll av PDF, bilagsflyt og rettigheter
  besto med 32 av 32 tester, fulgt av ny migrering på dev.
- Browseren kjører med `nb-NO`. Årsrapporten viser korrekte NOK-beløp; den trenger ingen
  innsprøytet locale-fallback.

PDF-nedlastingen er også prøvd via ERPNexts HTTP-endepunkt med en bokført, fiktiv faktura.
Den ga HTTP 200 og én A4-side. Visuell kontroll bekreftet stilfiler, tabell, datoer og
beløpet `kr 1.500,00`. Testen bruker intern ressursadresse slik produksjon trenger bak Access.

Saldogruppedialogen er også kjørt mot backend i nettleseren: et fiktivt aktivert kjøp på
1 200 kroner ga en saldogruppe med riktig kildebilag og 360 kroner i avskrivning.
Årsrapporten og knappen for avskrivning opprettet deretter et signert journalutkast på
360 kroner. Driftsmiddelavgang er integrasjonstestet i backend; dialogen er kontrollert
visuelt, men det er ikke opprettet avgang gjennom nettleseren.

[CI-kjøring 35282575671](https://github.com/Medpus/enk_norge/actions/runs/35282575671)
besto for `54b4f98a4a5f19301b9698765f49c9936f2baaf8`. Den kjørte de rene testene,
kontrollerte wheel-innholdet, bygget og publiserte imaget, og verifiserte alle tre
kildecommittene i det nedlastede imaget.

## Produksjon

Verifisert på Tower 2026-09-18: alle seks appcontainere kjører
`ghcr.io/medpus/erpnext-enk:v16-54b4f98a4a5f19301b9698765f49c9936f2baaf8`.
Installerte versjoner er Frappe 16.34.0, ERPNext 16.35.0 og ENK Norge 0.1.0.
Migreringen besto, intern ping ga HTTP 200, og scheduleren hadde to workers.
Offentlig URL ga HTTP 302 til Cloudflare Access med `www-authenticate`.

Full backup før utrulling har prefikset `20260918_041453-erp_example_com` i
sitets `private/backups/`: database, offentlige og private filer samt site-konfigurasjon.
Tidsstempelet er backupens faktiske filnavn, ikke en angivelse av norsk lokaltid.

PDF-konfigurasjonen bruker `http://erpnext-frontend:8080` for statiske ressurser.
En utskrift av DocType-metadata hentet intern CSS med HTTP 200 og ga en PDF på
41 217 byte. Siden ble rendret og kontrollert visuelt med stil, tabeller og sidefot.
Dette prøver ressursveien i produksjon; selve fakturanedlastingen er prøvd på testsite.
Det er ikke opprettet testforetak eller bilag i produksjon.

Administrator-kontoen er aktiv, og ENK-siden og veiviserens filer er installert.
Company, Sales Invoice, Purchase Invoice og Journal Entry hadde alle null poster etter
kontrollen. Brukeren fullfører oppsettet selv etter [bruksveiledningen](bruk.md).

## Avgrensninger

- Skattemelding og MVA-melding leveres manuelt. Appen gir grunnlag og lagrer kvittering;
  den har ingen verifisert direkteinnsending til Skatteetaten.
- Bankkobling og EHF krever egne integrasjoner. Bankimporten bruker et eget dokumentert
  CSV-format, ikke en norsk banks eksportformat. Import fra en norsk bank venter på en
  eksempelfil fra banken. Bankavstemming skjer fortsatt i ERPNexts eget verktøy.
- Salg gjennom Stripe forutsetter en bokført faktura per salg. Mange små abonnementssalg
  direkte til forbrukere er ikke tilpasset ennå.
- Lønn, varelager, kassasalg, særnæringer og salg av digitale tjenester til utenlandske
  privatkunder er ikke dekket av første regelsett. Ustøttede bokføringsveier sperres for ENK-foretak.
- Driftsmiddelsalg er begrenset til dokumentert, allerede betalt salg med eksternt
  salgsdokument før MVA-registrering. Salget inngår i kontrollen av registreringsgrensen.
  MVA-pliktig driftsmiddelsalg og unntatt aktivitet krever videre arbeid.
- Oppgjørsgebyrer i den enkle bankflyten forutsetter at gebyret ikke har fradragsberettiget
  MVA. Avgiftspliktig leverandørgebyr føres som eget kjøp med bilag.
- Tolvmånederskontrollen undersøker også tidligere grensepasseringer ved tilbakedatering.
  Inklusjon av samme kalenderdato året før må avklares før regelen utvides til senere år.
- Årsgrunnlaget må gjennomgås sammen med innehaverens øvrige opplysninger. Rapportkodene
  og skatteavstemmingen er underlag, ikke en ferdig innsendt personlig skattemelding.
