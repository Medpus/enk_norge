"""Sporbar bankimport og idempotente betalingsutkast."""

import csv
import hashlib
import io
import json
from datetime import date
from decimal import Decimal, InvalidOperation

import frappe
from frappe.utils import getdate

from enk_norge.api import _amount
from enk_norge.setup import get_settings


class BankingError(ValueError):
	pass


def _sha256(value):
	if isinstance(value, str):
		value = value.encode()
	return hashlib.sha256(value).hexdigest()


def _row_hash(identifier, when, amount, description):
	payload = json.dumps(
		{
			"amount": f"{amount:.2f}",
			"currency": "NOK",
			"date": when.isoformat(),
			"description": description,
			"transaction_id": identifier,
		},
		ensure_ascii=False,
		separators=(",", ":"),
		sort_keys=True,
	)
	return _sha256(payload)


def _parse_bank_csv(content, start_date):
	"""Les den lille, eksplisitte bankfilkontrakten uten å endre databasen."""
	if isinstance(content, bytes):
		if len(content) > 5_000_000:
			raise BankingError("Del bankfilen i mindre filer, under 5 MB.")
		try:
			content = content.decode("utf-8-sig")
		except UnicodeDecodeError as error:
			raise BankingError("Bankfilen må være UTF-8-kodet CSV.") from error
	elif len(content.encode()) > 5_000_000:
		raise BankingError("Del bankfilen i mindre filer, under 5 MB.")
	reader = csv.DictReader(io.StringIO(content))
	required = {"transaction_id", "date", "amount", "currency", "description"}
	if not required <= set(reader.fieldnames or []):
		raise BankingError(
			"CSV-filen må ha kolonnene transaction_id,date,amount,currency,description. "
			"Bruk punktum som desimaltegn og ISO-dato YYYY-MM-DD."
		)
	rows, identifiers = [], set()
	for index, row in enumerate(reader, 2):
		if index > 10002:
			raise BankingError("Importer høyst 10 000 banklinjer om gangen.")
		identifier = (row.get("transaction_id") or "").strip()
		if not identifier or len(identifier) > 140:
			raise BankingError(f"Linje {index}: transaksjons-ID mangler eller er for lang.")
		if identifier in identifiers:
			raise BankingError(f"Linje {index}: transaksjons-ID forekommer flere ganger i samme fil.")
		identifiers.add(identifier)
		try:
			amount = Decimal(row["amount"])
			if not amount.is_finite() or amount == 0 or amount != amount.quantize(Decimal(".01")):
				raise ValueError
		except (InvalidOperation, ValueError, TypeError):
			raise BankingError(f"Linje {index}: ugyldig beløp. Bruk to desimaler og punktum.") from None
		try:
			when = date.fromisoformat((row.get("date") or "").strip())
		except ValueError:
			raise BankingError(f"Linje {index}: dato må være ISO-formatet YYYY-MM-DD.") from None
		if row.get("currency") != "NOK" or when < start_date:
			raise BankingError(f"Linje {index}: filen må gjelde NOK-kontoen og dato fra regnskapsstart.")
		description = row.get("description") or ""
		rows.append(
			dict(
				amount=amount,
				date=when,
				description=description,
				row_hash=_row_hash(identifier, when, amount, description),
				transaction_id=identifier,
			)
		)
	return rows


def _key_and_fingerprint(category, values):
	key_values = {key: values[key] for key in ("category", "company", "invoice", "reference")}
	key_values["category"] = category
	key = _sha256(json.dumps(key_values, separators=(",", ":"), sort_keys=True))
	fingerprint = _sha256(json.dumps(values | {"category": category}, separators=(",", ":"), sort_keys=True))
	return key, fingerprint


