"""Kontrollerte NOK-oppgjør fra betalingsformidler mot allerede bokførte fakturaer."""

import hashlib
import json
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


class SettlementError(ValueError):
	pass


def _frappe():
	import frappe

	return frappe


def _money(value, label, positive=False):
	try:
		amount = Decimal(str(value))
	except (InvalidOperation, TypeError, ValueError) as error:
		raise SettlementError(f"{label} må være et gyldig NOK-beløp.") from error
	if not amount.is_finite() or amount != amount.quantize(Decimal(".01"), rounding=ROUND_HALF_UP):
		raise SettlementError(f"{label} må være et NOK-beløp med høyst to desimaler.")
	if positive and amount <= 0:
		raise SettlementError(f"{label} må være større enn null.")
	if not positive and amount < 0:
		raise SettlementError(f"{label} kan ikke være negativt.")
	return amount


def _data(data):
	f = _frappe()
	data = f.parse_json(data) if isinstance(data, str) else data
	if not isinstance(data, dict):
		f.throw("Ugyldig oppgjørsgrunnlag.")
	return f._dict(data)


def _content_hash(file):
	content = file.get_content()
	if isinstance(content, str):
		content = content.encode()
	return hashlib.sha256(content).hexdigest()


def _normalise_references(rows, label):
	if not isinstance(rows, list) or not rows:
		raise SettlementError(f"Oppgjøret krever minst én {label}.")
	normalised, names = [], set()
	for row in rows:
		if not isinstance(row, dict):
			raise SettlementError(f"Hver {label} må ha faktura og beløp.")
		name = str(row.get("name") or "").strip()
		if not name or name in names:
			raise SettlementError(f"Hver {label} kan bare forekomme én gang.")
		names.add(name)
		normalised.append({"name": name, "amount": format(_money(row.get("amount"), label, True), ".2f")})
	return sorted(normalised, key=lambda row: row["name"])


