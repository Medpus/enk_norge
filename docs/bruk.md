# Kom i gang med ENK Norge

Oppsettet og bilagene fylles ut av den som driver foretaket. Eksempeldata hører hjemme på
testsite. Se [verifiseringsstatus](implementering.md) før du tar en ny versjon i bruk.

## Foretaksoppsett

På Tower åpner du `https://erp.example.com`, fullfører Cloudflare Access og logger inn
med den klargjorte Administrator-kontoen. Cloudflare Access og ERPNext har hver sin innlogging.

Ved første innlogging starter ENK-veiviseren. Oppgi foretak, organisasjonsnummer, adresse,
bank og datoen regnskapet starter. Bekreft MVA-status og eventuell virkningsdato. Veiviseren
oppretter en egen bruker med passordet du velger. Den oppretter også kontoplan og kontoer for
foretaket.

Kontroller tidligere fakturaer og regnskap før du bekrefter historikken. Eksisterende saldoer
blir ikke hentet automatisk fra et annet system. ENK-siden ligger på `/app/enk-norge`;
ERPNext kan endre adressen til `/desk/enk-norge`.

## Før et kjøp

Velg «Nytt kjøp». Oppgi leverandør, bilagsnummer, dato, formål og beløpet på leverandørens
bilag. Velg kostnadstype og avgiftsbehandling. Tre andeler har ulik betydning:

- Virksomhetsandel er hvor mye av kjøpet som gjelder næringen. Resten føres som privat uttak.
- MVA-fradragsandel er hvor mye av hele bilagets MVA som kan trekkes fra. Den kan ikke
  være større enn virksomhetsandelen. Et uregistrert foretak får ikke MVA-fradrag.
- Skattemessig fradragsandel gjelder den bokførte næringskostnaden. Ved redusert fradrag
  må du oppgi begrunnelse. Årsrapporten tar med justeringen og referansen til kjøpet.

Kjøpet blir et utkast. Åpne utkastet, legg ved originalbilaget som privat fil og kontroller
beløp og fordeling før bokføring. Et bokført bilag og vedlegget skal bevares.

Valuta på kjøp støttes bare for utenlandske tjenester med omvendt MVA. Oppgi valuta, kurs til
NOK, kurskilde og kursdato fra bilaget eller betalingsdokumentasjonen. Leverandørens utenlandske
hjemland må være registrert før du velger denne flyten.

Betalte du med egne penger, velger du «Betalt privat» på det bokførte kjøpet. Kontroller
betalingsutkastet før du bokfører det. Kostnaden er allerede ført gjennom kjøpet;
betalingsbilaget gjør opp leverandørgjelden mot eierkontoen.

## Lag en faktura

Velg «Ny salgsfaktura». Kunden må ha fakturaadresse. Oppgi hva du har levert, leveringsdato,
pris, antall og betalingsfrist. Velg avgiftsbehandling ut fra foretakets registrering og
den konkrete leveransen. Et unntak fra MVA krever regel og begrunnelse.

Kontroller utkastet og bruk «Norsk faktura / PDF» for utskriften. Et utkast er merket
«UTKAST. Skal ikke betales.» Bokfør først når opplysningene stemmer. Opprettelse av et
utkast sender ikke fakturaen til kunden.

For en fjernleverbar tjeneste til en utenlandsk bedrift kan fakturaen stå i valuta. Oppgi valuta,
kurs til NOK, kurskilde og kursdato fra dokumentasjonen. Valuta velger ikke kurs automatisk.
Valutasalg krever avgiftsbehandlingen «Export services».

For innsendte timer kan «Fakturer timer» lage ett utkast fra en Timesheet. Velg kunde, adresse,
vare, fakturadato og leveringsbeskrivelse. Timesheet bestemmer satsen; endre den der før du lager
utkast hvis prisen er feil. Samme Timesheet kan ikke gi et nytt ENK-utkast med endrede opplysninger.

For et ERPNext-abonnement kan «Fakturer abonnement» lage ett utkast for den aktive perioden. Etter
at forrige periode er bokført, kan du også velge nøyaktig neste sammenhengende periode. Slå av
«Submit Generated Invoices» i abonnementet først. Velg abonnementets kunde og adresse, bruk riktige
tjenestedatoer og last opp avtalen som privat fil. Flyten lager bare kladd, hopper aldri over en
periode og avviser en faktura som overlapper perioden.

Ved feil på en bokført faktura kan «Lag kreditnota» lage et utkast som viser til originalen.
Kontroller beløpet og bokfør kreditnotaen. En erstatningsfaktura skal ha eget nummer. For et
periodisert abonnement må kreditnotaen ha privat refusjonsgrunnlag.

For forskuddsbetalt SaaS kan du velge periodisering når du lager fakturaen. Oppgi tjenestestart,
tjenesteslutt og privat avtaledokument. Fakturaen må være før eller på tjenestestart, og perioden
kan være høyst ett kalenderår. På den bokførte fakturaen lager «Lag inntektsføringsutkast» et
signert utkast for opptjent beløp. Kontroller avtalen, datoen og konteringen før bokføring.

