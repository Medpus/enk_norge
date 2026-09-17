# Enkel ENK-drift med ERPNext

Beslutningsgrunnlag undersøkt 2026-09-17. Planen beskriver kravene og den opprinnelige
utviklingsrekkefølgen. Gjeldende leveransestatus og testbevis står i
[implementering og verifisering](implementering.md). Regelgrunnlag og kilder ligger i
[norske ENK-krav](norske-enk-krav.md).

Målet er at en ENK-innehaver skal kunne registrere et kjøp, fakturere en kunde, kontrollere bank og
avslutte året uten å måtte kunne ERPNexts interne begreper. Regnskapet skal samtidig være
sporbart og kunne kontrolleres. En enkel flate må bygge på korrekt bokføring.

Modulen skal være gjenbrukbar for norske ENK. Første bruker har opprettet ENK for
konsulenttjenester til bedrifter, familie og venner, samt SaaS-prosjekter.
Disse brukes som prøvetilfeller, ikke som hardkodede valg. Foretak, eier, bank,
registreringer og produkter er konfigurasjon per Company. Felles regler og tester skal
fungere med flere fiktive foretak uten at data eller avgiftsstatus blandes.

En felles norsk kjerne kan bygges først, med uttrykkelig støtte for bestemte aktiviteter.
Det er ikke nødvendig å bygge alle særnæringer, lønn og kassasystem samtidig for å unngå
personspesifikk kode.

## Hva som finnes, og hva vi må bygge

Kartleggingen gjelder lokal ERPNext 16.35.0, revisjon `12cd563`, og enk_norge ved
`22d8089`. Koden er lest, men norske regnskapsscenarioer er ikke kjørt. Dokumenterte
standardfunksjoner er ikke det samme som verifisert norsk etterlevelse.

| Behov | ERPNext har | Arbeid i enk_norge |
|---|---|---|
| Salg og kjøp | Sales Invoice, Purchase Invoice, hovedbok og reskontro | Norske standardvalg, avgiftsregler, fakturakrav og enklere inngang |
| Betalinger | Payment Entry, delbetaling og allokering | Norske arbeidsflyter og eiertransaksjoner |
| Konsulentarbeid | Project, Timesheet og fakturering fra timer | Enkel flyt for timepris/fastpris, leveringsperiode og kundetype |
| Abonnement | Subscription og periodisering av inntekt | Norske avgiftsvalg, eksterne salgsdata og avstemming av oppgjør |
| Bank | Bank Transaction, filimport og avstemmingsverktøy | Bankens konkrete format, kontroll av duplikater og senere bankkobling |
| Eiendeler | Asset, Asset Category og avskrivningsposteringer | Norske saldogrupper, skatteverdier, salg/uttak og årsoppgjør |
| Periodestenging | Accounting Period, frys til dato og Period Closing Voucher | Avslutningsrutine og kontroll av relevante posteringstyper |
| Kontrollspor | Versjonslogg og valgfri Immutable Ledger | Rettigheter, låst fakturaserie, bevarte bilag og test av rettinger |
| Norsk kontoplan | Ingen norsk mal funnet | Avgrenset, lisensavklart kontoplan med rapportkoblinger |
| Norsk MVA | Oppsettet inneholder Norway VAT 25% og 12% | Komplett relevant oppsett, fradragsrett, terskler, koder og meldingsgrunnlag |
| Norsk språk | Delvis bokmålsoversettelse | Norsk tekst for daglige ENK-oppgaver |
| SAF-T | Ingen norsk eksport funnet | Eksport, offisiell skjemavalidering og avstemming |
| Skattemelding | Ingen norsk funksjon funnet | Årsoppgjørsgrunnlag først, separat innsending senere |