def _existing_idempotent(doctype, key, fingerprint):
	name = frappe.db.get_value(doctype, {"enk_payment_key": key}, "name")
	if not name:
		return None
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	if doc.enk_payment_fingerprint != fingerprint:
		frappe.throw("Betalingsreferansen finnes allerede med andre opplysninger.")
	if doc.docstatus == 2:
		frappe.throw(
			"Betalingsreferansen peker på et annullert bilag. Bruk en ny, dokumentert referanse for korrigeringen."
		)
	return dict(doctype=doctype, name=name, reused=True)


def _source_content(file):
	content = file.get_content()
	if isinstance(content, str):
		return content.encode()
	return content


def _batch_result(batch):
	try:
		transactions = frappe.parse_json(batch.transactions_json)
	except (TypeError, ValueError):
		frappe.throw("Den arkiverte bankimporten mangler lesbare transaksjonsreferanser.")
	return dict(
		batch=batch.name,
		created=[],
		reused=[row["bank_transaction"] for row in transactions],
		source_sha256=batch.source_sha256,
	)


def _existing_bank_transaction(bank, row):
	existing = frappe.db.get_value(
		"Bank Transaction",
		{"bank_account": bank.name, "transaction_id": row["transaction_id"]},
		["name", "docstatus", "enk_row_hash"],
		as_dict=True,
	)
	if not existing:
		return None
	if existing.docstatus != 1 or not existing.enk_row_hash:
		frappe.throw(
			f"Transaksjons-ID {row['transaction_id']} finnes uten verifiserbar bankimport eller er annullert."
		)
	if existing.enk_row_hash != row["row_hash"]:
		frappe.throw(f"Transaksjons-ID {row['transaction_id']} finnes med andre opplysninger i bankfilen.")
	return existing


@frappe.whitelist(methods=["POST"])
def import_bank_csv(company, file_url):
	settings = get_settings(company)
	frappe.has_permission("ENK Bank Import", "create", throw=True)
	frappe.has_permission("ENK Bank Import", "submit", throw=True)
	frappe.has_permission("Bank Transaction", "create", throw=True)
	frappe.has_permission("Bank Transaction", "submit", throw=True)
	file = frappe.get_doc("File", {"file_url": file_url})
	file.check_permission("read")
	if not file.is_private:
		frappe.throw("Bankfilen må lastes opp som privat vedlegg.")
	content = _source_content(file)
	try:
		rows = _parse_bank_csv(content, getdate(settings.start_date))
	except BankingError as error:
		frappe.throw(str(error))
	source_sha256 = _sha256(content)
	bank = frappe.get_doc("Bank Account", settings.bank_account_record)
	bank.check_permission("write")
	# Én lås per bankkonto dekker både kildefil og transaksjons-ID-er for foretaket.
	frappe.db.sql("select name from `tabBank Account` where name=%s for update", bank.name)
	existing_batch = frappe.db.get_value(
		"ENK Bank Import", {"company": company, "source_sha256": source_sha256}, "name"
	)
	if existing_batch:
		batch = frappe.get_doc("ENK Bank Import", existing_batch)
		batch.check_permission("read")
		if batch.docstatus != 1:
			frappe.throw("Bankfilen har en ufullført import. Kontroller den før filen importeres på nytt.")
		return _batch_result(batch)
	if file.attached_to_doctype or file.attached_to_name:
		frappe.throw("Bankfilen er allerede knyttet til et dokument. Last opp en ny, privat kildefil.")
	file.check_permission("write")
	transaction_refs, created, reused = [], [], []
	for row in rows:
		existing = _existing_bank_transaction(bank, row)
		if existing:
			reused.append(existing.name)
			transaction_refs.append(dict(bank_transaction=existing.name, row_hash=row["row_hash"], status="Reused"))
		else:
			transaction_refs.append(dict(bank_transaction=None, row_hash=row["row_hash"], status="Created"))
	batch = frappe.get_doc(
		dict(
			doctype="ENK Bank Import",
			company=company,
			bank_account=bank.name,
			source_file=file.name,
			source_sha256=source_sha256,
			source_file_name=file.file_name,
			row_count=len(rows),
			transactions_json="[]",
		)
	)
	batch.insert()
	file.attached_to_doctype = batch.doctype
	file.attached_to_name = batch.name
	file.save()
	for row, reference in zip(rows, transaction_refs, strict=True):
		if reference["bank_transaction"]:
			continue
		doc = frappe.get_doc(
			dict(
				doctype="Bank Transaction",
				bank_account=bank.name,
				company=company,
				date=row["date"],
				currency="NOK",
				transaction_id=row["transaction_id"],
				description=row["description"],
				deposit=float(max(row["amount"], 0)),
				withdrawal=float(max(-row["amount"], 0)),
				enk_bank_import=batch.name,
				enk_row_hash=row["row_hash"],
			)
		)
		doc.insert()
		doc.submit()
		created.append(doc.name)
		reference["bank_transaction"] = doc.name
	batch.transactions_json = frappe.as_json(transaction_refs)
	batch.import_status = "Imported"
	batch.submit()
	return dict(batch=batch.name, created=created, reused=reused, source_sha256=source_sha256)


