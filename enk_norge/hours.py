"""Timeføring for ENK-siden.

ERPNexts Timesheet er fortsatt timegrunnlaget. Hver kunde har én åpen kladd som timene
samles i, og den sendes inn når timene faktureres.
"""

from datetime import timedelta

import frappe
from frappe.utils import flt, get_datetime, getdate

from enk_norge.api import _data
from enk_norge.setup import get_settings

HOURS_ITEM = "ENK Konsulenttimer"


def hours_item():
	if not frappe.db.exists("Item", HOURS_ITEM):
		from enk_norge.parties import _root

		if not frappe.db.count("Item Group"):
			# ENK-veiviseren kjører ikke ERPNexts fulle eksempeloppsett, så varetreet kan være tomt.
			frappe.get_doc(dict(doctype="Item Group", item_group_name="All Item Groups", is_group=1)).insert(
				ignore_permissions=True
			)
		group = _root("Item Group", "Services")
		# Fast teknisk vare for timefakturaer. Brukeren skal ikke trenge varerettigheter for å føre timer.
		frappe.get_doc(
			dict(
				doctype="Item",
				item_code=HOURS_ITEM,
				item_name="Konsulenttimer",
				description="Konsulenttimer",
				item_group=group,
				stock_uom="Hour" if frappe.db.exists("UOM", "Hour") else "Nos",
				is_stock_item=0,
				is_sales_item=1,
				is_purchase_item=0,
			)
		).insert(ignore_permissions=True)
	return HOURS_ITEM


def _positive(value, label, maximum=None):
	number = flt(value)
	if number <= 0 or (maximum and number > maximum):
		frappe.throw(f"Oppgi gyldig {label}.")
	return number


def _summary(timesheet):
	return dict(
		timesheet=timesheet.name,
		customer=timesheet.customer,
		customer_name=frappe.db.get_value("Customer", timesheet.customer, "customer_name"),
		docstatus=timesheet.docstatus,
		hours=flt(timesheet.total_billable_hours) - flt(timesheet.total_billed_hours),
		amount=str(flt(timesheet.total_billable_amount) - flt(timesheet.total_billed_amount)),
		logs=[
			dict(
				row=row.name,
				date=str(getdate(row.from_time)),
				hours=flt(row.hours),
				rate=str(flt(row.billing_rate)),
				amount=str(flt(row.billing_amount)),
				description=row.description,
			)
			for row in timesheet.time_logs
			if row.is_billable and not row.sales_invoice
		],
	)


@frappe.whitelist()
def open_hours(company):
	get_settings(company)
	names = frappe.get_list(
		"Timesheet",
		filters={"company": company, "docstatus": ["<", 2], "customer": ["is", "set"], "per_billed": ["<", 100]},
		pluck="name",
		order_by="modified desc",
	)
	result = []
	for name in names:
		summary = _summary(frappe.get_doc("Timesheet", name))
		if summary["logs"]:
			result.append(summary)
	return result


@frappe.whitelist(methods=["POST"])
def log_hours(data):
	data = _data(data)
	get_settings(data.company)
	frappe.get_doc("Customer", data.customer).check_permission("read")
	hours = _positive(data.hours, "antall timer", 24)
	rate = _positive(data.rate, "timepris")
	description = (data.description or "").strip()
	if not description:
		frappe.throw("Beskriv hva timene gjelder.")
	work_date = getdate(data.date)
	name = frappe.db.get_value(
		"Timesheet", {"company": data.company, "customer": data.customer, "docstatus": 0}, "name"
	)
	if name:
		timesheet = frappe.get_doc("Timesheet", name)
		timesheet.check_permission("write")
	else:
		frappe.has_permission("Timesheet", "create", throw=True)
		timesheet = frappe.new_doc("Timesheet")
		timesheet.update(dict(company=data.company, customer=data.customer, currency="NOK"))
	# Timer samme dag legges etter hverandre, så ERPNext ikke ser dem som overlappende.
	start = get_datetime(f"{work_date} 08:00:00")
	for row in timesheet.time_logs:
		if row.to_time and getdate(row.from_time) == work_date:
			start = max(start, get_datetime(row.to_time))
	# ERPNext regner bare ut beløpet i nettleserskjemaet når ingen aktivitetstype har sats.
	amount = flt(hours * rate, 2)
	timesheet.append(
		"time_logs",
		dict(
			from_time=start,
			hours=hours,
			to_time=start + timedelta(hours=hours),
			is_billable=1,
			billing_hours=hours,
			billing_rate=rate,
			billing_amount=amount,
			base_billing_rate=rate,
			base_billing_amount=amount,
			description=description,
		),
	)
	timesheet.save()
	return _summary(timesheet)


@frappe.whitelist(methods=["POST"])
def remove_hours(timesheet, row):
	doc = frappe.get_doc("Timesheet", timesheet)
	get_settings(doc.company)
	doc.check_permission("write")
	if doc.docstatus != 0:
		frappe.throw("Timer som er sendt til fakturering kan ikke fjernes her.")
	doc.time_logs = [log for log in doc.time_logs if log.name != row]
	if not doc.time_logs:
		frappe.delete_doc("Timesheet", doc.name)
		return None
	doc.save()
	return _summary(doc)


@frappe.whitelist(methods=["POST"])
def invoice_hours(data):
	data = _data(data)
	from enk_norge.billing import create_timesheet_invoice_draft
	from enk_norge.parties import billing_address

	timesheet = frappe.get_doc("Timesheet", data.timesheet)
	get_settings(timesheet.company)
	if timesheet.company != data.company:
		frappe.throw("Timene tilhører et annet foretak.")
	address = billing_address(timesheet.customer)
	if not address:
		frappe.throw("Kunden mangler fakturaadresse. Legg til adressen på kunden først.")
	item = hours_item()
	if timesheet.docstatus == 0:
		timesheet.check_permission("submit")
		timesheet.submit()
	last_day = max(getdate(row.from_time) for row in timesheet.time_logs if row.is_billable)
	return create_timesheet_invoice_draft(
		dict(
			company=timesheet.company,
			timesheet=timesheet.name,
			customer=timesheet.customer,
			customer_address=address.name,
			item_code=item,
			posting_date=data.posting_date,
			delivery_date=str(last_day),
			delivery_description=data.delivery_description,
			due_date=data.due_date,
			tax_treatment=data.get("tax_treatment"),
			tax_reason=data.get("tax_reason"),
		)
	)
