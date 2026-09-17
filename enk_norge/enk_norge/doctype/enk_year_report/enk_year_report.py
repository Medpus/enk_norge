from frappe.model.document import Document

from enk_norge.year_end import validate_year_report_document


class ENKYearReport(Document):
	def validate(self):
		validate_year_report_document(self)
