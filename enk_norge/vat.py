"""Avgrenset MVA-rapportering og omvendt avgift for 2026.

Rapporten er et kontrollert grunnlag for manuell levering, ikke en innsending.

Kilder:
- https://www.skatteetaten.no/rettskilder/type/handboker/merverdiavgiftshandboken/gjeldende/M-11/M-11-3/M-11-3.2/
- https://www.skatteetaten.no/rettskilder/type/handboker/skatteforvaltningshandboken/gjeldende/kapittel-8-opplysningsplikt-for-skattepliktige-trekkpliktige-mv/ID-8-3.001/ID-8-3.014/
"""

from __future__ import annotations

import json
from calendar import monthrange
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from hashlib import sha256

MONEY = Decimal(".01")
RATES = {"Domestic 25": Decimal(".25"), "Domestic 15": Decimal(".15"), "Domestic 12": Decimal(".12")}


class VatError(ValueError):
	pass


def _d(v, neg=True):
	if isinstance(v, bool) or isinstance(v, float):
		raise VatError("Beløp må gis som desimaltekst eller Decimal.")
	x = v if isinstance(v, Decimal) else Decimal(str(v))
	if not x.is_finite() or (not neg and x < 0):
		raise VatError("Ugyldig beløp.")
	return x


def _m(v):
	return _d(v).quantize(MONEY, ROUND_HALF_UP)


def _s(v):
	return format(_m(v), ".2f")


def _json(v):
	return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(v):
	return sha256(_json(v).encode()).hexdigest()


def _frappe():
	import frappe

	return frappe


def _return_name(company, end, report_type, revision=1):
	"""Et navn per foretak, periode og rapporttype, også i overgangskvartal."""
	key = f"{company}|{end}|{report_type}" if revision == 1 else f"{company}|{end}|{report_type}|{revision}"
	return "ENK-VAT-" + sha256(key.encode()).hexdigest()[:24]


