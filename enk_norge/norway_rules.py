"""Avgrensede norske ENK-regler med virkning for inntektsåret 2026.

Denne modulen er bevisst uavhengig av Frappe. Den validerer og beregner bare de
regelområdene som API-et uttrykkelig modellerer. Ukjent avgiftsbehandling,
utenforliggende datoer og ugyldige data blir avvist i stedet for gjettet.

Kilder:
- https://www.skatteetaten.no/bedrift-og-organisasjon/avgifter/mva/registrere-endre-slette/
- https://www.skatteetaten.no/rettskilder/type/handboker/merverdiavgiftshandboken/merverdiavgiftshandboken-2024/M-2/M-2-1/M-2-1.3/
- https://www.skatteetaten.no/rettskilder/type/vedtak/klagenemnda-for-merverdiavgift/kmva-8431/
- https://lovdata.no/lov/2009-06-19-58/%C2%A711-3
- https://lovdata.no/lov/1999-03-26-14/%C2%A714-40
- https://lovdata.no/lov/1999-03-26-14/%C2%A714-42
- https://lovdata.no/lov/1999-03-26-14/%C2%A714-44
- https://lovdata.no/lov/1999-03-26-14/%C2%A714-46
- https://lovdata.no/lov/1999-03-26-14/%C2%A714-47
"""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

SUPPORTED_RULE_YEAR = 2026
VAT_REGISTRATION_THRESHOLD = Decimal("50000")
REVERSE_CHARGE_UNREGISTERED_THRESHOLD = Decimal("2000")
ASSET_COST_THRESHOLD = Decimal("30000")
SMALL_SALDO_THRESHOLD = Decimal("30000")
NOK_MINOR_UNIT = Decimal("0.01")


class RuleValidationError(ValueError):
	"""Data mangler eller er utenfor den uttrykkelig støttede regelmodellen."""


class UnsupportedRuleDateError(RuleValidationError):
	"""Regelen er ikke implementert for oppgitt dato."""


class VATTreatment(StrEnum):
	"""Norsk MVA-behandling for omsetning i registreringsgrunnlaget.

	``ZERO_RATED`` er fritatt omsetning med nullsats og teller i grunnlaget.
	``EXEMPT`` er unntatt omsetning og teller ikke i grunnlaget.
	"""

	TAXABLE = "taxable"
	ZERO_RATED = "zero_rated"
	EXEMPT = "exempt"


class AssetTreatment(StrEnum):
	DIRECT_EXPENSE = "direct_expense"
	ACTIVATE_AND_DEPRECIATE = "activate_and_depreciate"
	OUTSIDE_SUPPORTED_SCOPE = "outside_supported_scope"


class SaldoGroup(StrEnum):
	A = "a"
	D = "d"


@dataclass(frozen=True, slots=True)
class ValidationResult:
	valid: bool
	normalized_value: str | None
	reason: str | None = None


@dataclass(frozen=True, slots=True)
class TurnoverEvent:
	occurred_on: date
	amount: Decimal
	treatment: VATTreatment


@dataclass(frozen=True, slots=True)
class RollingVatResult:
	as_of: date
	window_start: date
	taxable_turnover: Decimal
	zero_rated_turnover: Decimal
	exempt_turnover: Decimal
	registration_basis: Decimal
	registration_required: bool


@dataclass(frozen=True, slots=True)
class VatRegistrationCrossing:
	"""Datoen der hendelsene på datoen bringer tolv-månedersgrunnlaget over grensen."""

	occurred_on: date
	window_start: date
	registration_basis: Decimal


@dataclass(frozen=True, slots=True)
class ForeignRemoteServicePurchase:
	purchased_on: date
	net_amount: Decimal


@dataclass(frozen=True, slots=True)
class ReverseChargeResult:
	quarter_start: date
	quarter_end: date
	registered_for_vat: bool
	relevant_purchase_basis: Decimal
	liability_arises: bool
	separate_return_required: bool
	output_vat: Decimal


@dataclass(frozen=True, slots=True)
class AssetAssessment:
	treatment: AssetTreatment
	cost_basis: Decimal
	expected_useful_life_months: int
	reason: str


