"""Rene tester for server-signerte utkast til hovedbokbilag."""

import json
import unittest
from types import SimpleNamespace

from enk_norge.posting_contract import PostingContractError, seal_draft, validate_contract

SECRET = "bare-testnøkkel"


class PostingContractTest(unittest.TestCase):
	def test_bank_reference_cannot_change(self):
		doc = self.journal_entry()
		doc.cheque_no = "BANK-1"
		seal_draft(doc, secret=SECRET)
		doc.cheque_no = "BANK-2"
		with self.assertRaises(PostingContractError):
			validate_contract(doc, secret=SECRET)

	def journal_entry(self, company="Fiktivt ENK"):
		return SimpleNamespace(
			doctype="Journal Entry",
			name="ACC-JV-0001",
			company=company,
			posting_date="2026-09-18",
			docstatus=0,
			voucher_type="Journal Entry",
			enk_vat_period="",
			enk_payment_key="owner-key",
			enk_payment_fingerprint="owner-fingerprint",
			user_remark="Kan endres uten å påvirke føringen",
			accounts=[
				SimpleNamespace(
					account="Bank - ENK",
					account_currency="NOK",
					credit=0,
					credit_in_account_currency=0,
					cost_center="Hoved - ENK",
					debit=100,
					debit_in_account_currency=100,
					exchange_rate=1,
					party_type="",
					party="",
					reference_type="",
					reference_name="",
					project="",
				),
				SimpleNamespace(
					account="Eierinnskudd - ENK",
					account_currency="NOK",
					credit=100,
					credit_in_account_currency=100,
					cost_center="Hoved - ENK",
					debit=0,
					debit_in_account_currency=0,
					exchange_rate=1,
					party_type="",
					party="",
					reference_type="",
					reference_name="",
					project="",
				),
			],
		)

	def payment_entry(self):
		return SimpleNamespace(
			doctype="Payment Entry",
			name="ACC-PAY-0001",
			company="Fiktivt ENK",
			posting_date="2026-09-18",
			docstatus=0,
			party_type="Customer",
			party="Kunde",
			payment_type="Receive",
			cost_center="Hoved - ENK",
			project="",
			enk_payment_key="payment-key",
			enk_payment_fingerprint="payment-fingerprint",
			paid_from="Kundefordringer - ENK",
			paid_to="Bank - ENK",
			paid_from_account_currency="NOK",
			paid_to_account_currency="NOK",
			paid_amount=100,
			received_amount=100,
			base_paid_amount=100,
			base_received_amount=100,
			source_exchange_rate=1,
			target_exchange_rate=1,
			reference_no="BANK-1",
			reference_date="2026-09-18",
			references=[
				SimpleNamespace(
					reference_doctype="Sales Invoice",
					reference_name="SINV-1",
					allocated_amount=100,
					exchange_rate=1,
				)
			],
			deductions=[SimpleNamespace(account="Gebyr - ENK", amount=5, cost_center="Hoved - ENK")],
			taxes=[],
		)

	def test_valid_signature_allows_metadata_change(self):
		doc = self.journal_entry()
		seal_draft(doc, secret=SECRET)
		doc.user_remark = "Beskrivelsen er korrigert"
		self.assertTrue(validate_contract(doc, secret=SECRET))

	def test_changed_amount_is_rejected(self):
		doc = self.payment_entry()
		seal_draft(doc, secret=SECRET)
		doc.deductions[0].amount = 6
		with self.assertRaisesRegex(PostingContractError, "finansielle innhold"):
			validate_contract(doc, secret=SECRET)

	def test_forged_contract_is_rejected(self):
		doc = self.journal_entry()
		seal_draft(doc, secret=SECRET)
		contract = json.loads(doc.enk_posting_contract)
		contract["payload"]["company"] = "Forfalsket ENK"
		doc.enk_posting_contract = json.dumps(contract)
		with self.assertRaisesRegex(PostingContractError, "signatur"):
			validate_contract(doc, secret=SECRET)

	def test_other_company_is_rejected(self):
		doc = self.journal_entry()
		seal_draft(doc, secret=SECRET)
		doc.company = "Annet ENK"
		with self.assertRaisesRegex(PostingContractError, "finansielle innhold"):
			validate_contract(doc, secret=SECRET)

	def test_journal_debit_credit_change_is_rejected(self):
		doc = self.journal_entry()
		seal_draft(doc, secret=SECRET)
		doc.accounts[0].debit = 101
		with self.assertRaisesRegex(PostingContractError, "finansielle innhold"):
			validate_contract(doc, secret=SECRET)

	def test_replayed_contract_cannot_be_used_for_another_document(self):
		source = self.journal_entry()
		seal_draft(source, secret=SECRET)
		clone = self.journal_entry()
		clone.name = "ACC-JV-0002"
		clone.enk_posting_contract = source.enk_posting_contract
		with self.assertRaisesRegex(PostingContractError, "finansielle innhold"):
			validate_contract(clone, secret=SECRET)

	def test_changed_payment_direction_is_rejected(self):
		doc = self.payment_entry()
		seal_draft(doc, secret=SECRET)
		doc.payment_type = "Pay"
		with self.assertRaisesRegex(PostingContractError, "finansielle innhold"):
			validate_contract(doc, secret=SECRET)

	def test_changed_vat_period_is_rejected(self):
		doc = self.journal_entry()
		seal_draft(doc, secret=SECRET)
		doc.enk_vat_period = "2026-10-31"
		with self.assertRaisesRegex(PostingContractError, "finansielle innhold"):
			validate_contract(doc, secret=SECRET)