def _fingerprint(values):
	return hashlib.sha256(
		json.dumps(values, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
	).hexdigest()


def _invoice_reference(company, row, credit_note=False):
	f = _frappe()
	doc = f.get_doc("Sales Invoice", row["name"])
	doc.check_permission("read")
	amount = Decimal(row["amount"])
	if (
		doc.company != company
		or doc.docstatus != 1
		or doc.currency != "NOK"
		or bool(doc.is_return) != credit_note
	):
		f.throw("Oppgjøret må vise en bokført NOK-faktura eller kreditnota fra samme foretak.")
	outstanding = Decimal(str(doc.outstanding_amount))
	if credit_note:
		if outstanding >= 0 or amount > -outstanding:
			f.throw("Kreditnotaens oppgjørsbeløp overstiger utestående refusjon.")
	else:
		if outstanding <= 0 or amount > outstanding:
			f.throw("Fakturaens oppgjørsbeløp overstiger utestående fordring.")
	return doc, amount


def _settlement_payload(data, source_sha256):
	external_id = str(data.get("external_settlement_id") or "").strip()
	if not external_id or len(external_id) > 140:
		raise SettlementError("Oppgi betalingsformidlerens oppgjørs-ID på høyst 140 tegn.")
	if data.get("currency") != "NOK":
		raise SettlementError("Oppgjør støttes bare i NOK.")
	if data.get("merchant_of_record") != "Direct seller":
		raise SettlementError("Oppgjør støttes bare når foretaket er den direkte selgeren.")
	invoices = _normalise_references(data.get("invoices"), "faktura")
	credits = _normalise_references(data.get("credit_notes", []), "kreditnota") if data.get("credit_notes") else []
	if {row["name"] for row in invoices} & {row["name"] for row in credits}:
		raise SettlementError("Samme dokument kan ikke være både faktura og kreditnota i ett oppgjør.")
	fee = _money(data.get("fee", 0), "Gebyr")
	net = _money(data.get("net_amount"), "Netto utbetaling", True)
	gross = sum((Decimal(row["amount"]) for row in invoices), Decimal())
	refunds = sum((Decimal(row["amount"]) for row in credits), Decimal())
	if gross - refunds - fee != net:
		raise SettlementError("Brutto salg minus refusjoner og gebyr må være lik netto utbetaling.")
	return {
		"company": str(data.get("company") or ""),
		"credit_notes": credits,
		"currency": "NOK",
		"external_settlement_id": external_id,
		"fee": format(fee, ".2f"),
		"gross_amount": format(gross, ".2f"),
		"invoices": invoices,
		"merchant_of_record": "Direct seller",
		"net_amount": format(net, ".2f"),
		"posting_date": str(data.get("posting_date") or ""),
		"refund_amount": format(refunds, ".2f"),
		"source_sha256": source_sha256,
	}


def _existing(company, external_id, fingerprint):
	f = _frappe()
	name = f.db.get_value(
		"ENK Settlement", {"company": company, "external_settlement_id": external_id}, "name", for_update=True
	)
	if not name:
		return None
	doc = f.get_doc("ENK Settlement", name)
	doc.check_permission("read")
	if doc.request_fingerprint != fingerprint:
		f.throw("Oppgjørs-ID-en finnes allerede med andre opplysninger. Kontroller oppgjørsfilen.")
	if doc.status != "Ready for review" or not doc.journal_entry:
		f.throw("Oppgjørs-ID-en har et ufullført utkast. Kontroller det før nytt forsøk.")
	entry = f.get_doc("Journal Entry", doc.journal_entry)
	entry.check_permission("read")
	if entry.docstatus == 2:
		f.throw("Oppgjørs-ID-en peker på et annullert bilag. Bruk en ny dokumentert oppgjørs-ID.")
	return {"doctype": "Journal Entry", "name": entry.name, "settlement": doc.name, "reused": True}


def _journal_entry(settings, payload):
	f = _frappe()
	entries = []
	for row in payload["invoices"]:
		invoice, amount = _invoice_reference(payload["company"], row)
		entries.extend(
			[
				dict(account=settings.clearing_account, debit_in_account_currency=format(amount, ".2f")),
				dict(
					account=invoice.debit_to,
					credit_in_account_currency=format(amount, ".2f"),
					party_type="Customer",
					party=invoice.customer,
					reference_type="Sales Invoice",
					reference_name=invoice.name,
				),
			]
		)
	for row in payload["credit_notes"]:
		credit, amount = _invoice_reference(payload["company"], row, credit_note=True)
		entries.extend(
			[
				dict(
					account=credit.debit_to,
					debit_in_account_currency=format(amount, ".2f"),
					party_type="Customer",
					party=credit.customer,
					reference_type="Sales Invoice",
					reference_name=credit.name,
				),
				dict(account=settings.clearing_account, credit_in_account_currency=format(amount, ".2f")),
			]
		)
	fee = Decimal(payload["fee"])
	if fee:
		entries.extend(
			[
				dict(account=settings.fees_account, debit_in_account_currency=format(fee, ".2f")),
				dict(account=settings.clearing_account, credit_in_account_currency=format(fee, ".2f")),
			]
		)
	net = Decimal(payload["net_amount"])
	entries.extend(
		[
			dict(account=settings.bank_ledger_account, debit_in_account_currency=format(net, ".2f")),
			dict(account=settings.clearing_account, credit_in_account_currency=format(net, ".2f")),
		]
	)
	return f.get_doc(
		dict(
			doctype="Journal Entry",
			company=payload["company"],
			posting_date=payload["posting_date"],
			voucher_type="Journal Entry",
			cheque_no=payload["external_settlement_id"],
			cheque_date=payload["posting_date"],
			user_remark="Betalingsformidleroppgjør " + payload["external_settlement_id"],
			accounts=entries,
		)
	)


def _attach_source(file, entry):
	file.attached_to_doctype = entry.doctype
	file.attached_to_name = entry.name
	file.save()


def create_settlement(data):
	"""Lag et signert, men ikke innsendt, oppgjørsutkast fra én privat kildefil."""
	f = _frappe()
	from enk_norge.posting_contract import seal_draft
	from enk_norge.setup import get_settings

	data = _data(data)
	settings = get_settings(data.company, write=True)
	f.has_permission("ENK Settlement", "create", throw=True)
	f.has_permission("Journal Entry", "create", throw=True)
	f.db.sql("select name from `tabCompany` where name=%s for update", data.company)
	file = f.get_doc("File", data.source_file)
	file.check_permission("read")
	if not file.is_private or file.is_folder or not file.file_url:
		f.throw("Oppgjørsfilen må være en privat fil.")
	payload = _settlement_payload(data, _content_hash(file))
	if not payload["company"] or not payload["posting_date"]:
		f.throw("Oppgjøret krever foretak og bokføringsdato.")
	fingerprint = _fingerprint(payload)
	if existing := _existing(data.company, payload["external_settlement_id"], fingerprint):
		return existing
	if file.attached_to_doctype or file.attached_to_name:
		f.throw("Oppgjørsfilen er allerede knyttet til et dokument.")
	settlement = f.get_doc(
		dict(
			doctype="ENK Settlement",
			company=data.company,
			external_settlement_id=payload["external_settlement_id"],
			posting_date=payload["posting_date"],
			source_file=file.name,
			source_sha256=payload["source_sha256"],
			request_fingerprint=fingerprint,
			merchant_of_record="Direct seller",
			currency="NOK",
			gross_amount=payload["gross_amount"],
			refund_amount=payload["refund_amount"],
			fee_amount=payload["fee"],
			net_amount=payload["net_amount"],
			references_json=json.dumps(
				[
					{"doctype": "Sales Invoice", **row} for row in payload["invoices"]
				]
				+ [{"doctype": "Sales Invoice", **row, "credit_note": True} for row in payload["credit_notes"]],
				ensure_ascii=False,
				sort_keys=True,
				separators=(",", ":"),
			),
			status="Draft",
		)
	)
	settlement.flags.enk_settlement_build = True
	settlement.insert()
	entry = _journal_entry(settings, payload)
	entry.insert()
	entry.db_set("enk_posting_contract", seal_draft(entry), update_modified=False)
	_attach_source(file, entry)
	settlement.journal_entry = entry.name
	settlement.status = "Ready for review"
	settlement.flags.enk_settlement_build = True
	settlement.save()
	return {"doctype": "Journal Entry", "name": entry.name, "settlement": settlement.name, "reused": False}


def _wl(fn, methods=None):
	try:
		return _frappe().whitelist(methods=methods)(fn)
	except ModuleNotFoundError:
		return fn


create_settlement = _wl(create_settlement, methods=["POST"])


def validate_settlement_entry(entry):
	"""Valider kildefilen når et generert oppgjørsutkast skal bokføres."""
	f = _frappe()
	if not f.db.exists("DocType", "ENK Settlement"):
		return
	settlements = f.get_all(
		"ENK Settlement",
		filters={"journal_entry": entry.name},
		fields=["name", "company", "external_settlement_id", "source_file", "source_sha256", "status"],
		limit_page_length=2,
	)
	if not settlements:
		return
	if len(settlements) != 1:
		f.throw("Journalutkastet er knyttet til flere oppgjør.")
	settlement = settlements[0]
	if settlement.company != entry.company or settlement.status != "Ready for review":
		f.throw("Oppgjøret må være klart til kontroll i samme foretak før bokføring.")
	if entry.cheque_no != settlement.external_settlement_id:
		f.throw("Journalutkastets oppgjørs-ID stemmer ikke med oppgjøret.")
	file = f.get_doc("File", settlement.source_file)
	file.check_permission("read")
	if not file.is_private or file.attached_to_doctype != "Journal Entry" or file.attached_to_name != entry.name:
		f.throw("Oppgjørsfilen må være privat og knyttet til journalutkastet.")
	if _content_hash(file) != settlement.source_sha256:
		f.throw("Oppgjørsfilen er endret etter at oppgjørsutkastet ble opprettet.")
