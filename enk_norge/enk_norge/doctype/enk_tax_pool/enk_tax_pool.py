from frappe.model.document import Document

from enk_norge.year_end import validate_pool_document


class ENKTaxPool(Document):
	def validate(self):
		validate_pool_document(self)
