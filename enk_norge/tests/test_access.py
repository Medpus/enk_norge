"""Tilgang, historikk og gjentatte forespørsler med faktiske Frappe-dokumenter."""

import unittest
from uuid import uuid4

import frappe

from enk_norge.api import create_credit_note, dashboard, pay_purchase_privately
from enk_norge.setup import create_company, get_settings, list_companies
from enk_norge.tests.test_saft_integration import _mod11
from enk_norge.tests.test_workflows import WorkflowsTest


class AccessTest(unittest.TestCase):
	setUp = WorkflowsTest.setUp
	sale = WorkflowsTest.sale
	purchase = WorkflowsTest.purchase
	attach = WorkflowsTest.attach

	def test_external_event_retries_and_changed_payload(self):
		first = self.sale(external_id="event-1")
		self.assertEqual(first.name, self.sale(external_id="event-1").name)
		with self.assertRaises(frappe.ValidationError):
			self.sale(external_id="event-1", unit_price="10001")
		self.assertNotEqual(self.sale().name, self.sale().name)

	def test_tax_exception_requires_documented_basis(self):
		with self.assertRaises(frappe.ValidationError):
			self.sale(tax_treatment="Exempt")
		invoice = self.sale(tax_treatment="Exempt", tax_reason="Fiktiv undervisning, mval. § 3-5")
		invoice.enk_tax_reason = ""
		with self.assertRaises(frappe.ValidationError):
			invoice.submit()

	def test_foreign_service_requires_supplier_country(self):
		with self.assertRaises(frappe.ValidationError):
			self.purchase(foreign_service=1, vat_rate="0")
		self.supplier.country = "United States"
		self.supplier.save()
		invoice = self.purchase(foreign_service=1, vat_rate="0")
		self.attach(invoice)
		self.supplier.country = "Norway"
		self.supplier.save()
		with self.assertRaises(frappe.ValidationError):
			invoice.submit()

	def test_native_purchase_cannot_change_private_allocation(self):
		self.settings.vat_registered = 1
		self.settings.vat_registration_date = "2026-01-01"
		self.settings.save()
		invoice = self.purchase(business_fraction="0.6", deductible_fraction="0.6")
		self.attach(invoice)
		invoice.items[-1].expense_account = self.settings.software_account
		with self.assertRaises(frappe.ValidationError):
			invoice.submit()

	def test_native_purchase_cannot_inflate_tax_basis(self):
		self.settings.vat_registered = 1
		self.settings.vat_registration_date = "2026-01-01"
		self.settings.save()
		invoice = self.purchase()
		self.attach(invoice)
		invoice.enk_vat_basis = 2000
		invoice.enk_deductible_fraction = 0.5
		with self.assertRaises(frappe.ValidationError):
			invoice.submit()

	def test_cancelled_external_event_is_not_reused(self):
		invoice = self.sale(external_id="cancelled-event")
		invoice.submit()
		invoice.cancel()
		with self.assertRaises(frappe.ValidationError):
			self.sale(external_id="cancelled-event")

	def test_full_credit_note_retry_and_duplicate_native_credit_are_rejected(self):
		from erpnext.controllers.sales_and_purchase_return import make_return_doc

		original = self.sale()
		original.submit()
		first = create_credit_note("Sales Invoice", original.name, "2026-09-18")
		retry = create_credit_note("Sales Invoice", original.name, "2026-09-18")
		self.assertEqual(first["name"], retry["name"])
		self.assertTrue(retry["reused"])
		frappe.get_doc("Sales Invoice", first["name"]).submit()
		with self.assertRaises(frappe.ValidationError):
			create_credit_note("Sales Invoice", original.name, "2026-09-18")
		duplicate = make_return_doc("Sales Invoice", original.name)
		duplicate.posting_date = "2026-09-18"
		duplicate.insert()
		with self.assertRaises(frappe.ValidationError):
			duplicate.submit()

	def test_native_partial_credits_cannot_exceed_original_line(self):
		from erpnext.controllers.sales_and_purchase_return import make_return_doc

		original = self.sale()
		original.submit()
		first = make_return_doc("Sales Invoice", original.name)
		first.posting_date = "2026-09-18"
		first.items[0].qty = -0.4
		first.insert()
		first.submit()
		second = make_return_doc("Sales Invoice", original.name)
		second.posting_date = "2026-09-18"
		self.assertEqual(second.items[0].qty, -0.6)
		second.insert()
		second.submit()
		over_credit = make_return_doc("Sales Invoice", original.name)
		over_credit.posting_date = "2026-09-18"
		over_credit.items[0].qty = -0.01
		over_credit.insert()
		with self.assertRaises(frappe.ValidationError):
			over_credit.submit()

	def test_purchase_credit_note_does_not_require_sales_deferral_field(self):
		purchase = self.purchase()
		self.attach(purchase)
		purchase.submit()
		credit = create_credit_note("Purchase Invoice", purchase.name, "2026-09-18")
		self.assertEqual(credit["doctype"], "Purchase Invoice")

	def test_native_asset_sale_and_perpetual_inventory_are_not_available_to_enk(self):
		from enk_norge.validation import validate_company_perpetual_inventory

		invoice = self.sale()
		invoice.items[0].is_fixed_asset = 1
		with self.assertRaises(frappe.ValidationError):
			invoice.submit()
		company = frappe.get_doc("Company", self.company)
		company.enable_perpetual_inventory = 1
		with self.assertRaises(frappe.ValidationError):
			validate_company_perpetual_inventory(company)

	def test_unsupported_native_accounting_drivers_are_hooked_for_enk(self):
		from enk_norge.validation import validate_subscription, validate_unsupported_native_accounting

		for doctype in ("Stock Entry", "POS Invoice", "Delivery Note", "Purchase Receipt"):
			self.assertIn(
				"enk_norge.validation.validate_unsupported_native_accounting",
				frappe.get_hooks("doc_events")[doctype]["before_submit"],
			)
			doc = frappe.new_doc(doctype)
			doc.company = self.company
			doc.posting_date = "2026-09-18"
			with self.assertRaises(frappe.ValidationError):
				validate_unsupported_native_accounting(doc)
		self.assertIn(
			"enk_norge.validation.validate_subscription",
			frappe.get_hooks("doc_events")["Subscription"]["before_insert"],
		)
		with self.assertRaises(frappe.ValidationError):
			validate_subscription(frappe._dict(company=self.company, submit_invoice=1))

	def test_private_payment_retry_and_conflicting_date(self):
		purchase = self.purchase()
		self.attach(purchase)
		purchase.submit()
		first = pay_purchase_privately(purchase.name, "2026-09-17")
		self.assertEqual(first["name"], pay_purchase_privately(purchase.name, "2026-09-17")["name"])
		with self.assertRaises(frappe.ValidationError):
			pay_purchase_privately(purchase.name, "2026-09-18")
		frappe.get_doc("Journal Entry", first["name"]).submit()
		self.assertEqual(first["name"], pay_purchase_privately(purchase.name, "2026-09-17")["name"])

	def test_generated_payment_cannot_change_financial_content(self):
		from enk_norge.banking import owner_transfer

		name = owner_transfer(self.company, "100", "2026-09-18", "Deposit", "Testinnskudd", "CONTRACT-1")[
			"name"
		]
		entry = frappe.get_doc("Journal Entry", name)
		entry.accounts[0].debit_in_account_currency = 200
		entry.accounts[1].credit_in_account_currency = 200
		with self.assertRaises(frappe.ValidationError):
			entry.submit()

	def test_manual_entry_requires_source_and_reason(self):
		entry = frappe.get_doc(
			dict(
				doctype="Journal Entry",
				company=self.company,
				posting_date="2026-09-18",
				accounts=[
					dict(account=self.settings.software_account, debit_in_account_currency=100),
					dict(account=self.settings.bank_ledger_account, credit_in_account_currency=100),
				],
			)
		).insert()
		with self.assertRaises(frappe.ValidationError):
			entry.submit()
		entry.reload()
		entry.enk_manual_reason = "Dokumentert korreksjon til test"
		entry.save()
		with self.assertRaises(frappe.ValidationError):
			entry.submit()
		entry.reload()
		self.attach(entry)
		entry.submit()

	def test_registered_zero_vat_purchase_requires_reason(self):
		self.settings.vat_registered = 1
		self.settings.vat_registration_date = "2026-01-01"
		self.settings.save()
		with self.assertRaises(frappe.ValidationError):
			self.purchase(vat_rate="0")
		invoice = self.purchase(vat_rate="0", tax_reason="Fiktiv leverandør er ikke MVA-registrert")
		self.attach(invoice)
		invoice.submit()
		self.assertEqual(invoice.enk_tax_treatment, "No input VAT")

	def test_posted_setup_identity_and_mapping_are_preserved(self):
		self.sale().submit()
		self.settings.bank_account = "86011117963"
		with self.assertRaises(frappe.ValidationError):
			self.settings.save()
		self.settings.reload()
		self.settings.accounts[0].grouping_code = "1500"
		with self.assertRaises(frappe.ValidationError):
			self.settings.save()

	def test_company_user_permission_applies_to_endpoints(self):
		other = create_company(
			dict(
				company_name="Annet tilgangstestforetak " + uuid4().hex[:8],
				abbr=uuid4().hex[:5].upper(),
				organization_number=_mod11("12345678", (3, 2, 7, 6, 5, 4, 3, 2)),
				bank_account=_mod11("8601111795", (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)),
				start_date="2026-01-01",
				address_line="Testveien 2",
				postal_code="0001",
				city="Oslo",
				phone="00000000",
				bank_name="Testbank",
				history_confirmed=1,
			)
		)["company"]
		user = frappe.get_doc(
			dict(
				doctype="User",
				email=f"enk-test-{uuid4().hex}@example.invalid",
				first_name="Tilgangstest",
				send_welcome_email=0,
				roles=[dict(role="Accounts User")],
			)
		).insert()
		frappe.get_doc(
			dict(
				doctype="User Permission",
				user=user.name,
				allow="Company",
				for_value=self.company,
				apply_to_all_doctypes=1,
			)
		).insert()
		frappe.set_user(user.name)
		self.assertEqual(get_settings(self.company).company, self.company)
		self.assertIn(self.company, [row["company"] for row in list_companies()])
		self.assertNotIn(other, [row["company"] for row in list_companies()])
		with self.assertRaises(frappe.PermissionError):
			get_settings(other)
		with self.assertRaises(frappe.PermissionError):
			dashboard(other)
		with self.assertRaises(frappe.PermissionError):
			get_settings(self.company, write=True)


def run():
	if frappe.local.site != "test.localhost":
		raise RuntimeError("Kun test.localhost kan kjøre disse integrasjonstestene.")
	result = unittest.TextTestRunner(verbosity=2).run(
		unittest.defaultTestLoader.loadTestsFromTestCase(AccessTest)
	)
	frappe.db.rollback()
	if not result.wasSuccessful():
		raise RuntimeError("ENK-tilgangstestene feilet.")
	return {"tests": result.testsRun, "successful": True}
