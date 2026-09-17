from frappe.model.document import Document

from enk_norge.vat import _return_name, validate_vat_return_document


class ENKVATReturn(Document):
	def autoname(self):
		self.name = _return_name(self.company, self.period_end, self.report_type, int(self.revision or 1))

	def validate(self):
		validate_vat_return_document(self)
