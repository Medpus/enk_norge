import json
import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase

from enk_norge.vat import VatError, _foreign, _foreign_for_report, period_for

try:
	import frappe

	from enk_norge.tests.test_workflows import WorkflowsTest
except ModuleNotFoundError:
	frappe = None
	WorkflowsTest = None

VatWorkflowBase = WorkflowsTest or TestCase


class VatCoreTest(TestCase):
	def settings(self, registered=True, registration_date="2026-01-01"):
		return SimpleNamespace(vat_registered=registered, vat_registration_date=registration_date)

	def test_registered_uses_six_bimonthly_terms(self):
		start, end, _kind, overlap = period_for(self.settings(), date(2026, 4, 30), "Ordinary")
		self.assertEqual(
			(start, end, _kind, overlap),
			(date(2026, 3, 1), date(2026, 4, 30), "Registered bi-monthly", False),
		)

	def test_registration_mid_term_starts_ordinary_report_on_registration_date(self):
		start, end, _kind, overlap = period_for(
			self.settings(registration_date="2026-03-15"), date(2026, 4, 30), "Ordinary"
		)
		self.assertEqual(start, date(2026, 3, 1))
		self.assertEqual(end, date(2026, 4, 30))
		self.assertTrue(overlap)

	def test_unregistered_reverse_charge_uses_calendar_quarter(self):
		start, end, _kind, overlap = period_for(
			self.settings(False), date(2026, 6, 30), "Reverse charge unregistered"
		)
		self.assertEqual(
			(start, end, _kind, overlap),
			(date(2026, 4, 1), date(2026, 6, 30), "Unregistered reverse charge quarterly", False),
		)
		with self.assertRaises(VatError):
			period_for(self.settings(False), date(2026, 5, 31), "Reverse charge unregistered")

	def test_registration_inside_quarter_splits_reverse_charge_purchases_by_date(self):
		settings = self.settings(registration_date="2026-06-15")
		start, end, _kind, overlap = period_for(
			settings, date(2026, 6, 30), "Reverse charge unregistered"
		)
		self.assertEqual((start, end), (date(2026, 4, 1), date(2026, 6, 30)))
		self.assertTrue(overlap)
		purchases = [
			SimpleNamespace(posting_date="2026-06-14", enk_vat_basis="100"),
			SimpleNamespace(posting_date="2026-06-15", enk_vat_basis="200"),
		]
		self.assertEqual(
			[entry.enk_vat_basis for entry in _foreign_for_report(
				purchases, "Reverse charge unregistered", date(2026, 6, 15)
			)],
			["100"],
		)
		self.assertEqual(
			[entry.enk_vat_basis for entry in _foreign_for_report(purchases, "Ordinary", date(2026, 6, 15))],
			["200"],
		)

	def test_fully_registered_quarter_cannot_use_unregistered_reverse_charge_return(self):
		with self.assertRaisesRegex(VatError, "ordinær"):
			period_for(
				self.settings(registration_date="2026-04-01"),
				date(2026, 6, 30),
				"Reverse charge unregistered",
			)

	def test_foreign_service_partial_deduction_and_credit_note(self):
		purchases = [
			SimpleNamespace(enk_vat_basis="1000.00", enk_deductible_fraction="0.60"),
			SimpleNamespace(enk_vat_basis="-200.00", enk_deductible_fraction="0.60"),
		]
		basis, output, input_vat = _foreign(purchases, True)
		self.assertEqual(basis, Decimal("800.00"))
		self.assertEqual(output, Decimal("200.00"))
		self.assertEqual(input_vat, Decimal("120.00"))

	def test_outside_2026_fails_closed(self):
		with self.assertRaises(VatError):
			period_for(self.settings(), date(2027, 2, 28), "Ordinary")


