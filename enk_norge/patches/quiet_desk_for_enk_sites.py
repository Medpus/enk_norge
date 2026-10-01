"""Skjul ERPNexts lagerveileder og versjonsvarsler på ENK-siter som alt er satt opp."""

import frappe

from enk_norge.setup import quiet_desk


def execute():
	if frappe.is_setup_complete() and frappe.db.count("ENK Settings"):
		quiet_desk()
