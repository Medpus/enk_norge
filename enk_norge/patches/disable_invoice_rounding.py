"""Slå av ERPNexts avrunding til hele kroner på ENK-siter."""

import frappe


def execute():
	if frappe.db.count("ENK Settings"):
		frappe.db.set_single_value("Global Defaults", "disable_rounded_total", 1)
