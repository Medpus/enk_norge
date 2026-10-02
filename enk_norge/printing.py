import re
from urllib.parse import unquote, urlsplit

import frappe
from bs4 import BeautifulSoup
from frappe.model.document import Document
from frappe.translate import print_language
from frappe.utils.pdf import get_pdf
from frappe.www.printview import validate_print_permission


_CSS_ASSET_URL = re.compile(r"url\(\s*(?P<quote>['\"]?)(?P<url>/assets/[^\s)'\"]+)(?P=quote)\s*\)", re.IGNORECASE)


def _pdf_asset_origin():
	value = str(frappe.conf.get("enk_pdf_asset_origin") or "").strip()
	if not value:
		return None
	parsed = urlsplit(value)
	try:
		port = parsed.port
	except ValueError:
		frappe.throw("enk_pdf_asset_origin har ugyldig port.")
	if (
		parsed.scheme not in ("http", "https")
		or not parsed.hostname
		or parsed.username
		or parsed.password
		or parsed.path not in ("", "/")
		or parsed.query
		or parsed.fragment
	):
		frappe.throw("enk_pdf_asset_origin må være en ren http(s)-origin fra serverkonfigurasjonen.")
	if port is not None and not 1 <= port <= 65535:
		frappe.throw("enk_pdf_asset_origin har ugyldig port.")
	return f"{parsed.scheme}://{parsed.netloc}"


def _trusted_asset_url(value, origin):
	parsed = urlsplit(value)
	if parsed.scheme or parsed.netloc or not parsed.path.startswith("/assets/"):
		return value
	if any(part in (".", "..") for part in unquote(parsed.path).split("/")):
		return value
	return origin + value


def rewrite_pdf_asset_urls(html, origin):
	"""Peker bare statiske ressursreferanser mot den serverkonfigurerte interne origin-en."""
	soup = BeautifulSoup(html, "html.parser")
	for link in soup.find_all("link", href=True):
		if "stylesheet" in {str(value).lower() for value in (link.get("rel") or [])}:
			link["href"] = _trusted_asset_url(link["href"], origin)
	for image in soup.find_all(("img", "source"), src=True):
		image["src"] = _trusted_asset_url(image["src"], origin)
	for tag in soup.find_all(style=True):
		tag["style"] = _CSS_ASSET_URL.sub(
			lambda match: f"url({match.group('quote')}{_trusted_asset_url(match.group('url'), origin)}{match.group('quote')})",
			tag["style"],
		)
	for style in soup.find_all("style"):
		if style.string:
			style.string.replace_with(
				_CSS_ASSET_URL.sub(
					lambda match: f"url({match.group('quote')}{_trusted_asset_url(match.group('url'), origin)}{match.group('quote')})",
					style.string,
				)
			)
	return str(soup)


def _native_download_pdf(*args, **kwargs):
	from frappe.utils.print_format import download_pdf as native_download_pdf

	return native_download_pdf(*args, **kwargs)


@frappe.whitelist(allow_guest=True)
@frappe.concurrent_limit()
def download_pdf(
	doctype: str,
	name: str,
	format: str | None = None,
	doc: Document | None = None,
	no_letterhead: bool | int = 0,
	language: str | None = None,
	letterhead: str | None = None,
	pdf_generator: str | None = None,
):
	"""ENK-fakturaer kan hente statiske ressurser fra en intern, serverkonfigurert origin under PDF-rendering."""
	if doctype != "Sales Invoice" or pdf_generator == "chrome":
		return _native_download_pdf(
			doctype, name, format, doc, no_letterhead, language, letterhead, pdf_generator
		)
	doc = doc or frappe.get_doc(doctype, name)
	validate_print_permission(doc)
	if not doc.company or not frappe.db.exists("ENK Settings", doc.company):
		return _native_download_pdf(
			doctype, name, format, doc, no_letterhead, language, letterhead, pdf_generator
		)
	origin = _pdf_asset_origin()
	if not origin:
		return _native_download_pdf(
			doctype, name, format, doc, no_letterhead, language, letterhead, pdf_generator
		)
	with print_language(language):
		html = frappe.get_print(
			doctype,
			name,
			format,
			doc=doc,
			as_pdf=False,
			letterhead=letterhead,
			no_letterhead=no_letterhead,
			pdf_generator="wkhtmltopdf",
		)
		pdf_file = get_pdf(rewrite_pdf_asset_urls(html, origin))
	frappe.local.response.filename = "{name}.pdf".format(name=name.replace(" ", "-").replace("/", "-"))
	frappe.local.response.filecontent = pdf_file
	frappe.local.response.type = "pdf"


def enk_invoice_issuer(doc):
	doc.check_permission("read")
	if doc.get("enk_invoice_snapshot"):
		return frappe._dict(frappe.parse_json(doc.enk_invoice_snapshot))
	from enk_norge.setup import get_settings

	return get_settings(doc.company).as_dict() | {"company_name": doc.company}


def enk_invoice_buyer(doc):
	"""Kjøperens navn og adresse som linjer. Norge skrives ikke ut for norske kunder."""
	doc.check_permission("read")
	address = frappe.db.get_value(
		"Address",
		doc.customer_address,
		["address_line1", "address_line2", "pincode", "city", "country"],
		as_dict=True,
	) or frappe._dict()
	lines = [address.address_line1, address.address_line2, " ".join(filter(None, [address.pincode, address.city]))]
	if address.country and address.country != "Norway":
		lines.append(address.country)
	return frappe._dict(name=doc.customer_name, lines=[line for line in lines if line], tax_id=doc.tax_id)


def enk_format_number(value, kind):
	"""Norsk visning av kontonummer (1234.56.78901), organisasjonsnummer (123 456 789) og telefon (400 00 000)."""
	digits = "".join(ch for ch in str(value or "") if ch.isdigit())
	if kind == "account" and len(digits) == 11:
		return f"{digits[:4]}.{digits[4:6]}.{digits[6:]}"
	if kind == "org" and len(digits) == 9:
		return f"{digits[:3]} {digits[3:6]} {digits[6:]}"
	if kind == "phone":
		local = digits[2:] if len(digits) == 10 and digits.startswith("47") else digits
		if len(local) == 8:
			prefix = "+47 " if len(digits) == 10 else ""
			return f"{prefix}{local[:3]} {local[3:5]} {local[5:]}"
	return value or ""
