"""Signert innholdskontrakt for smale, genererte hovedbokbilag."""

import hashlib
import hmac
import json
from decimal import Decimal, InvalidOperation


class PostingContractError(ValueError):
	"""Bilaget er ikke det samme som systemet opprinnelig genererte."""


def _get(doc, field, default=None):
	if isinstance(doc, dict):
		return doc.get(field, default)
	if hasattr(doc, "get"):
		return doc.get(field, default)
	return getattr(doc, field, default)


def _text(value):
	return str(value or "").strip()


def _money(value):
	try:
		amount = Decimal(str(value if value is not None else 0))
	except (InvalidOperation, ValueError, TypeError) as error:
		raise PostingContractError("Kontrakten inneholder et ugyldig beløp.") from error
	if not amount.is_finite():
		raise PostingContractError("Kontrakten inneholder et ugyldig beløp.")
	return format(amount.normalize(), "f") if amount else "0"


def _rows(rows):
	return sorted(rows, key=lambda row: json.dumps(row, separators=(",", ":"), sort_keys=True))


def _journal_entry_payload(doc):
	accounts = []
	for row in (_get(doc, "accounts", []) or []):
		accounts.append(
			{
				"account": _text(_get(row, "account")),
				"account_currency": _text(_get(row, "account_currency")),
				"credit": _money(_get(row, "credit")),
				"credit_in_account_currency": _money(_get(row, "credit_in_account_currency")),
				"cost_center": _text(_get(row, "cost_center")),
				"debit": _money(_get(row, "debit")),
				"debit_in_account_currency": _money(_get(row, "debit_in_account_currency")),
				"exchange_rate": _money(_get(row, "exchange_rate")),
				"party": _text(_get(row, "party")),
				"party_type": _text(_get(row, "party_type")),
				"project": _text(_get(row, "project")),
				"reference_name": _text(_get(row, "reference_name")),
				"reference_type": _text(_get(row, "reference_type")),
			}
		)
	return {
		"accounts": _rows(accounts),
		"cheque_no": _text(_get(doc, "cheque_no")),
		"cheque_date": _text(_get(doc, "cheque_date")),
		"enk_payment_fingerprint": _text(_get(doc, "enk_payment_fingerprint")),
		"enk_payment_key": _text(_get(doc, "enk_payment_key")),
		"enk_deferral_details": _text(_get(doc, "enk_deferral_details")),
		"enk_deferral_key": _text(_get(doc, "enk_deferral_key")),
		"enk_vat_period": _text(_get(doc, "enk_vat_period")),
		"enk_fx_payment_entry": _text(_get(doc, "enk_fx_payment_entry")),
		"voucher_type": _text(_get(doc, "voucher_type")),
	}


def _payment_entry_payload(doc):
	references = []
	for row in (_get(doc, "references", []) or []):
		references.append(
			{
				"allocated_amount": _money(_get(row, "allocated_amount")),
				"exchange_rate": _money(_get(row, "exchange_rate")),
				"reference_name": _text(_get(row, "reference_name")),
				"reference_doctype": _text(_get(row, "reference_doctype")),
			}
		)
	deductions = []
	for row in (_get(doc, "deductions", []) or []):
		deductions.append(
			{
				"account": _text(_get(row, "account")),
				"amount": _money(_get(row, "amount")),
				"cost_center": _text(_get(row, "cost_center")),
			}
		)
	taxes = []
	for row in (_get(doc, "taxes", []) or []):
		taxes.append(
			{
				"account_head": _text(_get(row, "account_head")),
				"add_deduct_tax": _text(_get(row, "add_deduct_tax")),
				"base_tax_amount": _money(_get(row, "base_tax_amount")),
				"charge_type": _text(_get(row, "charge_type")),
				"cost_center": _text(_get(row, "cost_center")),
				"project": _text(_get(row, "project")),
				"rate": _money(_get(row, "rate")),
				"tax_amount": _money(_get(row, "tax_amount")),
			}
		)
	return {
		"base_paid_amount": _money(_get(doc, "base_paid_amount")),
		"base_received_amount": _money(_get(doc, "base_received_amount")),
		"cost_center": _text(_get(doc, "cost_center")),
		"deductions": _rows(deductions),
		"enk_payment_fingerprint": _text(_get(doc, "enk_payment_fingerprint")),
		"enk_payment_key": _text(_get(doc, "enk_payment_key")),
		"paid_amount": _money(_get(doc, "paid_amount")),
		"enk_exchange_rate_source": _text(_get(doc, "enk_exchange_rate_source")),
		"enk_exchange_rate_date": _text(_get(doc, "enk_exchange_rate_date")),
		"enk_bank_amount_nok": _money(_get(doc, "enk_bank_amount_nok")),
		"enk_fx_journal_entry": _text(_get(doc, "enk_fx_journal_entry")),
		"enk_fee_amount_nok": _money(_get(doc, "enk_fee_amount_nok")),
		"paid_from": _text(_get(doc, "paid_from")),
		"paid_from_account_currency": _text(_get(doc, "paid_from_account_currency")),
		"paid_to": _text(_get(doc, "paid_to")),
		"paid_to_account_currency": _text(_get(doc, "paid_to_account_currency")),
		"party": _text(_get(doc, "party")),
		"party_type": _text(_get(doc, "party_type")),
		"payment_type": _text(_get(doc, "payment_type")),
		"project": _text(_get(doc, "project")),
		"received_amount": _money(_get(doc, "received_amount")),
		"reference_date": _text(_get(doc, "reference_date")),
		"reference_no": _text(_get(doc, "reference_no")),
		"references": _rows(references),
		"source_exchange_rate": _money(_get(doc, "source_exchange_rate")),
		"target_exchange_rate": _money(_get(doc, "target_exchange_rate")),
		"taxes": _rows(taxes),
	}


