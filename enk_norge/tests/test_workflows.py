"""Virkelige Frappe-dokumenter og hovedbok på et separat testsite."""

import unittest
from unittest.mock import patch
from uuid import uuid4

import frappe
from frappe.boot import add_home_page

from enk_norge.api import create_purchase, create_sale, pay_purchase_privately
from enk_norge.setup import create_company, get_settings, repair_completed_setup_home_page


class WorkflowsTest(unittest.TestCase):
	def setUp(self):
		self.previous_user = frappe.session.user
		frappe.set_user("Administrator")
		frappe.db.savepoint("enk_test")
		self.addCleanup(frappe.db.rollback, save_point="enk_test")
		self.addCleanup(frappe.set_user, self.previous_user)
		self.company = create_company(
			dict(
				company_name="Fiktivt ENK " + uuid4().hex[:8],
				abbr=uuid4().hex[:5].upper(),
				organization_number="974761076",
				bank_account="86011117947",
				start_date="2026-01-01",
				address_line="Testveien 1",
				postal_code="0001",
				city="Oslo",
				phone="00000000",
				bank_name="Fiktiv testbank",
				vat_registered=0,
				history_confirmed=1,
			)
		)["company"]
		self.settings = get_settings(self.company)
		self.customer = frappe.get_doc(
			dict(
				doctype="Customer",
				customer_name="Fiktiv kunde " + uuid4().hex[:8],
				customer_type="Company",
				customer_group="Commercial",
				territory="Norway",
			)
		).insert()
		self.address = frappe.get_doc(
			dict(
				doctype="Address",
				address_title=self.customer.name,
				address_type="Billing",
				address_line1="Kundeveien 1",
				city="Oslo",
				pincode="0001",
				country="Norway",
				links=[dict(link_doctype="Customer", link_name=self.customer.name)],
			)
		).insert()
		self.supplier = frappe.get_doc(
			dict(
				doctype="Supplier",
				supplier_name="Fiktiv leverandør " + uuid4().hex[:8],
				supplier_group="Services",
				supplier_type="Company",
			)
		).insert()

	def tearDown(self):
		pass

	def sale(self, **overrides):
		data = dict(
			company=self.company,
			customer=self.customer.name,
			customer_address=self.address.name,
			posting_date="2026-09-17",
			delivery_date="2026-09-17",
			due_date="2026-10-01",
			description="Fiktivt programvareprodukt",
			quantity="1",
			unit_price="10000",
		)
		data.update(overrides)
		return frappe.get_doc("Sales Invoice", create_sale(data)["name"])

	def purchase(self, **overrides):
		data = dict(
			company=self.company,
			supplier=self.supplier.name,
			posting_date="2026-09-17",
			bill_date="2026-09-17",
			bill_no="TEST-1",
			description="Programvare",
			category="software",
			gross_amount="1250",
			vat_rate="25",
		)
		data.update(overrides)
		return frappe.get_doc("Purchase Invoice", create_purchase(data)["name"])

	def attach(self, doc):
		frappe.get_doc(
			dict(
				doctype="File",
				file_name="testbilag.txt",
				content="Fiktivt bilag for test",
				is_private=1,
				attached_to_doctype=doc.doctype,
				attached_to_name=doc.name,
			)
		).insert()

	def test_completed_setup_repairs_wizard_home_page_for_boot(self):
		frappe.db.set_default("desktop:home_page", "setup-wizard")
		frappe.clear_cache()
		with patch.object(frappe, "is_setup_complete", return_value=True):
			self.assertTrue(repair_completed_setup_home_page())

		bootinfo = frappe._dict()
		docs = []
		add_home_page(bootinfo, docs)

		self.assertEqual(bootinfo.home_page, "enk-norge")
		self.assertEqual(docs[0].name, "enk-norge")

	def test_sale_no_vat_and_receivable(self):
		doc = self.sale()
		doc.submit()
		self.assertEqual(doc.grand_total, 10000)
		rows = frappe.get_all(
			"GL Entry",
			filters={"voucher_type": doc.doctype, "voucher_no": doc.name},
			fields=["debit", "credit"],
		)
		self.assertEqual(sum(r.debit for r in rows), 10000)
		self.assertEqual(sum(r.credit for r in rows), 10000)

	def test_purchase_attachment_and_private_payment(self):
		doc = self.purchase()
		with self.assertRaises(frappe.ValidationError):
			doc.submit()
		doc.reload()
		self.attach(doc)
		doc.submit()
		self.assertEqual(doc.grand_total, 1250)
		self.assertEqual(doc.items[0].amount, 1250)
		entry = frappe.get_doc("Journal Entry", pay_purchase_privately(doc.name, "2026-09-17")["name"])
		entry.submit()
		doc.reload()
		self.assertEqual(doc.outstanding_amount, 0)
		self.assertEqual(
			frappe.db.get_value(
				"GL Entry", {"voucher_no": entry.name, "account": self.settings.owner_account}, "credit"
			),
			1250,
		)

	def test_registered_purchase_and_sale(self):
		self.settings.vat_registered = 1
		self.settings.vat_registration_date = "2026-01-01"
		self.settings.save()
		sale = self.sale()
		sale.submit()
		self.assertEqual(sale.grand_total, 12500)
		purchase = self.purchase()
		self.attach(purchase)
		purchase.submit()
		self.assertEqual(purchase.grand_total, 1250)
		self.assertEqual(purchase.items[0].amount, 1000)

	def test_closed_period_and_duplicate(self):
		doc = self.sale(external_id="fake-event-" + uuid4().hex)
		self.settings.frozen_through = "2026-09-30"
		self.settings.save()
		with self.assertRaises(frappe.ValidationError):
			doc.submit()
		self.purchase()
		with self.assertRaises(frappe.ValidationError):
			self.purchase()

	def test_bank_file_idempotency_and_sale_payment(self):
		from enk_norge.banking import create_payment, import_bank_csv

		doc = self.sale()
		doc.submit()
		payment = frappe.get_doc(
			"Payment Entry",
			create_payment("Sales Invoice", doc.name, "10000", "2026-09-18", "FIKTIV-PAY", "25")["name"],
		)
		payment.submit()
		doc.reload()
		self.assertEqual(doc.outstanding_amount, 0)
		self.assertEqual(
			frappe.db.get_value(
				"GL Entry",
				{"voucher_no": payment.name, "account": self.settings.bank_ledger_account},
				"debit",
			),
			9975,
		)
		file = frappe.get_doc(
			dict(
				doctype="File",
				file_name="bank.csv",
				is_private=1,
				content="transaction_id,date,amount,currency,description\nfake1,2026-09-18,9975.00,NOK,Fiktiv betaling\n",
			)
		).insert()
		first = import_bank_csv(self.company, file.file_url)
		second = import_bank_csv(self.company, file.file_url)
		self.assertEqual(len(first["created"]), 1)
		self.assertEqual(second["created"], [])
		self.assertEqual(second["reused"], first["created"])

	def test_vat_threshold_and_server_tax_guard(self):
		first = self.sale(unit_price="45000")
		first.submit()
		crossing = self.sale(unit_price="10000")
		with self.assertRaisesRegex(frappe.ValidationError, "50 000"):
			crossing.submit()
		crossing.reload()
		crossing.enk_vat_registration_pending = 1
		crossing.save()
		crossing.submit()
		self.assertEqual(crossing.grand_total, 10000)
		self.settings.vat_registered = 1
		self.settings.vat_registration_date = "2026-09-17"
		self.settings.save()
		tampered = self.sale(unit_price="1000")
		tampered.taxes[0].rate = 0
		tampered.save()
		with self.assertRaisesRegex(frappe.ValidationError, "MVA-beløpet"):
			tampered.submit()

	def test_invoice_print_and_attachment_retention(self):
		doc = self.sale()
		doc.submit()
		html = frappe.get_print(doc.doctype, doc.name, print_format="ENK Faktura")
		self.assertIn("8601.11.17947", html)
		self.assertIn("974 761 076", html)
		self.assertIn("Leveringsdato", html)
		purchase = self.purchase()
		self.attach(purchase)
		purchase.submit()
		file = frappe.get_doc(
			"File", {"attached_to_doctype": purchase.doctype, "attached_to_name": purchase.name}
		)
		with self.assertRaises(frappe.ValidationError):
			file.delete()

	def test_private_share_is_not_business_expense(self):
		self.settings.vat_registered = 1
		self.settings.vat_registration_date = "2026-01-01"
		self.settings.save()
		doc = self.purchase(business_fraction="0.6", deductible_fraction="0.6")
		self.attach(doc)
		doc.submit()
		self.assertEqual(doc.grand_total, 1250)
		self.assertEqual(
			frappe.db.get_value(
				"GL Entry", {"voucher_no": doc.name, "account": self.settings.software_account}, "debit"
			),
			600,
		)
		self.assertEqual(
			frappe.db.get_value(
				"GL Entry", {"voucher_no": doc.name, "account": self.settings.withdrawal_account}, "debit"
			),
			500,
		)
		self.assertEqual(
			frappe.db.get_value(
				"GL Entry", {"voucher_no": doc.name, "account": self.settings.input_vat_account}, "debit"
			),
			150,
		)

	def test_credit_note_and_vat_registration_correction(self):
		from enk_norge.api import create_credit_note, dashboard

		original = self.sale()
		original.enk_vat_registration_pending = 1
		original.submit()
		self.assertEqual(len(dashboard(self.company)["vat_followup"]), 1)
		self.settings.vat_registered = 1
		self.settings.vat_registration_date = "2026-09-17"
		self.settings.save()
		credit = frappe.get_doc(
			"Sales Invoice", create_credit_note("Sales Invoice", original.name, "2026-09-18")["name"]
		)
		credit.submit()
		self.assertEqual(credit.grand_total, -10000)
		self.assertEqual(credit.total_taxes_and_charges, 0)
		self.assertEqual(credit.return_against, original.name)
		self.assertEqual(dashboard(self.company)["vat_followup"], [])
		self.assertTrue(frappe.parse_json(credit.enk_invoice_snapshot)["vat_registered"])
		replacement = self.sale()
		replacement.submit()
		self.assertEqual(replacement.grand_total, 12500)


def run():
	if frappe.local.site != "test.localhost":
		raise RuntimeError("Kun test.localhost kan kjøre disse integrasjonstestene.")
	result = unittest.TextTestRunner(verbosity=2).run(
		unittest.defaultTestLoader.loadTestsFromTestCase(WorkflowsTest)
	)
	frappe.db.rollback()
	if not result.wasSuccessful():
		raise RuntimeError("ENK-integrasjonstestene feilet.")
	return {"tests": result.testsRun, "successful": True}
