import frappe
from frappe.model.document import Document

from enk_norge.validation import validate_setup_values


class ENKSettings(Document):
	def validate(self):
		validate_setup_values(self.as_dict())
		company = frappe.get_doc("Company", self.company)
		if company.country != "Norway" or company.default_currency != "NOK":
			frappe.throw("ENK-oppsettet krever norsk foretak med NOK som regnskapsvaluta.")
		seen = set()
		for row in self.accounts:
			account = frappe.get_doc("Account", row.account)
			if account.company != self.company or account.is_group or row.account in seen:
				frappe.throw("Kontokoblingene må være unike hovedbokskontoer i dette foretaket.")
			if row.tax_category != account.root_type:
				frappe.throw("Årsoppgjørskategorien må stemme med kontoens type.")
			seen.add(row.account)
		for field in self.meta.fields:
			if (
				field.fieldtype == "Link"
				and field.options == "Account"
				and self.get(field.fieldname) not in seen
			):
				frappe.throw(f"Kontoen for {field.label} må ha en rapportkobling.")
		old = self.get_doc_before_save()
		if old and old.company != self.company:
			frappe.throw("Et ENK-oppsett kan ikke flyttes til et annet foretak.")
		if old and frappe.db.exists("GL Entry", {"company": self.company}):
			protected = {
				"organization_number",
				"start_date",
				"invoice_prefix",
				"bank_account",
				"bank_name",
				"bank_account_record",
			}
			protected.update(
				field.fieldname
				for field in self.meta.fields
				if field.fieldtype == "Link" and field.options == "Account" and old.get(field.fieldname)
			)
			if any(old.get(field) != self.get(field) for field in protected):
				frappe.throw(
					"Regnskapsidentitet, kontoer og bankoppsett kan ikke skrives om etter første føring. Endringer krever en dokumentert overgang."
				)
			current = {row.account: row for row in self.accounts}
			for before in old.accounts:
				after = current.get(before.account)
				if not after or any(
					before.get(key) != after.get(key)
					for key in ("tax_category", "grouping_category", "grouping_code", "standard_account_id")
				):
					frappe.throw(
						"Eksisterende rapportkoblinger skal bevares etter bokføring. Nye kontoer kan legges til."
					)
			if old.vat_registered and (
				not self.vat_registered or old.vat_registration_date != self.vat_registration_date
			):
				frappe.throw(
					"En etablert MVA-registrering kan ikke skrives om etter bokføring. Avklar dokumentert korreksjon eller avregistrering."
				)