@dataclass(frozen=True, slots=True)
class SaldoPoolResult:
	group: SaldoGroup
	year_end: date
	depreciation_rate: Decimal
	opening_balance: Decimal
	acquisitions: Decimal
	disposal_proceeds: Decimal
	disposal_proceeds_taken_to_income: Decimal
	balance_before_year_end_adjustments: Decimal
	depreciation_deduction: Decimal
	negative_balance_income: Decimal
	closing_balance: Decimal


def validate_norwegian_organization_number(value: str) -> ValidationResult:
	"""Validerer norsk ni-sifret organisasjonsnummer med Mod11-kontrollsiffer."""

	normalized = _normalize_number(value)
	if normalized is None:
		return ValidationResult(False, None, "Verdien må bestå av sifre og vanlige skilletegn.")
	if len(normalized) != 9:
		return ValidationResult(False, normalized, "Organisasjonsnummer må ha ni sifre.")
	if not _mod11_check_digit_matches(normalized, (3, 2, 7, 6, 5, 4, 3, 2)):
		return ValidationResult(False, normalized, "Ugyldig Mod11-kontrollsiffer.")
	return ValidationResult(True, normalized)


def validate_org_number(value: str) -> bool:
	"""Returnerer om et norsk organisasjonsnummer har gyldig Mod11-kontroll."""

	return validate_norwegian_organization_number(value).valid


def validate_bank_account(value: str) -> bool:
	"""Returnerer om et norsk kontonummer har gyldig Mod11-kontroll."""

	return validate_norwegian_bank_account(value).valid


def validate_norwegian_bank_account(value: str) -> ValidationResult:
	"""Validerer norsk ellevesifret kontonummer med Mod11-kontrollsiffer."""

	normalized = _normalize_number(value)
	if normalized is None:
		return ValidationResult(False, None, "Verdien må bestå av sifre og vanlige skilletegn.")
	if len(normalized) != 11:
		return ValidationResult(False, normalized, "Kontonummer må ha elleve sifre.")
	if not _mod11_check_digit_matches(normalized, (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)):
		return ValidationResult(False, normalized, "Ugyldig Mod11-kontrollsiffer.")
	return ValidationResult(True, normalized)


def rolling_vat_registration_status(
	events: Iterable[TurnoverEvent], *, as_of: date
) -> RollingVatResult:
	"""Beregner registreringsgrunnlag i siste tolv kalendermåneder per ``as_of``.

	Kun avgiftspliktig og fritatt/nullsats omsetning inngår. Unntatt omsetning
	vises separat og teller ikke mot grensen. Krediteringer må sendes inn som
	negative beløp med samme behandling som den opprinnelige omsetningen.
	"""

	_require_supported_date(as_of)
	window_start = _one_year_before(as_of)
	taxable = Decimal("0")
	zero_rated = Decimal("0")
	exempt = Decimal("0")
	for event in events:
		if not isinstance(event, TurnoverEvent):
			raise RuleValidationError("Alle hendelser må være TurnoverEvent.")
		amount = _decimal_amount(event.amount, "Omsetningsbeløp", allow_negative=True)
		if not window_start <= event.occurred_on <= as_of:
			continue
		if event.treatment is VATTreatment.TAXABLE:
			taxable += amount
		elif event.treatment is VATTreatment.ZERO_RATED:
			zero_rated += amount
		elif event.treatment is VATTreatment.EXEMPT:
			exempt += amount
		else:
			raise RuleValidationError("Ukjent MVA-behandling.")

	basis = taxable + zero_rated
	return RollingVatResult(
		as_of=as_of,
		window_start=window_start,
		taxable_turnover=taxable,
		zero_rated_turnover=zero_rated,
		exempt_turnover=exempt,
		registration_basis=basis,
		registration_required=basis > VAT_REGISTRATION_THRESHOLD,
	)


