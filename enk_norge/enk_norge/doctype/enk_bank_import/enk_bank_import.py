import frappe
from frappe.model.document import Document


class ENKBankImport(Document):
	def before_submit(self):
		file = frappe.get_doc("File", self.source_file)
		if (
			not file.is_private
			or file.attached_to_doctype != self.doctype
			or file.attached_to_name != self.name
			or self.import_status != "Imported"
		):
			frappe.throw("Importen må ha en privat kildefil knyttet til batchen før den arkiveres.")

	def before_cancel(self):
		if self.import_status == "Imported":
			frappe.throw("En arkivert bankimport kan ikke annulleres.")

	def on_trash(self):
		if self.import_status == "Imported":
			frappe.throw("En arkivert bankimport kan ikke slettes.")
