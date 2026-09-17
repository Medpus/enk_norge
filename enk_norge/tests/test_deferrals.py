"""Periodisert SaaS-abonnement mot native faktura, hovedbok og SAF-T."""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from enk_norge.deferrals import (
	DeferralError,
	cumulative_earned_amount,
	recognition_increment,
	validate_subscription_period,
)

try:
	import frappe

	from enk_norge.tests.test_workflows import WorkflowsTest
except ModuleNotFoundError:
	frappe = None
	WorkflowsTest = unittest.TestCase


class DeferralCoreTest(unittest.TestCase):
	def test_annual_subscription_is_earned_linearly_per_delivered_day(self):
		earned = cumulative_earned_amount("1200.00", "2026-12-15", "2027-12-14", "2026-12-31")
		self.assertEqual(earned.total_days, 365)
		self.assertEqual(earned.earned_days, 17)
		self.assertEqual(earned.cumulative_amount, Decimal("55.89"))
		self.assertEqual(recognition_increment(earned.cumulative_amount, "0"), Decimal("55.89"))
		self.assertEqual(recognition_increment(earned.cumulative_amount, "55.89"), Decimal("0.00"))

	def test_period_must_be_prepaid_and_at_most_one_year(self):
		with self.assertRaisesRegex(DeferralError, "høyst ett år"):
			validate_subscription_period("2026-01-01", "2027-01-02")
		with self.assertRaisesRegex(DeferralError, "forskuddsfakturering"):
			validate_subscription_period("2026-02-01", "2027-01-31", invoice_date="2026-02-02")
		with self.assertRaisesRegex(DeferralError, "overstiger"):
			recognition_increment("10", "10.01")


