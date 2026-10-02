"""Bytt til fakturanummer 1, 2, 3 der ingen faktura er utstedt i den gamle serien.

Et foretak som alt har bokført en faktura, beholder serien sin. Ellers ville nummerrekken
blitt brutt. Kladder i den gamle serien kan ikke bokføres etter byttet og må lages på nytt.
"""

import frappe


def execute():
	companies = frappe.get_all("ENK Settings", fields=["name", "invoice_prefix"])
	if len(companies) != 1 or not companies[0].invoice_prefix:
		return
	company = companies[0].name
	if frappe.db.exists("Sales Invoice", {"company": company, "docstatus": ["in", [1, 2]]}):
		return
	# ENK Settings sperrer prefiksen etter første føring. Her er ingen faktura utstedt ennå.
	frappe.db.set_value("ENK Settings", company, "invoice_prefix", "", update_modified=False)
