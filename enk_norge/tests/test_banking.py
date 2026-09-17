"""Bankimport og betalingsnøkler på test.localhost."""

import unittest
from datetime import date

import frappe

from enk_norge.banking import BankingError, _key_and_fingerprint, _parse_bank_csv, _row_hash


class BankCsvContractTest(unittest.TestCase):
	def test_row_hash_includes_description(self):
		first = _row_hash("bank-1", date(2026, 9, 17), 100, "Første tekst")
		second = _row_hash("bank-1", date(2026, 9, 17), 100, "Endret tekst")
		self.assertNotEqual(first, second)

	def test_csv_rejects_duplicate_transaction_id(self):
		content = (
			"transaction_id,date,amount,currency,description\n"
			"bank-1,2026-09-17,100.00,NOK,Første\n"
			"bank-1,2026-09-17,100.00,NOK,Gjentatt\n"
		)
		with self.assertRaisesRegex(BankingError, "flere ganger"):
			_parse_bank_csv(content, date(2026, 1, 1))

	def test_payment_key_is_stable_but_fingerprint_catches_changed_fee(self):
		base = dict(
			amount="100.00",
			category="invoice-payment",
			company="Fiktivt ENK",
			fee="0.00",
			invoice="Sales Invoice:SINV-1",
			posting_date="2026-09-17",
			reference="BANK-1",
		)
		key, fingerprint = _key_and_fingerprint("invoice-payment", base)
		changed_key, changed_fingerprint = _key_and_fingerprint(
			"invoice-payment", base | {"fee": "5.00"}
		)
		self.assertEqual(key, changed_key)
		self.assertNotEqual(fingerprint, changed_fingerprint)
		changed_date_key, changed_date_fingerprint = _key_and_fingerprint(
			"invoice-payment", base | {"posting_date": "2026-09-18"}
		)
		self.assertEqual(key, changed_date_key)
		self.assertNotEqual(fingerprint, changed_date_fingerprint)


