"""Kontrollert periodisering av forskuddsfakturert SaaS i 2026-2027."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from hashlib import sha256
from typing import Any

NOK = Decimal("0.01")
class DeferralError(ValueError):
	"""Periodiseringen mangler et etterprøvbart grunnlag."""


@dataclass(frozen=True, slots=True)
class EarnedRevenue:
	service_start: date
	service_end: date
	through_date: date
	total_days: int
	earned_days: int
	cumulative_amount: Decimal


def _date(value: Any, label: str) -> date:
	if isinstance(value, date):
		return value
	try:
		return date.fromisoformat(str(value))
	except (TypeError, ValueError) as error:
		raise DeferralError(f"{label} må være en dato på formen YYYY-MM-DD.") from error


def _money(value: Any, label: str, *, allow_negative: bool = False) -> Decimal:
	try:
		amount = Decimal(str(value))
	except (InvalidOperation, TypeError, ValueError) as error:
		raise DeferralError(f"{label} må være et gyldig beløp.") from error
	if not amount.is_finite() or (not allow_negative and amount < 0):
		raise DeferralError(f"{label} må være et gyldig beløp.")
	return amount.quantize(NOK, rounding=ROUND_HALF_UP)


def validate_subscription_period(
	service_start: Any, service_end: Any, *, invoice_date: Any | None = None
) -> tuple[date, date]:
	"""Godtar en sammenhengende, forskuddsfakturert tjenesteperiode på høyst ett år."""
	start = _date(service_start, "Tjenestestart")
	end = _date(service_end, "Tjenesteslutt")
	if end < start:
		raise DeferralError("Tjenesteslutt kan ikke være før tjenestestart.")
	try:
		next_anniversary = start.replace(year=start.year + 1)
	except ValueError:  # 29. februar får 28. februar året etter.
		next_anniversary = start.replace(year=start.year + 1, day=28)
	if end > next_anniversary - timedelta(days=1):
		raise DeferralError("Jevn SaaS-periodisering støtter abonnement på høyst ett år.")
	if invoice_date is not None and _date(invoice_date, "Fakturadato") > start:
		raise DeferralError("Periodisering støtter bare forskuddsfakturering før eller på tjenestestart.")
	if start.year != 2026 or end.year not in (2026, 2027):
		raise DeferralError("Denne periodiseringsflyten støtter bare avtaler som starter i 2026 og slutter i 2026 eller 2027.")
	return start, end


def cumulative_earned_amount(
	amount: Any, service_start: Any, service_end: Any, through_date: Any
) -> EarnedRevenue:
	"""Fordeler NOK-beløpet lineært per levert kalenderdag, begge endepunkter medregnet."""
	total = _money(amount, "Abonnementsbeløp")
	start, end = validate_subscription_period(service_start, service_end)
	through = _date(through_date, "Periodiseringsdato")
	if through < start:
		raise DeferralError("Periodiseringsdatoen kan ikke være før tjenestestart.")
	if through > end:
		raise DeferralError("Periodiseringsdatoen kan ikke være etter tjenesteslutt.")
	earned_through = through
	total_days = (end - start).days + 1
	earned_days = (earned_through - start).days + 1
	return EarnedRevenue(
		service_start=start,
		service_end=end,
		through_date=earned_through,
		total_days=total_days,
		earned_days=earned_days,
		cumulative_amount=(total * Decimal(earned_days) / Decimal(total_days)).quantize(NOK, rounding=ROUND_HALF_UP),
	)


def recognition_increment(cumulative_amount: Any, already_recognized: Any) -> Decimal:
	"""Returnerer ny opptjent inntekt uten å la en omkjøring bokføre samme beløp to ganger."""
	cumulative = _money(cumulative_amount, "Opptjent beløp")
	recognized = _money(already_recognized, "Allerede periodisert beløp")
	if recognized > cumulative:
		raise DeferralError("Tidligere periodisering overstiger opptjent abonnementsinntekt.")
	return cumulative - recognized


def subscription_sale_values(data: Any, settings: Any, posting_date: Any) -> dict[str, str] | None:
	"""Validerer API-kontrakten og gir native Sales Invoice Item-felter ved periodisering."""
	keys = ("service_start_date", "service_end_date", "subscription_source_file")
	provided = [bool(str((data.get(key) if hasattr(data, "get") else None) or "").strip()) for key in keys]
	if not any(provided):
		return None
	if not all(provided):
		raise DeferralError("Periodisering krever tjenestestart, tjenesteslutt og privat avtaledokument.")
	start, end = validate_subscription_period(
		data.get("service_start_date"), data.get("service_end_date"), invoice_date=posting_date
	)
	if not getattr(settings, "deferred_revenue_account", None):
		raise DeferralError("Foretaket mangler konto for utsatt inntekt.")
	return {
		"enable_deferred_revenue": 1,
		"deferred_revenue_account": settings.deferred_revenue_account,
		"service_start_date": start.isoformat(),
		"service_end_date": end.isoformat(),
	}


def _frappe():
	import frappe

	return frappe


def _settings(company: str, *, write: bool):
	from enk_norge.setup import get_settings

	return get_settings(company, write=write)


def _source_file(file_name: str, *, invoice: Any | None = None):
	frappe = _frappe()
	if not file_name:
		frappe.throw("Periodisert abonnement krever et privat avtaledokument.")
	try:
		file = frappe.get_doc("File", file_name)
	except Exception:
		frappe.throw("Avtaledokumentet finnes ikke.")
	file.check_permission("read")
	file.check_permission("write")
	if not file.is_private:
		frappe.throw("Avtaledokumentet må være privat.")
	if invoice and file.attached_to_name not in (None, "", invoice.name):
		frappe.throw("Avtaledokumentet er allerede knyttet til et annet dokument.")
	return file


def attach_subscription_source(invoice: Any, file_name: str) -> None:
	"""Knytter en privat avtale til fakturaen før den kan bokføres."""
	file = _source_file(file_name, invoice=invoice)
	if not file.attached_to_name:
		file.attached_to_doctype = invoice.doctype
		file.attached_to_name = invoice.name
		file.save()
	invoice.enk_subscription_source_file = file.name
	invoice.db_set("enk_subscription_source_file", file.name, update_modified=False)


def _source_hash(file: Any) -> str:
	content = file.get_content()
	if isinstance(content, str):
		content = content.encode()
	return sha256(content).hexdigest()


def _ensure_open_period(settings: Any, posting_date: date) -> None:
	frappe = _frappe()
	if settings.frozen_through and posting_date <= _date(settings.frozen_through, "Stengt dato"):
		frappe.throw("Perioden er stengt i ENK-oppsettet. Periodiseringsbilag kan ikke opprettes.")


def _ensure_deferral_fiscal_year(invoice: Any, posting_date: date) -> None:
	"""Oppretter bare 2027-regnskapsår når et kontrollert 2026-abonnement trenger det."""
	if posting_date.year == 2026:
		return
	frappe = _frappe()
	if posting_date.year != 2027 or _date(invoice.posting_date, "Fakturadato").year != 2026:
		frappe.throw("Denne periodiseringsflyten støtter bare 2026-fakturaer og opptjent inntekt i 2027.")
	from erpnext.accounts.utils import get_fiscal_year

	if get_fiscal_year(posting_date, company=invoice.company, raise_on_missing=False):
		return
	frappe.db.sql("select name from `tabDocType` where name='Fiscal Year' for update")
	if get_fiscal_year(posting_date, company=invoice.company, raise_on_missing=False):
		return
	if frappe.db.exists("Fiscal Year", "2027"):
		frappe.throw("Regnskapsåret 2027 finnes, men er ikke åpent for foretaket. Kontroller regnskapsåret.")
	frappe.get_doc(
		dict(doctype="Fiscal Year", year="2027", year_start_date="2027-01-01", year_end_date="2027-12-31")
	).insert(ignore_permissions=True)


def _invoice_items(invoice: Any, settings: Any) -> list[Any]:
	items = [item for item in invoice.items if item.enable_deferred_revenue]
	if not items:
		raise DeferralError("Fakturaen inneholder ikke et periodisert abonnement.")
	for item in items:
		if item.service_stop_date:
			raise DeferralError("Tjenestestopp støttes ikke for kontrollert periodisering. Bruk kreditnota med refusjonsgrunnlag.")
		start, end = validate_subscription_period(
			item.service_start_date, item.service_end_date, invoice_date=invoice.posting_date
		)
		if item.deferred_revenue_account != settings.deferred_revenue_account:
			raise DeferralError("Periodisert abonnement må bruke foretakets konto for utsatt inntekt.")
		if not item.income_account:
			raise DeferralError("Periodisert abonnement mangler inntektskonto.")
		item.service_start_date, item.service_end_date = start, end
	return items


def _existing_key(key: str):
	frappe = _frappe()
	name = frappe.db.get_value("Journal Entry", {"enk_deferral_key": key}, "name", for_update=True)
	if not name:
		return None
	doc = frappe.get_doc("Journal Entry", name)
	doc.check_permission("read")
	if doc.docstatus == 2:
		frappe.throw("Et tidligere periodiseringsbilag er annullert. Kontroller grunnlaget før du lager en dokumentert erstatning.")
	return doc


def _active_draft(invoice: Any, deferred_account: str, *, except_key: str = "") -> str | None:
	frappe = _frappe()
	rows = frappe.db.sql(
		"""select distinct entry.name
		from `tabJournal Entry` entry
		join `tabJournal Entry Account` row on row.parent=entry.name
		where entry.company=%s and entry.docstatus=0 and entry.enk_deferral_key is not null
		and entry.enk_deferral_key != %s and row.account=%s and row.reference_type='Sales Invoice'
		and row.reference_name=%s""",
		(invoice.company, except_key, deferred_account, invoice.name),
		as_dict=True,
	)
	return rows[0].name if rows else None


def _recognized_amount(invoice: Any, item: Any, deferred_account: str) -> Decimal:
	frappe = _frappe()
	amount = frappe.db.sql(
		"""select coalesce(sum(row.debit-row.credit), 0) amount
		from `tabJournal Entry` entry
		join `tabJournal Entry Account` row on row.parent=entry.name
		where entry.company=%s and entry.docstatus=1 and entry.voucher_type='Deferred Revenue'
		and row.account=%s and row.reference_type='Sales Invoice' and row.reference_name=%s
		and row.reference_detail_no=%s""",
		(invoice.company, deferred_account, invoice.name, item.name),
		as_dict=True,
	)[0].amount
	return _money(amount, "Allerede periodisert beløp", allow_negative=True)


def _draft_key(kind: str, invoice_name: str, through_date: date) -> str:
	return sha256(f"{kind}|{invoice_name}|{through_date.isoformat()}".encode()).hexdigest()


def _make_entry(invoice: Any, settings: Any, posting: date, details: dict[str, Any], accounts: list[dict[str, Any]]):
	frappe = _frappe()
	from enk_norge.posting_contract import seal_draft

	entry = frappe.get_doc(
		dict(
			doctype="Journal Entry",
			company=invoice.company,
			posting_date=posting,
			voucher_type="Deferred Revenue",
			user_remark="ENK periodisering av SaaS-abonnement " + invoice.name,
			enk_deferral_key=details["key"],
			enk_deferral_details=json.dumps(details, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
			accounts=accounts,
		)
	)
	entry.insert()
	entry.db_set("enk_posting_contract", seal_draft(entry), update_modified=False)
	return entry


def create_revenue_recognition_draft(company: str, invoice_name: str, through_date: Any) -> dict[str, Any]:
	"""Lager ett signert utkast for samlet opptjent inntekt frem til angitt dato."""
	frappe = _frappe()
	settings = _settings(company, write=True)
	frappe.has_permission("Journal Entry", "create", throw=True)
	frappe.db.sql("select name from `tabCompany` where name=%s for update", company)
	invoice = frappe.get_doc("Sales Invoice", invoice_name, for_update=True)
	invoice.check_permission("read")
	if invoice.company != company or invoice.docstatus != 1 or invoice.is_return:
		frappe.throw("Velg en bokført ordinær salgsfaktura fra samme foretak.")
	posting = _date(through_date, "Periodiseringsdato")
	if posting.year not in (2026, 2027):
		frappe.throw("Periodisering støtter bare opptjent inntekt i 2026 eller 2027.")
	_ensure_open_period(settings, posting)
	_ensure_deferral_fiscal_year(invoice, posting)
	key = _draft_key("revenue_recognition", invoice.name, posting)
	if existing := _existing_key(key):
		return {"doctype": existing.doctype, "name": existing.name, "reused": True}
	if draft := _active_draft(invoice, settings.deferred_revenue_account, except_key=key):
		frappe.throw(f"Periodiseringsutkastet {draft} må bokføres eller annulleres før ny periodisering.")
	try:
		items = _invoice_items(invoice, settings)
	except DeferralError as error:
		frappe.throw(str(error))
	file = _source_file(invoice.enk_subscription_source_file, invoice=invoice)
	if file.attached_to_doctype != "Sales Invoice" or file.attached_to_name != invoice.name:
		frappe.throw("Avtaledokumentet må være vedlagt den periodiserte fakturaen.")
	accounts, rows = [], []
	for item in items:
		earned = cumulative_earned_amount(item.base_net_amount, item.service_start_date, item.service_end_date, posting)
		increment = recognition_increment(
			earned.cumulative_amount, _recognized_amount(invoice, item, settings.deferred_revenue_account)
		)
		if not increment:
			continue
		rows.append(
			{
				"item": item.name,
				"income_account": item.income_account,
				"service_start_date": earned.service_start.isoformat(),
				"service_end_date": earned.service_end.isoformat(),
				"earned_days": earned.earned_days,
				"total_days": earned.total_days,
				"amount": f"{increment:.2f}",
			}
		)
		common = dict(reference_type="Sales Invoice", reference_name=invoice.name, reference_detail_no=item.name)
		accounts.extend(
			[
				dict(account=settings.deferred_revenue_account, debit_in_account_currency=increment, **common),
				dict(
					account=item.income_account,
					credit_in_account_currency=increment,
					cost_center=item.cost_center,
					**common,
				),
			]
		)
	if not accounts:
		return {"doctype": "Journal Entry", "name": None, "reused": True, "amount": "0.00"}
	details = {
		"version": 1,
		"kind": "revenue_recognition",
		"key": key,
		"invoice": invoice.name,
		"source_file": file.name,
		"source_sha256": _source_hash(file),
		"through_date": posting.isoformat(),
		"rows": rows,
	}
	entry = _make_entry(invoice, settings, posting, details, accounts)
	return {"doctype": entry.doctype, "name": entry.name, "reused": False, "amount": f"{sum((Decimal(row['amount']) for row in rows), Decimal()):.2f}"}


def create_credit_reversal_draft(credit_note: Any, source_file: str) -> dict[str, Any] | None:
	"""Nøytraliserer utsatt og allerede inntektsført beløp når et periodisert abonnement refunderes fullt."""
	frappe = _frappe()
	if credit_note.doctype != "Sales Invoice" or not credit_note.is_return or not credit_note.return_against:
		return None
	original = frappe.get_doc("Sales Invoice", credit_note.return_against, for_update=True)
	if original.company != credit_note.company or original.docstatus != 1:
		frappe.throw("Kreditnotaen må vise til en bokført faktura i samme foretak.")
	settings = _settings(credit_note.company, write=True)
	if not any(item.enable_deferred_revenue for item in original.items):
		return None
	try:
		items = _invoice_items(original, settings)
	except DeferralError as error:
		frappe.throw(str(error))
	file = _source_file(source_file, invoice=credit_note)
	if not file.attached_to_name:
		file.attached_to_doctype = credit_note.doctype
		file.attached_to_name = credit_note.name
		file.save()
	posting = _date(credit_note.posting_date, "Kreditnotadato")
	_ensure_open_period(settings, posting)
	key = _draft_key("credit_reversal", credit_note.name, posting)
	if existing := _existing_key(key):
		return {"doctype": existing.doctype, "name": existing.name, "reused": True}
	accounts, rows = [], []
	for item in items:
		total = _money(item.base_net_amount, "Abonnementsbeløp")
		recognized = _recognized_amount(original, item, settings.deferred_revenue_account)
		unearned = total - recognized
		if unearned < 0:
			frappe.throw("Allerede periodisert beløp overstiger den opprinnelige fakturaen.")
		if not unearned:
			continue
		common = dict(reference_type="Sales Invoice", reference_name=original.name, reference_detail_no=item.name)
		accounts.extend(
			[
				dict(account=settings.deferred_revenue_account, debit_in_account_currency=unearned, **common),
				dict(
					account=item.income_account,
					credit_in_account_currency=unearned,
					cost_center=item.cost_center,
					**common,
				),
			]
		)
		rows.append({"item": item.name, "amount": f"{unearned:.2f}"})
	if not accounts:
		return None
	details = {
		"version": 1,
		"kind": "credit_reversal",
		"key": key,
		"invoice": original.name,
		"credit_note": credit_note.name,
		"source_file": file.name,
		"source_sha256": _source_hash(file),
		"through_date": posting.isoformat(),
		"rows": rows,
	}
	entry = _make_entry(credit_note, settings, posting, details, accounts)
	credit_note.enk_deferral_reversal_journal_entry = entry.name
	credit_note.db_set("enk_deferral_reversal_journal_entry", entry.name, update_modified=False)
	return {"doctype": entry.doctype, "name": entry.name, "reused": False}


def validate_deferred_revenue_invoice(doc: Any, method: str | None = None) -> None:
	"""Hook-hjelper: native deferred accounting får bare bruke den kontrollerte ENK-kontrakten."""
	frappe = _frappe()
	if not doc.get("company") or not frappe.db.exists("ENK Settings", doc.company):
		return
	settings = _settings(doc.company, write=False)
	if doc.is_return and doc.return_against:
		original = frappe.get_doc("Sales Invoice", doc.return_against)
		if any(row.enable_deferred_revenue for row in original.items):
			if any(row.enable_deferred_revenue for row in doc.items):
				frappe.throw("Kreditnota for periodisert abonnement kan ikke starte ERPNexts native periodisering.")
			if method == "before_submit" and not doc.enk_deferral_reversal_journal_entry:
				frappe.throw("Kreditnota for periodisert abonnement krever et signert reverseringsutkast.")
		return
	items = [row for row in doc.items if row.enable_deferred_revenue]
	if not items:
		return
	file = _source_file(doc.enk_subscription_source_file, invoice=doc)
	if file.attached_to_doctype != "Sales Invoice" or file.attached_to_name != doc.name:
		frappe.throw("Periodisert abonnement må ha privat avtaledokument vedlagt fakturaen.")
	for row in items:
		if row.service_stop_date:
			frappe.throw("Tjenestestopp støttes ikke for kontrollert periodisering. Bruk kreditnota med refusjonsgrunnlag.")
		try:
			validate_subscription_period(row.service_start_date, row.service_end_date, invoice_date=doc.posting_date)
		except DeferralError as error:
			frappe.throw(str(error))
		if row.deferred_revenue_account != settings.deferred_revenue_account:
			frappe.throw("Periodisert abonnement må bruke foretakets konto for utsatt inntekt.")


def validate_deferred_revenue_update(doc: Any, method: str | None = None) -> None:
	"""Tjenestestopp etter innsending ville endre abonnementets forseglede periodiseringsgrunnlag."""
	frappe = _frappe()
	if not doc.get("company") or not frappe.db.exists("ENK Settings", doc.company):
		return
	for row in doc.items:
		if not row.name:
			continue
		old_stop = frappe.db.get_value("Sales Invoice Item", row.name, "service_stop_date")
		if row.enable_deferred_revenue and str(row.service_stop_date or "") != str(old_stop or ""):
			frappe.throw("Tjenestestopp kan ikke endres etter bokføring. Bruk kreditnota med refusjonsgrunnlag.")


def validate_deferral_entry(entry: Any) -> None:
	"""Hook-hjelper som avstemmer et forseglet periodiseringsutkast før innsending."""
	frappe = _frappe()
	if not entry.get("enk_deferral_details"):
		return
	try:
		details = json.loads(entry.enk_deferral_details or "")
	except (TypeError, ValueError):
		frappe.throw("Periodiseringsbilaget mangler gyldige detaljopplysninger.")
	if entry.voucher_type != "Deferred Revenue" or details.get("kind") not in ("revenue_recognition", "credit_reversal"):
		return
	invoice = frappe.get_doc("Sales Invoice", details.get("invoice"))
	if invoice.company != entry.company or invoice.docstatus != 1:
		frappe.throw("Periodiseringsbilaget viser ikke til en bokført faktura i samme foretak.")
	file = _source_file(details.get("source_file"))
	if _source_hash(file) != details.get("source_sha256"):
		frappe.throw("Avtale- eller refusjonsdokumentet er endret etter at periodiseringsutkastet ble laget.")
	if details["kind"] == "credit_reversal":
		credit = frappe.get_doc("Sales Invoice", details.get("credit_note"))
		if credit.company != entry.company or credit.docstatus != 1 or not credit.is_return:
			frappe.throw("Reverseringsbilaget kan først bokføres etter den tilhørende kreditnotaen.")
		if frappe.flags.get("enk_deferral_credit_operation") != credit.name:
			frappe.throw("Refusjonsreverseringen bokføres og annulleres sammen med kreditnotaen.")


def sync_credit_reversal(doc: Any, method: str | None = None) -> None:
	"""Kreditnota og dens utsatt-inntekt-reversering går i samme DB-transaksjon."""
	frappe = _frappe()
	name = doc.get("enk_deferral_reversal_journal_entry")
	if not name:
		return
	entry = frappe.get_doc("Journal Entry", name)
	if entry.company != doc.company:
		frappe.throw("Reverseringsbilaget tilhører ikke kreditnotaens foretak.")
	try:
		details = json.loads(entry.enk_deferral_details or "")
	except (TypeError, ValueError):
		frappe.throw("Kreditnotaen peker på et ugyldig reverseringsbilag.")
	if details.get("kind") != "credit_reversal" or details.get("credit_note") != doc.name:
		frappe.throw("Kreditnotaen peker ikke på sitt eget reverseringsbilag.")
	previous = frappe.flags.get("enk_deferral_credit_operation")
	frappe.flags.enk_deferral_credit_operation = doc.name
	try:
		if method == "on_submit":
			if entry.docstatus != 0:
				frappe.throw("Reverseringsbilaget må være utkast når kreditnotaen bokføres.")
			entry.submit()
		elif method == "before_cancel":
			if entry.docstatus != 1:
				frappe.throw("Reverseringsbilaget må være bokført når kreditnotaen annulleres.")
			# Kreditnotaen som akkurat annulleres peker på journalen. Frappe ser den
			# fortsatt som en lenke under samme transaksjon, så denne ene, kontrollerte
			# annuleringen må passere lenkesjekken.
			previous_ignore_links = entry.flags.ignore_links
			entry.flags.ignore_links = True
			try:
				entry.cancel()
			finally:
				entry.flags.ignore_links = previous_ignore_links
	finally:
		frappe.flags.enk_deferral_credit_operation = previous


def validate_deferral_cancellation(entry: Any) -> None:
	"""Hook-hjelper: kreditnotas reverseringsbilag kan ikke annulleres alene."""
	if not entry.get("enk_deferral_details"):
		return
	try:
		details = json.loads(entry.enk_deferral_details)
	except (TypeError, ValueError):
		return
	if details.get("kind") == "credit_reversal" and _frappe().flags.get("enk_deferral_credit_operation") != details.get(
		"credit_note"
	):
		_frappe().throw("Refusjonsreverseringen annulleres sammen med kreditnotaen. Annuller kreditnotaen i stedet.")


def block_native_deferred_accounting(doc: Any, method: str | None = None) -> None:
	"""Hook-hjelper som stanser ERPNexts månedskjøring, som ellers skriver direkte til GL."""
	frappe = _frappe()
	if doc.get("company") and frappe.db.exists("ENK Settings", doc.company):
		frappe.throw("ERPNexts automatiske periodisering er deaktivert for ENK. Bruk et kontrollert periodiseringsutkast.")


def is_supported_deferral_posting(entry: Any) -> bool:
	"""Lar valideringshooken tillate bare 2027-inntektsføring som tilhører en 2026-avtale."""
	if getattr(entry, "doctype", None) != "Journal Entry" or getattr(entry, "voucher_type", None) != "Deferred Revenue":
		return False
	try:
		details = json.loads(entry.get("enk_deferral_details") or "")
		posting = _date(entry.posting_date, "Bokføringsdato")
	except (DeferralError, TypeError, ValueError, AttributeError):
		return False
	if details.get("kind") != "revenue_recognition" or posting.year != 2027:
		return False
	try:
		frappe = _frappe()
		invoice = frappe.get_doc("Sales Invoice", details.get("invoice"))
		return invoice.docstatus == 1 and _date(invoice.posting_date, "Fakturadato").year == 2026
	except Exception:
		return False


def _wl(fn, methods=None):
	try:
		return _frappe().whitelist(methods=methods)(fn)
	except ModuleNotFoundError:
		return fn


create_revenue_recognition_draft = _wl(create_revenue_recognition_draft, methods=["POST"])