def vat_registration_threshold_crossings(
	events: Iterable[TurnoverEvent],
) -> tuple[VatRegistrationCrossing, ...]:
	"""Finner hver 2026-dato der dagens nettoomsetning passerer MVA-grensen.

	Skatteetaten angir at grensen gjelder en hvilken som helst tolv-månedersperiode
	og at leveringstidspunktet, ikke fakturadatoen, er avgjørende. Derfor vurderes
	hver faktisk leveringsdato, ikke bare datoen til siste innsendte faktura.
	En kreditnota føres som et negativt ``TurnoverEvent`` på korrigert
	leveringsdato og inngår før dagens grense vurderes.
	"""

	timeline = tuple(events)
	for event in timeline:
		if not isinstance(event, TurnoverEvent):
			raise RuleValidationError("Alle hendelser må være TurnoverEvent.")
		if not isinstance(event.occurred_on, date):
			raise RuleValidationError("Omsetningshendelsen må ha en dato.")
		_decimal_amount(event.amount, "Omsetningsbeløp", allow_negative=True)
		if not isinstance(event.treatment, VATTreatment):
			raise RuleValidationError("Ukjent MVA-behandling.")

	crossings = []
	for occurred_on in sorted({event.occurred_on for event in timeline if event.occurred_on.year == SUPPORTED_RULE_YEAR}):
		result = rolling_vat_registration_status(timeline, as_of=occurred_on)
		before_today = rolling_vat_registration_status(
			(event for event in timeline if event.occurred_on != occurred_on), as_of=occurred_on
		)
		if result.registration_required and not before_today.registration_required:
			crossings.append(
				VatRegistrationCrossing(
					occurred_on=occurred_on,
					window_start=result.window_start,
					registration_basis=result.registration_basis,
				)
			)
	return tuple(crossings)


def foreign_reverse_charge_status(
	purchases: Iterable[ForeignRemoteServicePurchase],
	*,
	period_end: date,
	registered_for_vat: bool,
	vat_rate: Decimal = Decimal("0.25"),
) -> ReverseChargeResult:
	"""Beregner omvendt avgiftsplikt for relevante utenlandske fjernleverbare tjenester.

	Kjøpene skal allerede være vurdert som relevante fjernleverbare tjenester
	med bruk i Norge. Registrerte har ingen beløpsgrense. Uregistrerte får plikt
	bare når samlet grunnlag i kvartalet er *over* 2 000 kroner eksklusive MVA.
	"""

	_require_supported_date(period_end)
	if not isinstance(registered_for_vat, bool):
		raise RuleValidationError("registered_for_vat må være bool.")
	rate = _decimal_amount(vat_rate, "MVA-sats")
	if rate > Decimal("1"):
		raise RuleValidationError("MVA-sats kan ikke overstige 100 prosent.")
	quarter_start, quarter_end = _quarter_bounds(period_end)
	basis = Decimal("0")
	for purchase in purchases:
		if not isinstance(purchase, ForeignRemoteServicePurchase):
			raise RuleValidationError("Alle kjøp må være ForeignRemoteServicePurchase.")
		amount = _decimal_amount(purchase.net_amount, "Kjøpsbeløp", allow_negative=True)
		if quarter_start <= purchase.purchased_on <= quarter_end:
			basis += amount

	liability = registered_for_vat or basis > REVERSE_CHARGE_UNREGISTERED_THRESHOLD
	output_vat = round_nok(basis * rate) if liability else Decimal("0.00")
	return ReverseChargeResult(
		quarter_start=quarter_start,
		quarter_end=quarter_end,
		registered_for_vat=registered_for_vat,
		relevant_purchase_basis=basis,
		liability_arises=liability,
		separate_return_required=not registered_for_vat and liability,
		output_vat=output_vat,
	)


