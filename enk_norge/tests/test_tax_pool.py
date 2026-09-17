"""Saldogrupper skal bygge på faktiske aktiveringer, uten dobbel bruk av bilag."""

import json
import unittest

import frappe

from enk_norge.tests.test_workflows import WorkflowsTest


class TaxPoolSourceTest(unittest.TestCase):
	setUp = WorkflowsTest.setUp
	attach = WorkflowsTest.attach
	purchase = WorkflowsTest.purchase

	def asset_source(self):
		entry = frappe.get_doc(
			dict(
				doctype="Journal Entry",
				company=self.company,
				posting_date="2026-09-17",
				enk_manual_reason="Dokumentert innskudd av utstyr til test",
				accounts=[
					dict(account=self.settings.asset_account, debit_in_account_currency=30000),
					dict(account=self.settings.owner_account, credit_in_account_currency=30000),
				],
			)
		).insert()
		self.attach(entry)
		entry.submit()
		return entry

	def pool(self, source, group, amount):
		return frappe.get_doc(
			dict(
				doctype="ENK Tax Pool",
				company=self.company,
				income_year=2026,
				saldo_group=group,
				opening_balance=0,
				acquisitions=amount,
				acquisition_sources_json=json.dumps(
					[dict(doctype=source.doctype, name=source.name, amount=str(amount))]
				),
			)
		)

	def test_source_amount_must_be_booked_as_asset(self):
		source = self.asset_source()
		with self.assertRaises(frappe.ValidationError):
			self.pool(source, "a", 31000).insert()
		expense = self.purchase()
		self.attach(expense)
		expense.submit()
		with self.assertRaises(frappe.ValidationError):
			self.pool(expense, "a", 1250).insert()

	def test_source_can_be_split_but_not_counted_twice(self):
		source = self.asset_source()
		self.pool(source, "a", 20000).insert()
		second = self.pool(source, "d", 10000).insert()
		second.acquisitions = 20000
		second.acquisition_sources_json = json.dumps(
			[dict(doctype=source.doctype, name=source.name, amount="20000")]
		)
		with self.assertRaises(frappe.ValidationError):
			second.save()

	def test_cancelled_acquisition_cannot_remain_in_annual_deduction(self):
		from enk_norge.year_end import build_year_report

		source = self.asset_source()
		self.pool(source, "a", 30000).insert()
		source.cancel()
		with self.assertRaises(frappe.ValidationError):
			build_year_report(self.company)

	def test_opening_balance_requires_private_preserved_source(self):
		pool = frappe.get_doc(
			dict(
				doctype="ENK Tax Pool",
				company=self.company,
				income_year=2026,
				saldo_group="a",
				opening_balance=30000,
				acquisitions=0,
			)
		)
		with self.assertRaises(frappe.ValidationError):
			pool.insert()
		proof = frappe.get_doc(
			dict(
				doctype="File",
				file_name="tidligere-saldo.txt",
				content="Fiktivt saldooppgjor 2025: 30000",
				is_private=1,
			)
		).insert()
		pool.opening_source_file = proof.name
		pool.insert()
		self.assertTrue(pool.source_hash)
		with self.assertRaises(frappe.ValidationError):
			proof.delete()
