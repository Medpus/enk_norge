"""Oppgjør fra betalingsformidler mot bokførte salg, kreditnotaer og mellomkonto."""

import unittest
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from enk_norge.settlement import SettlementError, _settlement_payload

try:
	import frappe

	from enk_norge.tests.test_workflows import WorkflowsTest
except ModuleNotFoundError:
	frappe = None
	WorkflowsTest = None


SettlementWorkflowBase = WorkflowsTest or TestCase


class SettlementContractTest(unittest.TestCase):
	def test_payload_reconciles_gross_refunds_fee_and_net(self):
		payload = _settlement_payload(
			{
				"company": "Fiktivt ENK",
				"currency": "NOK",
				"external_settlement_id": "PAY-1",
				"merchant_of_record": "Direct seller",
				"posting_date": "2026-09-18",
				"invoices": [{"name": "SINV-2", "amount": "200"}, {"name": "SINV-1", "amount": "100"}],
				"credit_notes": [{"name": "SINV-CN-1", "amount": "25"}],
				"fee": "5",
				"net_amount": "270",
			},
			"a" * 64,
		)
		self.assertEqual([row["name"] for row in payload["invoices"]], ["SINV-1", "SINV-2"])
		self.assertEqual(payload["gross_amount"], "300.00")
		self.assertEqual(payload["refund_amount"], "25.00")

	def test_payload_rejects_unknown_seller_or_unreconciled_total(self):
		data = dict(
			company="Fiktivt ENK",
			currency="NOK",
			external_settlement_id="PAY-1",
			merchant_of_record="Unknown",
			posting_date="2026-09-18",
			invoices=[{"name": "SINV-1", "amount": "100"}],
			fee="0",
			net_amount="100",
		)
		with self.assertRaisesRegex(SettlementError, "direkte selger"):
			_settlement_payload(data, "a" * 64)
		with self.assertRaisesRegex(SettlementError, "Brutto salg"):
			_settlement_payload(data | {"merchant_of_record": "Direct seller", "net_amount": "99"}, "a" * 64)


@unittest.skipUnless(
	bool(frappe and frappe.db.exists("DocType", "ENK Settlement")), "Krever migrert ENK Settlement"
)
class SettlementWorkflowTest(SettlementWorkflowBase):
	def setUp(self):
		super().setUp()

	def source_file(self, content="oppgjør PAY-1"):
		return frappe.get_doc(
			dict(doctype="File", file_name="settlement.txt", content=content, is_private=1)
		).insert()

	def sales_and_credit(self):
		from enk_norge.api import create_credit_note

		first = self.sale(unit_price="1000")
		second = self.sale(unit_price="2000")
		first.submit()
		second.submit()
		credit = frappe.get_doc(
			"Sales Invoice", create_credit_note("Sales Invoice", first.name, "2026-09-18")["name"]
		)
		credit.submit()
		return first, second, credit

	def data(self, first, second, credit, source, **overrides):
		result = dict(
			company=self.company,
			currency="NOK",
			external_settlement_id="PAY-" + uuid4().hex[:12],
			merchant_of_record="Direct seller",
			posting_date="2026-09-18",
			source_file=source.name,
			invoices=[{"name": first.name, "amount": "1000"}, {"name": second.name, "amount": "2000"}],
			credit_notes=[{"name": credit.name, "amount": "1000"}],
			fee="100",
			net_amount="1900",
		)
		result.update(overrides)
		return result

	def test_draft_settlement_clears_invoices_and_reconciles_clearing(self):
		from enk_norge.settlement import create_settlement

		first, second, credit = self.sales_and_credit()
		source = self.source_file()
		result = create_settlement(self.data(first, second, credit, source))
		entry = frappe.get_doc("Journal Entry", result["name"])
		settlement = frappe.get_doc("ENK Settlement", result["settlement"])
		source.reload()
		self.assertEqual(entry.docstatus, 0)
		self.assertTrue(entry.enk_posting_contract)
		self.assertEqual(settlement.status, "Ready for review")
		self.assertEqual(source.attached_to_doctype, "Journal Entry")
		self.assertEqual(source.attached_to_name, entry.name)
		self.assertEqual(entry.total_debit, 6000)
		self.assertEqual(entry.total_credit, 6000)
		clearing = sum(
			row.debit_in_account_currency - row.credit_in_account_currency
			for row in entry.accounts
			if row.account == self.settings.clearing_account
		)
		self.assertEqual(clearing, 0)

	def test_manual_submit_creates_native_payment_ledger_entries(self):
		from enk_norge.settlement import create_settlement

		first, second, credit = self.sales_and_credit()
		result = create_settlement(self.data(first, second, credit, self.source_file()))
		entry = frappe.get_doc("Journal Entry", result["name"])
		entry.submit()
		payment_entries = frappe.get_all(
			"Payment Ledger Entry",
			filters={"voucher_type": "Journal Entry", "voucher_no": entry.name, "delinked": 0},
			fields=["against_voucher_no"],
		)
		self.assertTrue({first.name, second.name, credit.name} <= {row.against_voucher_no for row in payment_entries})
		for invoice in (first, second, credit):
			invoice.reload()
			self.assertEqual(invoice.outstanding_amount, 0)

	def test_submit_validation_rejects_changed_file_content_or_stored_hash(self):
		from enk_norge.settlement import create_settlement, validate_settlement_entry

		first, second, credit = self.sales_and_credit()
		source = self.source_file()
		result = create_settlement(self.data(first, second, credit, source))
		entry = frappe.get_doc("Journal Entry", result["name"])
		with patch("frappe.core.doctype.file.file.File.get_content", return_value=b"endret oppgjorsfil"):
			with self.assertRaisesRegex(frappe.ValidationError, "endret"):
				validate_settlement_entry(entry)
		frappe.db.set_value("ENK Settlement", result["settlement"], "source_sha256", "0" * 64)
		with self.assertRaisesRegex(frappe.ValidationError, "endret"):
			validate_settlement_entry(entry)

	def test_retry_is_idempotent_and_changed_source_or_amount_is_rejected(self):
		from enk_norge.settlement import create_settlement

		first, second, credit = self.sales_and_credit()
		source = self.source_file()
		data = self.data(first, second, credit, source, external_settlement_id="PAY-RETRY")
		created = create_settlement(data)
		reused = create_settlement(data)
		self.assertEqual(created["name"], reused["name"])
		self.assertTrue(reused["reused"])
		changed = self.source_file("endret oppgjørsfil")
		with self.assertRaisesRegex(frappe.ValidationError, "andre opplysninger"):
			create_settlement(data | {"source_file": changed.name})
		with self.assertRaisesRegex(frappe.ValidationError, "andre opplysninger"):
			create_settlement(data | {"fee": "101", "net_amount": "1899"})

	def test_cross_company_invoice_is_rejected(self):
		from enk_norge.settlement import create_settlement
		from enk_norge.setup import create_company
		from enk_norge.tests.test_saft_integration import _mod11

		first, second, credit = self.sales_and_credit()
		other = create_company(
			dict(
				company_name="Annet oppgjørsforetak " + uuid4().hex[:8],
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
		with self.assertRaisesRegex(frappe.ValidationError, "samme foretak"):
			create_settlement(self.data(first, second, credit, self.source_file(), company=other))