def assess_asset(
	*,
	cost_basis: Decimal,
	expected_useful_life_months: int,
	physical_asset: bool,
	declines_in_value: bool,
	predominantly_income_producing: bool,
	as_of: date,
) -> AssetAssessment:
	"""Avgrenser direkte fradrag mot skattemessig aktivering av et driftsmiddel."""

	_require_supported_date(as_of)
	cost = _decimal_amount(cost_basis, "Kostpris")
	if isinstance(expected_useful_life_months, bool) or not isinstance(expected_useful_life_months, int):
		raise RuleValidationError("Forventet brukstid må oppgis som helt antall måneder.")
	if expected_useful_life_months < 0:
		raise RuleValidationError("Forventet brukstid kan ikke være negativ.")
	for name, flag in {
		"physical_asset": physical_asset,
		"declines_in_value": declines_in_value,
		"predominantly_income_producing": predominantly_income_producing,
	}.items():
		if not isinstance(flag, bool):
			raise RuleValidationError(f"{name} må være bool.")

	if not (physical_asset and declines_in_value and predominantly_income_producing):
		return AssetAssessment(
			treatment=AssetTreatment.OUTSIDE_SUPPORTED_SCOPE,
			cost_basis=cost,
			expected_useful_life_months=expected_useful_life_months,
			reason="Regelmotoren klassifiserer bare fysiske, verdiforringende driftsmidler i næring.",
		)
	if cost >= ASSET_COST_THRESHOLD and expected_useful_life_months >= 36:
		return AssetAssessment(
			treatment=AssetTreatment.ACTIVATE_AND_DEPRECIATE,
			cost_basis=cost,
			expected_useful_life_months=expected_useful_life_months,
			reason="Kostpris og forventet brukstid når begge lovens grenser.",
		)
	return AssetAssessment(
		treatment=AssetTreatment.DIRECT_EXPENSE,
		cost_basis=cost,
		expected_useful_life_months=expected_useful_life_months,
		reason="Minst én av grensene for aktivering er ikke nådd.",
	)


def asset_cost_basis(
	*, net_amount: Decimal, input_vat: Decimal, input_vat_deductible: bool
) -> Decimal:
	"""Gir kostpris der ikke-fradragsberettiget inngående MVA inngår i kostprisen."""

	net = _decimal_amount(net_amount, "Nettobeløp")
	vat = _decimal_amount(input_vat, "Inngående MVA")
	if not isinstance(input_vat_deductible, bool):
		raise RuleValidationError("input_vat_deductible må være bool.")
	return net if input_vat_deductible else net + vat


def calculate_saldo_pool(
	*,
	group: SaldoGroup,
	year_end: date,
	opening_balance: Decimal,
	acquisitions: Decimal = Decimal("0"),
	disposal_proceeds: Decimal = Decimal("0"),
	disposal_proceeds_taken_to_income: Decimal = Decimal("0"),
	requested_depreciation: Decimal | None = None,
	write_off_small_positive_balance: bool = False,
	additional_negative_balance_income: Decimal = Decimal("0"),
) -> SaldoPoolResult:
	"""Beregner saldogruppe a eller d for ett fullt 2026-inntektsår.

	Realisasjonsvederlag som ikke er valgt tatt direkte til inntekt nedskrives på
	saldoen. Positiv restsaldo under 30 000 kroner kan velges fullt fradragsført.
	Negativ restsaldo under 30 000 kroner skal inntektsføres fullt; ved 30 000
	kroner eller mer er minst gruppens sats pliktig inntektsføring.
	"""

	_require_year_end(year_end)
	if not isinstance(group, SaldoGroup):
		raise RuleValidationError("Kun saldogruppe a og d er støttet.")
	if not isinstance(write_off_small_positive_balance, bool):
		raise RuleValidationError("write_off_small_positive_balance må være bool.")
	rate = {SaldoGroup.A: Decimal("0.30"), SaldoGroup.D: Decimal("0.20")}[group]
	opening = _decimal_amount(opening_balance, "Inngående saldo", allow_negative=True)
	adds = _decimal_amount(acquisitions, "Anskaffelser")
	proceeds = _decimal_amount(disposal_proceeds, "Realisasjonsvederlag")
	direct_income = _decimal_amount(
		disposal_proceeds_taken_to_income, "Direkte inntektsført realisasjonsvederlag"
	)
	if direct_income > proceeds:
		raise RuleValidationError("Direkte inntektsført vederlag kan ikke overstige samlet vederlag.")
	additional_income = _decimal_amount(
		additional_negative_balance_income, "Ekstra inntektsføring av negativ saldo"
	)
	if requested_depreciation is not None:
		requested = _decimal_amount(requested_depreciation, "Ønsket avskrivning")
	else:
		requested = None

	balance = opening + adds - (proceeds - direct_income)
	depreciation = Decimal("0")
	negative_income = Decimal("0")
	if balance > 0:
		if additional_income:
			raise RuleValidationError("Ekstra negativ-saldo-inntekt krever negativ saldo.")
		if write_off_small_positive_balance:
			if balance >= SMALL_SALDO_THRESHOLD:
				raise RuleValidationError("Full fradragsføring av restsaldo krever saldo under 30 000 kroner.")
			maximum_deduction = balance
		else:
			maximum_deduction = balance * rate
		depreciation = maximum_deduction if requested is None else requested
		if depreciation > maximum_deduction:
			raise RuleValidationError("Ønsket avskrivning overstiger tillatt fradrag.")
		closing = balance - depreciation
	elif balance < 0:
		if requested is not None or write_off_small_positive_balance:
			raise RuleValidationError("Avskrivning og positiv-restsaldo-valg krever positiv saldo.")
		negative_amount = -balance
		mandatory_income = negative_amount if negative_amount < SMALL_SALDO_THRESHOLD else negative_amount * rate
		negative_income = mandatory_income + additional_income
		if negative_income > negative_amount:
			raise RuleValidationError("Inntektsføring kan ikke overstige negativ saldo.")
		closing = balance + negative_income
	else:
		if requested not in (None, Decimal("0")) or additional_income or write_off_small_positive_balance:
			raise RuleValidationError("Ingen årsjustering kan velges når saldoen er null.")
		closing = Decimal("0")

	return SaldoPoolResult(
		group=group,
		year_end=year_end,
		depreciation_rate=rate,
		opening_balance=opening,
		acquisitions=adds,
		disposal_proceeds=proceeds,
		disposal_proceeds_taken_to_income=direct_income,
		balance_before_year_end_adjustments=balance,
		depreciation_deduction=depreciation,
		negative_balance_income=negative_income,
		closing_balance=closing,
	)