def _payment_currency_details(doc, amount, fee, bank_amount_nok, exchange_rate_source, exchange_rate_date, posting_date):
	"""Returner den bokførte NOK-hovedstolen og eventuell signert valuta-JE."""
	if doc.currency == "NOK":
		expected = amount - fee if doc.doctype == "Sales Invoice" else amount + fee
		if bank_amount_nok is not None and _amount(bank_amount_nok, "Faktisk bankbeløp") != expected:
			frappe.throw("Faktisk NOK-bankbeløp stemmer ikke med betaling og gebyr.")
		if exchange_rate_source or exchange_rate_date:
			frappe.throw("Kurskilde og kursdato brukes bare for valutabetalinger.")
		return dict(booked_nok=expected, bank_nok=expected, source=None, rate_date=None, adjustment=None)
	if bank_amount_nok is None:
		frappe.throw("Oppgi faktisk bankbeløp i NOK for valutabetalingen.")
	bank_nok = _amount(bank_amount_nok, "Faktisk bankbeløp")
	source = (exchange_rate_source or "").strip()
	if not source or len(source) > 140:
		frappe.throw("Oppgi kurskilde på høyst 140 tegn for valutabetalingen.")
	if not exchange_rate_date:
		frappe.throw("Oppgi kursdato for valutabetalingen.")
	try:
		rate_date = getdate(exchange_rate_date)
	except (TypeError, ValueError):
		frappe.throw("Kursdato må være YYYY-MM-DD.")
	if rate_date > getdate(posting_date):
		frappe.throw("Kursdato kan ikke være etter betalingsdatoen.")
	if doc.doctype == "Purchase Invoice" and bank_nok <= fee:
		frappe.throw("Faktisk bankbeløp må være større enn gebyret.")
	booked_nok = (amount * Decimal(str(doc.conversion_rate))).quantize(Decimal(".01"))
	principal_nok = bank_nok + fee if doc.doctype == "Sales Invoice" else bank_nok - fee
	gain = principal_nok - booked_nok if doc.doctype == "Sales Invoice" else booked_nok - principal_nok
	# Denne differansen justerer banklinjen fra reskontrooppgjørets historiske kurs
	# til den faktiske NOK-bevegelsen i banken.
	bank_adjustment = bank_nok - booked_nok if doc.doctype == "Sales Invoice" else booked_nok - bank_nok
	return dict(
		booked_nok=booked_nok,
		bank_nok=bank_nok,
		source=source,
		rate_date=rate_date,
		adjustment=dict(bank_adjustment=bank_adjustment, fee=fee, gain=gain),
	)