Standardfunksjonene er dokumentert i
[Sales Invoice](https://docs.frappe.io/erpnext/sales-invoice),
[Purchase Invoice](https://docs.frappe.io/erpnext/purchase-invoice),
[Payment Entry](https://docs.frappe.io/erpnext/payment-entry) og
[Banking](https://docs.frappe.io/erpnext/banking-in-erpnext).
For konsulent- og SaaS-flyt finnes også
[Timesheet](https://docs.frappe.io/erpnext/timesheets),
[Subscription](https://docs.frappe.io/erpnext/subscription) og
[Deferred Revenue](https://docs.frappe.io/erpnext/deferred-revenue).
Dette bekreftes av lokal
`erpnext/projects/doctype/timesheet/timesheet.py`,
`erpnext/accounts/doctype/subscription/subscription.py` og
`erpnext/accounts/deferred_revenue.py`.

Et avgrenset søk etter offentlig norsk ERPNext-/Frappe-lokalisering fant ingen kandidat
som vi kunne bekrefte som vedlikeholdt og kompatibel med v16. Dette beviser ikke at ingen
finnes. Planen avhenger derfor ikke av et ukjent tillegg.

### Hvor funnene kan etterprøves

Stiene under er relative til `~/frappe-dev/development/frappe-bench/apps/erpnext/`:

- `erpnext/accounts/doctype/sales_invoice/sales_invoice.py`
- `erpnext/accounts/doctype/purchase_invoice/purchase_invoice.py`
- `erpnext/accounts/doctype/payment_entry/payment_entry.py`
- `erpnext/accounts/doctype/bank_statement_import/bank_statement_import.py`
- `erpnext/accounts/doctype/bank_reconciliation_tool/bank_reconciliation_tool.py`
- `erpnext/assets/doctype/asset/asset.py` og `depreciation.py` i samme mappe
- `erpnext/accounts/general_ledger.py`
- `erpnext/accounts/doctype/accounting_period/accounting_period.py`
- `erpnext/accounts/doctype/account/chart_of_accounts/`
- `erpnext/setup/setup_wizard/data/country_wise_tax.json`
- `erpnext/locale/nb.po`

Frappe-endringsloggen implementeres blant annet i `apps/frappe/frappe/model/document.py`.
Alle disse filene er kun referanser. Vi endrer dem ikke.

## Fiken som produktreferanse

Det nyttige å hente fra Fiken er arbeidsflyten: kvittering inn, forståelig kategori,
kontroll mot banken og en veiviser fram til levert rapportering. Fiken dokumenterer
bankfunksjoner og direkte levering av MVA og ENK-skattemelding.
[Fiken bank](https://hjelp.fiken.no/tema/bank),
[Fiken Altinn-integrasjon](https://fiken.no/integrasjoner/altinn),
[Fiken ENK-skattemelding](https://webinar.fiken.no/skattemelding-for-enkeltpersonforetak).

Arbeidsflyten må prøves med representative bilagstyper, inkludert disse:

| Oppgave | Hva brukeren gjør | Hva systemet håndterer |
|---|---|---|
| Registrer kjøp | Legger inn kvittering og bekrefter formål og betaling | Leverandør, konto, MVA-vurdering, duplikatsjekk og bilagskobling |
| Send faktura | Velger kunde, beskriver leveranse og pris | Nummer, avgiftsstatus, pliktige felt og bokføring |
| Betalt privat | Velger at kjøpet ble betalt med egne penger | Eierkonto og refusjon uten dobbel kostnad |
| Kontroller bank | Bekrefter foreslåtte treff og løser avvik | Bilagskobling, delbetaling, gebyr og valutaavvik |
| Registrer utstyr | Oppgir kjøp, bruk og forventet levetid | Aktivering, saldogruppe og årsberegning |
| Gjør opp MVA | Kontrollerer avvik og meldingsgrunnlag | Avstemming mot hovedbok og bevaring av rapportversjon |
| Avslutt året | Går gjennom mangler og godkjenner grunnlaget | Årsrapporter, skattejusteringer og tall til skattemeldingen |

Forsiden bør prioritere manglende bilag, bankavvik og frister. Vis omsetning, resultat,
bankbeholdning og anslått skatt/MVA hver for seg. Penger på konto må ikke presenteres
som penger tilgjengelig til privat bruk.

Dette er funksjonelle forslag, ikke et vedtatt visuelt design. Før UI bygges avklares
mobilbruk, bilagsmengde og vanligste oppgaver. Mobilopplasting, tastaturnavigasjon,
norske tall/datoer og tydelig feilretting inngår i akseptansekriteriene.

OCR kan foreslå dato, beløp og leverandør. Regelkode bestemmer beregningen, og brukeren
bekrefter usikre klassifiseringer. Automatisk bokføring krever avgrensede, testede regler.
En språkmodell skal ikke avgjøre fradragsrett eller MVA-behandling uten kontroll.

## Arkitektur og datagrunnlag

### Konsulentarbeid og abonnementer

Bruk prosjekt og timer der kunden betaler per time, og vanlig fakturalinje ved fastpris.
Flere prosjekter i samme ENK skal kunne vises separat uten å bli egne juridiske foretak.

Abonnementer trenger kobling mellom produkt, avtale, tjenesteperiode, faktura og oppgjør.
Gjenbruk Subscription og Deferred Revenue der de passer. Dersom SaaS-plattformen allerede
utsteder fakturaer, må én kilde eie faktureringen. Import skal ikke opprette en ny faktura
for et salg som allerede er fakturert.

En betalingsutbetaling kan inneholde mange salg og trekk. Før brutto salg, avgift,
refusjoner, gebyrer og valutaeffekter separat, og avstem nettoutbetalingen gjennom en
mellomkonto. Eksterne hendelses- og oppgjørsidentifikatorer hindrer dobbeltføring ved
gjentatt import. Ved faktisk videresalg gjennom en annen selger følger føringen avtalen;
sluttkundens kjøp må ikke automatisk behandles som ENK-ets eget direktesalg.

Kundetype, kundeland og hvem som er selger styrer avgiftsvurderingen. Utenlandsk
forbrukersalg skal ha eksplisitt støttet behandling eller en synlig avklaring før det
automatiseres. Se [SaaS-kravene](norske-enk-krav.md#konsulenttjenester-og-saas).

### Felles norsk grunnlag

Gjenbruk ERPNexts standarddokumenter og hovedbok. Nye dokumenter i enk_norge skal bare
lagre norsk tilleggsgrunnlag, for eksempel avgiftsregistrering, saldogrupper og
rapportversjoner. Unngå et parallelt regnskap som kan komme ut av takt med ERPNext.
Nye dokumenttyper som kan føre regnskap må også omfattes av periodelåsing, blant annet
gjennom `period_closing_doctypes` der ERPNext krever det.

Nødvendige data utover vanlig bilagsføring:

- Registreringer, virkningstidspunkt, rapporteringsperioder og støttede transaksjonstyper.
- Kobling fra konto til norsk rapportering, fra avgiftskode til SAF-T/MVA-melding,
  og fra årsoppgjør til næringsspesifikasjon. Dette er forskjellige koblinger.
- Næringsbruk, fradragsberettiget MVA og skattemessig fradrag som separate vurderinger.
- Leveringsdato, bilagsdato, bokføringsdato og betalingsdato der de er forskjellige.
- Saldogruppe og inngangsverdi med kildebilag og tidligere avskrivninger.
- Originalrapport, innsendingsstatus, ekstern kvittering og senere korreksjoner.

Beregn med fast desimalpresisjon, dokumentert avrunding og satser med gyldighetsdato.
En historisk rapport må kunne gjenskapes selv om neste års regler endres.

Kontoplanen må kunne rapportere riktig, men NS 4102 er ikke en fritt kopierbar datasamling.
Standard Norge beskriver rettigheter til bruk og kopiering. Skatteetatens SAF-T-repo
begrenser bruken av standardkontokodene til SAF-T-mapping. Avklar lisens eller velg et
lovlig grunnlag før en full mal legges i MIT-repoet.
[Standard Norge: kontoplan](https://standard.no/fagomrader/kontoplan-for-regnskap/),
[bruk og kopiering](https://standard.no/standarder/hjelp/opphavsrett/bruk-og-kopiering/),
[SAF-T-repoets bruksvilkår](https://github.com/Skatteetaten/saf-t).

## Innsending til myndighetene

| Leveranse | Første støttede fremgangsmåte | Senere automatisering |
|---|---|---|
| MVA-melding | Avstemt kode-/beløpsrapport og levering i Skatteetatens løsning | Validering og innsending med ekstern kvittering |
| Skattemelding/næringsspesifikasjon | Årsoppgjør med feltmapping, web-levering der ENK-et kan bruke den | Leverandørintegrasjon for aktuelt inntektsår |
| SAF-T | Validert regnskapsuttrekk til kontroll/forespørsel | Forbedringer av eksport- og kontrollflyten |

Direkte MVA-innsending er dokumentert som ID-porten-autentisering, validering, oppretting
av instans i Altinn 3, opplasting, fullføring og henting av tilbakemeldinger. Skatteetaten
må gi tilgang til validerings-API-et. Vi må skille ordinær melding fra meldingen for
omvendt avgiftsplikt for uregistrerte.
[Offisiell API-prosess](https://skatteetaten.github.io/mva-meldingen/documentation/api/),
[tilgang til validering](https://skatteetaten.github.io/api-dokumentasjon/api/mvameldingvalidering).

For skattemeldingen gir Skatteetaten leverandørtilgang til spesifikasjoner og integrasjon.
Den åpne repoen inneholder også historisk materiale. Den dokumenterer ikke alene at vår
app har produksjonstilgang eller støtter et bestemt inntektsår.
[Skatteetatens skattemeldingsrepo](https://github.com/Skatteetaten/skattemeldingen).

Skatteetatens overgangsveiledning for 2026 presiserer at validering og innsending av
skattemeldingen fortsatt bruker ID-porten. Systembruker via Maskinporten støttes for
enkelte henteoperasjoner for inntektsåret 2025. MVA-innsending bruker også ID-porten i
2026. Generell støtte for Altinn-systembruker betyr derfor ikke at innsending kan
automatiseres uten personlig autentisering. Kontrakten for inntektsåret 2026, som leveres
i 2027, må kontrolleres før implementering.
[Skatteetaten: Overgangen til Altinn 3](https://www.skatteetaten.no/samarbeidspartnere/sluttbrukersystemer/sbs-nyheter/nyttig-a-vite-om-overgangen-fra-altinn-2-til-altinn-3-for-de-moderniserte-losningene-mva-og-skattemelding/)

Tilgangspakker og delegering må verifiseres for den enkelte tjenesten. Maskinporten-tilgang
alene gir ikke tilgang til Skatteetatens API-er. Integrasjonen trenger testmiljø,
rettigheter, sikker tokenhåndtering og håndtering av tidsavbrudd. Ikke merk en melding
som levert før ekstern status/kvittering bekrefter det.
[Altinn: Systembruker](https://docs.altinn.studio/nb/authorization/getting-started/systemuser/)

Eksport til et eksternt årsoppgjørssystem kan være et alternativ. Det er først en reell
løsning når mottakersystemet har dokumentert import, støtter ENK og er testet med våre
data. Fikens API eller støtte for SAF-T hos en leverandør er ikke i seg selv bevis på at
ERPNext kan levere et komplett årsoppgjør gjennom den tjenesten.

Bankkobling og EHF behandles som separate integrasjoner. Start med bankfil og avstemming.
EHF krever dokumentformat og transport gjennom et aksesspunkt.
[DFØ: EHF og Peppol](https://www.anskaffelser.no/kategorispesifik-veiledning/fagsystemer-digitale-anskaffelser/elektronisk-handelsformat-ehf)

## Utviklingsrekkefølge

### 0. Avklar foretaket og åpningen av regnskapet

Avklar hva som selges, kundeland, bedrift/forbruker, registreringer, startdato, bank,
betalingsformidlere, eksisterende regnskap og første inntektsår. Kartlegg eiendeler og
oppstartskjøp. Ved systembytte trengs avstemte inngående balanser, åpne poster,
MVA-status og historiske saldogrupper. Dato for bytte må være entydig.

Resultat: en liste over støttede transaksjoner og dokumentert åpningsgrunnlag.
Ansatte, kontantsalg, varelager, utenlandsk forbrukersalg og særnæringer tas med dersom
virksomheten trenger dem. De skal ikke få antatt støtte.

### 1. Bokføringsgrunnlag med norsk kontroll og eksport

Lag kontoplan, avgiftskoder, eierkontoer, fakturaoppsett og begrenset daglig brukerrolle.
Gjenbruk fakturaer, bilag og bankimport. Implementer kontrollspor, korreksjoner, låsing,
SAF-T og arkivrutine. Test at fakturaer og vedlegg kan gjenfinnes etter gjenoppretting.

Resultat: fiktive bilag kan føres, avstemmes og eksporteres med samme tall. SAF-T og
arkiv er en del av denne leveransen, ikke en valgfri sluttfase.

### 2. Daglig ENK-flyt og nødvendig MVA-behandling

Lag enkle innganger for kjøp, salg, privat utlegg og bankavvik. Implementer rullerende
MVA-overvåkning, registreringsovergang, aktuelle satser, utenlandsk tjenestekjøp,
fradragsfordeling og meldingsgrunnlag. Ukjente tilfeller må henvises til faglig avklaring.

Resultat: brukeren kan håndtere de avtalte hverdagstilfellene uten fri journalføring,
og MVA kan leveres manuelt på grunnlag av en kontrollert rapport.

### 3. Eiendeler og første årsoppgjør

Bygg norske saldogrupper, årsberegning, relevante private korreksjoner og mapping til
næringsspesifikasjonen. Avstem bank, reskontro, avgift og egenkapital. Bevar årets
rapportpakke og dokumenter manuell innlevering med kvittering.

Resultat: et komplett prøveår kan avsluttes med kontrollert skattemeldingsgrunnlag.
Jeg anbefaler at en norsk regnskapsfører kontrollerer prøveåret og de valgte reglene før
løsningen blir eneste regnskap. Dette er et kvalitetstiltak, ikke et generelt revisorkrav.

### 4. Automatiser det som gir mest nytte

Prioriter bankkobling, EHF, bilagslesing og direkte MVA-innsending ut fra faktisk bruk.
Direkte skattemelding kommer når beregningene, feltmappingen og leverandørtilgangen er
avklart. Hver integrasjon må vise både feil, mottak og endelig status.

## Akseptansekriterier før reell bruk

Dette er testkrav for kommende implementasjon. De er ikke kjørt i denne undersøkelsen.

| Scenario | Forventet resultat |
|---|---|
| 50 000 kroner nøyaktig i registreringsgrunnlaget | Ingen ordinær registreringsplikt fra beløpet alene |
| 45 000 tidligere + nytt avgiftspliktig salg på 10 000 | Hele nye salget avgiftsberegnes gjennom korrekt registrerings-/fakturaflyt |
| Salg på begge sider av nyttår | Rullerende tolv måneder fortsetter uten nullstilling |
| Leveringsdato og fakturadato avviker | Registreringsgrunnlag og rapportering følger hver sine periodiseringsregler |
| Unntatt og fritatt omsetning | Ulike koder, registreringsgrunnlag og fradragsrett |
| Uregistrert med utenlandsk SaaS på 2 000 og 2 000,01 i kvartalet | Bare over grensen utløser beregning, på hele det relevante grunnlaget |
| Registrert med lite utenlandsk tjenestekjøp | Ingen 2 000-kronersgrense; fradragsrett vurderes separat |
| Privatbetalt kjøp med senere refusjon | Én kostnad og korrekt eierkonto |
| Pengeuttak til innehaver | Ingen lønn, utgående MVA eller kostnad |
| Utstyr på 29 999 og 30 000 med minst tre års brukstid | Riktig grense og kostpris med/uten MVA-fradrag |
| Flere eiendeler i samme saldogruppe, delvis salg og restsaldo | Norsk saldooppgjør stemmer med dokumentert fasit |
| Desembersalg, betaling i januar | Inntekt og bankbetaling havner i riktig år uten dobbeltføring |
| Samme bankfil importeres to ganger | Ingen dupliserte regnskapsføringer |
| Faktura i valuta med betalingsgebyr | Fordring, kursdifferanse, gebyr og bank avstemmes |
| SaaS-oppgjør med mange salg, gebyrer og refusjoner | Salg, avgift og gebyr skilles; nettoutbetaling avstemmes mot mellomkonto |
| Ekstern salgshendelse leveres to ganger | Samme eksterne identifikator gir ikke to fakturaer/betalinger |
| Årsabonnement betalt før årsskiftet | Inntekten fordeles etter leveransen; MVA vurderes etter egne regler |
| To fiktive ENK med ulik MVA-status | Oppsett, beregning og eksport er isolert per foretak |
| Kreditnota etter levert MVA-melding | Korreksjonen kan spores, opprinnelig rapport bevares |
| Sletting/nummerendring eller føring i lukket periode | Avvises for daglig bruker; administrative inngrep dokumenteres |
| SAF-T-eksport | Gyldig valgt XSD, balanserte summer, riktige referanser og samsvar med hovedbok |
| Gjenoppretting | Database, bilag, rapporter og kontrollspor kommer tilbake samlet |
| Innsending med nettverksbrudd | Ingen falsk levert-status eller blind dobbeltinnsending |

Bruk eget testsite og fiktive bilag. Norske regler testes separat fra ERPNext-integrasjonen.
XSD-validering alene beviser ikke riktig regnskap; summer, grunnlag og referanser må også
avstemmes. Før deploy kjøres relevante tester og `bench migrate` i dev som beskrevet i
[utviklingsrutinen](utvikling.md).

## Omfang, kostnad og åpne valg

Min vurdering er at en enkel ENK-flate er gjennomførbar over ERPNext. Å erstatte hele
Fikens norske rapporterings- og integrasjonsansvar er et vesentlig større prosjekt.
Det krever løpende regelverksarbeid selv om programvaren driftes på egen server.

For ett foretak kan egen utvikling koste mer tid enn et ferdig norsk system. ERPNext-valget
gir mest mening dersom kontroll over data, egne arbeidsflyter og videre utvidelser er
viktige nok til å forsvare vedlikeholdet. Første beslutningspunkt er en demonstrert
bokføringsflyt og et komplett prøveår, med kjent vei til levering av skattemeldingen.

Konsulenttjenester og SaaS er avklart som første brukstilfeller. Følgende er fortsatt
uavklart: MVA-status, kundeland, bank/oppgjørstjenester, første regnskapsår, tidligere bilag,
eiendeler, private andeler og behov for ansatte eller varer. Et tidsestimat og automatiske
skatteregler krever at dette avgrenses. Disse avklaringene styrer første konfigurasjon og
testutvalg, ikke om regelverket skal kunne gjenbrukes av andre ENK.