def posting_payload(doc):
	"""Returner bare feltene som endrer bokføringen eller kilden den avstemmes mot."""
	doctype = _text(_get(doc, "doctype"))
	if doctype not in ("Journal Entry", "Payment Entry"):
		raise PostingContractError("Posting-kontrakt støtter bare Journal Entry og Payment Entry.")
	payload = {
		"company": _text(_get(doc, "company")),
		"doctype": doctype,
		"name": _text(_get(doc, "name")),
		"posting_date": _text(_get(doc, "posting_date")),
	}
	if not payload["company"] or not payload["name"] or not payload["posting_date"]:
		raise PostingContractError("Posting-kontrakten krever dokumentnavn, foretak og bokføringsdato.")
	payload |= _journal_entry_payload(doc) if doctype == "Journal Entry" else _payment_entry_payload(doc)
	return payload


def _site_secret():
	try:
		import frappe

		secret = frappe.local.conf.get("encryption_key")
	except (AttributeError, ImportError) as error:
		raise PostingContractError("Serverens krypteringsnøkkel er ikke tilgjengelig.") from error
	if not secret:
		raise PostingContractError("Serverens krypteringsnøkkel er ikke konfigurert.")
	return str(secret)


def _signature(payload, secret):
	encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
	return hmac.new(str(secret).encode(), encoded, hashlib.sha256).hexdigest()


def seal_draft(doc, *, secret=None):
	"""Signer det finansielle innholdet på et utkast før brukeren kan sende det inn."""
	if _get(doc, "docstatus", 0) not in (0, "0", None):
		raise PostingContractError("Bare utkast kan få en ny posting-kontrakt.")
	payload = posting_payload(doc)
	contract = {"payload": payload, "signature": _signature(payload, secret or _site_secret()), "version": 1}
	serialized = json.dumps(contract, separators=(",", ":"), sort_keys=True)
	if isinstance(doc, dict):
		doc["enk_posting_contract"] = serialized
	else:
		doc.enk_posting_contract = serialized
	return serialized


def validate_contract(doc, *, secret=None):
	"""Avvis endret bokføring, men tillat ufarlige metadata og vedlegg på utkastet."""
	stored = _get(doc, "enk_posting_contract")
	try:
		contract = json.loads(stored or "")
		payload = contract["payload"]
		signature = contract["signature"]
	except (KeyError, TypeError, ValueError) as error:
		raise PostingContractError("Bilaget mangler en gyldig posting-kontrakt.") from error
	if contract.get("version") != 1 or not isinstance(payload, dict) or not isinstance(signature, str):
		raise PostingContractError("Bilaget mangler en gyldig posting-kontrakt.")
	key = secret or _site_secret()
	if not hmac.compare_digest(signature, _signature(payload, key)):
		raise PostingContractError("Posting-kontraktens signatur stemmer ikke.")
	if payload != posting_payload(doc):
		raise PostingContractError("Bilagets finansielle innhold er endret etter at utkastet ble generert.")
	return True