def _currency_adjustment_entry(doc, settings, posting, reference, key, details, payment_name):
	adjustment = details["adjustment"]
	if not any(adjustment.values()):
		return None
	adjustment_key, adjustment_fingerprint = _key_and_fingerprint(
		"currency-payment-adjustment",
		dict(
			category="currency-payment-adjustment",
			company=doc.company,
			invoice=f"{doc.doctype}:{doc.name}",
			posting_date=posting.isoformat(),
			reference=reference,
			payment_key=key,
			bank_adjustment=f"{adjustment['bank_adjustment']:.2f}",
			fee=f"{adjustment['fee']:.2f}",
			gain=f"{adjustment['gain']:.2f}",
		),
	)
	if existing := _existing_idempotent("Journal Entry", adjustment_key, adjustment_fingerprint):
		return existing["name"]
	cost_center = frappe.get_cached_value("Company", doc.company, "cost_center")
	accounts = []
	if adjustment["bank_adjustment"] > 0:
		accounts.append(dict(account=settings.bank_ledger_account, debit_in_account_currency=float(adjustment["bank_adjustment"])))
	elif adjustment["bank_adjustment"] < 0:
		accounts.append(dict(account=settings.bank_ledger_account, credit_in_account_currency=float(-adjustment["bank_adjustment"])))
	if adjustment["fee"]:
		accounts.append(dict(account=settings.fees_account, debit_in_account_currency=float(adjustment["fee"]), cost_center=cost_center))
	if adjustment["gain"] > 0:
		accounts.append(dict(account=settings.fx_gain_account, credit_in_account_currency=float(adjustment["gain"]), cost_center=cost_center))
	elif adjustment["gain"] < 0:
		accounts.append(dict(account=settings.fx_loss_account, debit_in_account_currency=float(-adjustment["gain"]), cost_center=cost_center))
	entry = frappe.get_doc(
		dict(
			doctype="Journal Entry",
			company=doc.company,
			posting_date=posting,
			voucher_type="Journal Entry",
			cheque_no=reference,
			cheque_date=posting,
			user_remark=f"Valutaoppgjør for {doc.doctype} {doc.name}: {details['source']}, kursdato {details['rate_date']}",
			enk_fx_payment_entry=payment_name,
			enk_payment_key=adjustment_key,
			enk_payment_fingerprint=adjustment_fingerprint,
			accounts=accounts,
		)
	)
	try:
		entry.insert()
		from enk_norge.posting_contract import seal_draft

		entry.db_set("enk_posting_contract", seal_draft(entry), update_modified=False)
	except frappe.DuplicateEntryError:
		if existing := _existing_idempotent("Journal Entry", adjustment_key, adjustment_fingerprint):
			return existing["name"]
		raise
	return entry.name


