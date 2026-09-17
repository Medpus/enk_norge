# Norske krav til ENK og konsekvenser for enk_norge

Undersøkt 2026-09-17. Dette er et kildebasert beslutningsgrunnlag for utviklingen, ikke en
bekreftelse på at dagens installasjon oppfyller kravene. Modulen skal kunne brukes av
norske ENK generelt. Første brukstilfelle er et opprettet ENK som skal selge
konsulenttjenester til bedrifter og privatpersoner, samt SaaS. Kundeland, MVA-status og
eksisterende regnskap er ikke avklart. Bransjespesifikke plikter må avgrenses før reell bruk.

Den anbefalte løsningen er å bruke ERPNext til bokføringen og utvikle norske regler,
kontroller og en enklere arbeidsflyt i enk_norge. Direkte innsending til myndighetene er
en egen leveranse. Se [utviklingsplanen](enk-produktplan.md).

## Hva et vanlig ENK må gjøre

| Område | Hovedregel | Konsekvens for programmet |
|---|---|---|
| Bokføring | Dokumenter kjøp, salg og andre økonomiske hendelser | Bilag, hovedbok, kunde-/leverandørspesifikasjon og avstemming |
| Inntektsskatt | Overskuddet inngår i innehaverens skatt | Årsresultat med skattemessige justeringer og personinntekt |
| Skattemelding | Én samlet melding for person og næring | Næringsspesifikasjon må avstemmes mot personlige opplysninger |
| MVA | Registrering når omsetning omfattet av loven overstiger terskelen | Overvåkning før registrering og korrekt behandling etterpå |
| Årsregnskap til Brønnøysund | Gjelder regnskapspliktige, normalt ikke et lite ENK | Ikke legg på AS-plikter automatisk |
| SAF-T | Elektronisk bokføring medfører normalt krav om eksport på forespørsel | Norsk SAF-T må være med før ordinær bokføring tas i bruk |

