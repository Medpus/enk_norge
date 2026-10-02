"""Kontrollerte fakturautkast fra ERPNexts Timesheet og Subscription."""

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from hashlib import sha256

import frappe
from frappe.utils import add_days, getdate, today


class BillingError(ValueError):
	"""Kildedokumentet kan ikke brukes som kontrollert ENK-faktura."""


def timesheet_event_id(timesheet: str) -> str:
	name = str(timesheet or "").strip()
	if not name:
		raise BillingError("Timesheet mangler.")
	return f"timesheet:{name}"


def subscription_event_id(subscription: str, service_start, service_end) -> str:
	name = str(subscription or "").strip()
	if not name:
		raise BillingError("Abonnement mangler.")
	try:
		start, end = getdate(service_start), getdate(service_end)
	except Exception as error:
		raise BillingError("Abonnementsperioden må ha gyldige datoer.") from error
	if end < start:
		raise BillingError("Abonnementsperioden slutter før den starter.")
	return f"subscription:{name}:{start.isoformat()}:{end.isoformat()}"


def _data(data):
	data = frappe.parse_json(data) if isinstance(data, str) else data
	if not isinstance(data, dict):
		frappe.throw("Ugyldige opplysninger.")
	return frappe._dict(data)


def _money(value, label):
	try:
		amount = Decimal(str(value))
		if not amount.is_finite() or amount <= 0:
			raise ValueError
		rounded = amount.quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
		if amount != rounded:
			raise ValueError
	except (InvalidOperation, TypeError, ValueError):
		frappe.throw(f"{label} må være et positivt beløp med høyst to desimaler.")
	return amount


def _date(value, label):
	if not value:
		frappe.throw(f"Oppgi {label}.")
	try:
		return getdate(value)
	except Exception:
		frappe.throw(f"{label} må være en gyldig dato.")


def _fingerprint(data):
	return sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _existing(company, event_id, fingerprint):
	# Samme foretakslås som øvrige ENK-innganger. Den gjør en samtidig retry til
	# gjenbruk av samme utkast i stedet for to timesheet-koblinger.
	frappe.db.sql("select name from `tabCompany` where name=%s for update", company)
	name = frappe.db.get_value(
		"Sales Invoice", {"company": company, "enk_external_id": event_id}, "name", for_update=True
	)
	if not name:
		return None
	doc = frappe.get_doc("Sales Invoice", name, for_update=True)
	doc.check_permission("read")
	if doc.docstatus == 2:
		frappe.throw("Kildehendelsen viser en annullert faktura. Opprett dokumentert erstatning uten å gjenbruke den.")
	if doc.enk_request_fingerprint != fingerprint:
		frappe.throw("Kildehendelsen er allerede brukt med andre opplysninger.")
	return {"doctype": doc.doctype, "name": doc.name, "reused": True}


def _customer_address(customer, address):
	customer_doc = frappe.get_doc("Customer", customer)
	customer_doc.check_permission("read")
	address_doc = frappe.get_doc("Address", address)
	address_doc.check_permission("read")
	if not any(row.link_doctype == "Customer" and row.link_name == customer_doc.name for row in address_doc.links):
		frappe.throw("Fakturaadressen tilhører ikke valgt kunde.")
	return customer_doc, address_doc


def _tax_treatment(data, settings, posting):
	treatment = data.get("tax_treatment") or (
		"Domestic 25"
		if settings.vat_registered and settings.vat_registration_date and posting >= getdate(settings.vat_registration_date)
		else "Not registered"
	)
	allowed = {"Domestic 25", "Domestic 15", "Domestic 12", "Not registered", "Export services", "Exempt"}
	if treatment not in allowed:
		frappe.throw("Avgiftsbehandlingen støttes ikke for salg.")
	return treatment


def _apply_enk_invoice_fields(invoice, data, settings, event_id, fingerprint, items):
	posting = _date(data.get("posting_date") or today(), "fakturadato")
	delivery = _date(data.get("delivery_date"), "leveringsdato")
	description = str(data.get("delivery_description") or "").strip()
	if not description:
		frappe.throw("Oppgi hva som er levert.")
	customer, address = _customer_address(data.get("customer"), data.get("customer_address"))
	treatment = _tax_treatment(data, settings, posting)

	invoice.customer = customer.name
	invoice.customer_address = address.name
	invoice.posting_date = posting
	invoice.due_date = _date(data.get("due_date") or posting, "forfallsdato")
	invoice.set_posting_time = 1
	invoice.currency = "NOK"
	invoice.conversion_rate = 1
	invoice.selling_price_list = "ENK Selling"
	invoice.price_list_currency = "NOK"
	invoice.plc_conversion_rate = 1
	invoice.debit_to = settings.receivable_account
	from enk_norge.setup import invoice_naming_series

	invoice.naming_series = invoice_naming_series(settings)
	invoice.enk_tax_treatment = treatment
	invoice.enk_tax_reason = data.get("tax_reason")
	invoice.enk_external_id = event_id
	invoice.enk_request_fingerprint = fingerprint
	invoice.enk_delivery_date = delivery
	invoice.enk_delivery_description = description
	invoice.set("items", items)
	invoice.set("taxes", [])
	if treatment.startswith("Domestic"):
		invoice.append(
			"taxes",
			{
				"charge_type": "On Net Total",
				"account_head": settings.output_vat_account,
				"description": "Merverdiavgift",
				"rate": int(treatment.split()[1]),
			},
		)
	return treatment


