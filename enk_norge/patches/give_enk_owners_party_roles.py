"""Gi eksisterende ENK-eiere rollene som trengs for å opprette kunder og leverandører."""

import frappe

from enk_norge.setup import OWNER_ROLES


def execute():
	if not frappe.db.count("ENK Settings"):
		return
	owners = frappe.get_all(
		"Has Role",
		filters={"role": "Accounts Manager", "parenttype": "User", "parent": ["not in", ["Administrator", "Guest"]]},
		pluck="parent",
	)
	for name in set(owners):
		user = frappe.get_doc("User", name)
		if user.enabled and user.user_type == "System User":
			user.add_roles(*[role for role in OWNER_ROLES if frappe.db.exists("Role", role)])
