"""Årsavslutning for avgrenset norsk ENK-regelsett i 2026.

Dette er ikke en full næringsspesifikasjon. Personinntekt, skjerming og private
korreksjoner må dokumenteres som særskilte kontrollpunkter før en rapport kan
markeres klar for kontroll eller manuelt levert.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from hashlib import sha256
from typing import Any

from enk_norge.norway_rules import SaldoGroup, calculate_saldo_pool

SUPPORTED_INCOME_YEAR = 2026
NOK_MINOR_UNIT = Decimal("0.01")


class YearEndError(ValueError):
	"""Data er ikke tilstrekkelige til et sporbar årsoppgjør."""


@dataclass(frozen=True, slots=True)
class LedgerEntry:
	account: str
	debit: Decimal
	credit: Decimal
	voucher_type: str = ""
	voucher_no: str = ""
	posting_date: date | None = None


@dataclass(frozen=True, slots=True)
class TaxAdjustment:
	effect: Decimal
	reason: str
	reference_doctype: str
	reference_name: str


@dataclass(frozen=True, slots=True)
class TaxPoolSummary:
	name: str
	depreciation_deduction: Decimal
	negative_balance_income: Decimal
	disposal_proceeds: Decimal = Decimal("0")
	disposal_proceeds_taken_to_income: Decimal = Decimal("0")
	source_hash: str = ""


@dataclass(frozen=True, slots=True)
class PersonalIncomeInput:
	"""Poster i Skatteetatens E-5-4.2; beløp er dokumenterte årsbeløp."""

	capital_return_base: Decimal
	capital_income: Decimal = Decimal("0")
	financial_gains: Decimal = Decimal("0")
	capital_costs: Decimal = Decimal("0")
	financial_losses: Decimal = Decimal("0")
	private_debt_interest: Decimal = Decimal("0")
	qualifying_business_debt: Decimal = Decimal("0")
	qualifying_business_debt_interest: Decimal = Decimal("0")
	special_deductions: Decimal = Decimal("0")
	shielding_rate: Decimal | None = None
	documented_shielding: Decimal | None = None
	carried_forward_negative: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class PersonalIncomeCalculation:
	business_profit: Decimal
	capital_income_deduction: Decimal
	capital_cost_addback: Decimal
	interest_addback: Decimal
	special_deduction_addback: Decimal
	shielding: Decimal
	person_income_before_carryforward: Decimal
	carried_forward_negative_used: Decimal
	person_income: Decimal
	remaining_negative_carryforward: Decimal


def calculate_personal_income(
	business_profit: Decimal, inputs: PersonalIncomeInput
) -> PersonalIncomeCalculation:
	"""Foretaksmodellen etter E-5-4.2, avgrenset til dokumenterte poster."""
	profit = _to_decimal(business_profit, "Skattemessig næringsresultat", allow_negative=True)
	base = _amount(inputs.capital_return_base, "Kapitalavkastningsgrunnlag")
	if inputs.documented_shielding is not None:
		shielding = _amount(inputs.documented_shielding, "Dokumentert skjerming")
	elif inputs.shielding_rate is not None:
		rate = _to_decimal(inputs.shielding_rate, "Skjermingsrente")
		if not Decimal("0") <= rate <= Decimal("1"):
			raise YearEndError("Skjermingsrente må være mellom 0 og 1.")
		shielding = _money(base * rate)
	elif base == 0:
		shielding = Decimal("0")
	else:
		raise YearEndError(
			"Dokumentert skjermingsbeløp eller skjermingsrente kreves når grunnlaget ikke er null."
		)
	minus = _amount(inputs.capital_income, "Kapitalinntekt") + _amount(
		inputs.financial_gains, "Finansgevinst"
	)
	plus = (
		_amount(inputs.capital_costs, "Kapitalkostnad")
		+ _amount(inputs.financial_losses, "Finanstap")
		+ _amount(inputs.private_debt_interest, "Privat gjeldsrente")
		+ _amount(inputs.special_deductions, "Særskilt fradrag")
	)
	debt = _amount(inputs.qualifying_business_debt, "Kvalifiserende foretaks­gjeld")
	interest = _amount(inputs.qualifying_business_debt_interest, "Rente på kvalifiserende foretaks­gjeld")
	interest_addback = Decimal("0") if not debt else _money(interest * max(Decimal("0"), debt - base) / debt)
	negative = _amount(inputs.carried_forward_negative, "Fremførbar negativ personinntekt")
	before = profit - minus + plus + interest_addback - shielding
	used = min(max(Decimal("0"), before), negative)
	person_income = before - used
	remaining_negative = negative - used + max(Decimal("0"), -before)
	return PersonalIncomeCalculation(
		*map(
			_money,
			(
				profit,
				minus,
				plus,
				interest_addback,
				_amount(inputs.special_deductions, "Særskilt fradrag"),
				shielding,
				before,
				used,
				person_income,
				remaining_negative,
			),
		)
	)


@dataclass(frozen=True, slots=True)
class YearEndCalculation:
	operating_income: Decimal
	operating_expenses: Decimal
	accounting_profit: Decimal
	book_depreciation: Decimal
	tax_depreciation: Decimal
	negative_balance_income: Decimal
	manual_tax_adjustments: Decimal
	taxable_business_profit: Decimal
	asset_balance: Decimal
	liability_balance: Decimal
	equity_balance: Decimal
	net_assets: Decimal
	equity_reconciliation_difference: Decimal
	book_disposal_result: Decimal
	direct_disposal_income: Decimal


def parse_source_references(
	value: str | list[dict[str, Any]] | None, expected_amount: Decimal, label: str
) -> list[dict[str, str]]:
	"""Leser kildebilag med ``doctype``, ``name`` og ``amount`` uten Frappe-avhengighet."""

	expected = _amount(expected_amount, label)
	if value in (None, ""):
		references: Any = []
	elif isinstance(value, str):
		try:
			references = json.loads(value)
		except json.JSONDecodeError as error:
			raise YearEndError(f"{label} må være gyldig JSON.") from error
	else:
		references = value
	if not isinstance(references, list):
		raise YearEndError(f"{label} må være en JSON-liste.")
	if expected and not references:
		raise YearEndError(f"{label} krever minst ett kildebilag.")
	normalized: list[dict[str, str]] = []
	total = Decimal("0")
	for reference in references:
		if not isinstance(reference, dict):
			raise YearEndError(f"{label} inneholder et ugyldig kildebilag.")
		doctype = reference.get("doctype")
		name = reference.get("name")
		if (
			not isinstance(doctype, str)
			or not doctype.strip()
			or not isinstance(name, str)
			or not name.strip()
		):
			raise YearEndError(f"{label} krever doctype og name for hvert kildebilag.")
		amount = _amount(_to_decimal(reference.get("amount"), f"{label} beløp"), f"{label} beløp")
		total += amount
		normalized.append({"doctype": doctype, "name": name, "amount": _decimal_text(amount)})
	if _money(total) != _money(expected):
		raise YearEndError(f"Summen av {label.lower()} må stemme med beløpet i saldogruppen.")
	return normalized


def calculate_pool_from_values(values: Mapping[str, Any]):
	"""Anvender den testede 2026-regelmotoren på en lagret saldogruppe."""

	income_year = _income_year(values.get("income_year"))
	try:
		group = SaldoGroup(str(values.get("saldo_group")))
	except ValueError as error:
		raise YearEndError("Kun saldogruppe a og d er støttet.") from error
	return calculate_saldo_pool(
		group=group,
		year_end=date(income_year, 12, 31),
		opening_balance=_to_decimal(values.get("opening_balance"), "Inngående saldo", allow_negative=True),
		acquisitions=_to_decimal(values.get("acquisitions", "0"), "Anskaffelser"),
		disposal_proceeds=_to_decimal(values.get("disposal_proceeds", "0"), "Realisasjonsvederlag"),
		disposal_proceeds_taken_to_income=_to_decimal(
			values.get("disposal_proceeds_taken_to_income", "0"), "Direkte inntektsført vederlag"
		),
		requested_depreciation=(
			_to_decimal(values["requested_depreciation"], "Ønsket avskrivning")
			if values.get("requested_depreciation") not in (None, "")
			else None
		),
		write_off_small_positive_balance=bool(values.get("write_off_small_positive_balance", False)),
		additional_negative_balance_income=_to_decimal(
			values.get("additional_negative_balance_income", "0"), "Ekstra inntektsføring"
		),
	)


def calculate_year_end(
	entries: Iterable[LedgerEntry],
	*,
	account_categories: Mapping[str, str],
	depreciation_account: str,
	asset_gain_account: str | None = None,
	asset_loss_account: str | None = None,
	tax_pools: Iterable[TaxPoolSummary] = (),
	tax_adjustments: Iterable[TaxAdjustment] = (),
) -> YearEndCalculation:
	"""Beregner årsresultat og skattemessige, dokumenterte korreksjoner.

	Balansekategorier summeres til og med 2026-12-31. Resultatkategorier må være
	begrenset til inntektsåret av kalleren. Ukjente kontoer avvises.
	"""

	balances = {category: Decimal("0") for category in ("Asset", "Liability", "Equity", "Income", "Expense")}
	book_depreciation = Decimal("0")
	book_disposal_result = Decimal("0")
	for entry in entries:
		if not isinstance(entry, LedgerEntry):
			raise YearEndError("Alle hovedbokslinjer må være LedgerEntry.")
		category = account_categories.get(entry.account)
		if category not in balances:
			raise YearEndError(f"Kontoen {entry.account} mangler årsoppgjørskategori.")
		debit = _to_decimal(entry.debit, "Debet")
		credit = _to_decimal(entry.credit, "Kredit")
		if debit < 0 or credit < 0:
			raise YearEndError("Hovedbokslinjer kan ikke ha negative debet- eller kreditbeløp.")
		if category in ("Asset", "Expense"):
			net = debit - credit
		else:
			net = credit - debit
		balances[category] += net
		if entry.account in (asset_gain_account, asset_loss_account):
			book_disposal_result += credit - debit
		if entry.account == depreciation_account:
			book_depreciation += debit - credit

	tax_depreciation = Decimal("0")
	direct_disposal_income = Decimal("0")
	negative_balance_income = Decimal("0")
	for pool in tax_pools:
		if not isinstance(pool, TaxPoolSummary):
			raise YearEndError("Alle saldogrupper må være TaxPoolSummary.")
		direct_disposal_income += _amount(
			pool.disposal_proceeds_taken_to_income, "Direkte skattemessig inntekt ved avgang"
		)
		tax_depreciation += _amount(pool.depreciation_deduction, "Skattemessig avskrivning")
		negative_balance_income += _amount(pool.negative_balance_income, "Inntektsføring av negativ saldo")

	manual_adjustment_total = Decimal("0")
	for adjustment in tax_adjustments:
		if not isinstance(adjustment, TaxAdjustment):
			raise YearEndError("Alle skattekorrigeringer må være TaxAdjustment.")
		if (
			not adjustment.reason.strip()
			or not adjustment.reference_doctype.strip()
			or not adjustment.reference_name.strip()
		):
			raise YearEndError("Skattekorrigering krever begrunnelse og kildebilag.")
		manual_adjustment_total += _to_decimal(adjustment.effect, "Skattekorrigering", allow_negative=True)

	operating_income = balances["Income"]
	operating_expenses = balances["Expense"]
	accounting_profit = operating_income - operating_expenses
	taxable_business_profit = (
		accounting_profit
		+ book_depreciation
		- tax_depreciation
		+ negative_balance_income
		- book_disposal_result
		+ direct_disposal_income
		+ manual_adjustment_total
	)
	net_assets = balances["Asset"] - balances["Liability"]
	equity_reconciliation_difference = net_assets - balances["Equity"] - accounting_profit
	return YearEndCalculation(
		book_disposal_result=_money(book_disposal_result),
		direct_disposal_income=_money(direct_disposal_income),
		operating_income=_money(operating_income),
		operating_expenses=_money(operating_expenses),
		accounting_profit=_money(accounting_profit),
		book_depreciation=_money(book_depreciation),
		tax_depreciation=_money(tax_depreciation),
		negative_balance_income=_money(negative_balance_income),
		manual_tax_adjustments=_money(manual_adjustment_total),
		taxable_business_profit=_money(taxable_business_profit),
		asset_balance=_money(balances["Asset"]),
		liability_balance=_money(balances["Liability"]),
		equity_balance=_money(balances["Equity"]),
		net_assets=_money(net_assets),
		equity_reconciliation_difference=_money(equity_reconciliation_difference),
	)


def calculate_purchase_tax_adjustment(
	expense_amounts: Iterable[Decimal], tax_deductible_fraction: Decimal, *, is_credit_note: bool
) -> Decimal:
	"""Beregner skattemessig tilbakeføring fra kostnadslinjer, med fortegn for kreditnota."""

	fraction = _to_decimal(tax_deductible_fraction, "Skattemessig fradragsandel")
	if fraction > Decimal("1"):
		raise YearEndError("Skattemessig fradragsandel må være mellom 0 og 1.")
	base = abs(
		sum(
			(_to_decimal(amount, "Kostnadslinje", allow_negative=True) for amount in expense_amounts),
			Decimal("0"),
		)
	)
	effect = _money(base * (Decimal("1") - fraction))
	return -effect if is_credit_note else effect


def snapshot_payload(
	calculation: YearEndCalculation,
	*,
	income_year: int,
	entries: Iterable[LedgerEntry],
	tax_pools: Iterable[TaxPoolSummary],
	tax_adjustments: Iterable[TaxAdjustment],
	controls: Mapping[str, bool],
) -> dict[str, Any]:
	"""Gir et deterministisk, serialiserbart grunnlag for hash og revisjon."""

	_income_year(income_year)
	return {
		"income_year": income_year,
		"calculation": _json_value(asdict(calculation)),
		"entries": sorted(
			(_json_value(asdict(entry)) for entry in entries),
			key=lambda entry: (entry["account"], entry["voucher_type"], entry["voucher_no"]),
		),
		"tax_pools": sorted((_json_value(asdict(pool)) for pool in tax_pools), key=lambda pool: pool["name"]),
		"tax_adjustments": sorted(
			(_json_value(asdict(adjustment)) for adjustment in tax_adjustments),
			key=lambda adjustment: (
				adjustment["reference_doctype"],
				adjustment["reference_name"],
				adjustment["reason"],
			),
		),
		"controls": {key: bool(value) for key, value in sorted(controls.items())},
	}


def snapshot_hash(payload: Mapping[str, Any]) -> str:
	"""Hash av kanonisk JSON slik at en lagret beregning kan kontrolleres senere."""

	canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
	return sha256(canonical.encode("utf-8")).hexdigest()


def validate_pool_document(doc: Any) -> None:
	"""Frappe-validering for dokumentert saldogruppe og kildebilag."""

	frappe = _frappe()
	from enk_norge.setup import get_settings

	settings = get_settings(doc.company, write=True)
	frappe.db.sql("select name from `tabCompany` where name=%s for update", doc.company)
	pool_values = doc.as_dict()
	for field in (
		"opening_balance",
		"acquisitions",
		"disposal_proceeds",
		"disposal_proceeds_taken_to_income",
		"requested_depreciation",
		"additional_negative_balance_income",
	):
		if pool_values.get(field) not in (None, ""):
			pool_values[field] = str(pool_values[field])
	calculation = calculate_pool_from_values(pool_values)
	opening_proof = None
	if _frappe_decimal(doc.opening_balance or "0", "Inngående saldo", allow_negative=True):
		if not doc.get("opening_source_file"):
			frappe.throw("Inngående skattesaldo krever et privat vedlegg fra tidligere saldooppgjør.")
		file = frappe.get_doc("File", doc.opening_source_file)
		file.check_permission("read")
		if not file.is_private:
			frappe.throw("Dokumentasjonen av inngående saldo må være privat.")
		content = file.get_content()
		opening_proof = dict(
			file=file.name,
			sha256=sha256(content.encode() if isinstance(content, str) else content).hexdigest(),
			amount=str(doc.opening_balance),
		)
	acquisitions = _frappe_decimal(doc.acquisitions or "0", "Anskaffelser")
	proceeds = _frappe_decimal(doc.disposal_proceeds or "0", "Realisasjonsvederlag")
	acquisition_sources = parse_source_references(
		doc.acquisition_sources_json, acquisitions, "Kildebilag for anskaffelser"
	)
	disposal_sources = parse_source_references(doc.disposal_sources_json, proceeds, "Kildebilag for avgang")
	for reference in acquisition_sources + disposal_sources:
		_validate_source_document_company(reference, doc.company)
	_validate_acquisition_allocations(doc, acquisition_sources, settings)
	_validate_disposal_allocations(doc, disposal_sources, settings)

	duplicates = frappe.get_all(
		"ENK Tax Pool",
		filters={"company": doc.company, "income_year": doc.income_year, "saldo_group": doc.saldo_group},
		pluck="name",
	)
	if any(name != doc.name for name in duplicates):
		frappe.throw("Det finnes allerede en saldogruppe for dette foretaket og inntektsåret.")
	doc.acquisition_sources_json = _json_dump(acquisition_sources)
	doc.disposal_sources_json = _json_dump(disposal_sources)
	doc.balance_before_year_end_adjustments = _decimal_text(calculation.balance_before_year_end_adjustments)
	doc.depreciation_deduction = _decimal_text(calculation.depreciation_deduction)
	doc.negative_balance_income = _decimal_text(calculation.negative_balance_income)
	doc.closing_balance = _decimal_text(calculation.closing_balance)
	doc.source_hash = snapshot_hash(
		{
			"opening_proof": opening_proof,
			"acquisition_sources": acquisition_sources,
			"disposal_sources": disposal_sources,
			"disposal_proceeds_taken_to_income": _decimal_text(
				_frappe_decimal(doc.disposal_proceeds_taken_to_income or "0", "Direkte inntektsført vederlag")
			),
		}
	)
	doc.calculated_at = frappe.utils.now_datetime()


def _validate_acquisition_allocations(doc: Any, sources: list[dict[str, str]], settings: Any) -> None:
	"""En anskaffelse kan fordeles mellom grupper, men ikke trekkes fra flere ganger."""
	frappe = _frappe()
	allocated: dict[tuple[str, str], Decimal] = {}
	for pool in frappe.get_all(
		"ENK Tax Pool",
		filters={"company": doc.company, "income_year": doc.income_year},
		fields=["name", "acquisition_sources_json"],
	):
		if pool.name == doc.name:
			continue
		for source in json.loads(pool.acquisition_sources_json or "[]"):
			key = (source["doctype"], source["name"])
			allocated[key] = allocated.get(key, Decimal(0)) + _to_decimal(source["amount"], "Anskaffelse")
	for source in sources:
		key = (source["doctype"], source["name"])
		amount = _to_decimal(source["amount"], "Anskaffelse")
		rows = frappe.db.sql(
			"""select coalesce(sum(debit-credit),0) amount from `tabGL Entry`
			where company=%s and voucher_type=%s and voucher_no=%s and account=%s
			and is_cancelled=0 and posting_date between %s and %s""",
			(
				doc.company,
				*key,
				settings.asset_account,
				f"{doc.income_year}-01-01",
				f"{doc.income_year}-12-31",
			),
			as_dict=True,
		)
		available = _frappe_decimal(rows[0].amount, "Bokført anskaffelse", allow_negative=True)
		if available <= 0 or allocated.get(key, Decimal(0)) + amount > available:
			frappe.throw(
				"Anskaffelsen overstiger årets bokførte aktivering eller er allerede fordelt til en annen saldogruppe."
			)


def _validate_disposal_allocations(doc: Any, sources: list[dict[str, str]], settings: Any) -> None:
	"""Avgang må være en faktisk, dokumentert Asset Disposal-føring uten dobbelt spor."""
	frappe = _frappe()
	proceeds = _frappe_decimal(doc.disposal_proceeds or "0", "Realisasjonsvederlag")
	direct_income = _frappe_decimal(
		doc.disposal_proceeds_taken_to_income or "0", "Direkte inntektsført realisasjonsvederlag"
	)
	if not proceeds:
		return
	if direct_income > proceeds:
		frappe.throw("Direkte inntektsført vederlag kan ikke overstige realisasjonsvederlaget.")
	used_sources = {
		(source["doctype"], source["name"])
		for pool in frappe.get_all(
			"ENK Tax Pool",
			filters={"company": doc.company, "income_year": doc.income_year},
			fields=["name", "disposal_sources_json"],
		)
		if pool.name != doc.name
		for source in json.loads(pool.disposal_sources_json or "[]")
	}
	for source in sources:
		key = (source["doctype"], source["name"])
		if key in used_sources:
			frappe.throw("Et avgangsbilag kan bare brukes i én saldogruppe for samme inntektsår.")
		if source["doctype"] != "Journal Entry":
			frappe.throw("Avgang støttes bare med et bokført Asset Disposal-bilag.")
		entry = frappe.get_doc("Journal Entry", source["name"])
		if entry.voucher_type != "Asset Disposal":
			frappe.throw("Avgangskilden må være et Asset Disposal-bilag.")
		if not frappe.db.exists(
			"File",
			{"attached_to_doctype": "Journal Entry", "attached_to_name": entry.name, "is_private": 1},
		):
			frappe.throw("Avgangsbilaget må ha et privat kildebilag som dokumenterer salg eller uttak.")
		rows = frappe.get_all(
			"GL Entry",
			filters={
				"company": doc.company,
				"voucher_type": "Journal Entry",
				"voucher_no": entry.name,
				"posting_date": ["between", [f"{doc.income_year}-01-01", f"{doc.income_year}-12-31"]],
				"is_cancelled": 0,
			},
			fields=["account", "debit", "credit"],
			limit_page_length=0,
		)
		allowed_accounts = {
			settings.asset_account,
			settings.asset_gain_account,
			settings.asset_loss_account,
			settings.bank_ledger_account,
			settings.withdrawal_account,
		}
		if not rows or any(row.account not in allowed_accounts for row in rows):
			frappe.throw(
				"Avgangsbilaget kan bare inneholde bank eller uttak, driftsmiddel og direkte inntekt."
			)
		asset_credit = sum(
			(
				_frappe_decimal(row.credit, "Kredit") - _frappe_decimal(row.debit, "Debet")
				for row in rows
				if row.account == settings.asset_account
			),
			Decimal("0"),
		)
		income_credit = sum(
			(
				_frappe_decimal(row.credit, "Kredit") - _frappe_decimal(row.debit, "Debet")
				for row in rows
				if row.account in (settings.asset_gain_account, settings.asset_loss_account)
			),
			Decimal("0"),
		)
		consideration_debit = sum(
			(
				_frappe_decimal(row.debit, "Debet") - _frappe_decimal(row.credit, "Kredit")
				for row in rows
				if row.account in {settings.bank_ledger_account, settings.withdrawal_account}
			),
			Decimal("0"),
		)
		amount = _to_decimal(source["amount"], "Realisasjonsvederlag")
		if (
			_money(consideration_debit) != _money(amount)
			or asset_credit < 0
			or _money(income_credit) != _money(amount - asset_credit)
		):
			frappe.throw(
				"Avgangsbilaget må fjerne dokumentert bokført verdi og avstemme gevinst eller tap mot vederlaget."
			)


def validate_year_report_document(doc: Any) -> None:
	"""Hindrer at dokument-API-et kan late som om rapporten er kontrollert eller levert."""

	frappe = _frappe()
	from enk_norge.setup import get_settings

	get_settings(doc.company, write=True)
	_income_year(doc.income_year)
	old = doc.get_doc_before_save()
	if old and old.status == "Manually filed":
		frappe.throw("En manuelt levert årsrapport kan ikke endres. Opprett en korrigerende revisjon.")
	if doc.status in ("Draft", "Ready for review"):
		if not doc.flags.enk_year_report_build:
			frappe.throw("Årsrapportens status og snapshot kan bare opprettes via årsoppgjørsberegningen.")
		_validate_report_snapshot(doc)
	if doc.status == "Manually filed":
		if not old or old.status != "Ready for review" or not doc.flags.enk_year_report_filing:
			frappe.throw("Bare en klar årsrapport kan markeres manuelt levert via årsoppgjørsflyten.")
		_validate_report_snapshot(doc)
		_validate_private_receipt(doc)


def _validate_report_snapshot(report: Any) -> None:
	"""Kontrollerer både aktivt og historisk hashgrunnlag før status kan brukes."""
	frappe = _frappe()
	try:
		payload = json.loads(report.snapshot_json or "")
	except json.JSONDecodeError:
		frappe.throw("Årsrapportens snapshot må være gyldig JSON.")
	if not isinstance(payload, dict) or snapshot_hash(payload) != report.snapshot_hash:
		frappe.throw("Årsrapportens snapshot-hash stemmer ikke med beregningen.")
	for field, payload_key in (
		("personal_income_inputs_json", "personal_income_inputs"),
		("person_income_result_json", "personal_income_result"),
	):
		try:
			stored_value = json.loads(report.get(field) or "null")
		except json.JSONDecodeError:
			frappe.throw(f"{field} må være gyldig JSON.")
		if stored_value != payload.get(payload_key):
			frappe.throw("Personinntektsfeltene stemmer ikke med årsrapportens snapshot.")
	for revision in _parse_snapshot_history(report.snapshot_history_json):
		if not isinstance(revision, dict):
			frappe.throw("Historisk årsrapport-snapshot er ugyldig.")
		stored_hash = revision.get("snapshot_hash")
		stored_payload = revision.get("snapshot_json")
		if not isinstance(stored_payload, dict) or not isinstance(stored_hash, str):
			frappe.throw("Historisk årsrapport-snapshot er ugyldig.")
		if snapshot_hash(stored_payload) != stored_hash:
			frappe.throw("Historisk årsrapport-snapshot har feil hash.")


def _validate_private_receipt(report: Any) -> None:
	frappe = _frappe()
	if report.manual_filing_status != "Manually filed" or not report.private_receipt_file:
		frappe.throw("Manuell levering krever privat leveringskvittering.")
	try:
		receipt = frappe.get_doc("File", report.private_receipt_file)
	except Exception:
		frappe.throw("Leveringskvitteringen finnes ikke.")
	receipt.check_permission("read")
	if (
		not receipt.is_private
		or receipt.attached_to_doctype != "ENK Year Report"
		or receipt.attached_to_name != report.name
	):
		frappe.throw(
			"Leveringskvitteringen må være privat, knyttet til denne rapporten og lesbar for brukeren."
		)


# Frappe-API. Importeres først ved kall slik at kjerneregler kan testes uten Frappe.
def build_year_report(
	company: str,
	income_year: int | str = SUPPORTED_INCOME_YEAR,
	tax_adjustments: Any = None,
	controls: Any = None,
	personal_income_inputs: Any = None,
) -> dict[str, Any]:
	"""Oppretter en ny revisjon av årsrapporten når den ikke er manuelt levert."""

	frappe = _frappe()
	from enk_norge.setup import get_settings

	year = _income_year(income_year)
	settings = get_settings(company, write=True)
	manual_adjustments = _parse_adjustments(tax_adjustments, company)
	automatic_adjustments = _load_purchase_tax_adjustments(company, year, manual_adjustments)
	adjustments = manual_adjustments + automatic_adjustments
	control_values = _parse_controls(controls)
	frappe.db.sql("select name from `tabCompany` where name=%s for update", company)
	previous = _find_year_report(company, year)
	if previous:
		previous.check_permission("write")
		if controls is None:
			control_values = _controls_from_report(previous)

	entries = _load_gl_entries(company, year)
	categories = {row.account: row.tax_category for row in settings.accounts}
	pools = _load_tax_pools(company, year)
	_validate_disposal_coverage(company, year, settings)
	calculation = calculate_year_end(
		entries,
		account_categories=categories,
		depreciation_account=settings.depreciation_account,
		asset_gain_account=settings.asset_gain_account,
		asset_loss_account=settings.asset_loss_account,
		tax_pools=pools,
		tax_adjustments=adjustments,
	)
	if personal_income_inputs is None and previous and previous.personal_income_inputs_json:
		personal_income_inputs = previous.personal_income_inputs_json
	personal = _parse_personal_income_inputs(personal_income_inputs)
	personal_result = (
		calculate_personal_income(calculation.taxable_business_profit, personal) if personal else None
	)
	clarifications = _open_clarifications(calculation, control_values)
	if calculation.taxable_business_profit > 0 and personal_result is None:
		clarifications.append("Personinntekt mangler for positivt skattemessig næringsresultat.")
	payload = snapshot_payload(
		calculation,
		income_year=year,
		entries=entries,
		tax_pools=pools,
		tax_adjustments=adjustments,
		controls=control_values,
	)
	payload["return_basis"] = _return_basis(entries, settings.accounts)
	payload["personal_income_inputs"] = _json_value(asdict(personal)) if personal else None
	payload["personal_income_result"] = _json_value(asdict(personal_result)) if personal_result else None
	report = _store_year_report(
		previous=previous,
		company=company,
		income_year=year,
		calculation=calculation,
		adjustments=adjustments,
		controls=control_values,
		clarifications=clarifications,
		payload=payload,
		personal=personal,
		personal_result=personal_result,
	)
	return _report_response(report)


def get_year_report(company: str, income_year: int | str = SUPPORTED_INCOME_YEAR) -> dict[str, Any]:
	"""Henter årsrapport for et foretak brukeren har tilgang til."""

	from enk_norge.setup import get_settings

	year = _income_year(income_year)
	get_settings(company)
	report = _find_year_report(company, year)
	if not report:
		raise YearEndError("Årsrapporten finnes ikke.")
	report.check_permission("read")
	return _report_response(report)


def mark_year_report_manually_filed(
	company: str, income_year: int | str, private_receipt_file: str
) -> dict[str, Any]:
	"""Markerer en klar rapport som levert når den har privat kvittering."""

	frappe = _frappe()
	from enk_norge.setup import get_settings

	year = _income_year(income_year)
	get_settings(company, write=True)
	report = _find_year_report(company, year)
	if not report:
		frappe.throw("Årsrapporten finnes ikke.")
	report.check_permission("write")
	if report.status != "Ready for review":
		frappe.throw("Årsrapporten må være klar for kontroll før den kan markeres levert.")
	report.status = "Manually filed"
	report.manual_filing_status = "Manually filed"
	report.private_receipt_file = private_receipt_file
	report.manually_filed_at = frappe.utils.now_datetime()
	report.flags.enk_year_report_filing = True
	report.save()
	return _report_response(report)


def create_depreciation_journal_entry_draft(company: str, income_year: int | str) -> dict[str, str]:
	"""Lager bare et JE-utkast for udekket bokført avskrivning, aldri en innsending."""

	frappe = _frappe()
	from enk_norge.setup import get_settings

	year = _income_year(income_year)
	settings = get_settings(company, write=True)
	report = _find_year_report(company, year)
	if not report or report.status == "Manually filed":
		frappe.throw("Velg en ikke-levert årsrapport før du lager avskrivningsutkast.")
	entries = _load_gl_entries(company, year)
	categories = {row.account: row.tax_category for row in settings.accounts}
	current_book_depreciation = calculate_year_end(
		entries,
		account_categories=categories,
		depreciation_account=settings.depreciation_account,
	).book_depreciation
	remaining = (
		_frappe_decimal(report.tax_depreciation, "Skattemessig avskrivning") - current_book_depreciation
	)
	available = frappe.db.sql(
		"select coalesce(sum(debit-credit),0) from `tabGL Entry` where company=%s and account=%s and is_cancelled=0 and posting_date<=%s",
		(company, settings.asset_account, f"{year}-12-31"),
	)[0][0]
	remaining = min(remaining, Decimal(str(available)))
	if remaining <= 0:
		frappe.throw("Rapporten har ingen udekket avskrivning å foreslå som bilag.")
	frappe.has_permission("Journal Entry", "create", throw=True)
	remark = f"ENK avskrivningsutkast {report.name} snapshot {report.snapshot_hash}"
	drafts = frappe.get_list(
		"Journal Entry",
		filters={
			"company": company,
			"docstatus": 0,
			"voucher_type": "Depreciation Entry",
			"posting_date": f"{year}-12-31",
			"user_remark": ["like", "ENK avskrivningsutkast %"],
		},
		fields=["name", "user_remark", "total_debit"],
		limit_page_length=0,
	)
	if drafts:
		current = next((draft for draft in drafts if draft.user_remark == remark), None)
		if current:
			return {"doctype": "Journal Entry", "name": current.name, "amount": _decimal_text(remaining)}
		frappe.throw(
			"Et avskrivningsutkast fra et eldre årsrapport-snapshot finnes allerede. Kontroller eller avbryt det før nytt utkast lages."
		)
	entry = frappe.get_doc(
		dict(
			doctype="Journal Entry",
			company=company,
			posting_date=f"{year}-12-31",
			voucher_type="Depreciation Entry",
			user_remark=remark,
			accounts=[
				dict(
					account=settings.depreciation_account, debit_in_account_currency=_decimal_text(remaining)
				),
				dict(account=settings.asset_account, credit_in_account_currency=_decimal_text(remaining)),
			],
		)
	)
	entry.insert()
	from enk_norge.posting_contract import seal_draft

	entry.db_set("enk_posting_contract", seal_draft(entry))
	return {"doctype": entry.doctype, "name": entry.name, "amount": _decimal_text(remaining)}


def create_asset_disposal_journal_entry_draft(
	company: str,
	posting_date: str,
	proceeds: Any,
	direct_income: Any = "0",
	disposition: str = "Sale",
	description: str = "",
	private_source_file: str = "",
	carrying_amount: Any = None,
) -> dict[str, Any]:
	"""Lager et begrenset Asset Disposal-utkast med virkelig vederlag og privat bevis."""
	frappe = _frappe()
	from enk_norge.setup import get_settings

	settings = get_settings(company, write=True)
	if not posting_date:
		frappe.throw("Oppgi dato for salg eller uttak.")
	when = frappe.utils.getdate(posting_date)
	if when.year != SUPPORTED_INCOME_YEAR:
		frappe.throw("Driftsmiddelavgang støttes bare i inntektsåret 2026.")
	if settings.vat_registered and when >= frappe.utils.getdate(settings.vat_registration_date):
		frappe.throw("Salg eller uttak av driftsmiddel etter MVA-registrering krever egen MVA-flyt.")
	if disposition not in ("Sale", "Withdrawal"):
		frappe.throw("Velg salg eller uttak av driftsmiddel.")
	amount = _frappe_decimal(proceeds, "Vederlag")
	direct = _frappe_decimal(direct_income, "Direkte inntektsført realisasjonsvederlag")
	if amount <= 0 or direct > amount:
		frappe.throw("Vederlaget må være positivt, og direkte inntekt kan ikke overstige vederlaget.")
	if not (description or "").strip():
		frappe.throw("Oppgi hva som er solgt eller tatt ut.")
	if not private_source_file:
		frappe.throw("Salg eller uttak krever et privat kildebilag.")
	try:
		source_file = frappe.get_doc("File", private_source_file)
	except Exception:
		frappe.throw("Kildebilaget finnes ikke.")
	source_file.check_permission("read")
	source_file.check_permission("write")
	if not source_file.is_private or source_file.attached_to_doctype or source_file.attached_to_name:
		frappe.throw("Kildebilaget må være privat og ikke allerede knyttet til et annet dokument.")
	frappe.has_permission("Journal Entry", "create", throw=True)
	frappe.db.sql("select name from `tabCompany` where name=%s for update", company)
	if carrying_amount is None:
		frappe.throw("Oppgi dokumentert bokført verdi for utstyret som tas ut av balansen.")
	carrying = _frappe_decimal(carrying_amount, "Bokført verdi")
	available = frappe.db.sql(
		"select coalesce(sum(debit-credit),0) from `tabGL Entry` where company=%s and account=%s and is_cancelled=0 and posting_date<=%s",
		(company, settings.asset_account, when),
	)[0][0]
	if carrying > Decimal(str(available)):
		frappe.throw("Bokført verdi overstiger driftsmiddelkontoens disponible balanse.")
	debit_account = settings.bank_ledger_account if disposition == "Sale" else settings.withdrawal_account
	accounts = [dict(account=debit_account, debit_in_account_currency=_decimal_text(amount))]
	if carrying:
		accounts.append(
			dict(account=settings.asset_account, credit_in_account_currency=_decimal_text(carrying))
		)
	gain = amount - carrying
	if gain:
		accounts.append(
			dict(
				account=settings.asset_gain_account if gain > 0 else settings.asset_loss_account,
				credit_in_account_currency=_decimal_text(max(gain, Decimal(0))),
				debit_in_account_currency=_decimal_text(max(-gain, Decimal(0))),
				cost_center=frappe.get_cached_value("Company", company, "cost_center"),
			)
		)
	entry = frappe.get_doc(
		dict(
			doctype="Journal Entry",
			company=company,
			posting_date=when,
			voucher_type="Asset Disposal",
			user_remark=(
				f"ENK {'salg' if disposition == 'Sale' else 'uttak'} av driftsmiddel: "
				f"{description.strip()}. Dokumentert bokført verdi {_decimal_text(carrying)} NOK."
			),
			accounts=accounts,
		)
	)
	entry.insert()
	source_file.attached_to_doctype = "Journal Entry"
	source_file.attached_to_name = entry.name
	source_file.save()
	from enk_norge.posting_contract import seal_draft

	entry.db_set("enk_posting_contract", seal_draft(entry), update_modified=False)
	return {
		"doctype": entry.doctype,
		"name": entry.name,
		"disposal_source": {"doctype": "Journal Entry", "name": entry.name, "amount": _decimal_text(amount)},
		"disposal_proceeds_taken_to_income": _decimal_text(direct),
	}


def _load_gl_entries(company: str, income_year: int) -> list[LedgerEntry]:
	frappe = _frappe()
	end = f"{income_year}-12-31"
	profit_and_loss = frappe.get_list(
		"GL Entry",
		filters={
			"company": company,
			"posting_date": ["between", [f"{income_year}-01-01", end]],
			"is_cancelled": 0,
			"voucher_type": ["!=", "Period Closing Voucher"],
		},
		fields=["name", "account", "debit", "credit", "voucher_type", "voucher_no", "posting_date"],
		order_by="posting_date, name",
		limit_page_length=0,
	)
	balance_sheet = frappe.get_list(
		"GL Entry",
		filters={"company": company, "posting_date": ["<=", end], "is_cancelled": 0},
		fields=["name", "account", "debit", "credit", "voucher_type", "voucher_no", "posting_date"],
		order_by="posting_date, name",
		limit_page_length=0,
	)
	settings = frappe.get_doc("ENK Settings", company)
	categories = {row.account: row.tax_category for row in settings.accounts}
	profit_accounts = {
		account for account, category in categories.items() if category in ("Income", "Expense")
	}
	balance_accounts = set(categories) - profit_accounts
	entries = [
		_ledger_entry(row)
		for row in profit_and_loss
		if row.account in profit_accounts and row.voucher_type != "Period Closing Voucher"
	] + [_ledger_entry(row) for row in balance_sheet if row.account in balance_accounts]
	unknown_accounts = {
		row.account for row in profit_and_loss + balance_sheet if row.account not in categories
	}
	if unknown_accounts:
		frappe.throw("Hovedbokskontoer mangler årsoppgjørskategori: " + ", ".join(sorted(unknown_accounts)))
	return entries


def _ledger_entry(row: Any) -> LedgerEntry:
	return LedgerEntry(
		account=row.account,
		debit=_frappe_decimal(row.debit, "Debet"),
		credit=_frappe_decimal(row.credit, "Kredit"),
		voucher_type=row.voucher_type or "",
		voucher_no=row.voucher_no or "",
		posting_date=date.fromisoformat(str(row.posting_date)),
	)


def _load_tax_pools(company: str, income_year: int) -> list[TaxPoolSummary]:
	frappe = _frappe()
	pools = frappe.get_list(
		"ENK Tax Pool",
		filters={"company": company, "income_year": income_year},
		fields=[
			"name",
			"depreciation_deduction",
			"negative_balance_income",
			"disposal_proceeds",
			"disposal_proceeds_taken_to_income",
			"source_hash",
		],
		order_by="saldo_group",
		limit_page_length=0,
	)
	verified_pools = []
	for row in pools:
		pool = frappe.get_doc("ENK Tax Pool", row.name)
		validate_pool_document(pool)
		verified_pools.append(pool)
	return [
		TaxPoolSummary(
			name=pool.name,
			depreciation_deduction=_frappe_decimal(pool.depreciation_deduction, "Skattemessig avskrivning"),
			negative_balance_income=_frappe_decimal(pool.negative_balance_income, "Negativ saldo"),
			disposal_proceeds=_frappe_decimal(pool.disposal_proceeds or "0", "Realisasjonsvederlag"),
			disposal_proceeds_taken_to_income=_frappe_decimal(
				pool.disposal_proceeds_taken_to_income or "0", "Direkte inntektsført realisasjonsvederlag"
			),
			source_hash=str(pool.source_hash or ""),
		)
		for pool in verified_pools
	]


def _load_purchase_tax_adjustments(
	company: str, income_year: int, manual_adjustments: Iterable[TaxAdjustment]
) -> list[TaxAdjustment]:
	"""Tar bare med ikke-fradragsberettiget del av bokførte Expense-linjer på kjøp."""
	frappe = _frappe()
	invoices = frappe.get_list(
		"Purchase Invoice",
		filters={
			"company": company,
			"docstatus": 1,
			"posting_date": ["between", [f"{income_year}-01-01", f"{income_year}-12-31"]],
			"enk_tax_deductible_fraction": ["<", 1],
		},
		fields=["name", "is_return", "enk_tax_deductible_fraction", "enk_tax_adjustment_reason"],
		order_by="posting_date, name",
		limit_page_length=0,
	)
	automatic_names = {invoice.name for invoice in invoices}
	if any(
		adjustment.reference_doctype == "Purchase Invoice" and adjustment.reference_name in automatic_names
		for adjustment in manual_adjustments
	):
		frappe.throw("Skattekorrigering for kjøpsfakturaen beregnes allerede fra fradragsvurderingen.")
	adjustments: list[TaxAdjustment] = []
	for invoice_row in invoices:
		invoice = frappe.get_doc("Purchase Invoice", invoice_row.name)
		invoice.check_permission("read")
		reason = (invoice.enk_tax_adjustment_reason or "").strip()
		if not reason:
			frappe.throw("Ikke-fradragsberettiget kjøp krever skattemessig begrunnelse.")
		expense_amounts = [
			_to_decimal(str(item.base_net_amount), "Kostnadslinje", allow_negative=True)
			for item in invoice.items
			if item.expense_account
			and frappe.get_cached_value("Account", item.expense_account, "root_type") == "Expense"
		]
		effect = calculate_purchase_tax_adjustment(
			expense_amounts,
			_frappe_decimal(invoice.enk_tax_deductible_fraction, "Skattemessig fradragsandel"),
			is_credit_note=bool(invoice.is_return),
		)
		if effect:
			adjustments.append(TaxAdjustment(effect, reason, "Purchase Invoice", invoice.name))
	return adjustments


def _parse_adjustments(value: Any, company: str) -> list[TaxAdjustment]:
	frappe = _frappe()
	if value in (None, ""):
		rows: Any = []
	elif isinstance(value, str):
		try:
			rows = frappe.parse_json(value)
		except Exception as error:
			frappe.throw("Skattekorrigeringer må være gyldig JSON.")
			raise error
	else:
		rows = value
	if not isinstance(rows, list):
		frappe.throw("Skattekorrigeringer må være en liste.")
	adjustments: list[TaxAdjustment] = []
	for row in rows:
		if not isinstance(row, dict):
			frappe.throw("Hver skattekorrigering må være et objekt.")
		adjustment = TaxAdjustment(
			effect=_to_decimal(row.get("effect"), "Skattekorrigering", allow_negative=True),
			reason=str(row.get("reason") or "").strip(),
			reference_doctype=str(row.get("reference_doctype") or "").strip(),
			reference_name=str(row.get("reference_name") or "").strip(),
		)
		if not adjustment.reason or not adjustment.reference_doctype or not adjustment.reference_name:
			frappe.throw("Skattekorrigering krever begrunnelse og kildebilag.")
		_validate_source_document_company(
			{"doctype": adjustment.reference_doctype, "name": adjustment.reference_name}, company
		)
		adjustments.append(adjustment)
	return adjustments


def _parse_personal_income_inputs(value: Any) -> PersonalIncomeInput | None:
	"""Godtar bare de eksplisitte, dokumenterte postene i personinntektsberegningen."""
	frappe = _frappe()
	if value in (None, ""):
		return None
	if isinstance(value, str):
		try:
			value = frappe.parse_json(value)
		except Exception:
			frappe.throw("Personinntektsinput må være gyldig JSON.")
	if not isinstance(value, dict):
		frappe.throw("Personinntektsinput må være et objekt.")
	allowed = set(PersonalIncomeInput.__dataclass_fields__)
	unknown = sorted(set(value) - allowed)
	if unknown:
		frappe.throw("Ukjente personinntektsfelt: " + ", ".join(unknown))
	if "capital_return_base" not in value:
		frappe.throw("Personinntektsinput krever capital_return_base.")
	decimal_fields = allowed - {"shielding_rate", "documented_shielding"}
	parsed: dict[str, Decimal | None] = {}
	for field in decimal_fields:
		if field in value:
			parsed[field] = _to_decimal(value[field], field.replace("_", " "))
	for field in ("shielding_rate", "documented_shielding"):
		if value.get(field) not in (None, ""):
			parsed[field] = _to_decimal(value[field], field.replace("_", " "))
	return PersonalIncomeInput(**parsed)  # type: ignore[arg-type]


def _parse_controls(value: Any) -> dict[str, bool]:
	frappe = _frappe()
	if value in (None, ""):
		value = {}
	elif isinstance(value, str):
		value = frappe.parse_json(value)
	if not isinstance(value, dict):
		frappe.throw("Kontrollpunkter må være et objekt.")
	result = {}
	for key in ("person_income_reviewed", "shielding_reviewed", "private_corrections_reviewed"):
		if key in value and not isinstance(value[key], bool):
			frappe.throw(f"{key} må være true eller false.")
		result[key] = bool(value.get(key, False))
	return result


def _controls_from_report(report: Any) -> dict[str, bool]:
	return {
		"person_income_reviewed": bool(report.person_income_reviewed),
		"shielding_reviewed": bool(report.shielding_reviewed),
		"private_corrections_reviewed": bool(report.private_corrections_reviewed),
	}


def _open_clarifications(calculation: YearEndCalculation, controls: Mapping[str, bool]) -> list[str]:
	clarifications = []
	if calculation.equity_reconciliation_difference != 0:
		clarifications.append("Egenkapitalavstemmingen har avvik og må forklares med dokumenterte bilag.")
	if not controls.get("person_income_reviewed"):
		clarifications.append("Personinntekt er ikke beregnet i denne rapporten og må vurderes særskilt.")
	if not controls.get("shielding_reviewed"):
		clarifications.append("Skjerming er ikke beregnet i denne rapporten og må vurderes særskilt.")
	if not controls.get("private_corrections_reviewed"):
		clarifications.append(
			"Private uttak og skattemessige korreksjoner er ikke dokumentert som gjennomgått."
		)
	return clarifications


def _store_year_report(
	*,
	previous: Any | None,
	company: str,
	income_year: int,
	calculation: YearEndCalculation,
	adjustments: list[TaxAdjustment],
	controls: Mapping[str, bool],
	clarifications: list[str],
	payload: dict[str, Any],
	personal: PersonalIncomeInput | None,
	personal_result: PersonalIncomeCalculation | None,
) -> Any:
	frappe = _frappe()
	if previous and previous.status != "Manually filed":
		report = previous
		history = _parse_snapshot_history(report.snapshot_history_json)
		if report.snapshot_json and report.snapshot_hash:
			history.append(
				{
					"revision": int(report.revision or 1),
					"snapshot_hash": report.snapshot_hash,
					"snapshot_json": json.loads(report.snapshot_json),
					"prepared_at": str(report.prepared_at),
				}
			)
		report.revision = int(report.revision or 0) + 1
	else:
		report = frappe.new_doc("ENK Year Report")
		report.company = company
		report.income_year = income_year
		report.revision = int(previous.revision or 0) + 1 if previous else 1
		history = _parse_snapshot_history(previous.snapshot_history_json) if previous else []
		if previous and previous.snapshot_json and previous.snapshot_hash:
			history.append(
				{
					"revision": int(previous.revision),
					"snapshot_hash": previous.snapshot_hash,
					"snapshot_json": json.loads(previous.snapshot_json),
					"prepared_at": str(previous.prepared_at),
				}
			)
	report.status = "Ready for review" if not clarifications else "Draft"
	report.manual_filing_status = "Not filed"
	report.prepared_at = frappe.utils.now_datetime()
	report.snapshot_json = _json_dump(payload)
	report.snapshot_hash = snapshot_hash(payload)
	report.snapshot_history_json = _json_dump(history)
	report.tax_adjustments_json = _json_dump([_json_value(asdict(item)) for item in adjustments])
	report.open_clarifications_json = _json_dump(clarifications)
	report.personal_income_inputs_json = _json_dump(_json_value(asdict(personal))) if personal else ""
	report.person_income_result_json = (
		_json_dump(_json_value(asdict(personal_result))) if personal_result else ""
	)
	report.person_income = _decimal_text(personal_result.person_income) if personal_result else "0.00"
	for field, value in asdict(calculation).items():
		setattr(report, field, _decimal_text(value))
	for field, value in controls.items():
		setattr(report, field, int(value))
	report.flags.enk_year_report_build = True
	report.save()
	return report


def _parse_snapshot_history(value: str | None) -> list[dict[str, Any]]:
	if not value:
		return []
	try:
		history = json.loads(value)
	except json.JSONDecodeError as error:
		raise YearEndError("Eksisterende revisjonshistorikk er ødelagt.") from error
	if not isinstance(history, list):
		raise YearEndError("Eksisterende revisjonshistorikk er ugyldig.")
	return history


def _find_year_report(company: str, income_year: int) -> Any | None:
	frappe = _frappe()
	names = frappe.get_list(
		"ENK Year Report",
		filters={"company": company, "income_year": income_year},
		pluck="name",
		order_by="revision desc, creation desc",
		limit_page_length=1,
	)
	return frappe.get_doc("ENK Year Report", names[0]) if names else None


def _report_response(report: Any) -> dict[str, Any]:
	return {
		"name": report.name,
		"company": report.company,
		"income_year": report.income_year,
		"status": report.status,
		"revision": report.revision,
		"snapshot_hash": report.snapshot_hash,
		"accounting_profit": report.accounting_profit,
		"taxable_business_profit": report.taxable_business_profit,
		"equity_reconciliation_difference": report.equity_reconciliation_difference,
		"open_clarifications": json.loads(report.open_clarifications_json or "[]"),
		"return_basis": json.loads(report.snapshot_json).get("return_basis", []),
		"tax_bridge": json.loads(report.snapshot_json).get("calculation", {}),
		"personal_income": json.loads(report.snapshot_json).get("personal_income_result"),
		"tax_pools": json.loads(report.snapshot_json).get("tax_pools", []),
	}


def _validate_source_document_company(reference: Mapping[str, str], company: str) -> None:
	frappe = _frappe()
	try:
		document = frappe.get_doc(reference["doctype"], reference["name"])
	except Exception as error:
		frappe.throw(f"Kildebilag finnes ikke: {reference.get('doctype')} {reference.get('name')}.")
		raise error
	document.check_permission("read")
	if document.meta.has_field("docstatus") and document.docstatus != 1:
		frappe.throw("Kildebilaget må være bokført før det brukes i årsoppgjøret.")
	if document.get("company") != company:
		frappe.throw("Kildebilaget tilhører et annet foretak eller mangler Company.")


def _income_year(value: int | str | None) -> int:
	if isinstance(value, bool):
		raise YearEndError("Inntektsår må være 2026.")
	try:
		year = int(value)
	except (TypeError, ValueError) as error:
		raise YearEndError("Inntektsår må være 2026.") from error
	if year != SUPPORTED_INCOME_YEAR:
		raise YearEndError("Årsoppgjørsmotoren støtter bare inntektsåret 2026.")
	return year


def _to_decimal(value: Any, label: str, *, allow_negative: bool = False) -> Decimal:
	if isinstance(value, bool) or isinstance(value, float):
		raise YearEndError(f"{label} må oppgis som Decimal eller desimaltekst.")
	try:
		amount = value if isinstance(value, Decimal) else Decimal(str(value))
	except Exception as error:
		raise YearEndError(f"{label} må være et gyldig beløp.") from error
	if not amount.is_finite() or (not allow_negative and amount < 0):
		raise YearEndError(f"{label} har ugyldig fortegn eller verdi.")
	return amount


def _amount(value: Decimal, label: str) -> Decimal:
	return _to_decimal(value, label)


def _frappe_decimal(value: Any, label: str, *, allow_negative: bool = False) -> Decimal:
	"""Overgang ved Frappe-grensen, som materialiserer Currency som float."""

	return _to_decimal(str(value), label, allow_negative=allow_negative)


def _money(value: Decimal) -> Decimal:
	return value.quantize(NOK_MINOR_UNIT)


def _decimal_text(value: Decimal) -> str:
	return format(_money(value), ".2f")


def _json_value(value: Any) -> Any:
	if isinstance(value, Decimal):
		return _decimal_text(value)
	if isinstance(value, date):
		return value.isoformat()
	if isinstance(value, dict):
		return {key: _json_value(item) for key, item in value.items()}
	if isinstance(value, list):
		return [_json_value(item) for item in value]
	return value


def _json_dump(value: Any) -> str:
	return json.dumps(_json_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _frappe():
	import frappe

	return frappe


def _whitelist(function, methods: list[str]):
	"""Merker API når Frappe er installert, men lar kjernen testes uten Frappe."""

	try:
		return _frappe().whitelist(methods=methods)(function)
	except ModuleNotFoundError:
		return function


build_year_report = _whitelist(build_year_report, ["POST"])
get_year_report = _whitelist(get_year_report, ["GET"])
mark_year_report_manually_filed = _whitelist(mark_year_report_manually_filed, ["POST"])
create_depreciation_journal_entry_draft = _whitelist(create_depreciation_journal_entry_draft, ["POST"])
create_asset_disposal_journal_entry_draft = _whitelist(create_asset_disposal_journal_entry_draft, ["POST"])


def _validate_disposal_coverage(company, year, settings):
	frappe = _frappe()
	covered = set()
	for pool in frappe.get_all(
		"ENK Tax Pool", filters={"company": company, "income_year": year}, fields=["disposal_sources_json"]
	):
		covered.update(
			row["name"]
			for row in json.loads(pool.disposal_sources_json or "[]")
			if row["doctype"] == "Journal Entry"
		)
	actual = set(
		frappe.get_all(
			"Journal Entry",
			filters={
				"company": company,
				"docstatus": 1,
				"voucher_type": "Asset Disposal",
				"posting_date": ["between", [f"{year}-01-01", f"{year}-12-31"]],
			},
			pluck="name",
		)
	)
	actual.update(
		frappe.get_all(
			"GL Entry",
			filters={
				"company": company,
				"is_cancelled": 0,
				"account": ["in", [settings.asset_gain_account, settings.asset_loss_account]],
				"posting_date": ["between", [f"{year}-01-01", f"{year}-12-31"]],
			},
			pluck="voucher_no",
		)
	)
	if actual - covered:
		frappe.throw(
			"Knytt alle bokførte driftsmiddelavganger til dokumenterte saldogrupper før årsberegningen."
		)


def _return_basis(entries, mappings):
	"""Bevar hovedbokens rapportkoder sammen med årets skatteavstemming."""
	mapping = {row.account: row for row in mappings}
	grouped = {}
	for entry in entries:
		row = mapping[entry.account]
		key = (row.grouping_category, row.grouping_code)
		if not all(key):
			raise YearEndError(f"Kontoen {entry.account} mangler rapportkode.")
		group = grouped.setdefault(key, dict(category=key[0], code=key[1], amount=Decimal(0), accounts=set()))
		sign = 1 if row.tax_category in ("Asset", "Expense") else -1
		group["amount"] += sign * (entry.debit - entry.credit)
		group["accounts"].add(entry.account)
	return [
		dict(
			category=value["category"],
			code=value["code"],
			amount=_decimal_text(value["amount"]),
			accounts=sorted(value["accounts"]),
		)
		for _, value in sorted(grouped.items())
	]