@unittest.skipIf(frappe is None, "Krever Frappe-testsite")
class DeferralWorkflowTest(unittest.TestCase):
	setUp = WorkflowsTest.setUp
	tearDown = WorkflowsTest.tearDown

	def _file(self, filename):
		return frappe.get_doc(
			dict(doctype="File", file_name=filename, content="Fiktiv abonnementskontrakt", is_private=1)
		).insert()

	def _subscription_invoice(self):
		from enk_norge.api import create_sale

		source = self._file("abonnement-2026-2027.txt")
		created = create_sale(
			dict(
				company=self.company,
				customer=self.customer.name,
				customer_address=self.address.name,
				posting_date="2026-12-15",
				delivery_date="2026-12-15",
				due_date="2026-12-15",
				description="Fiktivt årlig SaaS-abonnement",
				quantity="1",
				unit_price="1200.00",
				service_start_date="2026-12-15",
				service_end_date="2027-12-14",
				subscription_source_file=source.name,
			)
		)
		invoice = frappe.get_doc("Sales Invoice", created["name"])
		source.reload()
		self.assertEqual(source.attached_to_doctype, "Sales Invoice")
		self.assertEqual(source.attached_to_name, invoice.name)
		self.assertEqual(invoice.enk_subscription_source_file, source.name)
		self.assertTrue(invoice.items[0].enable_deferred_revenue)
		self.assertEqual(invoice.items[0].deferred_revenue_account, self.settings.deferred_revenue_account)
		invoice.submit()
		return invoice

	def test_native_deferred_accounting_process_is_blocked(self):
		with self.assertRaisesRegex(frappe.ValidationError, "automatiske periodisering"):
			frappe.get_doc(
				dict(
					doctype="Process Deferred Accounting",
					company=self.company,
					posting_date="2026-12-31",
					start_date="2026-12-01",
					end_date="2026-12-31",
					type="Income",
				)
			).insert()

	def test_cross_year_subscription_recognition_is_signed_idempotent_and_saft_mapped(self):
		from enk_norge.deferrals import create_revenue_recognition_draft
		from enk_norge.saft import _frappe_export_data, build_saf_t, validate_saf_t

		invoice = self._subscription_invoice()
		self.assertEqual(
			Decimal(
				str(
					frappe.db.get_value(
						"GL Entry", {"voucher_no": invoice.name, "account": self.settings.deferred_revenue_account}, "credit"
					)
				)
			),
			Decimal("1200.00"),
		)
		created = create_revenue_recognition_draft(self.company, invoice.name, "2026-12-31")
		draft = frappe.get_doc("Journal Entry", created["name"])
		self.assertFalse(created["reused"])
		self.assertTrue(draft.enk_posting_contract)
		self.assertIn('"source_file"', draft.enk_deferral_details)
		draft.submit()
		self.assertEqual(Decimal(created["amount"]), Decimal("55.89"))
		reused = create_revenue_recognition_draft(self.company, invoice.name, "2026-12-31")
		self.assertTrue(reused["reused"])
		self.assertEqual(reused["name"], draft.name)
		deferred_balance = sum(
			(Decimal(str(row.debit)) - Decimal(str(row.credit)) for row in frappe.get_all(
				"GL Entry",
				filters={"company": self.company, "account": self.settings.deferred_revenue_account, "is_cancelled": 0},
				fields=["debit", "credit"],
			)),
			Decimal(),
		)
		self.assertEqual(deferred_balance, Decimal("-1144.11"))
		data = _frappe_export_data(self.company, date(2026, 12, 1), date(2026, 12, 31))
		self.assertEqual(
			data.account_mappings[self.settings.deferred_revenue_account].grouping_code,
			"2970",
		)
		validate_saf_t(build_saf_t(data))
		final = frappe.get_doc(
			"Journal Entry", create_revenue_recognition_draft(self.company, invoice.name, "2027-12-14")["name"]
		)
		final.submit()
		self.assertEqual(
			Decimal(
				str(
					frappe.db.get_value(
						"GL Entry", {"voucher_no": final.name, "account": self.settings.deferred_revenue_account}, "debit"
					)
				)
			),
			Decimal("1144.11"),
		)

	def test_full_refund_reverses_unearned_balance_after_credit_note(self):
		from enk_norge.api import create_credit_note
		from enk_norge.deferrals import create_revenue_recognition_draft

		invoice = self._subscription_invoice()
		frappe.get_doc("Journal Entry", create_revenue_recognition_draft(self.company, invoice.name, "2026-12-31")["name"]).submit()
		refund_proof = self._file("refusjon-abonnement.txt")
		created = create_credit_note("Sales Invoice", invoice.name, "2026-12-31", refund_proof.name)
		credit = frappe.get_doc("Sales Invoice", created["name"])
		reversal = frappe.get_doc("Journal Entry", created["deferral_reversal"]["name"])
		self.assertTrue(reversal.enk_posting_contract)
		credit.submit()
		reversal.reload()
		self.assertEqual(reversal.docstatus, 1)
		deferred_balance = sum(
			(Decimal(str(row.debit)) - Decimal(str(row.credit)) for row in frappe.get_all(
				"GL Entry",
				filters={"company": self.company, "account": self.settings.deferred_revenue_account, "is_cancelled": 0},
				fields=["debit", "credit"],
			)),
			Decimal(),
		)
		income_balance = sum(
			(Decimal(str(row.debit)) - Decimal(str(row.credit)) for row in frappe.get_all(
				"GL Entry",
				filters={"company": self.company, "account": self.settings.income_account, "is_cancelled": 0},
				fields=["debit", "credit"],
			)),
			Decimal(),
		)
		self.assertEqual(deferred_balance, Decimal("0.00"))
		self.assertEqual(income_balance, Decimal("0.00"))
		refund_proof.reload()
		self.assertEqual(refund_proof.attached_to_name, credit.name)
		with self.assertRaises(frappe.ValidationError):
			reversal.cancel()
		reversal.reload()
		credit.cancel()
		reversal.reload()
		self.assertEqual(reversal.docstatus, 2)

	def test_submitted_subscription_cannot_gain_service_stop_date(self):
		invoice = self._subscription_invoice()
		invoice.items[0].service_stop_date = "2026-12-31"
		with self.assertRaisesRegex(frappe.ValidationError, "Tjenestestopp kan ikke endres"):
			invoice.save()


def run():
	if frappe is None or frappe.local.site != "test.localhost":
		raise RuntimeError("Kun test.localhost kan kjøre periodiseringstesten.")
	result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DeferralWorkflowTest))
	frappe.db.rollback()
	if not result.wasSuccessful():
		raise RuntimeError("Periodiseringstesten feilet.")
	return {"tests": result.testsRun, "successful": True}