## Betaling og bank

Velg «Registrer bankbetaling» på en bokført faktura, oppgi betalingsdato og bankens referanse,
og kontroller utkastet. Gebyr føres separat. Bruk en referanse som identifiserer den konkrete
bankhendelsen.

For en valutafaktura er betalingsbeløpet i fakturaens valuta. Oppgi i tillegg den faktiske
NOK-bevegelsen i banken, kurskilde og kursdato. Gebyr og valutadifferanse følger
betalingsutkastet når det bokføres. Du bokfører bare betalingsutkastet.

Gebyrfeltet gjelder bare bank- eller betalingsgebyr uten MVA. En avgiftspliktig tjeneste fra
betalingsformidleren føres som et eget dokumentert kjøp, ikke som fratrekk i betalingen.

Bankfilen bruker UTF-8, komma som skilletegn og kolonnene
`transaction_id,date,amount,currency,description`. Dato skrives `YYYY-MM-DD`, beløp har
punktum som desimaltegn, og kontoen er i NOK. Inn er positivt beløp, ut er negativt.
Hver transaksjon må ha en stabil, unik ID fra kilden. Importen bevarer originalfilen som
privat vedlegg og oppretter banktransaksjoner for avstemming.

En importert banklinje er ikke i seg selv et kostnads- eller salgsbilag. Koble den til riktig
bokført betaling i avstemmingen. Gjentatt import skal gjenbruke samme hendelse; endret
innhold med samme ID må avklares.

## Oppgjør fra betalingsformidler

«Registrer oppgjør fra betalingsformidler» gjelder bare når foretaket er direkte selger og
oppgjøret er i NOK. Last opp betalingsformidlerens oppgjørsfil som privat fil, oppgi oppgjørs-ID,
og legg til de bokførte salgsfakturaene og eventuelle kreditnotaene med beløpene som inngår.
Brutto salg minus refusjoner og gebyr må stemme med netto utbetaling i oppgjørsfilen.
Gebyr her betyr bank- eller betalingsgebyr uten MVA. Avgiftspliktige formidlertjenester må føres
som eget dokumentert kjøp.

Flyten lager et signert journalutkast og knytter den private kildefilen til utkastet. Kontroller
kildefilen, fakturaene og konteringen før du bokfører. Ikke bruk samme oppgjørs-ID eller fil på
nytt for en annen avstemming.

## Rapporter og årsavslutning

MVA- og årsrapportene beholder beregningsgrunnlag og revisjoner. Kontroller avvik før
manuell levering hos Skatteetaten. Last opp kvitteringen til den aktuelle rapporten før
du markerer den manuelt levert. Appen sender ikke meldingen til Skatteetaten.

Velg «Lag årsrapport» for å bygge kontrollgrunnlaget. Fyll bare inn dokumenterte tall for
personinntekt, kapitalposter, renter og skjerming. Kapitalavkastningsgrunnlag kan være null når
dokumentasjonen viser null. Dersom grunnlaget er større enn null, må du angi dokumentert
skjermingsbeløp eller skjermingsrente; appen antar aldri en rente.

Årsdialogen viser hovedbok fordelt på rapportkoder og en egen skatteavstemming. Skattemessige
korrigeringer er separate fra hovedboksummer. Kontroller hele grunnlaget før eventuell manuell
levering, siden beløpene ikke kan sendes blindt til Skatteetaten. Et tidligere innlevert grunnlag
og kvitteringen blir stående når du lager en korrigert rapport.

SAF-T er et regnskapsuttrekk til kontroll, og erstatter ikke skattemelding eller MVA-melding.
Regler og rapportgrunnlag er foreløpig knyttet til inntektsåret 2026. Åpne begrensninger og
tester står i [implementeringsstatusen](implementering.md).

## Driftsmidler og saldogrupper

Velg «Opprett saldogruppe» når et driftsmiddel skal ha skattemessig saldo i gruppe a eller d.
Et kjøp med kostnadskategorien «Utstyr med varig verdi» aktiveres først som utstyr. Legg deretter
bare dokumenterte anskaffelsesbilag i riktig saldogruppe. Kildebilagene må være bokført og summere
nøyaktig til anskaffelser eller realisasjonsvederlag. En inngående skattesaldo som ikke er null, også negativ,
krever privat vedlegg fra forrige saldooppgjør.

«Lag avskrivningsutkast» bruker årsrapportens kontrollgrunnlag og lager bare et journalutkast for
åpen bokført avskrivning. Kontroller utkastet før bokføring.

«Driftsmiddelavgang» er avgrenset til allerede betalt, dokumentert salg eller uttak før MVA-registrering. Den lager
ikke faktura og sender ingenting. Salg krever komplett eksternt salgsbilag, mens uttak krever
begrunnet markedsverdi. Oppgi dokumentert bokført verdi og last opp kildebilaget som privat fil
før du lager journalutkastet.
