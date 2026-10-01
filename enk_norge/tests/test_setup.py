"""Tester av avslutningen av ENKs førstegangsoppsett."""

import unittest
from unittest.mock import patch

import frappe

from enk_norge import setup


class SetupCompletionTest(unittest.TestCase):
	def test_finish_first_run_uses_native_completion_before_enk_home(self):
		events = []
		with (
			patch.object(frappe, "clear_cache", side_effect=lambda: events.append("clear")),
			patch(
				"enk_norge.setup.disable_future_access",
				side_effect=lambda: events.append("native"),
			),
			patch("enk_norge.setup.quiet_desk", side_effect=lambda: events.append("quiet")),
			patch.object(
				frappe.db,
				"set_default",
				side_effect=lambda key, value: events.append((key, value)),
			),
		):
			setup.finish_first_run()

		self.assertEqual(
			events,
			[
				"clear",
				"native",
				"quiet",
				("desktop:home_page", "enk-norge"),
				"clear",
			],
		)

	def test_repair_only_changes_completed_enk_site_with_stale_wizard_default(self):
		events = []
		with (
			patch.object(frappe, "is_setup_complete", return_value=True),
			patch.object(frappe.db, "count", side_effect=[1, 1]),
			patch.object(frappe.db, "get_default", return_value="setup-wizard"),
			patch.object(
				frappe.db,
				"set_default",
				side_effect=lambda key, value: events.append((key, value)),
			),
			patch.object(frappe, "clear_cache", side_effect=lambda: events.append("clear")),
			patch(
				"enk_norge.setup.disable_future_access",
				side_effect=AssertionError("Eksisterende site skal ikke endre onboarding."),
			),
		):
			self.assertTrue(setup.repair_completed_setup_home_page())

		self.assertEqual(events, [("desktop:home_page", "enk-norge"), "clear"])

	def test_repair_preserves_incomplete_or_intentionally_changed_home_page(self):
		for complete, home_page in ((False, "setup-wizard"), (True, "workspace")):
			with (
				patch.object(frappe, "is_setup_complete", return_value=complete),
				patch.object(frappe.db, "count", return_value=1),
				patch.object(frappe.db, "get_default", return_value=home_page),
				patch("enk_norge.setup.finish_first_run") as finish,
			):
				self.assertFalse(setup.repair_completed_setup_home_page())
			finish.assert_not_called()