Bokføringsplikt og regnskapsplikt betyr ulike ting. ENK blir etter de vanlige
størrelsesreglene regnskapspliktig ved eiendeler over 20 millioner kroner eller mer enn
20 årsverk, når grensen passeres to år på rad. Særlige virksomheter kan ha andre krav.
Kilder: [Altinn om bokføringsplikt](https://info.altinn.no/starte-og-drive/regnskap-og-revisjon/regnskap/bokforingsplikt)
og [Brønnøysundregistrene om regnskapsplikt](https://www.brreg.no/innsending-av-arsregnskap/innsendingsplikt-til-regnskapsregisteret/hvem-har-regnskapsplikt/).

50 000 kroner er ingen generell skattefri grense. Om aktiviteten er næring, vurderes blant
annet ut fra overskuddsevne, varighet, omfang og egen regning og risiko. Registrering alene
avgjør ikke dette. [Skatteetaten: Er jeg næringsdrivende?](https://www.skatteetaten.no/bedrift-og-organisasjon/starte-og-drive/er-jeg-naringsdrivende/)

## Inntekter, kjøp og private penger

Inntekter hører til året de er opptjent, selv om betalingen kommer senere. En faktura fra
desember som betales i januar gir derfor ikke automatisk inntekt i januar. Systemet må
skille levering/opptjening, fakturadato og betalingsdato.
[Skatteetaten: Inntekt i enkeltpersonforetak](https://www.skatteetaten.no/bedrift-og-organisasjon/skatt/skattemelding-naringsdrivende/fradrag/inntekt-formue-gjeld/inntekt-i-enkeltpersonforetak/)

Følgende arbeidsmåte anbefales:

- Et kjøp får originalbilag, leverandør, dato, valuta, formål og betalingsmåte.
- Systemet skiller skattemessig fradrag fra fradrag for inngående MVA. De er ikke samme vurdering.
- Privat betalte næringskjøp føres mot eierens mellomværende/egenkapital. Refusjonen til
  eieren skal ikke skape en ny kostnad.
- Kontantinnskudd fra eieren er ikke salgsinntekt. Pengeuttak til eieren er ikke lønn eller
  fradragsberettiget driftskostnad. Uttak av varer eller eiendeler kan ha egne skatte- og
  MVA-konsekvenser og må behandles separat.
- Bankhendelser brukes til avstemming. En banklinje er ikke alene tilstrekkelig kjøpsbilag,
  og importen må ikke føre samme kjøp på nytt.

Skatten følger overskuddet, også når pengene blir stående i foretaket. Betalt forskuddsskatt
for innehaveren må holdes utenfor driftskostnadene. Det er fornuftig å bruke en separat
bankkonto for næringen. ENK og innehaveren er ikke separate rettssubjekter.
[Altinn: Skatt for enkeltpersonforetak](https://info.altinn.no/starte-og-drive/skatt-og-avgift/skatt/skatt-for-enkeltpersonforetak)

Oppstartskostnader kan på vilkår gi fradrag inntil fem foregående oppstartsår. Gamle utgifter
skal knyttes til riktig inntektsår, ikke samles ukritisk i årets regnskap. Endring av tidligere
skattemeldinger kan være nødvendig. Eksisterende privat utstyr krever en egen vurdering
av inngangsverdi og næringsbruk.
[Skatteetaten: Oppstartsperiode og oppstartskostnader](https://www.skatteetaten.no/bedrift-og-organisasjon/starte-og-drive/ny-som-naringsdrivende/oppstartsperiode/)

Utgifter på 10 000 kroner eller mer må som hovedregel betales via bank/elektronisk for å gi
fradrag. Oppsplitting i flere betalinger skal ikke omgå regelen. Kvittering eller faktura
må bevares; en kontoutskrift erstatter ikke dokumentasjonen av kjøpet.
[Skatteetaten: Kom i gang med nytt ENK](https://www.skatteetaten.no/bedrift-og-organisasjon/starte-og-drive/ny-som-naringsdrivende/nytt-enk/)

### Eksempler på føring

Eksemplene under er foreslåtte kontrolltilfeller. De forutsetter dokumenterte kjøp til
næringen, ordinær 25 prosent MVA og full fradragsrett der foretaket er registrert.

| Hendelse | Føring og effekt |
|---|---|
| Forbruksmateriell til 1 250 kroner, uregistrert | 1 250 i kostnad, mot bank eller eierkonto. Ingen inngående MVA til fradrag. |
| Samme kjøp, registrert og full fradragsrett | 1 000 i kostnad og 250 inngående MVA, mot 1 250 bank/eierkonto. |
| Registrert salg på 10 000 eksklusiv MVA | 12 500 kundefordring, 10 000 inntekt og 2 500 utgående MVA. |
| Kunden betaler fakturaen | Bank øker og kundefordringen reduseres. Det føres ikke ny salgsinntekt. |
| Eieren setter inn 5 000 kroner | Bank øker mot eierkonto. Resultatet endres ikke. |

Fradrag betyr at skattegrunnlaget blir lavere. Det betyr ikke at staten betaler hele
kjøpet. Utgifter, skattefradrag, MVA-fradrag og kontantbetaling vises derfor separat.

## MVA før og etter 50 000 kroner

Den ordinære registreringsgrensen er omsetning og uttak omfattet av merverdiavgiftsloven
over 50 000 kroner uten MVA i en løpende periode på tolv måneder. Den nullstilles ikke
1. januar. Det er ikke overskudd eller summen av bankinnbetalinger som skal måles.
Før registrering skal virksomheten ikke fakturere med MVA.
[Skatteetaten: Registrering i Mva-registeret](https://www.skatteetaten.no/bedrift-og-organisasjon/avgifter/mva/registrere-endre-slette/)

Eksempel, forutsatt ordinært avgiftspliktig salg: Tidligere omsetning er 45 000 kroner,
og neste salg er 10 000 kroner eksklusiv MVA. Det er hele det grensepasserende salget som
skal avgiftsberegnes, ikke bare de 5 000 kronene over grensen. Registreringen må gjennomføres
før MVA kan oppgis på faktura. En allerede utstedt faktura må håndteres med dokumentert
etterfakturering eller kreditering og ny faktura etter gjeldende fremgangsmåte. Avtalt
pris avgjør om avgiften kan legges oppå prisen til kunden.
[Skatteetatens behandling av grensepasserende faktura](https://www.skatteetaten.no/rettskilder/type/vedtak/skatteklagenemnda/sporsmal-om-manglende-innberetning-av-merverdiavgift-av-hele-belopet-pa-faktura-som-overstiger-belopsgrensen-for-registrering-i-merverdiavgiftsregisteret/)

Programmet trenger separate tilstander for uregistrert, registrering pågår og registrert,
med registreringstermin/virkningstidspunkt fra registervedtaket. Vedtaksdatoen er ikke
nødvendigvis tidspunktet avgiftsplikten oppstod. Et varsel endrer ikke registreringsstatus.
Kreditnotaer, tilbakeføringer, historiske salg og flere aktiviteter må inngå i beregningen.

### Fire ulike årsaker til at en faktura ikke viser MVA

| Tilfelle | Betydning |
|---|---|
| Ikke registrert ennå | Virksomheten kan ikke kreve inn MVA som registrert avgiftssubjekt |
| Fritatt omsetning | Omsetningen er innenfor loven, men har nullsats; kan gi fradragsrett og telle mot registreringsgrensen |
| Unntatt omsetning | Omsetningen er utenfor avgiftsplikten; normalt ingen tilhørende fradragsrett |
| Utenlandstransaksjon | Krever vurdering av tjeneste/vare, kjøper, land og leveringssted |

Disse må ha ulike koder selv om fakturabeløpet kan se likt ut. Delt virksomhet trenger
fordeling av felleskostnader. Sats og fradragsandel må kunne variere per linje.
De vanlige satsene er 25 prosent, 15 prosent og 12 prosent, avhengig av ytelsen.
[Skatteetaten: Unntatt eller fritatt MVA](https://www.skatteetaten.no/bedrift-og-organisasjon/avgifter/mva/slik-fungerer-mva/forskjellen-pa-fritak-og-unntak-fra-merverdiavgift/)

### Kjøp fra utlandet

Kjøp av fjernleverbare tjenester, for eksempel SaaS, skytjenester og annonsering, kan
utløse omvendt avgiftsplikt. Registrerte virksomheter beregner avgiften uten noen nedre
beløpsgrense og vurderer inngående fradrag separat. Uregistrerte næringsdrivende får plikt
når slike kjøp samlet overstiger 2 000 kroner eksklusiv MVA i et kvartal. Da beregnes MVA
av hele det relevante grunnlaget, og det brukes en særskilt melding.
[Merverdiavgiftsloven § 11-3](https://lovdata.no/lov/2009-06-19-58/§11-3)
og [Skatteetatens veileder for tjenestekjøp](https://www.skatteetaten.no/bedrift-og-organisasjon/avgifter/mva/utland/tjenester/).

Systemet må fange dette før ordinær MVA-registrering. Utenlandsk avgift eller feilaktig
belastet forbruker-MVA må ikke automatisk godtas som fradragsberettiget norsk MVA.
Vareimport behandles separat med tolldeklarasjon og riktig avgiftsgrunnlag.
Ved salg til utlandet må eksportvilkår og mulige plikter i kundelandet undersøkes for den
faktiske virksomheten. Kundens land alene er ingen trygg regelmotor. Kilden under gjelder
norsk MVA-behandling. EU-forbrukersalg omtales separat nedenfor; øvrige kundeland er ikke kartlagt.
[Skatteetaten: Fjernleverbare tjenester ut av avgiftsområdet](https://www.skatteetaten.no/en/rettskilder/type/handboker/merverdiavgiftshandboken/gjeldende/M-6/M-6-22/M-6-22.4/)

Et tilbakegående avgiftsoppgjør kan gi MVA-fradrag for relevante anskaffelser inntil tre år
før registreringen, med vilkår og unntak. Dette er en annen ordning enn femårsregelen for
oppstartskostnader. Opprinnelig bilag, tilknytning til registrert virksomhet og tidligere
behandling må dokumenteres slik at samme beløp ikke trekkes fra to ganger.
[Skatteetaten: Nytt ENK, fradrag før MVA-registrering](https://www.skatteetaten.no/bedrift-og-organisasjon/starte-og-drive/ny-som-naringsdrivende/nytt-enk/)

## Konsulenttjenester og SaaS

Vanlig konsulentarbeid og SaaS til norske kunder vil normalt ha ordinær sats på
25 prosent når foretaket er MVA-registrert. Vurder den faktiske ytelsen; eksempelvis
undervisning kan ha andre regler. At kjøperen er familie eller en venn gir ikke i seg
selv et skatte- eller avgiftsfritak.
[Skatteetaten: MVA-satser](https://www.skatteetaten.no/satser/merverdiavgift/)

Fjernleverbare tjenester til mottakere hjemmehørende utenfor MVA-området kan være fritatt
for norsk MVA. Fra 2023 omfatter den generelle regelen også forbrukere. Eldre veiledning
som skiller elektroniske og andre fjernleverbare tjenester på dette punktet må ikke
brukes som gjeldende regel. Klassifisering og dokumentasjon av mottakeren er nødvendig.
[Skatteetaten: § 6-22 annet ledd](https://www.skatteetaten.no/en/rettskilder/type/handboker/merverdiavgiftshandboken/gjeldende/M-6/M-6-22/M-6-22.4/)

Norsk fritak løser ikke kundelandets avgiftskrav. Ved direkte salg av elektroniske
SaaS-tjenester til EU-forbrukere er utgangspunktet avgift i kundelandet. En leverandør
etablert bare i Norge kan ikke bruke EUs 10 000-euroterskel for EU-etablerte leverandører.
Non-Union OSS kan samle relevante B2C-tjenester i kvartalsvis rapportering gjennom ett
EU-land, dersom leverandøren oppfyller vilkårene. Norsk MVA-grense er ikke et fribeløp for
denne plikten. Andre markeder krever egen vurdering.
[EU-kommisjonen: One Stop Shop](https://vat-one-stop-shop.ec.europa.eu/one-stop-shop_en)

Modulen må skille mellom selger, betalingsformidler og eventuell videreselger som har
avgiftsansvaret overfor sluttkunden. Begrepet "merchant of record" er ikke tilstrekkelig
dokumentasjon; avtalen og den faktiske salgsmodellen styrer. Ren betalingsbehandling
gjør ikke automatisk betalingsleverandøren til selger.
[EU-reglene om elektroniske formidlere, artikkel 9a](https://eur-lex.europa.eu/eli/reg_impl/2011/282/2022-03-16/eng)

Forbrukersalg over nett trenger også tydelige priser, abonnementsvilkår og håndtering av
angrerett. Digitalt innhold og løpende digitale tjenester har ulike regler. At et abonnement
er aktivert betyr ikke alene at angreretten er borte. Checkout må dokumentere relevante
opplysninger, samtykker og bekreftelser; regnskapet må håndtere kreditnota/refusjon.
[Angrerettloven, særlig §§ 8, 21, 22 og 26](https://lovdata.no/lov/2014-06-20-27)

Abonnement og lignende ytelser kan på vilkår faktureres på forskudd for inntil ett år.
Fakturadato og avgiftsperiode er ikke nødvendigvis samme periode som inntekten er opptjent.
Avtale, tjenestestart og tjenesteslutt må derfor bevares, og inntektsføringen må følge den
faktiske leveransen. Første implementasjon fordeler dokumenterte, jevnt leverte tjenester
etter dager. Den forutsetningen passer ikke automatisk for alle prosjektavtaler.
[Skatteetaten: forskuddsfakturering og periodisering](https://www.skatteetaten.no/rettskilder/type/handboker/merverdiavgiftshandboken/gjeldende/M-15/M-15-9/M-15-9.3/),
[Skatte-ABC: tidfesting av virksomhetsinntekt](https://oppslag.rettskilder.skatteetaten.no/rettskilder2/type/handboker/skatte-abc/gjeldende/skatteabc-V-10/skatteabc-V-10.018).

Dette gjør konsulentvirksomhet og SaaS til nyttige første testtilfeller for en generell
modul: kundetype, land, avgiftsansvar og leveringsperiode må være data. Ingen av reglene
skal være knyttet til et bestemt prosjekt eller domenenavn.

## Eiendeler og avskrivninger

For fysiske driftsmidler som verdiforringes og hovedsakelig brukes i inntektsgivende
aktivitet, er den sentrale grensen kostpris minst 30 000 kroner og forventet brukstid
minst tre år. Da er hovedregelen aktivering og avskrivning. Under én av grensene kan
kostnaden normalt fradragsføres direkte. Ikke-fradragsberettiget MVA inngår i kostprisen;
fradragsberettiget inngående MVA gjør ikke det.
[Skatteloven § 14-40](https://lovdata.no/lov/1999-03-26-14/§14-40)
og [Skatte-ABC om direkte fradragsføring](https://www.skatteetaten.no/rettskilder/type/handboker/skatte-abc/gjeldende/d-3-driftsmiddel--direkte-fradragsforing/D-3.001/D-3.002/).

Grensetilfellene må testes på nøyaktig 30 000 kroner og nøyaktig tre år. Enkelte
forenklede veiledninger bruker ordene "over" og "inntil" annerledes. Implementasjonen
skal følge lovens presise grense. Immaterielle rettigheter, goodwill, påkostninger og
driftsmidler som ikke taper verdi har egne regler.

Kontormaskiner mv. i saldogruppe a kan avskrives med inntil 30 prosent årlig. Maskiner og
inventar mv. i gruppe d har inntil 20 prosent. Gruppe bestemmes av eiendelens art.
[Skatteetaten: Avskrivningssatser](https://www.skatteetaten.no/satser/avskrivningssatser/)

Norske skattemessige saldogrupper kan omfatte flere eiendeler. ERPNexts avskrivningsplan
per eiendel er derfor ikke tilstrekkelig i seg selv. Planlagt løsning er et norsk
saldoregister med inngående saldo, anskaffelser, salg/uttak, årets avskrivning og utgående
saldo. Historiske satser og valg må bevares per inntektsår.
[Skatteetaten: Kjøpe eiendeler til bedriften](https://www.skatteetaten.no/bedrift-og-organisasjon/skatt/skattemelding-naringsdrivende/fradrag/eiendeler-utstyr-eiendom/bedriftens-eiendeler/kjope-eiendeler-til-bedriften/)

Et vanlig ENK som bare er bokføringspliktig trenger normalt ikke et fullstendig dobbelt
oppsett for regnskapsmessige og skattemessige avskrivninger. Skattereglene kan styre
føringen. Om foretaket blir regnskapspliktig, må forskjeller og eventuelle forenklinger
vurderes særskilt.
[Skatteetaten om avskrivning for bokføringspliktige](https://www.skatteetaten.no/bedrift-og-organisasjon/utenlandsk/skattemelding-og-skatteoppgjor/fradrag/)

Ved salg av et driftsmiddel må bokført verdi fjernes fra balansen. Regnskapsmessig
gevinst eller tap og skattemessig behandling av salgssummen skal avstemmes hver for seg.
Et driftsmiddelsalg i avgiftspliktig virksomhet kan også utløse MVA-registrering. Det må
inngå i terskelkontrollen sammen med vanlig omsetning. Unntatt virksomhet må vurderes
særskilt; første driftsmiddelflyt dekker ikke den situasjonen.
[Skatteetaten: registreringsgrensen og salg av driftsmidler](https://www.skatteetaten.no/rettskilder/type/handboker/merverdiavgiftshandboken/gjeldende/M-2/M-2-1/M-2-1.3/).

## Skattemelding og årsoppgjør

ENK leverer én skattemelding med både personlige opplysninger og næringsspesifikasjon.
Mange kan levere på skatteetaten.no; regnskaps- eller revisjonspliktige ENK må levere
næringsspesifikasjonen gjennom system. Ordinær frist er 31. mai året etter inntektsåret,
med justering når fristen faller i helg. Også foretak uten aktivitet må levere.
Forenklet næringsspesifikasjon ved lave driftsinntekter er en annen regel enn
MVA-grensen og bruker ikke en rullerende tolvmånedersperiode.
[Skatteetaten: Skattemelding for ENK](https://www.skatteetaten.no/bedrift-og-organisasjon/skatt/skattemelding-naringsdrivende/enk/)

Årsoppgjøret må som minimum ha et kontrollert grunnlag for:

- Inntekter og kostnader i riktig år, inkludert ubetalte fakturaer og periodiseringer.
- Eiendeler, saldogrupper og relevante formuesverdier.
- Kundefordringer, leverandørgjeld, bank og annen relevant gjeld.
- Varelager dersom virksomheten har varer for salg.
- Privat bruk og kostnader som ikke gir skattemessig fradrag.
- Beregnet personinntekt og relevante korreksjoner.
- Samsvar med private bank-/gjeldsopplysninger slik at ingenting telles dobbelt.

Dette er en sjekkliste for produktet, ikke en påstand om at alle feltene gjelder hvert foretak.
Kontoplan alene er ikke nok: rapporteringen trenger en versjonert kobling fra kontoer og
skattejusteringer til feltene for det aktuelle inntektsåret. En SAF-T-fil er verken en
skattemelding eller dokumentasjon på at skattemeldingen er levert.

Personinntekt i ENK følger foretaksmodellen. Beregningen starter med netto næringsinntekt,
og korrigeres for relevante kapitalposter, renter, særskilte fradrag, skjerming og eventuell
fremført negativ personinntekt. Hver post må ha dokumentert grunnlag i rapportåret. Systemet
lagrer derfor input og resultat sammen med årsrapportens hash, men fastsetter ikke selv en
skjermingsrente for 2026. Bruk dokumentert skjermingsbeløp eller en rente som er bekreftet for
det aktuelle inntektsåret før rapporten markeres klar. Negativ beregnet personinntekt skal
bevares som fremføringsgrunnlag; tilgjengelig fremføring brukes mot positiv personinntekt ved
første anledning og aldri under null.
[Skatteetaten: oversikt over beregning av personinntekt](https://www.skatteetaten.no/rettskilder/type/handboker/skatte-abc/gjeldende/e-5-enkeltpersonforetak--beregnet-personinntekt-foretaksmodellen/E-5.016/E-5.018/),
[Skatteetaten: skjermingsfradrag](https://www.skatteetaten.no/rettskilder/type/handboker/skatte-abc/gjeldende/e-5-enkeltpersonforetak--beregnet-personinntekt-foretaksmodellen/E-5.054/E-5.055/)
og [Skatteetaten: skjermingsrente](https://www.skatteetaten.no/rettskilder/type/handboker/skatte-abc/gjeldende/e-5-enkeltpersonforetak--beregnet-personinntekt-foretaksmodellen/E-5.054/E-5.091/).
[Skatteetaten: fremføring av negativ beregnet personinntekt](https://www.skatteetaten.no/rettskilder/type/handboker/skatte-abc/2025/e-5-enkeltpersonforetak--beregnet-personinntekt-foretaksmodellen/E-5.096/E-5.105/)
beskriver kravet om fremføring ved første anledning.

Privat skatt avhenger også av lønn, andre inntekter, fradrag og personlige forhold.
Et felt med en fast prosent av resultatet kan være et spareanslag, men må ikke presenteres
som korrekt beregnet skatt. Forventet overskudd meldes i skattekortet og oppdateres ved
endringer. Ordinære terminer for forskuddsskatt er 15. mars, juni, september og desember.
[Altinn: Skatt for ENK](https://info.altinn.no/starte-og-drive/skatt-og-avgift/skatt/skatt-for-enkeltpersonforetak)

## MVA-meldinger og frister

Vanlig ordning er seks terminer årlig, også når det ikke er omsetning. Ordinære frister
for levering og betaling er 10. april, 10. juni, 31. august, 10. oktober, 10. desember og
10. februar året etter. Programmet må hente/beregne faktiske frister med helgejustering.
Årstermin krever søknad og vilkår, blant annet minst tolv måneder med ordinær registrering
og oppfylte rapporterings- og betalingsplikter. Det er ikke en automatisk innstilling for
små ENK. Godkjent ordinær årstermin har frist 10. mars året etter.
[Altinn: Rapportering og betaling av MVA](https://info.altinn.no/starte-og-drive/skatt-og-avgift/avgift/rapportering-og-betaling-av-mva)
og [Skatteetaten: Skattleggingsperioder](https://www.skatteetaten.no/rettskilder/type/handboker/skatteforvaltningshandboken/gjeldende/kapittel-8-opplysningsplikt-for-skattepliktige-trekkpliktige-mv/ID-8-3.001/ID-8-3.014/).

Et ferdig MVA-oppgjør må vise grunnlag, avgift og korrigeringer per norsk kode og kunne
følges helt tilbake til bilagene. Innsendt versjon, kvittering og betaling må ha separate
statuser. En endring etter innsending skal gi en synlig korrigeringsprosess.

## Faktura, sporbarhet og oppbevaring

Utgående faktura må blant annet identifisere partene, angi dato, leveransen, beløp og
eventuell MVA. Organisasjonsnummer med "MVA" brukes når selgeren er registrert.
Nummer tildeles maskinelt i en kontrollerbar sekvens. Vanlig bruk skal ikke kunne overstyre
nummeret eller slette en utstedt faktura. Feil må dokumenteres og korrigeres.
[Skatteetaten: Inntekter og fakturering](https://www.skatteetaten.no/bedrift-og-organisasjon/starte-og-drive/rutiner-regnskap-og-kassasystem/gode-rutiner-for-daglig-drift/inntekter/)

Kravet om sporbarhet gjelder også bilag, rettinger og pliktige spesifikasjoner. Vi må
kontrollere ERPNexts fakturaserier, kansellering, sletting og periodestenging i vår konkrete
versjon. Funksjonsnavnet "Immutable Ledger" er ikke bevis på norsk etterlevelse.

Primærdokumentasjon oppbevares som hovedregel i fem år etter regnskapsårets slutt;
sekundærdokumentasjon normalt i 3,5 år. Enkelte forhold krever lengre tid. Elektronisk
materiale skal sikkerhetskopieres, og rutinen må beskrive hva som kopieres, hvor det
oppbevares og hvor ofte. Utenlandsk oppbevaring har særskilte regler.
[Altinn: Oppbevaring av regnskapsmateriale](https://info.altinn.no/starte-og-drive/regnskap-og-revisjon/regnskap/oppbevaring-av-regnskapsmateriale)

For Tower betyr dette at databasebackup alene ikke er nok. Vedlegg, innsendingskvitteringer
og lesbare eksportfiler må følge med. Gjenoppretting må testes. En backup på samme disk
gir ikke tilstrekkelig beskyttelse mot tap av maskinen; en separat kopi anbefales.

SAF-T-kravet omfatter normalt også små bokføringspliktige med elektronisk tilgjengelige
regnskapsopplysninger. Unntaket for omsetning under fem millioner er derfor ikke en trygg
begrunnelse for å utelate SAF-T i ERPNext. Filen leveres ved kontroll/forespørsel, ikke
rutinemessig som årsoppgjør.
[Skatteetaten: Spørsmål og svar om SAF-T](https://www.skatteetaten.no/bedrift-og-organisasjon/starte-og-drive/rutiner-regnskap-og-kassasystem/saf-t-regnskap/sporsmal-og-svar---standardformat-regnskap/)

## Krav som avhenger av virksomheten

| Forhold | Hva som må avklares |
|---|---|
| Hjemmekontor | Rommet må brukes utelukkende i næringen for hjemmekontorfradrag. ENK kan ikke betale fradragsberettiget husleie til seg selv. Næringsbruk kan få følger ved boligsalg. |
| Telefon/internett | Privat bruk har egne regler. For ENK gir tilbakeføring av EK-kostnader et inntektstillegg på inntil 4 392 kroner årlig, begrenset av kostnadene. MVA-fordeling er en separat vurdering. |
| Bil og reise | Kjørebok, privat-/yrkesbil, formål, dokumentasjon og gjeldende satser må vurderes før automatisering. |
| Varer | Lager, telling, verdsetting, import og eventuelle regler om brukthandel krever egen støtte. |
| Kontantsalg | Også umiddelbar betaling med kort/Vipps kan være kontantsalg. Produkterklært kassasystem kan være påkrevd. ERPNext POS må ikke antas å oppfylle dette. |
| Offentlige kunder | EHF-fakturering kan være nødvendig. En PDF i e-post er ikke EHF. |
| Ansatte | Lønn, a-melding, arbeidsgiveravgift, ferie og øvrige arbeidsgiverplikter blir et eget omfang. Eieruttak utløser ikke i seg selv lønnsmodul. |
| Kundedata | Personvern, tilgang, lagring og databehandleravtaler gjelder også et lite foretak. |
| Nettsalg/utland | Forbrukerrettigheter, angrerett, utenlandsk avgift og betalingsformidlernes avtaler må vurderes for det faktiske salget. |

Kilder for hjemmekontor og EK:
[egen bolig i næring](https://www.skatteetaten.no/bedrift-og-organisasjon/skatt/skattemelding-naringsdrivende/fradrag/eiendeler-utstyr-eiendom/bruke-egen-bolig-i-naring/),
[telefon og internett](https://www.skatteetaten.no/bedrift-og-organisasjon/skatt/skattemelding-naringsdrivende/fradrag/eiendeler-utstyr-eiendom/telefon-og-internett/).
Andre kilder:
[Altinn om kontantsalg og unntak](https://info.altinn.no/starte-og-drive/regnskap-og-revisjon/regnskap/kontantsalg-og-kassasystem),
[DFØ om EHF](https://www.anskaffelser.no/verktoy/veiledere/ehf-fakturering),
[Altinn om a-melding](https://info.altinn.no/starte-og-drive/arbeidsforhold/lonn/a-meldingen),
[Datatilsynet om virksomhetenes plikter](https://www.datatilsynet.no/rettigheter-og-plikter/virksomhetenes-plikter/).

Ved ansatte må en ny løsning bruke reglene fra 2026: forskuddstrekk betales som hovedregel
til Skatteetaten senest første virkedag etter lønnsutbetaling. Gamle oppskrifter med
skattetrekkskonto skal ikke brukes.
[Skatteetaten: Foreta forskuddstrekk](https://www.skatteetaten.no/bedrift-og-organisasjon/arbeidsgiver/skattekort-og-skattetrekk/forskuddstrekk/)

Registrering i Enhetsregisteret gir organisasjonsnummer. Foretaksregisteret er ifølge
Brønnøysundregistrenes gjeldende ENK-veiledning frivillig for de fleste ENK; det skal ikke
automatisk antas plikt bare fordi virksomheten driver handel.
[Brønnøysundregistrene: Registreringsplikt](https://www.brreg.no/enkeltpersonforetak/registreringsplikt-i-foretaksregisteret/)

## Kildebruk og vedlikehold

Lov og forskrift styrer grensetilfeller. Skatteetatens håndbøker og oppdaterte veiledninger
brukes for tolkning og praktisk gjennomføring. Fiken brukes som produktreferanse, ikke
som rettskilde. ERPNext-dokumentasjon må sammenholdes med installert kode.

Satser, terskler, rapportfelter, SAF-T-skjema og integrasjonskrav må versjoneres og
kontrolleres ved hvert årsskifte. Inntektsåret 2026 leveres i 2027; en fungerende
2025-integrasjon beviser ikke støtte for 2026. Uavklarte virksomhetsforhold må vises som
uavklarte i produktet, ikke fylles med antatte fradrag eller avgiftsregler.
