"""Bilagsliste og bilagsvisning for ENK-siden.

ERPNext eier dokumentene og bokføringen. Her samler vi bare det brukeren trenger for å se,
bokføre eller slette en kladd uten å åpne ERPNexts skjema.
"""

import frappe
from frappe.utils import flt

from enk_norge.setup import get_settings

DOCTYPES = {
	"Sales Invoice": "customer_name",
	"Purchase Invoice": "supplier_name",
	"Payment Entry": "party_name",
	"Journal Entry": None,
}
KINDS = {
	"sales": ("Sales Invoice",),
	"purchases": ("Purchase Invoice",),
	"other": ("Payment Entry", "Journal Entry"),
}


def _check_doctype(doctype):
	if doctype not in DOCTYPES:
		frappe.throw("Dokumenttypen vises ikke i ENK Norge.")


def _list_fields(doctype):
	fields = ["name", "posting_date", "docstatus", "modified"]
	party = DOCTYPES[doctype]
	if party:
		fields.append(f"{party} as party")
	if doctype in ("Sales Invoice", "Purchase Invoice"):
		fields += ["grand_total as total", "outstanding_amount", "currency", "is_return"]
	elif doctype == "Payment Entry":
		fields += ["paid_amount as total", "payment_type", "paid_from_account_currency as currency"]
	else:
		fields += ["total_debit as total", "user_remark as description", "voucher_type"]
	return fields


def _status(doctype, row):
	if row.docstatus == 0:
		return "draft"
	if row.docstatus == 2:
		return "cancelled"
	if doctype in ("Sales Invoice", "Purchase Invoice"):
		if row.get("is_return"):
			return "credit_note"
		if flt(row.get("outstanding_amount")) > 0.005:
			return "unpaid"
		return "paid"
	return "posted"


@frappe.whitelist()
def list_documents(company, kind="all", search="", limit=50):
	get_settings(company)
	doctypes = KINDS.get(kind) or tuple(DOCTYPES)
	limit = min(max(int(limit or 50), 1), 200)
	search = (search or "").strip()
	rows = []
	for doctype in doctypes:
		filters = {"company": company}
		or_filters = None
		if search:
			or_filters = {"name": ["like", f"%{search}%"]}
			if DOCTYPES[doctype]:
				or_filters[DOCTYPES[doctype]] = ["like", f"%{search}%"]
		for row in frappe.get_list(
			doctype,
			filters=filters,
			or_filters=or_filters,
			fields=_list_fields(doctype),
			order_by="posting_date desc, modified desc",
			limit_page_length=limit,
		):
			row.doctype = doctype
			row.status = _status(doctype, row)
			row.total = str(flt(row.get("total"), 2))
			if "outstanding_amount" in row:
				row.outstanding_amount = str(flt(row.outstanding_amount, 2))
			row.posting_date = str(row.posting_date) if row.posting_date else None
			row.pop("modified", None)
			rows.append(row)
	rows.sort(key=lambda row: (row.posting_date or "", row.name), reverse=True)
	return rows[:limit]


def _load(doctype, name):
	_check_doctype(doctype)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	get_settings(doc.company)
	return doc


def _attachments(doc):
	return frappe.get_all(
		"File",
		filters={"attached_to_doctype": doc.doctype, "attached_to_name": doc.name},
		fields=["name", "file_name", "file_url", "is_private", "creation"],
		order_by="creation asc",
	)


def _lines(doc):
	if doc.doctype in ("Sales Invoice", "Purchase Invoice"):
		return [
			dict(
				description=row.description or row.item_name,
				qty=flt(row.qty),
				rate=str(flt(row.rate, 2)),
				amount=str(flt(row.amount, 2)),
				deferred=bool(row.get("enable_deferred_revenue") or row.get("enable_deferred_expense")),
			)
			for row in doc.items
		]
	if doc.doctype == "Journal Entry":
		names = {
			row.account: frappe.db.get_value("Account", row.account, "account_name") or row.account
			for row in doc.accounts
		}
		return [
			dict(
				description=names[row.account],
				debit=str(flt(row.debit, 2)),
				credit=str(flt(row.credit, 2)),
			)
			for row in doc.accounts
		]
	return [
		dict(
			description=row.reference_name,
			reference_doctype=row.reference_doctype,
			amount=str(flt(row.allocated_amount, 2)),
		)
		for row in doc.references
	]


def _summary(doc):
	party_field = DOCTYPES[doc.doctype]
	result = dict(
		doctype=doc.doctype,
		name=doc.name,
		company=doc.company,
		docstatus=doc.docstatus,
		posting_date=str(doc.posting_date) if doc.posting_date else None,
		party=doc.get(party_field) if party_field else None,
		lines=_lines(doc),
		attachments=_attachments(doc),
		can_submit=doc.docstatus == 0 and frappe.has_permission(doc.doctype, "submit", doc),
		can_delete=doc.docstatus == 0 and frappe.has_permission(doc.doctype, "delete", doc),
	)
	if doc.doctype in ("Sales Invoice", "Purchase Invoice"):
		result.update(
			currency=doc.currency,
			net_total=str(flt(doc.net_total, 2)),
			tax_total=str(flt(doc.total_taxes_and_charges, 2)),
			grand_total=str(flt(doc.grand_total, 2)),
			outstanding_amount=str(flt(doc.outstanding_amount, 2)),
			due_date=str(doc.due_date) if doc.due_date else None,
			is_return=bool(doc.is_return),
			return_against=doc.return_against,
			bill_no=doc.get("bill_no"),
			deferred=any(row.get("enable_deferred_revenue") for row in doc.items),
		)
	elif doc.doctype == "Payment Entry":
		result.update(
			currency=doc.paid_from_account_currency,
			grand_total=str(flt(doc.paid_amount, 2)),
			payment_type=doc.payment_type,
			reference_no=doc.reference_no,
		)
	else:
		result.update(
			currency=doc.get("total_amount_currency") or "NOK",
			grand_total=str(flt(doc.total_debit, 2)),
			description=doc.user_remark,
		)
	result["status"] = _status(doc.doctype, frappe._dict(result))
	return result


@frappe.whitelist()
def get_document(doctype, name):
	return _summary(_load(doctype, name))


@frappe.whitelist(methods=["POST"])
def submit_document(doctype, name):
	doc = _load(doctype, name)
	if doc.docstatus != 0:
		frappe.throw("Dokumentet er allerede bokført.")
	doc.check_permission("submit")
	doc.submit()
	return _summary(doc)


@frappe.whitelist(methods=["POST"])
def delete_draft(doctype, name):
	doc = _load(doctype, name)
	if doc.docstatus != 0:
		frappe.throw("Bare kladder kan slettes. Bruk kreditnota eller korrigeringsbilag for bokførte dokumenter.")
	doc.check_permission("delete")
	company = doc.company
	frappe.delete_doc(doctype, name)
	return dict(company=company)