@frappe.whitelist(methods=["POST"])
def create_payment(
	doctype,
	name,
	amount,
	posting_date,
	reference,
	fee="0",
	bank_amount_nok=None,
	exchange_rate_source=None,
	exchange_rate_date=None,
):
	if doctype not in ("Sales Invoice", "Purchase Invoice"):
		frappe.throw("Velg en salgs- eller kjøpsfaktura.")
	# Hent dokumentet etter låsen. Da kan to requests ikke begge lage et utkast
	# basert på samme utestående beløp.
	frappe.db.sql(f"select name from `tab{doctype}` where name=%s for update", name)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	settings = get_settings(doc.company)
	amount = _amount(amount)
	fee = _amount(fee, "Gebyr", positive=False)
	posting = getdate(posting_date)
	reference = (reference or "").strip()
	if len(reference) > 140:
		frappe.throw("Betalingsreferansen er for lang.")
	if doc.docstatus != 1 or doc.is_return:
		frappe.throw("Velg en bokført faktura. Kreditnotaer avstemmes i ERPNext.")
	if fee < 0 or (doc.currency == "NOK" and fee >= amount):
		frappe.throw("Gebyr må være null eller lavere enn betalingen.")
	if not reference:
		frappe.throw("Oppgi betalingsreferansen fra banken.")
	details = _payment_currency_details(
		doc, amount, fee, bank_amount_nok, exchange_rate_source, exchange_rate_date, posting
	)
	key, fingerprint = _key_and_fingerprint(
		"invoice-payment",
		dict(
			amount=f"{amount:.2f}",
			category="invoice-payment",
			company=doc.company,
			currency=doc.currency,
			fee=f"{fee:.2f}",
			invoice=f"{doctype}:{doc.name}",
			posting_date=posting.isoformat(),
			reference=reference,
			bank_amount_nok=f"{details['bank_nok']:.2f}",
			exchange_rate_source=details["source"],
			exchange_rate_date=details["rate_date"].isoformat() if details["rate_date"] else None,
		),
	)
	if existing := _existing_idempotent("Payment Entry", key, fingerprint):
		response = existing.copy()
		if doc.currency != "NOK":
			adjustment_key, _ = _key_and_fingerprint(
				"currency-payment-adjustment",
				dict(category="currency-payment-adjustment", company=doc.company, invoice=f"{doctype}:{doc.name}", reference=reference),
			)
			response["adjustment_journal_entry"] = frappe.db.get_value("Journal Entry", {"enk_payment_key": adjustment_key}, "name")
		return response
	if amount > Decimal(str(doc.outstanding_amount)):
		frappe.throw("Betalingen er større enn utestående på fakturaen.")
	frappe.has_permission("Payment Entry", "create", throw=True)
	_ensure_settlement_year(doc, posting)
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	payment = get_payment_entry(
		doctype,
		name,
		party_amount=float(amount),
		bank_account=settings.bank_ledger_account,
		bank_amount=float(details["booked_nok"]),
		reference_date=posting,
	)
	if doc.currency == "NOK":
		payment.paid_amount = float(details["booked_nok"])
		payment.received_amount = float(details["booked_nok"])
	else:
		if doctype == "Sales Invoice":
			payment.paid_amount = float(amount)
			payment.received_amount = float(details["booked_nok"])
			payment.source_exchange_rate = float(doc.conversion_rate)
			payment.target_exchange_rate = 1
		else:
			payment.paid_amount = float(details["booked_nok"])
			payment.received_amount = float(amount)
			payment.source_exchange_rate = 1
			payment.target_exchange_rate = float(doc.conversion_rate)
		payment.set_amounts()
	payment.posting_date = posting
	payment.reference_no = reference
	payment.reference_date = posting
	payment.enk_payment_key = key
	payment.enk_payment_fingerprint = fingerprint
	payment.enk_exchange_rate_source = details["source"]
	payment.enk_exchange_rate_date = details["rate_date"]
	payment.enk_bank_amount_nok = float(details["bank_nok"])
	payment.enk_fee_amount_nok = float(fee)
	if fee and doc.currency == "NOK":
		payment.append(
			"deductions",
			dict(
				account=settings.fees_account,
				amount=float(fee),
				cost_center=frappe.get_cached_value("Company", doc.company, "cost_center"),
			),
		)
	try:
		payment.insert()
		from enk_norge.posting_contract import seal_draft

	except frappe.DuplicateEntryError:
		if existing := _existing_idempotent("Payment Entry", key, fingerprint):
			return existing
		raise
	adjustment_entry = (
		_currency_adjustment_entry(doc, settings, posting, reference, key, details, payment.name)
		if details["adjustment"]
		else None
	)
	payment.enk_fx_journal_entry = adjustment_entry
	payment.db_set({"enk_fx_journal_entry": adjustment_entry, "enk_posting_contract": seal_draft(payment)}, update_modified=False)
	return dict(
		doctype=payment.doctype,
		name=payment.name,
		reused=False,
		adjustment_journal_entry=adjustment_entry,
	)


