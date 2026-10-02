# Kom i gang med ENK Norge

Oppsettet og bilagene fylles ut av den som driver foretaket. Eksempeldata hører hjemme på
testsite. Se [verifiseringsstatus](implementering.md) før du tar en ny versjon i bruk.

Alt daglig arbeid skjer på ENK-siden, `/desk/enk-norge`. ERPNext gjør bokføringen i
bakgrunnen, men du trenger ikke åpne ERPNexts egne skjemaer. Hvert bilag har likevel en
liten lenke «Åpne i ERPNext» nederst, for de sjeldne tilfellene der det trengs.

## Foretaksoppsett

På Tower åpner du `https://erp.example.com`, fullfører Cloudflare Access og logger inn
med den klargjorte Administrator-kontoen. Cloudflare Access og ERPNext har hver sin innlogging.

Ved første innlogging starter ENK-veiviseren. Oppgi din egen bruker, foretaket,
organisasjonsnummer, adresse, bank og datoen regnskapet starter. Bekreft MVA-status og
eventuell dato registreringen gjelder fra. Veiviseren oppretter brukeren med passordet du
velger, og kontoplan og kontoer for foretaket. Logg deretter inn med din egen bruker.

Kontroller tidligere fakturaer og regnskap før du bekrefter historikken. Eksisterende saldoer
blir ikke hentet automatisk fra et annet system.

## Slik er siden bygget opp

Øverst står foretaket og MVA-statusen. «Foretak og MVA» viser grunnopplysningene og er
stedet der du registrerer at foretaket er blitt MVA-registrert.

«Status i år» viser inntekter, kostnader, resultat og bankkontoen slik den står i
regnskapet. Under står det om noe venter, for eksempel kladder som ikke er bokført eller
fakturaer som ikke er betalt. Et klikk der filtrerer bilagslisten.

«Ny registrering» har de vanlige handlingene: ny faktura, nytt kjøp, føre timer, fakturere
timer, ny kunde og ny leverandør.

«Bilag» er listen over alt som er registrert. Du kan søke på nummer, kunde eller leverandør
og filtrere på salg, kjøp, kladder og ubetalte fakturaer. Et klikk åpner bilaget.

Nederst ligger det som brukes sjeldnere: bankimport, utbetalinger fra Stripe, innskudd og
uttak, MVA, årsoppgjør, SAF-T og utstyr.

## Kladd og bokføring

Alt du registrerer blir først en kladd. Åpne kladden, kontroller beløpet og trykk «Bokfør».
«Rediger kladd» åpner skjemaet igjen med opplysningene fylt inn, og kladden beholder nummeret.
Kladder fra timer, abonnement eller import redigeres ikke; slett dem og lag dem på nytt fra
kilden. En kladd kan du slette, men en slettet fakturakladd etterlater et hull i
fakturanumrene, så rediger heller enn å slette. Et bokført bilag kan ikke endres eller slettes, så feil retter du
med kreditnota. Siden ber deg bekrefte før bokføring.

## Faktura

Velg «Ny faktura». Velg kunden, eller lag en ny med «Ny kunde». En ny kunde trenger navn og
fakturaadresse, og bedrifter kan få organisasjonsnummer og e-post. Fakturaadressen hentes
automatisk når kunden er valgt.

Legg inn én linje per vare eller tjeneste: beskrivelse, antall og pris. «Legg til linje» gir
flere linjer, for eksempel en linje per modul. Summen vises mens du skriver.

Prisen er uten MVA. Er foretaket ikke MVA-registrert, er prisen det kunden betaler, og
fakturaen nevner ikke MVA. Er foretaket registrert, legges 25 % MVA til, og fakturaen viser
grunnlag, MVA og organisasjonsnummer med «MVA».

Fakturaene nummereres fortløpende fra 1001. Har sitet flere foretak, får hvert foretak et eget
prefiks. Seksjonen «Utenlandsk kunde, unntak eller abonnement» trenger du bare
for kunder i utlandet, unntatt omsetning eller abonnement.

Kladden er ikke sendt til kunden. Etter bokføring laster du ned PDF-en og sender den selv.
Når pengene kommer inn, trykker du «Registrer innbetaling» og oppgir datoen og teksten fra
kontoutskriften.

