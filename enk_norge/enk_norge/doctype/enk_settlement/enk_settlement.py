from hashlib import sha256

import frappe
from frappe.model.document import Document

from enk_norge.setup import get_settings


class ENKSettlement(Document):
	def autoname(self):
		key = f"{self.company}|{self.external_settlement_id}"
		self.name = "ENK-SET-" + sha256(key.encode()).hexdigest()[:24]

	def validate(self):
		get_settings(self.company, write=True)
		old = self.get_doc_before_save()
		if not old and not self.flags.enk_settlement_build:
			frappe.throw("Oppgjør kan bare opprettes gjennom betalingsformidlerflyten.")
		if old and old.status == "Ready for review":
			protected = (
				"company",
				"currency",
				"external_settlement_id",
				"fee_amount",
				"gross_amount",
				"journal_entry",
				"merchant_of_record",
				"net_amount",
				"posting_date",
				"references_json",
				"refund_amount",
				"request_fingerprint",
				"source_file",
				"source_sha256",
				"status",
			)
			if any(old.get(field) != self.get(field) for field in protected):
				frappe.throw("Et klart oppgjørsutkast kan ikke endres. Opprett et korrigerende oppgjør.")
		if self.status not in ("Draft", "Ready for review"):
			frappe.throw("Oppgjørsstatus må være utkast eller klar til kontroll.")
		if self.status == "Ready for review":
			if not self.journal_entry or ((not old or old.status != "Ready for review") and not self.flags.enk_settlement_build):
				frappe.throw("Klart oppgjør krever et generert journalutkast.")
			file = frappe.get_doc("File", self.source_file)
			if not file.is_private or file.attached_to_doctype != "Journal Entry" or file.attached_to_name != self.journal_entry:
				frappe.throw("Oppgjørsfilen må være privat og knyttet til journalutkastet.")

	def on_trash(self):
		if self.status == "Ready for review":
			frappe.throw("Et klart oppgjørsutkast skal bevares sammen med kildefilen.")