@frappe.whitelist(methods=["POST"])
def owner_transfer(company, amount, posting_date, direction, description, reference):
	settings = get_settings(company)
	frappe.has_permission("Journal Entry", "create", throw=True)
	amount = _amount(amount)
	posting = getdate(posting_date)
	reference = (reference or "").strip()
	if direction not in ("Deposit", "Withdrawal", "Refund") or not description or not reference:
		frappe.throw("Velg innskudd, uttak eller refusjon, og oppgi beskrivelse og bankreferanse.")
	if len(reference) > 140:
		frappe.throw("Bankreferansen er for lang.")
	key, fingerprint = _key_and_fingerprint(
		"owner-transfer",
		dict(
			amount=f"{amount:.2f}",
			category="owner-transfer",
			company=company,
			description=description,
			direction=direction,
			invoice="",
			posting_date=posting.isoformat(),
			reference=reference,
		),
	)
	if existing := _existing_idempotent("Journal Entry", key, fingerprint):
		return existing
	owner_account = settings.withdrawal_account if direction == "Withdrawal" else settings.owner_account
	debit, credit = (
		(settings.bank_ledger_account, owner_account)
		if direction == "Deposit"
		else (owner_account, settings.bank_ledger_account)
	)
	doc = frappe.get_doc(
		dict(
			doctype="Journal Entry",
			company=company,
			posting_date=posting,
			voucher_type="Journal Entry",
			cheque_no=reference,
			cheque_date=posting,
			user_remark=description,
			enk_payment_key=key,
			enk_payment_fingerprint=fingerprint,
			accounts=[
				dict(account=debit, debit_in_account_currency=float(amount)),
				dict(account=credit, credit_in_account_currency=float(amount)),
			],
		)
	)
	try:
		doc.insert()
		from enk_norge.posting_contract import seal_draft

		doc.db_set("enk_posting_contract", seal_draft(doc), update_modified=False)
	except frappe.DuplicateEntryError:
		if existing := _existing_idempotent("Journal Entry", key, fingerprint):
			return existing
		raise
	return dict(doctype=doc.doctype, name=doc.name, reused=False)


def sync_currency_adjustment(doc, method=None):
	"""Betalingen og valutaavviket bokføres i samme databasetransaksjon."""
	name = doc.get("enk_fx_journal_entry")
	if not name:
		return
	entry = frappe.get_doc("Journal Entry", name)
	if entry.company != doc.company or entry.enk_fx_payment_entry != doc.name:
		frappe.throw("Valutaføringen er ikke koblet til denne betalingen.")
	previous = frappe.flags.get("enk_fx_payment_operation")
	frappe.flags.enk_fx_payment_operation = doc.name
	try:
		if method == "on_submit":
			if entry.docstatus != 0:
				frappe.throw("Valutaføringen må være et utkast når betalingen bokføres.")
			entry.submit()
		elif method == "before_cancel":
			if entry.docstatus != 1:
				frappe.throw("Valutaføringen må være bokført når betalingen annulleres.")
			entry.cancel()
	finally:
		frappe.flags.enk_fx_payment_operation = previous


def validate_currency_adjustment_operation(doc):
	payment_name = doc.get("enk_fx_payment_entry")
	if payment_name and frappe.flags.get("enk_fx_payment_operation") != payment_name:
		frappe.throw("Valutaføringen bokføres og annulleres sammen med betalingen. Åpne betalingen i stedet.")


def _ensure_settlement_year(invoice, posting):
	if posting.year == 2026:
		return
	if posting.year != 2027 or getdate(invoice.posting_date).year != 2026:
		frappe.throw("Denne flyten støtter 2026-bilag og oppgjør av disse i 2027.")
	from erpnext.accounts.utils import get_fiscal_year

	if get_fiscal_year(posting, company=invoice.company, raise_on_missing=False):
		return
	frappe.db.sql("select name from `tabDocType` where name='Fiscal Year' for update")
	if not get_fiscal_year(posting, company=invoice.company, raise_on_missing=False):
		if frappe.db.exists("Fiscal Year", "2027"):
			frappe.throw("Regnskapsåret 2027 finnes, men er ikke åpent for foretaket. Kontroller regnskapsåret.")
		frappe.get_doc(dict(doctype="Fiscal Year", year="2027", year_start_date="2027-01-01", year_end_date="2027-12-31")).insert(ignore_permissions=True)
