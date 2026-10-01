"""SAF-T mot faktiske ERPNext-bilag på test.localhost."""

from datetime import date
from decimal import Decimal
from unittest import TestCase
from uuid import uuid4

import frappe
from lxml import etree

from enk_norge.saft import NS, _frappe_export_data, build_saf_t, export_saf_t, validate_saf_t
from enk_norge.setup import create_company, get_settings
from enk_norge.tests import test_workflows
from enk_norge.vat import create_reverse_charge_draft


def _mod11(prefix, weights):
	check = 11 - sum(int(value) * weight for value, weight in zip(prefix, weights, strict=True)) % 11
	if check == 11:
		return prefix + "0"
	if check == 10:
		raise ValueError("Ugyldig kontrollsiffer.")
	return prefix + str(check)


class TestSaftIntegration(TestCase):
	def setUp(self):
		test_workflows.WorkflowsTest.setUp(self)

	def sale(self, **overrides):
		return test_workflows.WorkflowsTest.sale(self, **overrides)

	def purchase(self, **overrides):
		return test_workflows.WorkflowsTest.purchase(self, **overrides)

	def attach(self, doc):
		return test_workflows.WorkflowsTest.attach(self, doc)

	def journal_entry(self, posting_date, amount):
		doc = frappe.get_doc(dict(
			doctype="Journal Entry",
			company=self.company,
			posting_date=posting_date,
			user_remark="Fiktivt SAF-T-bilag",
			enk_manual_reason="Fiktivt innskudd med kildebilag for eksporttest",
			accounts=[
				dict(account=self.settings.bank_ledger_account, debit_in_account_currency=amount),
				dict(account=self.settings.owner_account, credit_in_account_currency=amount),
			],
		))
		doc.insert()
		self.attach(doc)
		doc.submit()
		return doc

	def test_adapter_exports_company_ledger_and_opening_balance(self):
		opening = self.journal_entry("2026-08-31", 500)
		sale = self.sale()
		sale.submit()
		cancelled = self.journal_entry("2026-09-18", 125)
		cancelled.cancel()

		# Uforanderlig hovedbok fører tilbakeføringen på annulleringsdagen. Perioden må derfor
		# dekke dagens dato, ellers avhenger testen av når den kjøres.
		start, end = date(2026, 9, 1), date(2026, 12, 31)
		data = _frappe_export_data(self.company, start, end)
		active_rows = frappe.get_all(
			"GL Entry",
			filters={"company": self.company, "posting_date": ["<=", end], "is_cancelled": 0},
			fields=["name", "debit", "credit"],
		)
		cancelled_rows = frappe.get_all(
			"GL Entry", filters={"voucher_no": cancelled.name, "is_cancelled": 1}, fields=["name"]
		)
		self.assertEqual({entry.record_id for entry in data.entries}, {row.name for row in active_rows})
		self.assertFalse({row.name for row in cancelled_rows} & {entry.record_id for entry in data.entries})
		cancelled_entries = [entry for entry in data.entries if entry.voucher_no == cancelled.name]
		self.assertEqual(len(cancelled_rows), 0)
		self.assertEqual(len(cancelled_entries), 4)
		self.assertEqual(sum((entry.debit for entry in cancelled_entries), Decimal()), Decimal("250"))
		self.assertEqual(sum((entry.credit for entry in cancelled_entries), Decimal()), Decimal("250"))
		self.assertEqual(sum((entry.debit for entry in data.entries), Decimal()), sum((Decimal(str(row.debit)) for row in active_rows), Decimal()))
		self.assertEqual(sum((entry.credit for entry in data.entries), Decimal()), sum((Decimal(str(row.credit)) for row in active_rows), Decimal()))

		xml = build_saf_t(data)
		validate_saf_t(xml)
		root = etree.fromstring(xml)
		ns = {"s": NS}
		bank_id = frappe.db.get_value("Account", self.settings.bank_ledger_account, "account_number")
		self.assertEqual(root.xpath(f"string(.//s:Account[s:AccountID='{bank_id}']/s:OpeningDebitBalance)", namespaces=ns), "500.00")
		period_entries = [entry for entry in data.entries if start <= entry.posting_date <= end]
		transaction_count = len({(entry.voucher_type, entry.voucher_no, entry.posting_date) for entry in period_entries})
		self.assertEqual(root.xpath("string(.//s:GeneralLedgerEntries/s:NumberOfEntries)", namespaces=ns), str(transaction_count))
		self.assertEqual(root.xpath("string(.//s:GeneralLedgerEntries/s:TotalDebit)", namespaces=ns), f"{sum((entry.debit for entry in period_entries), Decimal()):.2f}")
		self.assertEqual(root.xpath("string(.//s:GeneralLedgerEntries/s:TotalCredit)", namespaces=ns), f"{sum((entry.credit for entry in period_entries), Decimal()):.2f}")
		self.assertIn(opening.name, {entry.voucher_no for entry in data.entries})

	def test_adapter_maps_native_invoice_tax(self):
		self.settings.vat_registered = 1
		self.settings.vat_registration_date = "2026-01-01"
		self.settings.save()
		sale = self.sale()
		sale.submit()
		purchase = self.purchase()
		self.attach(purchase)
		purchase.submit()

		data = _frappe_export_data(self.company, date(2026, 9, 1), date(2026, 9, 30))
		self.assertEqual(set(data.tax_mappings), {"1", "3"})
		self.assertEqual({entry.tax_code for entry in data.entries if entry.tax_code}, {"1", "3"})
		root = etree.fromstring(build_saf_t(data))
		ns = {"s": NS}
		self.assertEqual(root.xpath("string(.//s:TaxCodeDetails[s:TaxCode='3']/s:StandardTaxCode)", namespaces=ns), "3")
		self.assertEqual(root.xpath("string(.//s:TaxCodeDetails[s:TaxCode='1']/s:StandardTaxCode)", namespaces=ns), "1")

	def test_adapter_maps_partially_deductible_purchase_tax(self):
		self.settings.vat_registered = 1
		self.settings.vat_registration_date = "2026-01-01"
		self.settings.save()
		purchase = self.purchase(deductible_fraction="0.6")
		self.attach(purchase)
		purchase.submit()

		data = _frappe_export_data(self.company, date(2026, 9, 1), date(2026, 9, 30))
		tax_entry = next(entry for entry in data.entries if entry.tax_code == "1")
		self.assertEqual(tax_entry.debit, Decimal("150"))
		self.assertEqual(tax_entry.tax_base, Decimal("1000"))
		root = etree.fromstring(build_saf_t(data))
		ns = {"s": NS}
		self.assertEqual(root.xpath("string(.//s:TaxInformation/s:TaxBase)", namespaces=ns), "1000.00")

	def test_adapter_maps_partially_deductible_reverse_charge(self):
		self.supplier.country = "United States"
		self.supplier.save()
		self.settings.vat_registered = 1
		self.settings.vat_registration_date = "2026-01-01"
		self.settings.save()
		purchase = self.purchase(foreign_service=1, vat_rate="0", gross_amount="1000", deductible_fraction="0.6")
		self.attach(purchase)
		purchase.submit()
		draft = frappe.get_doc("Journal Entry", create_reverse_charge_draft(self.company, "2026-10-31")["name"])
		draft.submit()

		data = _frappe_export_data(self.company, date(2026, 9, 1), date(2026, 10, 31))
		self.assertEqual(set(data.tax_mappings), {"86", "87"})
		reverse = next(entry for entry in data.entries if entry.account == self.settings.reverse_vat_account)
		self.assertEqual([(item.code, item.tax_base, item.tax_amount) for item in reverse.tax_information], [
			("86", Decimal("600"), Decimal("150")),
			("87", Decimal("400"), Decimal("100")),
		])
		root = etree.fromstring(build_saf_t(data))
		ns = {"s": NS}
		self.assertEqual(root.xpath("string(.//s:TaxInformation[s:TaxCode='86']/s:TaxBase)", namespaces=ns), "600.00")
		self.assertEqual(root.xpath("string(.//s:TaxInformation[s:TaxCode='87']/s:TaxBase)", namespaces=ns), "400.00")

	def test_adapter_isolates_companies(self):
		other_company = create_company(dict(
			company_name="Andre fiktive SAF-T ENK " + uuid4().hex[:8],
			abbr=uuid4().hex[:5].upper(),
			organization_number=_mod11("12345678", (3, 2, 7, 6, 5, 4, 3, 2)),
			bank_account=_mod11("8601111795", (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)),
			start_date="2026-01-01",
			address_line="Annen testvei 1",
			postal_code="0001",
			city="Oslo",
			phone="00000000",
			bank_name="Andre fiktive testbank",
			vat_registered=0,
			history_confirmed=1,
		))["company"]
		other_settings = get_settings(other_company)
		journal = frappe.get_doc(dict(
			doctype="Journal Entry",
			company=other_company,
			posting_date="2026-09-17",
			enk_manual_reason="Fiktivt innskudd i separat foretak",
			accounts=[
				dict(account=other_settings.bank_ledger_account, debit_in_account_currency=200),
				dict(account=other_settings.owner_account, credit_in_account_currency=200),
			],
		)).insert()
		self.attach(journal)
		journal.submit()

		data = _frappe_export_data(self.company, date(2026, 9, 1), date(2026, 9, 30))
		other_rows = frappe.get_all("GL Entry", filters={"voucher_no": journal.name}, pluck="name")
		self.assertFalse(set(other_rows) & {entry.record_id for entry in data.entries})
		self.assertFalse(data.entries)

	def test_endpoint_requires_accounting_role(self):
		with self.assertRaises(frappe.PermissionError):
			frappe.set_user("Guest")
			export_saf_t(self.company, "2026-09-01", "2026-09-30")
		frappe.set_user("Administrator")
		export_saf_t(self.company, "2026-09-01", "2026-09-30")
		self.assertTrue(frappe.response.filename.startswith("SAF-T_"))
		self.assertEqual(frappe.response.type, "download")