def _income_account(settings, treatment):
	if treatment == "Export services":
		return settings.export_income_account
	if treatment == "Exempt":
		return settings.exempt_income_account
	return settings.income_account


def _native_timesheet_draft(timesheet):
	"""Finn en aktiv standardfaktura som allerede har koblet samme timer."""
	# Dette låser kilden for ENK-innsendere. Standard ERPNext bruker ikke denne
	# låsen når den selv lager et utkast, så en samtidig direkte native opprettelse
	# må fortsatt stanses av Subscription/Sales Invoice-policyen utenfor denne modulen.
	frappe.db.sql("select name from `tabTimesheet` where name=%s for update", timesheet.name)
	parents = frappe.get_all(
		"Sales Invoice Timesheet", filters={"time_sheet": timesheet.name}, pluck="parent"
	)
	if not parents:
		return None
	return frappe.db.get_value(
		"Sales Invoice",
		{"name": ["in", parents], "company": timesheet.company, "docstatus": ["<", 2]},
		"name",
	)


def _subscription_period_conflict(subscription, start, end):
	"""En eldre faktura er lovlig; bare samme eller overlappende periode blokkeres."""
	rows = frappe.get_all(
		"Sales Invoice",
		filters={"subscription": subscription.name, "company": subscription.company, "docstatus": ["<", 2]},
		fields=["name", "from_date", "to_date"],
	)
	for row in rows:
		# En gammel native faktura uten periode kan ikke avgrenses pålitelig.
		if not row.from_date or not row.to_date:
			return row.name
		if getdate(row.from_date) <= end and getdate(row.to_date) >= start:
			return row.name
	return None


def _advance_subscription_to_requested_period(subscription, start, end):
	"""Flytter bare én ferdig, bokført ENK-periode frem med ERPNexts egen periodeberegning."""
	current_start = getdate(subscription.current_invoice_start)
	current_end = getdate(subscription.current_invoice_end)
	if subscription.status in ("Cancelled", "Completed") or subscription.cancelation_date:
		frappe.throw("Abonnementet er avsluttet og kan ikke faktureres på nytt.")
	if start < getdate(subscription.start_date) or (subscription.end_date and end > getdate(subscription.end_date)):
		frappe.throw("Fakturaperioden må ligge innenfor abonnementets start- og sluttdato.")
	if (start, end) == (current_start, current_end):
		return
	if subscription.cancel_at_period_end:
		frappe.throw("Abonnementet avsluttes etter denne perioden og kan ikke flyttes videre.")
	next_start = add_days(current_end, 1)
	if start != next_start:
		frappe.throw("ENK kan bare opprette abonnementets neste sammenhengende fakturaperiode.")
	previous = frappe.db.sql(
		"""select name, enk_external_id from `tabSales Invoice`
		where subscription=%s and company=%s and docstatus=1 and is_return=0
		and from_date=%s and to_date=%s for update""",
		(subscription.name, subscription.company, current_start, current_end),
		as_dict=True,
	)
	expected_event = subscription_event_id(subscription.name, current_start, current_end)
	if len(previous) != 1 or previous[0].enk_external_id != expected_event:
		frappe.throw("Forrige abonnementsperiode må ha én bokført ENK-faktura før neste periode kan opprettes.")
	subscription.check_permission("write")
	subscription.update_subscription_period(next_start)
	if (start, end) != (getdate(subscription.current_invoice_start), getdate(subscription.current_invoice_end)):
		frappe.throw("Abonnementsperioden stemmer ikke med ERPNexts neste sammenhengende periode.")
	subscription.save()