@unittest.skipIf(frappe is None, "Krever Frappe-testsite")
class VatWorkflowTest(VatWorkflowBase):
	def foreign_purchase(self, amount, fraction="1", bill_no="FOREIGN-1000", **overrides):
		self.supplier.country = "United States"
		self.supplier.save()
		purchase = self.purchase(
			foreign_service=1,
			vat_rate="0",
			gross_amount=str(amount),
			bill_no=bill_no,
			deductible_fraction=fraction,
			**overrides,
		)
		self.attach(purchase)
		purchase.submit()
		return purchase

	def test_reverse_charge_draft_and_gl_reconciliation(self):
		from enk_norge.vat import build_vat_return, create_reverse_charge_draft

		self.settings.vat_registered = 1
		self.settings.vat_registration_date = "2026-01-01"
		self.settings.save()
		self.foreign_purchase("1000")

		created = create_reverse_charge_draft(self.company, "2026-10-31")
		entry = frappe.get_doc("Journal Entry", created["name"])
		self.assertEqual(entry.total_debit, 250)
		self.assertEqual(entry.total_credit, 250)
		entry.submit()

		report = build_vat_return(self.company, "2026-10-31")
		self.assertEqual(report["status"], "Ready for review")
		self.assertEqual(report["checks"], [])
		reused = create_reverse_charge_draft(self.company, "2026-10-31")
		self.assertTrue(reused["up_to_date"])

	def test_unregistered_reverse_charge_strictly_exceeds_2000(self):
		from enk_norge.vat import create_reverse_charge_draft

		self.foreign_purchase("2000", bill_no="FOREIGN-2000")
		self.assertTrue(
			create_reverse_charge_draft(self.company, "2026-09-30", "Reverse charge unregistered")[
				"up_to_date"
			]
		)
		self.foreign_purchase("0.01", bill_no="FOREIGN-2000-01")
		created = create_reverse_charge_draft(self.company, "2026-09-30", "Reverse charge unregistered")
		entry = frappe.get_doc("Journal Entry", created["name"])
		self.assertEqual(entry.total_debit, 500)
		self.assertEqual(entry.total_credit, 500)

	def test_backdated_sale_blocks_the_later_historical_threshold_crossing(self):
		from enk_norge.api import dashboard

		first = self.sale(
			unit_price="30000", posting_date="2026-01-10", delivery_date="2026-01-10", due_date="2026-02-10"
		)
		later = self.sale(
			unit_price="15000", posting_date="2026-06-20", delivery_date="2026-06-20", due_date="2026-07-20"
		)
		first.submit()
		later.submit()
		backdated = self.sale(
			unit_price="6000", posting_date="2026-05-15", delivery_date="2026-05-15", due_date="2026-06-15"
		)
		with self.assertRaisesRegex(frappe.ValidationError, "2026-06-20"):
			backdated.submit()
		backdated.reload()
		backdated.enk_vat_registration_pending = 1
		backdated.submit()
		crossing = dashboard(self.company)["vat_first_crossing"]
		self.assertEqual(crossing["date"], "2026-06-20")
		self.assertEqual(Decimal(crossing["basis"]), Decimal("51000"))

	def test_registration_mid_quarter_separates_unregistered_and_ordinary_reverse_charge(self):
		from enk_norge.vat import build_vat_return, create_reverse_charge_draft

		self.settings.vat_registered = 1
		self.settings.vat_registration_date = "2026-11-15"
		self.settings.save()
		self.foreign_purchase(
			"3000", bill_no="FOREIGN-BEFORE-REG", posting_date="2026-11-14", bill_date="2026-11-14"
		)
		self.foreign_purchase(
			"1200", bill_no="FOREIGN-AFTER-REG", posting_date="2026-11-15", bill_date="2026-11-15"
		)
		special = frappe.get_doc(
			"Journal Entry",
			create_reverse_charge_draft(self.company, "2026-12-31", "Reverse charge unregistered")["name"],
		)
		self.assertEqual(special.total_debit, 750)
		special.submit()
		ordinary = frappe.get_doc("Journal Entry", create_reverse_charge_draft(self.company, "2026-12-31")["name"])
		self.assertEqual(ordinary.total_debit, 300)
		ordinary.submit()
		self.assertEqual(
			build_vat_return(self.company, "2026-12-31", "Reverse charge unregistered")["status"],
			"Ready for review",
		)
		self.assertEqual(build_vat_return(self.company, "2026-12-31")["status"], "Ready for review")

	def test_registered_partial_deduction_and_modified_draft_are_not_overwritten(self):
		from enk_norge.vat import create_reverse_charge_draft

		self.settings.vat_registered = 1
		self.settings.vat_registration_date = "2026-01-01"
		self.settings.save()
		self.foreign_purchase("1000", fraction="0.60")
		created = create_reverse_charge_draft(self.company, "2026-10-31")
		draft = frappe.get_doc("Journal Entry", created["name"])
		amounts = {row.account: row.debit_in_account_currency for row in draft.accounts}
		self.assertEqual(amounts[self.settings.input_vat_account], 150)
		self.assertEqual(amounts[self.settings.software_account], 100)
		draft.accounts[0].user_remark = "Brukerens endring"
		draft.save()
		reused = create_reverse_charge_draft(self.company, "2026-10-31")
		self.assertEqual(reused["name"], draft.name)
		self.assertTrue(reused["needs_review"])
		self.assertTrue(reused["draft_hash"])

	def test_credit_note_creates_delta_draft(self):
		from enk_norge.vat import create_reverse_charge_draft

		self.settings.vat_registered = 1
		self.settings.vat_registration_date = "2026-01-01"
		self.settings.save()
		original = self.foreign_purchase("1000", bill_no="FOREIGN-ORIGINAL")
		first = frappe.get_doc(
			"Journal Entry", create_reverse_charge_draft(self.company, "2026-10-31")["name"]
		)
		first.submit()
		from erpnext.controllers.sales_and_purchase_return import make_return_doc

		credit = make_return_doc("Purchase Invoice", original.name)
		credit.bill_no = "FOREIGN-CREDIT"
		credit.bill_date = "2026-09-17"
		credit.enk_vat_basis = -200
		credit.items[0].qty = -1
		credit.items[0].rate = 200
		credit.insert()
		self.attach(credit)
		credit.submit()
		delta = frappe.get_doc(
			"Journal Entry", create_reverse_charge_draft(self.company, "2026-10-31")["name"]
		)
		self.assertEqual(delta.total_debit, 50)
		self.assertEqual(delta.total_credit, 50)

	def test_filing_receipt_must_be_private_and_attached_to_the_report(self):
		from enk_norge.vat import build_vat_return, mark_vat_return_manually_filed

		self.settings.vat_registered = 1
		self.settings.vat_registration_date = "2026-01-01"
		self.settings.save()
		report = build_vat_return(self.company, "2026-10-31")
		file = frappe.get_doc(
			dict(doctype="File", file_name="not-report.txt", content="ikke tilknyttet", is_private=1)
		).insert()
		with self.assertRaises(frappe.ValidationError):
			mark_vat_return_manually_filed(self.company, "2026-10-31", file.name)
		file.attached_to_doctype = "ENK VAT Return"
		file.attached_to_name = report["name"]
		file.save()
		self.assertEqual(
			mark_vat_return_manually_filed(self.company, "2026-10-31", file.name)["status"],
			"Manually filed",
		)

	def test_standard_document_api_cannot_create_or_change_vat_report_state(self):
		from enk_norge.vat import build_vat_return

		self.settings.vat_registered = 1
		self.settings.vat_registration_date = "2026-01-01"
		self.settings.save()
		with self.assertRaisesRegex(frappe.ValidationError, "bare opprettes via MVA-beregningen"):
			frappe.get_doc(
				dict(
					doctype="ENK VAT Return",
					company=self.company,
					period_start="2026-09-01",
					period_end="2026-10-31",
					report_type="Ordinary",
					period_type="Registered bi-monthly",
					status="Ready for review",
				)
			).insert()
		report = frappe.get_doc("ENK VAT Return", build_vat_return(self.company, "2026-10-31")["name"])
		report.snapshot_json = "{}"
		with self.assertRaisesRegex(frappe.ValidationError, "bare opprettes via MVA-beregningen"):
			report.save()

	def test_filed_return_is_immutable_and_rebuild_creates_correction_revision(self):
		from enk_norge.vat import build_vat_return, get_vat_return, mark_vat_return_manually_filed

		self.settings.vat_registered = 1
		self.settings.vat_registration_date = "2026-01-01"
		self.settings.save()
		first = build_vat_return(self.company, "2026-12-31")
		report = frappe.get_doc("ENK VAT Return", first["name"])
		receipt = frappe.get_doc(
			dict(
				doctype="File",
				file_name="mva-kvittering.txt",
				content="kvittering",
				is_private=1,
				attached_to_doctype="ENK VAT Return",
				attached_to_name=report.name,
			)
		).insert()
		filed = mark_vat_return_manually_filed(self.company, "2026-12-31", receipt.name)
		filed_report = frappe.get_doc("ENK VAT Return", filed["name"])
		filed_snapshot = filed_report.snapshot_json
		filed_history = json.loads(filed_report.snapshot_history_json)
		filed_report.reconciliation_json = "[]"
		with self.assertRaises(frappe.ValidationError):
			filed_report.save()
		with self.assertRaises(frappe.ValidationError):
			receipt.delete()

		correction = build_vat_return(self.company, "2026-12-31")
		self.assertNotEqual(correction["name"], filed["name"])
		self.assertGreater(correction["revision"], filed_report.revision)
		self.assertEqual(frappe.get_doc("ENK VAT Return", filed["name"]).snapshot_json, filed_snapshot)
		newest = frappe.get_doc("ENK VAT Return", correction["name"])
		self.assertGreaterEqual(len(json.loads(newest.snapshot_history_json)), len(filed_history) + 1)
		self.assertEqual(
			get_vat_return(self.company, "2026-12-31")["name"],
			correction["name"],
		)


def run():
	if frappe is None or frappe.local.site != "test.localhost":
		raise RuntimeError("Kun test.localhost kan kjøre denne integrasjonstesten.")
	result = unittest.TextTestRunner(verbosity=2).run(
		unittest.defaultTestLoader.loadTestsFromTestCase(VatWorkflowTest)
	)
	frappe.db.rollback()
	if not result.wasSuccessful():
		raise RuntimeError("MVA-integrasjonstesten feilet.")
	return {"tests": result.testsRun, "successful": True}
