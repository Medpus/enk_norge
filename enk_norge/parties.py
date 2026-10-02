"""Enkle kunder og leverandører for ENK-siden.

ERPNext krever egne dokumenter for kunde og fakturaadresse. Her lages begge i ett steg.
"""

import re

import frappe

from enk_norge.api import _data


def _root(doctype, preferred):
	"""Bruk ERPNexts standardgruppe når den finnes, ellers rotgruppen i treet."""
	if frappe.db.exists(doctype, preferred):
		return preferred
	# ENK-veiviseren installerer ikke ERPNexts eksempelgrupper. Roten har lavest lft.
	return frappe.get_all(doctype, filters={"is_group": 1}, order_by="lft asc", limit=1, pluck="name")[0]


def _clean(value, label, required=True, limit=140):
	value = (value or "").strip()
	if required and not value:
		frappe.throw(f"Oppgi {label}.")
	return value[:limit]


def _party_type(value):
	if value not in ("Company", "Individual"):
		frappe.throw("Velg bedrift eller privatperson.")
	return value


def _country(value):
	value = (value or "Norway").strip()
	if not frappe.db.exists("Country", value):
		frappe.throw("Velg et land fra listen.")
	return value


def _org_number(value, country):
	value = re.sub(r"\s", "", value or "")
	if value and country == "Norway":
		from enk_norge.norway_rules import validate_org_number

		if not validate_org_number(value):
			frappe.throw("Organisasjonsnummeret har feil format eller kontrollsiffer.")
	return value


@frappe.whitelist(methods=["POST"])
def create_customer(data):
	data = _data(data)
	frappe.has_permission("Customer", "create", throw=True)
	name = _clean(data.customer_name, "kundens navn")
	customer_type = _party_type(data.customer_type or "Company")
	country = _country(data.country)
	org_number = _org_number(data.organization_number, country)
	address_line = _clean(data.address_line, "fakturaadresse")
	city = _clean(data.city, "poststed")
	postal_code = _clean(data.postal_code, "postnummer", required=country == "Norway", limit=20)
	if country == "Norway" and not re.fullmatch(r"\d{4}", postal_code):
		frappe.throw("Postnummeret må ha fire siffer.")
	customer = frappe.get_doc(
		dict(
			doctype="Customer",
			customer_name=name,
			customer_type=customer_type,
			customer_group=_root("Customer Group", "Commercial" if customer_type == "Company" else "Individual"),
			territory=_root("Territory", country if frappe.db.exists("Territory", country) else "All Territories"),
			tax_id=org_number or None,
			email_id=(data.email or "").strip() or None,
		)
	).insert()
	address = frappe.get_doc(
		dict(
			doctype="Address",
			address_title=name,
			address_type="Billing",
			address_line1=address_line,
			pincode=postal_code or None,
			city=city,
			country=country,
			email_id=(data.email or "").strip() or None,
			is_primary_address=1,
			links=[dict(link_doctype="Customer", link_name=customer.name)],
		)
	).insert()
	customer.db_set("customer_primary_address", address.name)
	return dict(customer=customer.name, customer_name=customer.customer_name, customer_address=address.name)


@frappe.whitelist(methods=["POST"])
def create_supplier(data):
	data = _data(data)
	frappe.has_permission("Supplier", "create", throw=True)
	name = _clean(data.supplier_name, "leverandørens navn")
	country = _country(data.country)
	supplier = frappe.get_doc(
		dict(
			doctype="Supplier",
			supplier_name=name,
			supplier_type=_party_type(data.supplier_type or "Company"),
			supplier_group=_root("Supplier Group", "Services"),
			country=country,
			tax_id=_org_number(data.organization_number, country) or None,
		)
	).insert()
	return dict(supplier=supplier.name, supplier_name=supplier.supplier_name, country=country)


@frappe.whitelist()
def list_parties():
	customers = []
	for row in frappe.get_list(
		"Customer",
		filters={"disabled": 0},
		fields=["name", "customer_name", "customer_type", "tax_id", "email_id"],
		order_by="customer_name asc",
		limit_page_length=500,
	):
		address = billing_address(row.name)
		row.update(
			address_line=address.address_line1 if address else "",
			postal_code=address.pincode if address else "",
			city=address.city if address else "",
			country=address.country if address else "Norway",
		)
		customers.append(row)
	suppliers = frappe.get_list(
		"Supplier",
		filters={"disabled": 0},
		fields=["name", "supplier_name", "country", "tax_id"],
		order_by="supplier_name asc",
		limit_page_length=500,
	)
	return dict(customers=customers, suppliers=suppliers)


@frappe.whitelist(methods=["POST"])
def update_customer(customer, data):
	"""Ny adresse gjelder nye fakturaer. Bokførte fakturaer beholder adressen de ble utstedt med."""
	data = _data(data)
	doc = frappe.get_doc("Customer", customer)
	doc.check_permission("write")
	country = _country(data.country)
	doc.customer_name = _clean(data.customer_name, "kundens navn")
	doc.customer_type = _party_type(data.customer_type or doc.customer_type)
	doc.tax_id = _org_number(data.organization_number, country) or None
	doc.email_id = (data.email or "").strip() or None
	doc.save()
	postal_code = _clean(data.postal_code, "postnummer", required=country == "Norway", limit=20)
	if country == "Norway" and not re.fullmatch(r"\d{4}", postal_code):
		frappe.throw("Postnummeret må ha fire siffer.")
	address = billing_address(customer)
	values = dict(
		address_line1=_clean(data.address_line, "fakturaadresse"),
		pincode=postal_code or None,
		city=_clean(data.city, "poststed"),
		country=country,
		email_id=doc.email_id,
	)
	if address:
		address_doc = frappe.get_doc("Address", address.name)
		address_doc.check_permission("write")
		address_doc.update(values)
		address_doc.save()
	else:
		frappe.get_doc(
			dict(doctype="Address", address_title=doc.customer_name, address_type="Billing", is_primary_address=1,
				links=[dict(link_doctype="Customer", link_name=customer)], **values)
		).insert()
	return dict(customer=customer)


@frappe.whitelist(methods=["POST"])
def update_supplier(supplier, data):
	data = _data(data)
	doc = frappe.get_doc("Supplier", supplier)
	doc.check_permission("write")
	country = _country(data.country)
	doc.supplier_name = _clean(data.supplier_name, "leverandørens navn")
	doc.country = country
	doc.tax_id = _org_number(data.organization_number, country) or None
	doc.save()
	return dict(supplier=supplier)


@frappe.whitelist()
def billing_address(customer):
	frappe.get_doc("Customer", customer).check_permission("read")
	rows = frappe.get_all(
		"Address",
		filters=[["Dynamic Link", "link_doctype", "=", "Customer"], ["Dynamic Link", "link_name", "=", customer]],
		fields=["name", "address_line1", "pincode", "city", "country", "address_type", "is_primary_address"],
		order_by="is_primary_address desc, creation asc",
	)
	billing = [row for row in rows if row.address_type == "Billing"] or rows
	return billing[0] if billing else None