@frappe.whitelist(methods=["POST"])
def create_timesheet_invoice_draft(data):
	"""Oppretter ett ENK-utkast fra ubokførte fakturerbare timer i én Timesheet."""
	data = _data(data)
	from erpnext.projects.doctype.timesheet.timesheet import make_sales_invoice

	from enk_norge.setup import get_settings

	timesheet = frappe.get_doc("Timesheet", data.get("timesheet"))
	timesheet.check_permission("read")
	if timesheet.docstatus != 1:
		frappe.throw("Timesheet må være innsendt før den kan faktureres.")
	if timesheet.company != data.get("company"):
		frappe.throw("Timesheet tilhører et annet foretak.")
	if (timesheet.currency or "NOK") != "NOK":
		frappe.throw("Timesheet i annen valuta støttes ikke i ENK-flyten.")
	frappe.has_permission("Sales Invoice", "create", throw=True)
	settings = get_settings(timesheet.company)
	event_id = timesheet_event_id(timesheet.name)
	payload = dict(data) | {"event_id": event_id, "source_rate": str(timesheet.total_billable_amount or 0)}
	fingerprint = _fingerprint(payload)
	if existing := _existing(timesheet.company, event_id, fingerprint):
		return existing
	if native_draft := _native_timesheet_draft(timesheet):
		frappe.throw(f"Timesheet har allerede en aktiv native faktura {native_draft}. Ikke opprett et parallelt ENK-utkast.")

	invoice = make_sales_invoice(timesheet.name, data.get("item_code"), data.get("customer"), currency="NOK")
	if len(invoice.items) != 1 or not invoice.timesheets:
		frappe.throw("Timesheet mangler fakturerbare timer eller krever en støttet vare.")
	price = _money(invoice.items[0].rate, "Timesheet-pris")
	if data.get("unit_price") not in (None, "") and _money(data.unit_price, "Timesheet-pris") != price:
		frappe.throw("Endre prisen på Timesheet før fakturautkastet opprettes. Faktura og timegrunnlag må ha samme sats.")
	items = [invoice.items[0].as_dict(no_nulls=True)]
	treatment = _apply_enk_invoice_fields(invoice, data, settings, event_id, fingerprint, items)
	invoice.items[0].income_account = _income_account(settings, treatment)
	invoice.items[0].cost_center = frappe.get_cached_value("Company", timesheet.company, "cost_center")
	invoice.insert()
	return {"doctype": invoice.doctype, "name": invoice.name, "reused": False, "event_id": event_id}


@frappe.whitelist(methods=["POST"])
def create_subscription_invoice_draft(data):
	"""Oppretter ett kontrollert ENK-utkast fra en eksisterende Subscription-periode."""
	data = _data(data)
	from enk_norge.deferrals import DeferralError, attach_subscription_source, subscription_sale_values
	from enk_norge.setup import get_settings

	subscription = frappe.get_doc("Subscription", data.get("subscription"))
	subscription.check_permission("read")
	if subscription.company != data.get("company"):
		frappe.throw("Abonnementet tilhører et annet foretak.")
	if subscription.party_type != "Customer" or subscription.invoice_document_type != "Sales Invoice":
		frappe.throw("ENK støtter bare kundeabonnement som faktureres som Sales Invoice.")
	if subscription.submit_invoice:
		frappe.throw("Slå av «Submit Generated Invoices» på abonnementet før det brukes i ENK. ERPNext kan ellers bokføre fakturaen uten ENK-kontroll.")
	start = _date(data.get("service_start_date"), "tjenestestart")
	end = _date(data.get("service_end_date"), "tjenesteslutt")
	if subscription.party != data.get("customer"):
		frappe.throw("Valgt kunde stemmer ikke med abonnementet.")
	if any(frappe.get_cached_value("Subscription Plan", row.plan, "currency") != "NOK" for row in subscription.plans):
		frappe.throw("Abonnement i annen valuta støttes ikke i ENK-flyten.")
	frappe.has_permission("Sales Invoice", "create", throw=True)
	settings = get_settings(subscription.company)
	event_id = subscription_event_id(subscription.name, start, end)
	payload = dict(data) | {"event_id": event_id}
	fingerprint = _fingerprint(payload)
	if existing := _existing(subscription.company, event_id, fingerprint):
		return existing
	# Retry er ferdig over. Lås så abonnementet før vi eventuelt flytter én periode,
	# slik at to forespørsler ikke kan hoppe over eller lage samme neste periode.
	frappe.db.get_value("Subscription", subscription.name, "name", for_update=True)
	subscription.reload()
	if not subscription.current_invoice_start or not subscription.current_invoice_end:
		frappe.throw("Abonnementet mangler aktiv fakturaperiode.")
	_advance_subscription_to_requested_period(subscription, start, end)
	if conflict := _subscription_period_conflict(subscription, start, end):
		frappe.throw(f"Abonnementets periode er allerede fakturert i {conflict}. Ikke opprett en parallell ENK-faktura.")
	try:
		deferred = subscription_sale_values(data, settings, data.get("posting_date") or today())
	except DeferralError as error:
		frappe.throw(str(error))
	if not deferred:
		frappe.throw("Abonnementsutkast krever privat avtaledokument og tjenesteperiode for kontrollert periodisering.")

	items = subscription.get_items_from_plans(subscription.plans)
	if not items:
		frappe.throw("Abonnementet mangler fakturerbare planlinjer.")
	invoice = frappe.new_doc("Sales Invoice")
	invoice.company = subscription.company
	invoice.subscription = subscription.name
	invoice.from_date = start
	invoice.to_date = end
	treatment = _apply_enk_invoice_fields(invoice, data, settings, event_id, fingerprint, items)
	for item in invoice.items:
		item.income_account = _income_account(settings, treatment)
		item.cost_center = frappe.get_cached_value("Company", subscription.company, "cost_center")
		item.update(deferred)
	invoice.insert()
	attach_subscription_source(invoice, data.subscription_source_file)
	return {"doctype": invoice.doctype, "name": invoice.name, "reused": False, "event_id": event_id}
