"""Eksplisitte valutainndata for ENK-bilag. Ingen kurs hentes automatisk."""

import re
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import frappe
from frappe.utils import getdate

MONEY_QUANTUM = Decimal(".01")
RATE_QUANTUM = Decimal(".000001")


@dataclass(frozen=True)
class CurrencyInput:
	currency: str
	conversion_rate: Decimal
	source: str | None
	rate_date: date | None


def _decimal(value, label, quantum, *, positive=True):
	try:
		amount = Decimal(str(value))
		if not amount.is_finite() or (positive and amount <= 0):
			raise ValueError
		rounded = amount.quantize(quantum, rounding=ROUND_HALF_UP)
		if amount != rounded:
			raise ValueError
		return rounded
	except (InvalidOperation, TypeError, ValueError):
		frappe.throw(f"{label} må være et endelig {'positivt ' if positive else ''}tall med høyst " f"{abs(quantum.as_tuple().exponent)} desimaler.")


def parse_currency_input(data):
	"""Les valuta og dokumentert kurs fra et ENK-API-payload."""
	currency = str(data.get("currency") or "NOK").strip().upper()
	if not re.fullmatch(r"[A-Z]{3}", currency):
		frappe.throw("Valuta må være en ISO-valutakode på tre store bokstaver.")
	if currency == "NOK":
		if data.get("conversion_rate") not in (None, "") and _decimal(
			data.get("conversion_rate"), "Valutakurs", RATE_QUANTUM
		) != Decimal(1):
			frappe.throw("NOK-bilag må ha kurs 1.")
		if data.get("exchange_rate_source") or data.get("exchange_rate_date"):
			frappe.throw("NOK-bilag skal ikke ha en separat valutakurs eller kurskilde.")
		return CurrencyInput(currency="NOK", conversion_rate=Decimal(1), source=None, rate_date=None)

	source = (data.get("exchange_rate_source") or "").strip()
	if not source or len(source) > 140:
		frappe.throw("Oppgi en kurskilde på høyst 140 tegn for valutabilaget.")
	raw_rate_date = data.get("exchange_rate_date")
	if not raw_rate_date:
		frappe.throw("Oppgi kursdato for valutabilaget.")
	try:
		rate_date = getdate(raw_rate_date)
	except (TypeError, ValueError):
		frappe.throw("Oppgi kursdato som YYYY-MM-DD for valutabilaget.")
	return CurrencyInput(
		currency=currency,
		conversion_rate=_decimal(data.get("conversion_rate"), "Valutakurs", RATE_QUANTUM),
		source=source,
		rate_date=rate_date,
	)


def nok_amount(amount, conversion_rate):
	"""Konverter eksplisitt beløp til NOK med samme avrunding som bilagsbeløp."""
	return (_decimal(amount, "Beløp", MONEY_QUANTUM) * _decimal(conversion_rate, "Valutakurs", RATE_QUANTUM)).quantize(
		MONEY_QUANTUM, rounding=ROUND_HALF_UP
	)


def validate_currency_document(doc):
	"""Valider lagrede valutafelter før SI/PI bokføres, også uten ENK-API-et."""
	company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
	if company_currency != "NOK":
		frappe.throw("ENK støtter bare NOK som regnskapsvaluta.")
	currency = (doc.get("currency") or "").strip().upper()
	if not re.fullmatch(r"[A-Z]{3}", currency):
		frappe.throw("Bilagets valuta må være en ISO-valutakode på tre store bokstaver.")
	if currency == "NOK":
		if Decimal(str(doc.get("conversion_rate") or 0)) != Decimal(1):
			frappe.throw("NOK-bilag må ha kurs 1.")
		if doc.get("enk_exchange_rate_source") or doc.get("enk_exchange_rate_date"):
			frappe.throw("NOK-bilag skal ikke ha kurskilde eller kursdato.")
		return
	if not frappe.db.exists("Currency", currency):
		frappe.throw(f"Valutaen {currency} finnes ikke i ERPNext.")
	rate = _decimal(doc.get("conversion_rate"), "Valutakurs", RATE_QUANTUM)
	source = (doc.get("enk_exchange_rate_source") or "").strip()
	if not source or len(source) > 140:
		frappe.throw("Valutabilag må ha kurskilde på høyst 140 tegn.")
	raw_rate_date = doc.get("enk_exchange_rate_date")
	if not raw_rate_date:
		frappe.throw("Valutabilag må ha kursdato.")
	try:
		rate_date = getdate(raw_rate_date)
	except (TypeError, ValueError):
		frappe.throw("Valutabilag må ha kursdato som YYYY-MM-DD.")
	if rate_date > getdate(doc.posting_date):
		frappe.throw("Kursdato kan ikke være etter bilagsdatoen.")
	# Sørg for at en verdi med flere desimaler ikke blir godtatt bare fordi ERPNext
	# avrundet den i en annen kodevei.
	if Decimal(str(doc.get("conversion_rate"))) != rate:
		frappe.throw("Valutakurs må ha høyst seks desimaler.")


def get_currency_party_account(company, currency, kind):
	"""Finn eller opprett valuta-bundet reskontrokonto for et ENK-foretak."""
	if kind not in ("receivable", "payable"):
		raise ValueError("Ukjent type partskonto.")
	currency = (currency or "").strip().upper()
	if currency == "NOK" or not re.fullmatch(r"[A-Z]{3}", currency):
		frappe.throw("Valutakonto krever en utenlandsk ISO-valutakode.")
	if not frappe.db.exists("Currency", currency):
		frappe.throw(f"Valutaen {currency} finnes ikke i ERPNext.")
	frappe.get_doc("Company", company).check_permission("read")
	frappe.db.sql("select name from `tabCompany` where name=%s for update", company)
	from enk_norge.setup import get_settings

	settings = get_settings(company)
	prefix, label, root_type, account_type, standard, grouping_category, grouping_code = (
		("A110", "Kundefordringer", "Asset", "Receivable", "15", "balanseverdiForOmloepsmiddel", "1500")
		if kind == "receivable"
		else ("L100", "Leverandørgjeld", "Liability", "Payable", "24", "kortsiktigGjeld", "2400")
	)
	account_number = f"{prefix}-{currency}"
	account = frappe.db.get_value("Account", {"company": company, "account_number": account_number}, "name")
	if account:
		account_doc = frappe.get_doc("Account", account)
		if (
			account_doc.company != company
			or account_doc.is_group
			or account_doc.root_type != root_type
			or account_doc.account_type != account_type
			or account_doc.account_currency != currency
		):
			frappe.throw(f"Valutakontoen {account_number} har feil oppsett og kan ikke brukes.")
	else:
		parent = frappe.db.get_value(
			"Account",
			{"company": company, "root_type": root_type, "is_group": 1, "parent_account": ["is", "not set"]},
			"name",
		)
		if not parent:
			frappe.throw("Foretaket mangler rotkonto for valutarestkontro.")
		account = frappe.get_doc(
			dict(
				doctype="Account",
				company=company,
				account_name=f"{label} {currency}",
				account_number=account_number,
				parent_account=parent,
				root_type=root_type,
				account_type=account_type,
				account_currency=currency,
				is_group=0,
			)
		).insert(ignore_permissions=True).name
	if not any(row.account == account for row in settings.accounts):
		settings.append(
			"accounts",
			dict(
				account=account,
				standard_account_id=standard,
				grouping_category=grouping_category,
				grouping_code=grouping_code,
				tax_category=root_type,
			),
		)
		settings.save(ignore_permissions=True)
	return account
