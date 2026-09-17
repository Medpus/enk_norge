import frappe


def enk_invoice_issuer(doc):
	doc.check_permission("read")
	if doc.get("enk_invoice_snapshot"):
		return frappe._dict(frappe.parse_json(doc.enk_invoice_snapshot))
	from enk_norge.setup import get_settings

	return get_settings(doc.company).as_dict() | {"company_name": doc.company}
