"""Kontrollerer ERPNexts første fakturakjøring for ENK-abonnement."""

import frappe
from erpnext.accounts.doctype.subscription.subscription import Subscription


class ENKSubscription(Subscription):
	def after_insert(self):
		# Upstream oppretter faktura umiddelbart når startdatoen er i dag eller tidligere.
		# ENK må vente på den kontrollerte utkastinngangen med avtale- og periodiseringsgrunnlag.
		if self.company and frappe.db.exists("ENK Settings", self.company):
			return
		return super().after_insert()
