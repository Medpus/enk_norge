"""Bruk norsk datoformat på ENK-siter som fortsatt har ERPNexts dd-mm-yyyy."""

import frappe

from enk_norge.setup import use_norwegian_date_format


def execute():
	if not frappe.db.count("ENK Settings"):
		return
	if frappe.db.get_default("date_format") in ("dd-mm-yyyy", None, ""):
		use_norwegian_date_format()
		frappe.clear_cache()