def round_nok(amount: Decimal) -> Decimal:
	"""Avrunder et beløp til to desimaler med kommersiell halv-opp-avrunding.

	Dette er beløpsavrunding i beregningen, ikke avrunding til hele kroner i en
	konkret MVA-melding.
	"""

	return _decimal_amount(amount, "Beløp", allow_negative=True).quantize(NOK_MINOR_UNIT, ROUND_HALF_UP)


def _normalize_number(value: str) -> str | None:
	if not isinstance(value, str):
		return None
	if any(not (character.isdigit() or character in " .-") for character in value):
		return None
	normalized = "".join(character for character in value if character.isdigit())
	return normalized or None


def _mod11_check_digit_matches(value: str, weights: tuple[int, ...]) -> bool:
	weighted_sum = sum(int(digit) * weight for digit, weight in zip(value[:-1], weights, strict=True))
	check_digit = 11 - (weighted_sum % 11)
	if check_digit == 11:
		check_digit = 0
	return check_digit != 10 and check_digit == int(value[-1])


def _require_supported_date(value: date) -> None:
	if not isinstance(value, date):
		raise RuleValidationError("Dato må være datetime.date.")
	if value.year != SUPPORTED_RULE_YEAR:
		raise UnsupportedRuleDateError(
			f"Regelmotoren støtter bare datoer i {SUPPORTED_RULE_YEAR}, ikke {value.isoformat()}."
		)


def _require_year_end(value: date) -> None:
	_require_supported_date(value)
	if value.month != 12 or value.day != 31:
		raise RuleValidationError("Saldoberegning krever inntektsårets siste dato, 2026-12-31.")


def _one_year_before(value: date) -> date:
	try:
		return value.replace(year=value.year - 1)
	except ValueError:
		return value.replace(year=value.year - 1, day=28)


def _quarter_bounds(value: date) -> tuple[date, date]:
	quarter_start_month = ((value.month - 1) // 3) * 3 + 1
	quarter_end_month = quarter_start_month + 2
	quarter_end_day = monthrange(value.year, quarter_end_month)[1]
	return date(value.year, quarter_start_month, 1), date(value.year, quarter_end_month, quarter_end_day)


def _decimal_amount(value: Decimal, field_name: str, *, allow_negative: bool = False) -> Decimal:
	if isinstance(value, bool) or not isinstance(value, Decimal):
		raise RuleValidationError(f"{field_name} må oppgis som Decimal, ikke float eller int.")
	if not value.is_finite():
		raise RuleValidationError(f"{field_name} må være et endelig tall.")
	if not allow_negative and value < 0:
		raise RuleValidationError(f"{field_name} kan ikke være negativt.")
	return value