@unittest.skipUnless(frappe.db.exists("DocType", "ENK Bank Import"), "Krever migrert ENK Bank Import")
class BankWorkflowTest(unittest.TestCase):
	def setUp(self):
		from enk_norge.tests.test_workflows import WorkflowsTest

		self.workflows = WorkflowsTest
		WorkflowsTest.setUp(self)

	def bank_file(self, content):
		return frappe.get_doc(
			dict(doctype="File", file_name="bank.csv", is_private=1, content=content)
		).insert()

	def test_import_archives_source_and_reuses_exact_source(self):
		from enk_norge.banking import import_bank_csv

		file = self.bank_file(
			"transaction_id,date,amount,currency,description\n"
			"bank-1,2026-09-18,9975.00,NOK,Fiktiv betaling\n"
		)
		first = import_bank_csv(self.company, file.file_url)
		batch = frappe.get_doc("ENK Bank Import", first["batch"])
		file.reload()
		transaction = frappe.get_doc("Bank Transaction", first["created"][0])
		self.assertEqual(batch.docstatus, 1)
		self.assertEqual(batch.import_status, "Imported")
		self.assertEqual(file.attached_to_doctype, "ENK Bank Import")
		self.assertEqual(file.attached_to_name, batch.name)
		self.assertEqual(transaction.enk_bank_import, batch.name)
		self.assertEqual(len(transaction.enk_row_hash), 64)
		second = import_bank_csv(self.company, file.file_url)
		self.assertEqual(second["batch"], batch.name)
		self.assertEqual(second["created"], [])
		self.assertEqual(second["reused"], first["created"])
		with self.assertRaises(frappe.ValidationError):
			batch.cancel()
		with self.assertRaises(frappe.ValidationError):
			file.delete()

	def test_changed_description_for_known_bank_id_fails_closed(self):
		from enk_norge.banking import import_bank_csv

		first = self.bank_file(
			"transaction_id,date,amount,currency,description\n"
			"bank-1,2026-09-18,100.00,NOK,Første tekst\n"
		)
		import_bank_csv(self.company, first.file_url)
		changed = self.bank_file(
			"transaction_id,date,amount,currency,description\n"
			"bank-1,2026-09-18,100.00,NOK,Endret tekst\n"
		)
		with self.assertRaisesRegex(frappe.ValidationError, "andre opplysninger"):
			import_bank_csv(self.company, changed.file_url)

	def test_payment_and_owner_transfer_are_idempotent(self):
		from enk_norge.banking import create_payment, owner_transfer

		invoice = self.workflows.sale(self)
		invoice.submit()
		first = create_payment("Sales Invoice", invoice.name, "10000", "2026-09-18", "BANK-1")
		second = create_payment("Sales Invoice", invoice.name, "10000", "2026-09-18", "BANK-1")
		self.assertEqual(first["name"], second["name"])
		self.assertTrue(second["reused"])
		with self.assertRaisesRegex(frappe.ValidationError, "andre opplysninger"):
			create_payment("Sales Invoice", invoice.name, "10000", "2026-09-18", "BANK-1", "25")
		with self.assertRaisesRegex(frappe.ValidationError, "andre opplysninger"):
			create_payment("Sales Invoice", invoice.name, "10000", "2026-09-19", "BANK-1")
		owner = owner_transfer(
			self.company, "100", "2026-09-18", "Deposit", "Privat innskudd", "OWNER-1"
		)
		owner_again = owner_transfer(
			self.company, "100", "2026-09-18", "Deposit", "Privat innskudd", "OWNER-1"
		)
		self.assertEqual(owner["name"], owner_again["name"])
		self.assertEqual(frappe.get_doc("Journal Entry", owner["name"]).cheque_no, "OWNER-1")
		with self.assertRaisesRegex(frappe.ValidationError, "andre opplysninger"):
			owner_transfer(self.company, "101", "2026-09-18", "Deposit", "Privat innskudd", "OWNER-1")
		with self.assertRaisesRegex(frappe.ValidationError, "andre opplysninger"):
			owner_transfer(self.company, "100", "2026-09-19", "Deposit", "Privat innskudd", "OWNER-1")

	def test_cancelled_payment_keys_are_not_reused(self):
		from enk_norge.banking import create_payment, owner_transfer

		invoice = self.workflows.sale(self)
		invoice.submit()
		payment = frappe.get_doc(
			"Payment Entry",
			create_payment("Sales Invoice", invoice.name, "10000", "2026-09-18", "BANK-CANCEL")["name"],
		)
		payment.submit()
		payment.cancel()
		with self.assertRaisesRegex(frappe.ValidationError, "annullert bilag"):
			create_payment("Sales Invoice", invoice.name, "10000", "2026-09-18", "BANK-CANCEL")

		owner = frappe.get_doc(
			"Journal Entry",
			owner_transfer(self.company, "100", "2026-09-18", "Deposit", "Annullert eier", "OWNER-CANCEL")[
				"name"
			],
		)
		owner.submit()
		owner.cancel()
		with self.assertRaisesRegex(frappe.ValidationError, "annullert bilag"):
			owner_transfer(self.company, "100", "2026-09-18", "Deposit", "Annullert eier", "OWNER-CANCEL")


	def test_december_income_is_not_repeated_when_paid_in_january(self):
		from enk_norge.banking import create_payment

		invoice = self.workflows.sale(self, posting_date="2026-12-20", delivery_date="2026-12-20", due_date="2027-01-10")
		invoice.submit()
		payment = frappe.get_doc("Payment Entry", create_payment(
			"Sales Invoice", invoice.name, "10000", "2027-01-05", "JAN-PAYMENT"
		)["name"])
		payment.submit()
		invoice.reload()
		self.assertEqual(invoice.outstanding_amount, 0)
		rows = frappe.get_all("GL Entry", filters={"company":self.company, "is_cancelled":0}, fields=["account", "posting_date", "debit", "credit"])
		income = [row for row in rows if row.account == self.settings.income_account]
		bank = [row for row in rows if row.account == self.settings.bank_ledger_account]
		self.assertEqual(sum(row.credit-row.debit for row in income), 10000)
		self.assertTrue(all(row.posting_date.year == 2026 for row in income))
		self.assertEqual(sum(row.debit-row.credit for row in bank), 10000)
		self.assertTrue(all(row.posting_date.year == 2027 for row in bank))
		self.assertTrue(create_payment("Sales Invoice", invoice.name, "10000", "2027-01-05", "JAN-PAYMENT")["reused"])