def period_for(settings, end, report_type):
	if isinstance(end, str):
		end = date.fromisoformat(end)
	if end.year != 2026:
		raise VatError("MVA-motoren støtter bare 2026.")
	reg = (
		date.fromisoformat(str(settings.vat_registration_date))
		if settings.vat_registered and settings.vat_registration_date
		else None
	)
	if report_type == "Ordinary":
		if not reg or reg > end:
			raise VatError("Ordinær MVA-rapport krever MVA-registrering som gjelder i terminen.")
		month = ((end.month - 1) // 2) * 2 + 1
		term_start = date(end.year, month, 1)
		term_end = date(end.year, month + 1, monthrange(end.year, month + 1)[1])
		if end != term_end:
			raise VatError("Ordinær MVA-rapport må avsluttes siste dag i en tomånedstermin.")
		# Første melding omfatter også omsetning under beløpsgrensen i den
		# aktuelle terminen, jf. Skatteetatens veiledning om registrering.
		return term_start, term_end, "Registered bi-monthly", reg > term_start
	if report_type == "Reverse charge unregistered":
		month = ((end.month - 1) // 3) * 3 + 1
		qstart = date(end.year, month, 1)
		qend = date(end.year, month + 2, monthrange(end.year, month + 2)[1])
		if end != qend:
			raise VatError("Uregistrert omvendt MVA må avsluttes siste dag i kalenderkvartalet.")
		if reg and reg <= qstart:
			raise VatError("Registrert foretak rapporterer omvendt MVA i ordinær mva-melding.")
		return qstart, qend, "Unregistered reverse charge quarterly", bool(reg and reg <= qend)


def _docs(company, start, end, doctype):
	f = _frappe()
	return f.get_list(
		doctype,
		filters={"company": company, "docstatus": 1, "posting_date": ["between", [start, end]]},
		fields=[
			"name",
			"posting_date",
			"net_total",
			"grand_total",
			"enk_tax_treatment",
			"enk_vat_basis",
			"enk_deductible_fraction",
		],
		order_by="posting_date,name",
		limit_page_length=0,
	)


def _taxes(doc):
	f = _frappe()
	return f.get_list(
		"Sales Taxes and Charges" if doc.doctype == "Sales Invoice" else "Purchase Taxes and Charges",
		filters={"parent": doc.name},
		fields=["account_head", "tax_amount"],
		limit_page_length=0,
	)


def _gl(company, start, end, account):
	f = _frappe()
	rows = f.get_list(
		"GL Entry",
		filters={
			"company": company,
			"account": account,
			"posting_date": ["between", [start, end]],
			"is_cancelled": 0,
		},
		fields=["debit", "credit"],
		limit_page_length=0,
	)
	return sum((_d(str(r.credit)) - _d(str(r.debit)) for r in rows), Decimal())


def _generated_reverse_gl(company, period_end, report_type, account):
	"""Henter bare den genererte omvendt-MVA-posten for den aktuelle rapporttypen."""

	f = _frappe()
	remark = f"ENK omvendt MVA {report_type} {period_end}"
	vouchers = f.get_list(
		"Journal Entry",
		filters={
			"company": company,
			"enk_vat_period": str(period_end),
			"user_remark": remark,
			"docstatus": 1,
		},
		pluck="name",
		limit_page_length=0,
	)
	if not vouchers:
		return Decimal()
	rows = f.get_list(
		"GL Entry",
		filters={
			"company": company,
			"account": account,
			"voucher_type": "Journal Entry",
			"voucher_no": ["in", vouchers],
			"is_cancelled": 0,
		},
		fields=["debit", "credit"],
		limit_page_length=0,
	)
	return sum((_d(str(row.credit)) - _d(str(row.debit)) for row in rows), Decimal())


def _foreign_for_report(purchases, report_type, registration_date):
	"""Avgrenser innførte tjenester etter faktisk registreringsdato.

	Før registrering hører de i særskilt kvartalsmelding; fra datoen hører de i
	ordinær mva-melding. Kildene skiller meldingsform etter om mottakeren er
	registrert, slik at samme kjøp ikke kan inngå i begge rapportene.
	"""

	if registration_date is not None and not isinstance(registration_date, date):
		raise VatError("Registreringsdato må være dato.")
	if report_type not in ("Ordinary", "Reverse charge unregistered"):
		raise VatError("Ukjent MVA-rapporttype.")
	selected = []
	for purchase in purchases:
		posting = purchase.posting_date
		if isinstance(posting, str):
			posting = date.fromisoformat(posting)
		if not isinstance(posting, date):
			raise VatError("Kjøpets bokføringsdato må være dato.")
		if report_type == "Ordinary":
			if registration_date is None or posting >= registration_date:
				selected.append(purchase)
		elif registration_date is None or posting < registration_date:
			selected.append(purchase)
	return selected


def _foreign(purchases, registered):
	basis = Decimal()
	output = Decimal()
	input_vat = Decimal()
	for p in purchases:
		b = _d(str(p.enk_vat_basis))
		frac = _d(str(p.enk_deductible_fraction if p.enk_deductible_fraction is not None else 1), False)
		if frac > 1:
			raise VatError("Fradragsandel kan ikke overstige 1.")
		vat = _m(b * Decimal(".25"))
		basis += b
		output += vat
		if registered:
			input_vat += _m(vat * frac)
	return _m(basis), _m(output), _m(input_vat)


def build_vat_return(company, period_end, report_type="Ordinary"):
	f = _frappe()
	from enk_norge.setup import get_settings

	settings = get_settings(company, write=True)
	f.db.sql("select name from `tabCompany` where name=%s for update", company)
	start, end, ptype, _overlap = period_for(settings, period_end, report_type)
	sales = _docs(company, start, end, "Sales Invoice") if report_type == "Ordinary" else []
	purchases = _docs(company, start, end, "Purchase Invoice")
	registration_date = (
		date.fromisoformat(str(settings.vat_registration_date))
		if settings.vat_registered and settings.vat_registration_date
		else None
	)
	bases = {r: Decimal() for r in RATES}
	export = Decimal()
	exempt = Decimal()
	output = Decimal()
	input_invoice = Decimal()
	foreign = []
	for row in sales:
		t = row.enk_tax_treatment
		if t in RATES:
			bases[t] += _d(str(row.net_total))
			output += _m(_d(str(row.net_total)) * RATES[t])
		elif t == "Export services":
			export += _d(str(row.net_total))
		elif t == "Exempt":
			exempt += _d(str(row.net_total))
		elif t != "Not registered":
			f.throw("Ukjent avgiftsbehandling på salg: " + str(t))
		for tax in _taxes(f.get_doc("Sales Invoice", row.name)):
			if tax.account_head != settings.output_vat_account and _d(str(tax.tax_amount)) != 0:
				f.throw("Salg har MVA på feil konto.")
	for row in purchases:
		if row.enk_tax_treatment == "Foreign services":
			if _taxes(f.get_doc("Purchase Invoice", row.name)):
				f.throw("Utenlandsk tjeneste kan ikke ha leverandørens MVA-rader.")
			foreign.append(row)
			continue
		for tax in _taxes(f.get_doc("Purchase Invoice", row.name)):
			if tax.account_head == settings.input_vat_account:
				input_invoice += _d(str(tax.tax_amount))
	foreign = _foreign_for_report(foreign, report_type, registration_date)
	registered = report_type == "Ordinary"
	basis, reverse_output, reverse_input = _foreign(foreign, registered)
	if report_type == "Reverse charge unregistered" and basis <= Decimal("2000"):
		basis = reverse_output = reverse_input = Decimal()
	expected_output = _m(output)
	expected_input = _m(input_invoice + reverse_input)
	checks = []
	if report_type == "Ordinary":
		out_gl = _gl(company, start, end, settings.output_vat_account)
		in_gl = -_gl(company, start, end, settings.input_vat_account)
		if out_gl != expected_output:
			checks.append("Utgående MVA i hovedbok avviker fra fakturarader.")
		if in_gl != expected_input:
			checks.append("Inngående MVA i hovedbok avviker fra leverandørbilag og omvendt MVA.")
	else:
		out_gl = expected_output
		in_gl = expected_input
	rev_gl = _generated_reverse_gl(company, end, report_type, settings.reverse_vat_account)
	if rev_gl != reverse_output:
		checks.append("Omvendt MVA i hovedbok mangler eller avviker fra utenlandske tjenestekjøp.")
	payload = {
		"company": company,
		"start": str(start),
		"end": str(end),
		"type": report_type,
		"sales": [(r.name, str(r.net_total), r.enk_tax_treatment) for r in sales],
		"purchases": [(r.name, str(r.enk_vat_basis), r.enk_tax_treatment) for r in purchases],
		"checks": checks,
	}
	return _store(
		company,
		start,
		end,
		report_type,
		ptype,
		{
			"sales_25_basis": bases["Domestic 25"],
			"sales_15_basis": bases["Domestic 15"],
			"sales_12_basis": bases["Domestic 12"],
			"output_vat": expected_output,
			"export_turnover": export,
			"exempt_turnover": exempt,
			"purchase_input_vat": input_invoice,
			"reverse_charge_basis": basis,
			"reverse_charge_output_vat": reverse_output,
			"reverse_charge_input_vat": reverse_input,
			"net_vat_payable": _m(expected_output + reverse_output - expected_input),
			"output_vat_gl": out_gl,
			"input_vat_gl": in_gl,
			"reverse_vat_gl": rev_gl,
		},
		checks,
		payload,
	)


def _find_vat_return(company, end, report_type):
	f = _frappe()
	names = f.get_list(
		"ENK VAT Return",
		filters={"company": company, "period_end": end, "report_type": report_type},
		pluck="name",
		order_by="revision desc, creation desc",
		limit_page_length=1,
	)
	return f.get_doc("ENK VAT Return", names[0]) if names else None


def _snapshot_history(value):
	try:
		history = json.loads(value or "[]")
	except json.JSONDecodeError as error:
		raise VatError("MVA-rapportens snapshot-historikk må være gyldig JSON.") from error
	if not isinstance(history, list):
		raise VatError("MVA-rapportens snapshot-historikk må være en liste.")
	return history


def _append_snapshot(history, report):
	if report.snapshot_json and report.snapshot_hash:
		history.append(
			{
				"revision": int(report.revision or 1),
				"hash": report.snapshot_hash,
				"snapshot": json.loads(report.snapshot_json),
				"prepared_at": str(report.prepared_at),
			}
		)
	return history


def _store(company, start, end, report_type, ptype, values, checks, payload):
	f = _frappe()
	previous = _find_vat_return(company, end, report_type)
	if previous and previous.status != "Manually filed":
		doc = previous
		history = _append_snapshot(_snapshot_history(doc.snapshot_history_json), doc)
		doc.revision = int(doc.revision or 0) + 1
	else:
		doc = f.new_doc("ENK VAT Return")
		doc.company = company
		doc.period_end = end
		doc.report_type = report_type
		doc.revision = int(previous.revision or 0) + 1 if previous else 1
		doc.name = _return_name(company, end, report_type, doc.revision)
		history = _snapshot_history(previous.snapshot_history_json) if previous else []
		if previous:
			history = _append_snapshot(history, previous)
	doc.company = company
	doc.period_start = start
	doc.period_end = end
	doc.report_type = report_type
	doc.period_type = ptype
	doc.revision = int(doc.revision or 0) + 1
	doc.status = "Ready for review" if not checks else "Draft"
	doc.manual_filing_status = "Not filed"
	doc.prepared_at = f.utils.now_datetime()
	doc.snapshot_json = _json(payload)
	doc.snapshot_hash = _hash(payload)
	doc.snapshot_history_json = _json(history)
	doc.reconciliation_json = _json(checks)
	for k, v in values.items():
		setattr(doc, k, _s(v))
	doc.flags.enk_vat_return_build = True
	doc.save()
	return {
		"name": doc.name,
		"status": doc.status,
		"revision": doc.revision,
		"snapshot_hash": doc.snapshot_hash,
		"checks": checks,
	}


def create_reverse_charge_draft(company, period_end, report_type="Ordinary"):
	"""Lager et tydelig nytt utkast for netto delta etter bokførte periodjusteringer.

	Et eksisterende generert utkast endres aldri automatisk; brukeren må kontrollere
	eller slette det før ny beregning. MariaDB-låsen serialiserer samtidige kall.
	"""
	f = _frappe()
	from enk_norge.setup import get_settings

	settings = get_settings(company, write=True)
	start, end, _ptype, overlap = period_for(settings, period_end, report_type)
	# Denne raden holdes låst til requesten er committet. Det hindrer at et annet
	# kall ikke ser et nettopp opprettet, men ucommittet, utkast.
	f.db.sql("select name from `tabCompany` where name=%s for update", [company])
	key = f"enk-vat-reverse:{company}:{end}:{report_type}"
	locked = f.db.sql("select get_lock(%s, 10)", [key])[0][0]
	if not locked:
		f.throw("Kunne ikke låse MVA-terminen. Prøv igjen.")
	try:
		ps = [
			p
			for p in _docs(company, start, end, "Purchase Invoice")
			if p.enk_tax_treatment == "Foreign services"
		]
		registration_date = (
			date.fromisoformat(str(settings.vat_registration_date))
			if settings.vat_registered and settings.vat_registration_date
			else None
		)
		ps = _foreign_for_report(ps, report_type, registration_date)
		registered = report_type == "Ordinary"
		basis, out, inp = _foreign(ps, registered)
		if not registered and basis <= Decimal("2000"):
			basis = out = inp = Decimal()
		period = str(end)
		remark = f"ENK omvendt MVA {report_type} {period}"
		drafts = f.get_list(
			"Journal Entry",
			filters={"company": company, "enk_vat_period": period, "docstatus": 0, "user_remark": remark},
			pluck="name",
			limit_page_length=2,
		)
		if len(drafts) > 1:
			f.throw("Flere genererte MVA-utkast finnes for terminen.")
		if drafts:
			draft = f.get_doc("Journal Entry", drafts[0])
			content = [
				(
					row.account,
					_s(str(row.debit_in_account_currency)),
					_s(str(row.credit_in_account_currency)),
				)
				for row in draft.accounts
			]
			return {
				"doctype": "Journal Entry",
				"name": draft.name,
				"period": period,
				"needs_review": True,
				"draft_hash": _hash(content),
				"message": "Eksisterende MVA-utkast er ikke overskrevet.",
			}
		posted = f.get_list(
			"Journal Entry",
			filters={"company": company, "enk_vat_period": period, "docstatus": 1, "user_remark": remark},
			pluck="name",
			limit_page_length=0,
		)
		booked_out = booked_input = booked_cost = Decimal()
		if posted:
			for row in f.get_list(
				"GL Entry",
				filters={
					"company": company,
					"voucher_type": "Journal Entry",
					"voucher_no": ["in", posted],
					"is_cancelled": 0,
				},
				fields=["account", "debit", "credit"],
				limit_page_length=0,
			):
				amount = _d(str(row.credit)) - _d(str(row.debit))
				if row.account == settings.reverse_vat_account:
					booked_out += amount
				elif row.account == settings.input_vat_account:
					booked_input -= amount
				elif row.account == settings.software_account:
					booked_cost -= amount
		delta_out = _m(out - booked_out)
		delta_input = _m(inp - booked_input)
		delta_cost = _m((out - inp) - booked_cost)
		if not any((delta_out, delta_input, delta_cost)):
			return {"period": period, "up_to_date": True, "basis": _s(basis), "output_vat": _s(out)}
		doc = f.new_doc("Journal Entry")
		doc.company = company
		doc.posting_date = end
		doc.voucher_type = "Journal Entry"
		doc.user_remark = remark
		doc.enk_vat_period = period
		for account, amount in (
			(settings.input_vat_account, delta_input),
			(settings.software_account, delta_cost),
			(settings.reverse_vat_account, -delta_out),
		):
			if not amount:
				continue
			line = {"account": account}
			line["debit_in_account_currency" if amount > 0 else "credit_in_account_currency"] = _s(
				abs(amount)
			)
			doc.append("accounts", line)
		doc.insert()
		from enk_norge.posting_contract import seal_draft

		doc.db_set("enk_posting_contract", seal_draft(doc))
		return {
			"doctype": "Journal Entry",
			"name": doc.name,
			"period": period,
			"basis": _s(basis),
			"output_vat": _s(out),
			"delta_output_vat": _s(delta_out),
			"overlaps_registration": overlap,
		}
	finally:
		f.db.sql("select release_lock(%s)", [key])


def mark_vat_return_manually_filed(company, period_end, private_receipt_file, report_type="Ordinary"):
	f = _frappe()
	from enk_norge.setup import get_settings

	get_settings(company, write=True)
	names = f.get_list(
		"ENK VAT Return",
		filters={"company": company, "period_end": period_end, "report_type": report_type},
		pluck="name",
		order_by="revision desc",
		limit_page_length=1,
	)
	if not names:
		f.throw("MVA-rapporten finnes ikke.")
	doc = f.get_doc("ENK VAT Return", names[0])
	doc.check_permission("write")
	file = f.get_doc("File", private_receipt_file)
	file.check_permission("read")
	if (
		doc.status != "Ready for review"
		or not file.is_private
		or file.attached_to_doctype != "ENK VAT Return"
		or file.attached_to_name != doc.name
	):
		f.throw("Klar rapport og privat leveringskvittering knyttet til rapporten kreves.")
	doc.status = "Manually filed"
	doc.manual_filing_status = "Manually filed"
	doc.private_receipt_file = private_receipt_file
	doc.manually_filed_at = f.utils.now_datetime()
	doc.flags.enk_vat_return_filing = True
	doc.save()
	return {"name": doc.name, "status": doc.status}


def get_vat_return(company, period_end, report_type="Ordinary"):
	"""Henter kun rapporten for en Company brukeren har lesetilgang til."""
	f = _frappe()
	from enk_norge.setup import get_settings

	get_settings(company, write=False)
	doc = _find_vat_return(company, period_end, report_type)
	if not doc:
		f.throw("MVA-rapporten finnes ikke.")
	doc.check_permission("read")
	return {
		"name": doc.name,
		"company": doc.company,
		"period_start": str(doc.period_start),
		"period_end": str(doc.period_end),
		"report_type": doc.report_type,
		"status": doc.status,
		"revision": doc.revision,
		"snapshot_hash": doc.snapshot_hash,
		"checks": json.loads(doc.reconciliation_json or "[]"),
	}


def validate_vat_return_document(doc):
	"""Hindrer standard-REST fra å late som om MVA-grunnlaget er klart eller levert."""
	f = _frappe()
	from enk_norge.setup import get_settings

	get_settings(doc.company, write=True)
	old = doc.get_doc_before_save()
	if old and old.status == "Manually filed":
		f.throw("Manuelt levert MVA-rapport kan ikke endres. Opprett en korrigerende revisjon.")
	if doc.status in ("Draft", "Ready for review"):
		if not doc.flags.enk_vat_return_build:
			f.throw("MVA-rapportens status og snapshot kan bare opprettes via MVA-beregningen.")
		_validate_vat_snapshot(doc)
	if doc.status == "Manually filed":
		if not old or old.status != "Ready for review" or not doc.flags.enk_vat_return_filing:
			f.throw("Bare en klar MVA-rapport kan markeres som manuelt levert.")
		_validate_vat_snapshot(doc)
		_validate_private_receipt(doc)


def _validate_vat_snapshot(report):
	f = _frappe()
	try:
		payload = json.loads(report.snapshot_json or "")
	except json.JSONDecodeError:
		f.throw("MVA-rapportens snapshot må være gyldig JSON.")
	if not isinstance(payload, dict) or _hash(payload) != report.snapshot_hash:
		f.throw("MVA-rapportens snapshot-hash stemmer ikke med beregningen.")
	if (
		payload.get("company") != report.company
		or payload.get("end") != str(report.period_end)
		or payload.get("type") != report.report_type
	):
		f.throw("MVA-rapportens snapshot tilhører ikke rapporten.")
	try:
		checks = json.loads(report.reconciliation_json or "[]")
	except json.JSONDecodeError:
		f.throw("MVA-rapportens avstemming må være gyldig JSON.")
	if checks != payload.get("checks"):
		f.throw("MVA-rapportens avstemming stemmer ikke med snapshotet.")
	for revision in _snapshot_history(report.snapshot_history_json):
		if not isinstance(revision, dict) or not isinstance(revision.get("hash"), str):
			f.throw("Historisk MVA-snapshot er ugyldig.")
		if not isinstance(revision.get("snapshot"), dict) or _hash(revision["snapshot"]) != revision["hash"]:
			f.throw("Historisk MVA-snapshot har feil hash.")


def _validate_private_receipt(report):
	f = _frappe()
	if report.manual_filing_status != "Manually filed" or not report.private_receipt_file:
		f.throw("Manuell levering krever privat leveringskvittering.")
	try:
		receipt = f.get_doc("File", report.private_receipt_file)
	except Exception:
		f.throw("Leveringskvitteringen finnes ikke.")
	receipt.check_permission("read")
	if (
		not receipt.is_private
		or receipt.attached_to_doctype != "ENK VAT Return"
		or receipt.attached_to_name != report.name
	):
		f.throw("Leveringskvitteringen må være privat, knyttet til denne rapporten og lesbar for brukeren.")


def _wl(fn, methods=None):
	try:
		return _frappe().whitelist(methods=methods)(fn)
	except ModuleNotFoundError:
		return fn


build_vat_return = _wl(build_vat_return, methods=["POST"])
create_reverse_charge_draft = _wl(create_reverse_charge_draft, methods=["POST"])
mark_vat_return_manually_filed = _wl(mark_vat_return_manually_filed, methods=["POST"])
get_vat_return = _wl(get_vat_return, methods=["GET"])
