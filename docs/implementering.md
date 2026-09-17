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
| Oppstart | Veiviser med foretak, adresse, bank, registreringsstatus og regnskapshistorikk. Foretaksdata er konfigurasjon. |
| Kjøp og salg | Bilagsvedlegg, privat betaling, fradragsfordeling, fakturaserie, levering, kreditnota og periodestenging. |
| MVA | Norske satser, registreringsgrense, registreringsovergang, utenlandske tjenester og rapportgrunnlag med kildebilag. |
| Bank | CSV-import med bevart privat kildefil, delbetaling, gebyr, valuta og duplikatvern. Tilknyttede valutaposteringer bokføres og reverseres sammen med betalingen. |
| Eksterne oppgjør | Avstemming av eksisterende fakturaer og kreditnotaer mot nettooppgjør og dokumenterte gebyrer i NOK. |
| Konsulenttimer | Fakturautkast fra ERPNext Timesheet med bevart timekobling og vern mot dobbeltfakturering. |
| Abonnement | Dokumentert tjenesteperiode, utsatt inntekt, periodiseringsutkast og full refusjon. Fakturaer utstedes ikke automatisk. |
| Driftsmidler | Dokumenterte anskaffelser, saldogruppe a og d, avskrivning og avgrenset salg/uttak med avstemming av bokført verdi og skattesaldo. |
| Årsoppgjør | Hovedbok fordelt på rapportkoder, skatteavstemming, saldoberegning og grunnlag for beregnet personinntekt. |
| Rapportarkiv | Versjoner av MVA- og årsgrunnlag, avstemming og brukerens innleveringskvittering. |
| SAF-T | Eksport mot Skatteetatens offisielle XSD 1.40 og avstemming mot hovedbok. |

## Testmiljø og bevis

Integrasjonstestene kjører bare på `test.localhost` og tilbakefører databasetransaksjonene.
Nettlesertestene bruker `onboarding.localhost`, et eget site med fiktivt foretak.
Testene omfatter blant annet rettigheter mellom foretak, endrede kildebilag, duplikater,
stengte perioder og avstemming mot hovedbok. Rene beregningstester kjører også i CI.

Veiviseren er gjennomført fra tomt site. På desktop og mobil er påkrevde felt,
fullføring og åpning av ENK-siden kontrollert. En faktisk faktura-PDF er hentet og
verifisert som PDF. Full backup av testsite er gjenopprettet på isolert site; database,
vedlegg og signert regnskapsutkast er kontrollert etter gjenoppretting.

Tower har daglig fullbackup og Nobara mottar en kryptert kopi. Begge kjøringene er
prøvd. Se [backup og gjenoppretting](backup.md) for tidspunkt, bevaring og nøkkelbehov.
Gjenoppretting i produksjon er ikke brukt som test.

Sluttkontroll lokalt:

- Samlet suite: 156 av 156 testtilfeller besto uten hoppede tester. Abonnementsflyten
  er i tillegg kontrollert fra opprettelse med start i dag til neste sammenhengende periode.
- Rene Python-tester uten Frappe: 61 besto, 24 integrasjonstester ble eksplisitt hoppet over.
- `ruff check`, Python-kompilering, JavaScript-syntaks og `git diff --check` besto.
- `bench migrate` på `dev.localhost`, `test.localhost` og `onboarding.localhost` besto.
- Browseren kjører med `nb-NO`. Årsrapporten viser korrekte NOK-beløp; den trenger ingen
  innsprøytet locale-fallback.

Saldogruppedialogen er også kjørt mot backend i nettleseren: et fiktivt aktivert kjøp på
1 200 kroner ga en saldogruppe med riktig kildebilag og 360 kroner i avskrivning.
Årsrapporten og knappen for avskrivning opprettet deretter et signert journalutkast på
360 kroner. Driftsmiddelavgang er integrasjonstestet i backend; dialogen er kontrollert
visuelt, men det er ikke opprettet avgang gjennom nettleseren.

CI-bygget og produksjonsverifiseringen føres her når de er fullført. Lokale testresultater
alene betyr ikke at en versjon er satt i produksjon.

## Avgrensninger

- Skattemelding og MVA-melding leveres manuelt. Appen gir grunnlag og lagrer kvittering;
  den har ingen verifisert direkteinnsending til Skatteetaten.
- Bankkobling og EHF krever egne integrasjoner. Bankimporten bruker dokumentert CSV-format.
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