Ved feil på en bokført faktura lager «Lag kreditnota» en kladd som viser til originalen.
En erstatningsfaktura får eget nummer.

For en kunde i utlandet kan fakturaen stå i valuta. Oppgi valuta, kurs til NOK, kurskilde
og kursdato. Valutasalg krever avgiftsbehandlingen «Tjeneste til utenlandsk bedrift».

## Timer

«Før timer» lagrer dato, kunde, antall timer, timepris og hva du jobbet med. Skjemaet blir
stående åpent, så du kan føre flere linjer etter hverandre. Timene samles per kunde.

«Fakturer timer» viser timene som ikke er fakturert, gruppert per kunde. En feilført linje
kan fjernes. Velg kunden, skriv teksten som skal stå på fakturaen, og lag kladden. Timene
låses da til fakturaen.

## Abonnement

Kryss av for «Abonnement eller forskudd for en periode» når du lager fakturaen. Oppgi
tjenestestart og tjenesteslutt, og last opp avtalen eller ordrebekreftelsen. Fakturadatoen må
være før eller på tjenestestart. Inntekten fordeles over perioden.

På en bokført abonnementsfaktura lager «Lag faktura for neste periode» en kladd med samme
kunde, pris og periodelengde. Avtalen kopieres med. Knappen lager bare én kladd per faktura.
«Inntektsfør opptjent del» lager posteringen for den delen av perioden som er opptjent.

ERPNexts egne abonnementer brukes ikke. De lager fakturakladder automatisk, og de kan ikke
bokføres i et ENK-regnskap.

## Kjøp og utgifter

Velg «Nytt kjøp eller utgift». Velg leverandøren, eller lag en ny med «Ny leverandør». Landet
avgjør om kjøpet er en tjeneste fra utlandet, for eksempel et AI-abonnement fra USA.

Skriv hva som er kjøpt og hva det skal brukes til, totalbeløpet på kvitteringen, datoen og
kvitterings- eller fakturanummeret. Nummeret stopper dobbeltregistrering.

Type kjøp:

- Programvare og abonnementer, for eksempel AI-tjenester og nettjenester.
- Utstyr, for eksempel PC, Mac eller telefon. Oppgi hvor lenge du regner med å bruke det.
  Utstyr til 30 000 kr eller mer som varer minst tre år, aktiveres og avskrives automatisk.
  Billigere utstyr kostnadsføres med en gang.
- Annen driftskostnad.
- Bank- og betalingsgebyr.

MVA-sats og fradrag vises bare når foretaket er MVA-registrert. Et uregistrert foretak får
ikke MVA-fradrag.

Brukes kjøpet også privat, åpner du «Brukes også privat» og oppgir hvor mye som gjelder
næringen. Resten føres som privat uttak. Skattemessig fradrag er normalt 100 % av
næringsdelen. Settes det lavere, må du begrunne det.

Valutafeltene vises bare for leverandører i utlandet. Oppgi kurs til NOK, kurskilde og kursdato
fra kvitteringen eller kontoutskriften.

Kjøpet blir en kladd. Trykk «Legg ved kvittering». På mobil kan du ta bilde direkte. Først
når kvitteringen er lagt ved, kan kjøpet bokføres.

Etter bokføring registrerer du betalingen: «Betalt fra bankkontoen» når foretakets konto
ble brukt, eller «Betalt med egne penger» når du la ut privat. Et ENK kan ikke skylde
eieren penger. Det du betaler privat, føres som innskudd i foretaket på kontoen
«Innskudd og private utlegg», som er egenkapital. Kostnaden gir fradrag som vanlig, og
foretakets bankkonto i regnskapet blir urørt.

## Utstyr og avskrivning

Et aktivert kjøp får knappen «Legg i saldogruppe» etter bokføring. Velg gruppe a for
kontormaskiner, PC, Mac og telefon, eller d for maskiner, inventar og verktøy. Du ser årets
skattemessige avskrivning med en gang. Appen oppretter årets saldogruppe ved første kjøp.

