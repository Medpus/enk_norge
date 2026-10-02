"""Send en bokført faktura til kunden på e-post.

PDF-en lages som ved nedlasting, med stilfiler fra intern adresse bak Cloudflare Access.
Den lagres som privat vedlegg på fakturaen, så det som ble sendt, er arkivert.
"""

import frappe
from frappe.utils import escape_html, validate_email_address

from enk_norge.setup import get_settings

ACCOUNT_NAME = "ENK utsending"


def _outgoing_account():
	return frappe.db.get_value(
		"Email Account", {"enable_outgoing": 1, "default_outgoing": 1}, ["name", "email_id"], as_dict=True
	)


@frappe.whitelist()
def email_status():
	account = _outgoing_account()
	return dict(ready=bool(account), sender=account.email_id if account else None)


@frappe.whitelist(methods=["POST"])
def setup_email_account(email, password, smtp_server, smtp_port=587, security="tls"):
	"""Opprett eller oppdater kontoen fakturaer sendes fra. Frappe tester tilkoblingen ved lagring."""
	frappe.only_for("System Manager")
	email = (email or "").strip()
	validate_email_address(email, throw=True)
	if not (password and smtp_server):
		frappe.throw("Oppgi passord og SMTP-server.")
	if security not in ("tls", "ssl", "none"):
		frappe.throw("Velg sikkerhet for tilkoblingen.")
	name = frappe.db.get_value("Email Account", {"email_account_name": ACCOUNT_NAME}, "name")
	account = frappe.get_doc("Email Account", name) if name else frappe.new_doc("Email Account")
	account.update(
		dict(
			email_account_name=ACCOUNT_NAME,
			email_id=email,
			login_id_is_different=0,
			password=password,
			awaiting_password=0,
			enable_incoming=0,
			enable_outgoing=1,
			default_outgoing=1,
			smtp_server=smtp_server.strip(),
			smtp_port=str(int(smtp_port)),
			use_tls=1 if security == "tls" else 0,
			use_ssl_for_outgoing=1 if security == "ssl" else 0,
			always_use_account_email_id_as_sender=1,
		)
	)
	account.save()
	return email_status()


def invoice_pdf(doc):
	from frappe.utils.pdf import get_pdf

	from enk_norge.printing import _pdf_asset_origin, rewrite_pdf_asset_urls

	html = frappe.get_print(doc.doctype, doc.name, "ENK Faktura", doc=doc, as_pdf=False, no_letterhead=1)
	origin = _pdf_asset_origin()
	return get_pdf(rewrite_pdf_asset_urls(html, origin) if origin else html)


def sendings(doc):
	return [
		dict(recipients=row.recipients, sent=str(row.creation), status=row.delivery_status or "")
		for row in frappe.get_all(
			"Communication",
			filters={
				"reference_doctype": doc.doctype,
				"reference_name": doc.name,
				"sent_or_received": "Sent",
				"communication_medium": "Email",
			},
			fields=["recipients", "creation", "delivery_status"],
			order_by="creation asc",
		)
	]


@frappe.whitelist(methods=["POST"])
def send_invoice(name, recipient, subject, message):
	from frappe.core.doctype.communication.email import make

	doc = frappe.get_doc("Sales Invoice", name)
	doc.check_permission("email")
	get_settings(doc.company)
	if doc.docstatus != 1:
		frappe.throw("Bokfør fakturaen før den sendes. En kladd skal ikke sendes til kunden.")
	recipient = (recipient or "").strip()
	validate_email_address(recipient, throw=True)
	if not _outgoing_account():
		frappe.throw("Sett opp e-post for utsending under «Foretak og MVA» først.")
	kind = "Kreditnota" if doc.is_return else "Faktura"
	file = frappe.get_doc(
		dict(
			doctype="File",
			file_name=f"{kind}-{doc.name}.pdf",
			content=invoice_pdf(doc),
			is_private=1,
			attached_to_doctype=doc.doctype,
			attached_to_name=doc.name,
		)
	).insert()
	body = "".join(f"<p>{escape_html(part)}</p>" for part in (message or "").split("\n\n") if part.strip())
	make(
		doctype=doc.doctype,
		name=doc.name,
		content=body.replace("\n", "<br>"),
		subject=(subject or f"{kind} {doc.name}").strip()[:140],
		recipients=recipient,
		send_email=True,
		attachments=[file.name],
		now=True,
	)
	# Husk adressen til neste gang, hvis kunden ikke har en fra før.
	if not frappe.db.get_value("Customer", doc.customer, "email_id"):
		frappe.db.set_value("Customer", doc.customer, "email_id", recipient)
	return dict(sendings=sendings(doc))