«Lag avskrivning» under «Utstyr og avskrivning» lager posteringen for bokført avskrivning ut
fra årsrapportens kontrollgrunnlag. «Salg eller uttak av utstyr» gjelder allerede betalt,
dokumentert salg eller uttak før MVA-registrering.

## MVA

Velg «MVA» i menyen. Siden tilpasser seg foretakets status.

Er foretaket ikke registrert, gjelder siden omvendt avgiftsplikt for kjøp av tjenester fra
utlandet. Kjøper du slike tjenester for mer enn 2 000 kr i et kvartal, skal du levere melding
og betale MVA av dem. Velg kvartalet og trykk «Beregn». Står det «Må rettes», lager du
posteringen med «Lag postering», bokfører den og beregner på nytt.

Er foretaket registrert, beregner siden den ordinære MVA-meldingen for hver tomånedstermin.

Når siden viser «Klar til levering», fører du beløpene inn hos Skatteetaten. Appen sender
ikke meldingen selv. Last deretter opp kvitteringen med «Last opp kvittering og marker
levert».

Passerer omsetningen grensen for MVA-registrering, viser oversikten et varsel. Når
Skatteetaten har registrert foretaket, oppgir du datoen under «Foretak og MVA». En etablert
registrering kan ikke endres her etter at det er bokført bilag.

## Bank

Bankfilen bruker UTF-8, komma som skilletegn og kolonnene
`transaction_id,date,amount,currency,description`. Dato skrives `YYYY-MM-DD`, beløp har
punktum som desimaltegn, og kontoen er i NOK. Inn er positivt beløp, ut er negativt.
Hver transaksjon må ha en stabil, unik ID fra kilden. Importen bevarer originalfilen som
privat vedlegg og oppretter banktransaksjoner for avstemming. Formatet er ikke en norsk
banks eget eksportformat. Til importen for din bank er på plass, registrerer du betalingen
fra bilaget.

En importert banklinje er ikke i seg selv et kostnads- eller salgsbilag. Importerer du samme
fil på nytt, gjenbrukes hendelsene. Har en linje med samme ID fått nytt innhold, må du
avklare hvorfor før du går videre.

## Utbetaling fra Stripe e.l.

Bruk dette når Stripe, Vipps eller en lignende tjeneste har betalt ut penger for fakturaer du
har bokført, og foretaket selger selv til kundene. Last opp rapporten for utbetalingen,
oppgi utbetalings-ID, legg til fakturaene og eventuelle kreditnotaer med beløpene som inngår,
og oppgi gebyret og beløpet som ble utbetalt. Fakturaene minus refusjoner og gebyr må bli det
samme som utbetalingen. Utbetalingen må være i NOK.

Gebyret gjelder gebyr uten MVA. Får du faktura med MVA for tjenesten, føres den som eget kjøp.

## Innskudd og uttak

«Innskudd eller uttak» fører penger du setter inn i foretaket eller tar ut til privat bruk.
Begge deler endrer egenkapitalen. Ingen av dem påvirker skatten, som beregnes av overskuddet.
Oppgi beløp, dato, forklaring og teksten fra kontoutskriften.

## Årsoppgjør

Velg «Lag årsrapport» for å bygge kontrollgrunnlaget. Fyll bare inn dokumenterte tall for
personinntekt, kapitalposter, renter og skjerming. Kapitalavkastningsgrunnlag kan være null
når dokumentasjonen viser null. Dersom grunnlaget er større enn null, må du angi dokumentert
skjermingsbeløp eller skjermingsrente; appen antar aldri en rente.

Resultatet viser hovedboken fordelt på rapportkoder, skatteavstemmingen med skattemessig
avskrivning og beregnet personinntekt. Før tallene inn i skattemeldingen og
næringsspesifikasjonen hos Skatteetaten, og last opp kvitteringen for å markere årsoppgjøret
som levert. En korrigert rapport lager ny revisjon; et levert grunnlag og kvitteringen blir
stående.

SAF-T er et regnskapsuttrekk til kontroll, og erstatter ikke skattemelding eller MVA-melding.
Regler og rapportgrunnlag er foreløpig knyttet til inntektsåret 2026. Åpne begrensninger og
tester står i [implementeringsstatusen](implementering.md).
